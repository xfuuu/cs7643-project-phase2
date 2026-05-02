#!/usr/bin/env python3
"""
Record presentation-ready artefacts for Phase II:

  --terminal-log   Everything printed here (stdout/stderr tee) — full CLI transcript.
  --llm-log        JSONL written by ``LoggedLLMBackend`` inside ``game.py``.
  --llm-log-full   Include complete ``prompt`` and ``response`` per row (not just snippets).

Modes
-----
  full       Steps 1–10 from the Layer-2 regression route (no mid-game save/load),
             then continues through plot steps 9–15 until ``game.py`` exits on the
             resolution beat. Writes ``/save`` checkpoints (cheap — no LLM) so you
             can resume.

  resume     Loads ``--checkpoint`` via ``/load`` then runs **only** the second-half
             script (``EXTRA_FULL_PLAN``). Use after a ``full`` run that saved a
             checkpoint, or any compatible ``savegame.json``.

  exception  Boots fresh, fires ONE destructive player command so the EXCEPTIONAL →
             ``drama.accommodate`` pipeline runs (same acceptance criteria as
             ``tests/run_exception.py``).

Important
---------
World topology requires **Study → Library → Drawing Room**. Older scripts used
``go drawing room`` from the Study (invalid exit); that leaves the plot stuck on
*"The Household Gathers"* while narration still advances — ``/hint`` then lies.

Usage (example):
    mkdir -p presentation/logs
    export GEMINI_API_KEY=...
    python3 -u tests/run_presentation_record.py --mode full \\
        --terminal-log presentation/logs/normal_terminal.log \\
        --llm-log presentation/logs/normal_llm.jsonl \\
        --llm-log-full \\
        --checkpoint presentation/logs/presentation_checkpoint.json

    # Continue LLM JSONL into part 2 (same file appends):
    python3 -u tests/run_presentation_record.py --mode resume \\
        --checkpoint presentation/logs/presentation_checkpoint.json \\
        --terminal-log presentation/logs/normal_terminal_part2.log \\
        --llm-log presentation/logs/normal_llm.jsonl \\
        --llm-log-full

    python3 -u tests/run_presentation_record.py --mode exception \\
        --terminal-log presentation/logs/exception_terminal.log \\
        --llm-log presentation/logs/exception_llm.jsonl \\
        --llm-log-full \\
        --destructive-command "destroy the silver flask completely"

Tip: Long Gemini outages → ``export PHASE2_SESSION_TIMEOUT=300`` before running.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _session import ERROR_LINE_RE, HINT_RE, ROOT, GameSession  # noqa: E402
from run_layer2 import Check, PLAN as LAYER2_PLAN  # noqa: E402

PLOT_PATH = ROOT / "phase1" / "outputs" / "plot_plan.json"

SESSION_FULL = ROOT / "tests" / "presentation_full_session.log"
SESSION_EXCEPTION = ROOT / "tests" / "presentation_exception_session.log"

SESSION_RESUME = ROOT / "tests" / "presentation_resume_session.log"


# Continuation after Layer-2 step [10]: player is in Julian's Bedroom;
# next beat is step 9 title **The Bloodless Wound** (Study). Commands align
# with ``phase1/outputs/plot_plan.json`` steps 9–15; step 16 resolution is
# handled inside ``game._check_game_over`` (process exits — no trailing /hint).

EXTRA_FULL_PLAN: list[Check] = [
    Check(
        "[FULL 11] Step 9 — reach Study & analyse bloodless wound (EV-08 + EV-01)",
        [
            "go guest wing",
            "go main corridor",
            "go main entrance hall",
            "go drawing room",
            "go library",
            "go study",
            "examine EV-08",
            "examine EV-01",
        ],
        expected_title="The Doctor's Deception",
        critical=False,
    ),
    Check(
        "[FULL 12] Step 10 — Guest Wing / Dr Vance interference",
        [
            "go library",
            "go drawing room",
            "go main entrance hall",
            "go main corridor",
            "go guest wing",
            "interview Dr Percival Vance about the paper hidden in his medical bag",
        ],
        expected_title="The Loyal Wife",
        critical=False,
    ),
    Check(
        "[FULL 13] Step 11 — Drawing Room / Eleanor interview",
        [
            "go main corridor",
            "go main entrance hall",
            "go drawing room",
            "interview Eleanor Vance about her movements during the masquerade",
        ],
        expected_title="The Gardener's Secret",
        critical=False,
    ),
    Check(
        "[FULL 14] Step 12 — Conservatory / monkshood glove (EV-03)",
        [
            "go conservatory",
            "examine EV-03",
        ],
        expected_title="The Beaded Handbag",
        critical=False,
    ),
    Check(
        "[FULL 15] Step 13 — Main Entrance Hall / handbag petal (EV-07)",
        [
            "go drawing room",
            "go main entrance hall",
            "examine EV-07",
        ],
        expected_title="The Midnight Reckoning",
        critical=False,
    ),
    Check(
        "[FULL 16] Step 14 — Library / midnight reckoning (touch chain evidence)",
        [
            "go drawing room",
            "go library",
            "examine EV-04",
        ],
        expected_title="The Final Mask Removed",
        critical=False,
    ),
    Check(
        "[FULL 17] Step 15 — Study / confrontation (examine EV-01 advances beat; game exits on resolution)",
        [
            "go study",
            "examine EV-01",
        ],
        expected_title=None,
        critical=False,
    ),
]


def _tee_stdio(log_fp) -> tuple[object, object]:
    """Return replaced stdout/stderr that also write to ``log_fp``."""
    orig_out = sys.stdout
    orig_err = sys.stderr

    class Tee:
        def write(self, data: str) -> None:
            orig_out.write(data)
            log_fp.write(data)
            log_fp.flush()

        def flush(self) -> None:
            orig_out.flush()
            log_fp.flush()

    class TeeErr(Tee):
        def write(self, data: str) -> None:
            orig_err.write(data)
            log_fp.write(data)
            log_fp.flush()

        def flush(self) -> None:
            orig_err.flush()
            log_fp.flush()

    return Tee(), TeeErr()


def _game_args(
    llm_log: Path,
    llm_full: bool,
    save_file: Path | None = None,
) -> list[str]:
    args = ["--llm-log", str(llm_log.resolve())]
    if llm_full:
        args.append("--llm-log-full")
    if save_file is not None:
        args.extend(["--save-file", str(save_file.resolve())])
    return args


def _emit_child_stdout(chunk: str) -> None:
    """Echo subprocess output to our stdout so ``--terminal-log`` captures narration."""
    if chunk:
        sys.stdout.write(chunk)
        sys.stdout.flush()


def _hint_echo(session: GameSession) -> tuple[str, str] | None:
    raw = session.send("/hint")
    _emit_child_stdout(raw)
    m = HINT_RE.search(raw)
    return (m.group(1).strip(), m.group(2).strip()) if m else None


def _run_check_pres(
    session: GameSession,
    check: Check,
    *,
    warn_only: bool,
) -> tuple[bool, str | None, str]:
    notes: list[str] = []
    for cmd in check.commands:
        if session.proc.poll() is not None:
            notes.append(f"    > {cmd}")
            notes.append("      !! game process already exited")
            return True, None, "\n".join(notes)
        try:
            out = session.send(cmd)
        except (RuntimeError, TimeoutError) as e:
            notes.append(f"    > {cmd}")
            notes.append(f"      !! runner error: {e}")
            return False, None, "\n".join(notes)
        notes.append(f"    > {cmd}")
        _emit_child_stdout(out)
        for line in out.splitlines():
            if ERROR_LINE_RE.search(line):
                notes.append(f"      !! {line.strip()}")

    if session.proc.poll() is not None:
        notes.append("    /hint skipped — game exited after this segment (likely resolution)")
        return True, None, "\n".join(notes)

    h = _hint_echo(session)
    title = h[0] if h else None
    notes.append(f"    /hint -> {title!r}")

    if check.expected_title is None:
        return True, title, "\n".join(notes)

    ok = title == check.expected_title
    if not ok and warn_only:
        notes.append(
            f"    WARN expected /hint title {check.expected_title!r} "
            f"but got {title!r}"
        )
        return True, title, "\n".join(notes)
    return ok, title, "\n".join(notes)


def run_full(api_key: str, llm_log: Path, llm_full: bool, checkpoint: Path) -> int:
    """Layer-2 checks [1–10], checkpoint /save after block [10], then EXTRA_FULL_PLAN."""
    llm_log.parent.mkdir(parents=True, exist_ok=True)
    llm_log.write_text("", encoding="utf-8")

    checkpoint.parent.mkdir(parents=True, exist_ok=True)

    session: GameSession | None = None
    ok_any_fail = False

    print("Booting game (full presentation run)…")
    print(f"Checkpoint (--save-file): {checkpoint}\n")
    session = GameSession(
        api_key,
        log_path=SESSION_FULL,
        game_args=_game_args(llm_log, llm_full, checkpoint),
    )
    try:
        boot_out = session.read_until_idle(total_timeout=240)
        _emit_child_stdout(boot_out)
        if "Loading existing world map" in boot_out:
            print("  (world.json reused — no boot LLM cost)\n")
        elif "Building world map" in boot_out:
            print("  WARNING: building world — heavy LLM cost\n")

        segments = list(LAYER2_PLAN[:10]) + EXTRA_FULL_PLAN
        for i, seg in enumerate(segments):
            print(f"→ {seg.name}")
            ok, title, notes = _run_check_pres(session, seg, warn_only=True)
            print(notes)
            tag = "OK" if ok else "FAIL"
            print(f"    => {tag}\n")
            if session.proc.poll() is not None:
                ec = session.proc.poll()
                print(f"Game subprocess ended (exit code {ec}) — stopping.")
                break
            if seg.expected_title is not None and title != seg.expected_title:
                ok_any_fail = True

            if i == 9 and session.proc.poll() is None:
                print("→ checkpoint /save after Layer-2 segment [10]\n")
                _emit_child_stdout(session.send("/save"))

        if session.proc.poll() is None:
            print("→ final /save before recorder exits …\n")
            _emit_child_stdout(session.send("/save"))

        print("=" * 72)
        print(f"Full-run LLM JSONL: {llm_log.relative_to(ROOT)}")
        print(f"Raw game stdout:    {SESSION_FULL.relative_to(ROOT)}")
        print(f"Checkpoint JSON:    {checkpoint}")
        print(
            "\nResume second half only with:\n"
            "  python3 -u tests/run_presentation_record.py --mode resume \\\n"
            f"    --checkpoint {checkpoint} \\\n"
            "    --terminal-log presentation/logs/normal_terminal_part2.log \\\n"
            "    --llm-log presentation/logs/normal_llm_part2.jsonl --llm-log-full\n"
        )
        if ok_any_fail:
            print(
                "\nNote: one or more /hint titles drifted from expected "
                "(parser variance). Review terminal + JSONL — gameplay may "
                "still be fine."
            )
        return 0
    finally:
        if session is not None:
            session.quit_and_wait()


def run_resume(api_key: str, llm_log: Path, llm_full: bool, checkpoint: Path) -> int:
    """Load ``checkpoint`` via ``/load`` then append EXTRA_FULL_PLAN (second half only)."""
    session: GameSession | None = None
    ok_any_fail = False

    print(f"Booting game (resume from checkpoint)…")
    print(f"Checkpoint: {checkpoint}\n")
    session = GameSession(
        api_key,
        log_path=SESSION_RESUME,
        game_args=_game_args(llm_log, llm_full, checkpoint),
    )
    try:
        boot_out = session.read_until_idle(total_timeout=240)
        _emit_child_stdout(boot_out)
        print("\n→ /load …\n")
        _emit_child_stdout(session.send("/load"))

        for seg in EXTRA_FULL_PLAN:
            print(f"→ {seg.name}")
            ok, title, notes = _run_check_pres(session, seg, warn_only=True)
            print(notes)
            tag = "OK" if ok else "FAIL"
            print(f"    => {tag}\n")
            if session.proc.poll() is not None:
                ec = session.proc.poll()
                print(f"Game subprocess ended (exit code {ec}) — stopping.")
                break
            if seg.expected_title is not None and title != seg.expected_title:
                ok_any_fail = True

        if session.proc.poll() is None:
            print("→ final /save …\n")
            _emit_child_stdout(session.send("/save"))

        print("=" * 72)
        print(f"(resume) LLM JSONL (append mode): {llm_log}")
        print(f"(resume) Raw game stdout: {SESSION_RESUME.relative_to(ROOT)}")
        if ok_any_fail:
            print("\nNote: see WARN lines above — parser variance.")
        return 0
    finally:
        if session is not None:
            session.quit_and_wait()


def run_exception(
    api_key: str,
    llm_log: Path,
    llm_full: bool,
    destructive_command: str,
) -> int:
    llm_log.parent.mkdir(parents=True, exist_ok=True)
    llm_log.write_text("", encoding="utf-8")

    original_titles = {
        step["title"].strip()
        for step in json.loads(PLOT_PATH.read_text(encoding="utf-8"))["steps"]
    }

    print(f"Booting game (exception / accommodate demo)…")
    session = GameSession(
        api_key,
        log_path=SESSION_EXCEPTION,
        game_args=_game_args(llm_log, llm_full),
    )
    try:
        boot_out = session.read_until_idle(total_timeout=240)
        _emit_child_stdout(boot_out)
        if "Loading existing world map" not in boot_out:
            print("  WARNING: world.json missing — extra boot LLM cost.\n")

        h0 = _hint_echo(session)
        if not h0:
            print("FAIL: no baseline /hint")
            return 1
        print(f"Baseline /hint: {h0[0]!r}\n")

        print(f"→ destructive turn: {destructive_command!r}")
        try:
            out = session.send(destructive_command)
        except (RuntimeError, TimeoutError) as exc:
            print(f"FAIL: {exc}")
            return 1

        _emit_child_stdout(out)

        guards = [ln for ln in out.splitlines() if ERROR_LINE_RE.search(ln)]
        for g in guards:
            print(f"  !! {g.strip()}")

        h1 = _hint_echo(session)
        new_title = h1[0] if h1 else None

        if guards:
            print("FAIL: guard messages during EXCEPTIONAL turn.")
            return 1
        if new_title is None:
            print("FAIL: could not parse /hint after destructive turn.")
            return 1
        if new_title in original_titles:
            print(
                "FAIL: /hint still an ORIGINAL plot title — parser likely "
                "did not emit a destructive StateChange. Try a different "
                "--destructive-command."
            )
            return 1

        print("=" * 72)
        print(f"PASS — post-accommodation beat: {new_title!r}")
        print(f"LLM JSONL:         {llm_log.relative_to(ROOT)}")
        print(f"Raw game stdout:   {SESSION_EXCEPTION.relative_to(ROOT)}")
        return 0
    finally:
        session.quit_and_wait()


def main() -> None:
    default_ckpt = ROOT / "presentation" / "logs" / "presentation_checkpoint.json"

    ap = argparse.ArgumentParser(description="Presentation recorder for Phase II.")
    ap.add_argument("--mode", choices=("full", "exception", "resume"), required=True)
    ap.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY", ""))
    ap.add_argument(
        "--terminal-log",
        required=True,
        type=Path,
        help="Terminal transcript path (truncated when shell wrapper opens 'w').",
    )
    ap.add_argument(
        "--llm-log",
        required=True,
        type=Path,
        help="JSONL path for LLM calls; truncated at start of full/exception only "
        "(resume appends — LoggedLLMBackend opens append mode).",
    )
    ap.add_argument(
        "--llm-log-full",
        action="store_true",
        help="Pass --llm-log-full to game.py (full prompts/responses in JSONL).",
    )
    ap.add_argument(
        "--destructive-command",
        default="destroy the silver flask completely",
        help="exception mode only — player text that should destroy EV-01.",
    )
    ap.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help=f"Forwarded to game.py --save-file. full default: {default_ckpt}; "
        "resume requires this file to exist.",
    )
    args = ap.parse_args()

    if not args.api_key:
        sys.exit("Provide --api-key or set GEMINI_API_KEY.")

    args.llm_log.parent.mkdir(parents=True, exist_ok=True)

    if args.mode == "resume":
        ckpt = args.checkpoint if args.checkpoint is not None else default_ckpt
        if not ckpt.is_file():
            sys.exit(f"--mode resume requires an existing checkpoint file: {ckpt}")
    elif args.mode == "full":
        ckpt = args.checkpoint if args.checkpoint is not None else default_ckpt
        ckpt.parent.mkdir(parents=True, exist_ok=True)
        args.llm_log.write_text("", encoding="utf-8")
    else:
        ckpt = None
        args.llm_log.write_text("", encoding="utf-8")

    args.terminal_log.parent.mkdir(parents=True, exist_ok=True)
    rc = 1
    with args.terminal_log.open("w", encoding="utf-8") as tf:
        tout, terr = _tee_stdio(tf)
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = tout, terr
        try:
            print(f"Presentation recorder — mode={args.mode!r}")
            print(f"Terminal transcript: {args.terminal_log}")
            print(f"LLM JSONL:           {args.llm_log}")
            print(f"LLM full content:    {args.llm_log_full}\n")

            if args.mode == "full":
                rc = run_full(args.api_key, args.llm_log, args.llm_log_full, ckpt)
            elif args.mode == "resume":
                rc = run_resume(args.api_key, args.llm_log, args.llm_log_full, ckpt)
            else:
                rc = run_exception(
                    args.api_key,
                    args.llm_log,
                    args.llm_log_full,
                    args.destructive_command,
                )
        finally:
            sys.stdout, sys.stderr = old_out, old_err

    sys.exit(rc)


if __name__ == "__main__":
    main()
