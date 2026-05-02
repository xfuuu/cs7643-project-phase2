"""
Shared subprocess driver for the Layer-2 / Exception runners.

Spawns ``game.py`` as a child, owns its stdin/stdout, and exposes a small
synchronous API: ``send(cmd) -> str``, ``hint() -> (title, location)?``,
``read_until_idle()``, ``quit_and_wait()``.

Uses byte-level ``os.read`` on the child stdout so the prompt ``> `` (which
has no trailing newline) doesn't get stuck in line-buffered limbo.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue

ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "game.py"
SAVE_FILE = ROOT / "savegame.json"

# Generous: a single LLM turn can take 30s+ if Gemini retries on 5xx/429.
TURN_TIMEOUT_SECS = float(os.environ.get("PHASE2_SESSION_TIMEOUT", "180"))
# Consider the game "done responding" once we see this much silence after
# at least one chunk of output.
IDLE_SECS = 3.0

HINT_RE = re.compile(r"\[Hint\] Next beat:\s*(.+?)\s+—\s+(.+)")
ERROR_LINE_RE = re.compile(r"\[The line went dead|\[The narrator hesitates")


class GameSession:
    def __init__(
        self,
        api_key: str,
        log_path: Path,
        game_args: list[str] | None = None,
    ) -> None:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        cmd = [sys.executable, "-u", str(GAME), "--gemini-api-key", api_key]
        if game_args:
            cmd.extend(game_args)
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
            bufsize=0,
            cwd=str(ROOT),
            env=env,
        )
        self._q: "Queue[str]" = Queue()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = log_path.open("w", encoding="utf-8")
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        fd = self.proc.stdout.fileno()
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            text = chunk.decode("utf-8", "replace")
            self._q.put(text)
            try:
                self._log.write(text)
                self._log.flush()
            except ValueError:
                pass  # log was closed during shutdown; harmless race

    def read_until_idle(
        self,
        idle_secs: float = IDLE_SECS,  # noqa: ARG002 — kept for API compat
        total_timeout: float = TURN_TIMEOUT_SECS,
    ) -> str:
        """Read until the game prints its input prompt ``"\\n> "`` (the
        unambiguous marker that ``input()`` is now blocked waiting for us),
        OR the child process exits, OR ``total_timeout`` elapses.

        Note: ``idle_secs`` is intentionally NOT used as a "command done"
        heuristic anymore. The original idle-based termination was racing
        against legitimate LLM behaviour:

        * Gemini's urlopen timeout is 30s per attempt.
        * Exponential backoff sleeps reach ~8s + jitter on the 3rd retry.

        Both can produce stretches of stdout silence longer than any
        reasonable "idle" threshold, and using one would cut a turn short
        before the EXCEPTIONAL pipeline (or any guard message) finishes
        emitting. The prompt marker is the only correct signal.
        """
        start = time.time()
        chunks: list[str] = []
        while True:
            try:
                chunk = self._q.get(timeout=0.4)
                chunks.append(chunk)
            except Empty:
                pass

            joined = "".join(chunks) if chunks else ""
            # Strongest signal: the game is now blocked on input().
            if joined.endswith("\n> "):
                return joined

            now = time.time()
            if now - start >= total_timeout:
                if not chunks:
                    raise TimeoutError(
                        f"no output from game in {total_timeout:.0f}s"
                    )
                return joined
            if self.proc.poll() is not None:
                while True:
                    try:
                        chunks.append(self._q.get_nowait())
                    except Empty:
                        break
                return "".join(chunks)

    def send(self, command: str) -> str:
        if self.proc.poll() is not None:
            raise RuntimeError("game process has exited unexpectedly")
        self.proc.stdin.write((command + "\n").encode("utf-8"))
        self.proc.stdin.flush()
        return self.read_until_idle()

    def hint(self) -> tuple[str, str] | None:
        text = self.send("/hint")
        m = HINT_RE.search(text)
        return (m.group(1).strip(), m.group(2).strip()) if m else None

    def quit_and_wait(self, timeout: float = 10.0) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write(b"/quit\n")
                self.proc.stdin.flush()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self._reader.join(timeout=2)
        try:
            self._log.close()
        except Exception:
            pass
