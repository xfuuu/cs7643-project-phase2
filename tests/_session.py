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
TURN_TIMEOUT_SECS = 180
# Consider the game "done responding" once we see this much silence after
# at least one chunk of output.
IDLE_SECS = 3.0

HINT_RE = re.compile(r"\[Hint\] Next beat:\s*(.+?)\s+—\s+(.+)")
ERROR_LINE_RE = re.compile(r"\[The line went dead|\[The narrator hesitates")


class GameSession:
    def __init__(self, api_key: str, log_path: Path) -> None:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        self.proc = subprocess.Popen(
            [sys.executable, "-u", str(GAME), "--gemini-api-key", api_key],
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
        idle_secs: float = IDLE_SECS,
        total_timeout: float = TURN_TIMEOUT_SECS,
    ) -> str:
        start = time.time()
        last_recv = start
        chunks: list[str] = []
        while True:
            try:
                chunk = self._q.get(timeout=0.4)
                chunks.append(chunk)
                last_recv = time.time()
            except Empty:
                pass
            now = time.time()
            if chunks and now - last_recv >= idle_secs:
                break
            if now - start >= total_timeout:
                if not chunks:
                    raise TimeoutError(
                        f"no output from game in {total_timeout:.0f}s"
                    )
                break
            if self.proc.poll() is not None:
                while True:
                    try:
                        chunks.append(self._q.get_nowait())
                    except Empty:
                        break
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
