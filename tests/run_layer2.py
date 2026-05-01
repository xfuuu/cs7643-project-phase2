#!/usr/bin/env python3
"""
Layer-2 end-to-end playthrough against the real Gemini API.

Drives ``game.py`` through a fixed sequence of commands, captures the output
between prompts, and asserts the four fixes' expected signals. This is meant
to replace the interactive Layer-2 playthrough so you don't have to babysit
the terminal.

Usage:
    GEMINI_API_KEY=... python3 tests/run_layer2.py
    python3 tests/run_layer2.py --api-key <key>

Exit code:
    0  – every CRITICAL check passed
    1  – at least one CRITICAL check failed
         (non-critical failures are reported but do not affect exit code)

Side effects:
    Writes verbose session logs to:
      tests/layer2_run.log         (the long playthrough)
      tests/layer2_run_session2.log (the post-/load session for step 11)
    Writes savegame.json (overwrites any previous one).

Critical checks (track the four fixes patched in commit ff7d4db):
    [1]  discovery shortcut + room check  (Bug 4)
    [9]  presence-only auto-advance        (Bug 2 / step 7 alibi_check)
    [11] /load tracker rebuild             (Bug 3)
    The renumbering fix (Bug 1) is exercised implicitly: any /load round-trip
    with an accommodated plan would surface the renumber breakage as a
    /hint mismatch, but the offline tests/test_regressions.py is the
    cheap canonical assertion.

Cost note:
    The world map is reused from world.json (no boot LLM). Each non-/hint
    command typically costs 2–3 LLM calls (parser intent + parser effects +
    optional commonsense + narrator). /hint is free. Expect ~40 LLM calls
    end-to-end if every step succeeds first try.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _session import ERROR_LINE_RE, ROOT, SAVE_FILE, GameSession  # noqa: E402

LOG1 = ROOT / "tests" / "layer2_run.log"
LOG2 = ROOT / "tests" / "layer2_run_session2.log"


# ── plan ──────────────────────────────────────────────────────────────────────

@dataclass
class Check:
    name: str
    commands: list[str]
    expected_title: str | None = None
    critical: bool = False


PLAN: list[Check] = [
    Check(
        "[1]  examine the desk → /hint = 'A Room Disturbed'",
        ["examine the desk"],
        expected_title="A Room Disturbed",
        critical=True,  # Bug 4 — discovery shortcut + room check
    ),
    Check(
        "[2]  examine the flask → /hint = 'The Household Gathers'",
        ["examine the flask"],
        expected_title="The Household Gathers",
    ),
    Check(
        "[3]  go drawing room → /hint stays 'The Household Gathers'",
        ["go drawing room"],
        expected_title="The Household Gathers",
    ),
    Check(
        "[4]  ask Eleanor about her husband → /hint = 'The Silent Library'",
        ["ask Eleanor about her husband"],
        expected_title="The Silent Library",
    ),
    Check(
        "[5]  go library → /hint stays 'The Silent Library' (NO auto-advance — EV-06 still required)",
        ["go library"],
        expected_title="The Silent Library",
    ),
    Check(
        "[6]  examine the book → /hint = 'The Weapon in the Ashes'",
        ["examine the book"],
        expected_title="The Weapon in the Ashes",
    ),
    Check(
        "[7]  go study + examine the hearth → /hint = \"The Heir's Panic\"",
        ["go study", "examine the hearth"],
        expected_title="The Heir's Panic",
    ),
    Check(
        "[8]  multi-hop + ask Julian → /hint = 'The Muddy Terrace'",
        ["go library", "go drawing room", "go ballroom",
         "ask Julian about the green ribbon"],
        expected_title="The Muddy Terrace",
    ),
    # *** the single most important assertion ***
    Check(
        "[9]  go terrace → AUTO-ADVANCE → /hint = 'The Motive of Debt'",
        ["go terrace"],
        expected_title="The Motive of Debt",
        critical=True,  # Bug 2 — presence-only alibi_check auto-advance
    ),
    Check(
        "[10] traverse to Julian's Bedroom + examine the drawer → /hint = 'The Bloodless Wound'",
        ["go ballroom", "go drawing room", "go main entrance hall",
         "go main corridor", "go guest wing", "go julian's bedroom",
         "examine the drawer"],
        expected_title="The Bloodless Wound",
    ),
]


# ── runner ────────────────────────────────────────────────────────────────────

def _run_check(session: GameSession, check: Check) -> tuple[bool, str | None, str]:
    """Execute one Check; return (passed, post-title, notes-block)."""
    notes: list[str] = []
    for cmd in check.commands:
        try:
            out = session.send(cmd)
        except (RuntimeError, TimeoutError) as e:
            notes.append(f"    > {cmd}")
            notes.append(f"      !! runner error: {e}")
            return False, None, "\n".join(notes)
        notes.append(f"    > {cmd}")
        for line in out.splitlines():
            if ERROR_LINE_RE.search(line):
                notes.append(f"      !! {line.strip()}")

    h = session.hint()
    title = h[0] if h else None
    notes.append(f"    /hint -> {title!r}")

    if check.expected_title is None:
        return True, title, "\n".join(notes)
    return (title == check.expected_title), title, "\n".join(notes)


def _save_load_round_trip(api_key: str, expected_title: str) -> tuple[bool, str]:
    """Boot a fresh game.py, /load, /hint, and assert the title matches."""
    if not SAVE_FILE.exists():
        return False, "    !! savegame.json was not created — skipping"
    session2 = GameSession(api_key, log_path=LOG2)
    notes: list[str] = []
    try:
        boot_out = session2.read_until_idle(idle_secs=4, total_timeout=180)
        if "Building world map" in boot_out:
            notes.append("    !! world.json missing on relaunch — boot called LLM")
        notes.append("    > /load")
        out = session2.send("/load")
        for line in out.splitlines()[-3:]:
            if line.strip():
                notes.append(f"      {line.strip()}")
        h = session2.hint()
        title = h[0] if h else None
        notes.append(f"    /hint -> {title!r}")
        passed = (title == expected_title)
        if not passed:
            notes.append(f"    !! expected /hint title {expected_title!r}")
        return passed, "\n".join(notes)
    except (RuntimeError, TimeoutError) as e:
        notes.append(f"    !! runner error: {e}")
        return False, "\n".join(notes)
    finally:
        session2.quit_and_wait()


def main() -> None:
    ap = argparse.ArgumentParser(description="Layer-2 end-to-end playthrough.")
    ap.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY", ""))
    args = ap.parse_args()
    if not args.api_key:
        sys.exit("Provide a Gemini API key via $GEMINI_API_KEY or --api-key")

    # Fresh save state for this run.
    if SAVE_FILE.exists():
        SAVE_FILE.unlink()

    print("Booting game…")
    session = GameSession(args.api_key, log_path=LOG1)
    results: list[tuple[str, bool, bool]] = []  # (name, passed, critical)
    last_title: str | None = None
    try:
        boot_out = session.read_until_idle(idle_secs=4, total_timeout=180)
        if "Loading existing world map" in boot_out:
            print("  (world.json reused — no LLM cost on boot)")
        elif "Building world map" in boot_out:
            print("  WARNING: world.json missing; boot is calling the LLM "
                  "(this can be ~30+ calls)")
        print("Booted.\n")

        for check in PLAN:
            print(f"→ {check.name}")
            ok, title, notes = _run_check(session, check)
            tag = "PASS" if ok else "FAIL"
            if check.critical and not ok:
                tag += " (CRITICAL)"
            print(notes)
            print(f"    => {tag}\n")
            results.append((check.name, ok, check.critical))
            last_title = title

        if last_title is not None:
            print("→ /save (preparing for [11])")
            try:
                session.send("/save")
                print("    > /save")
                print(f"    => PASS (savegame.json {'present' if SAVE_FILE.exists() else 'MISSING'})\n")
            except Exception as e:
                print(f"    !! /save failed: {e}\n")
    finally:
        session.quit_and_wait()

    # Step 11: relaunch + /load + /hint round-trip.
    if last_title is not None:
        print("→ [11] /save → quit → relaunch → /load → /hint should match")
        ok, notes = _save_load_round_trip(args.api_key, last_title)
        print(notes)
        tag = "PASS" if ok else "FAIL (CRITICAL)"
        print(f"    => {tag}\n")
        results.append(("[11] /save + relaunch + /load round-trip", ok, True))

    # ── summary ───────────────────────────────────────────────────────────
    print("=" * 72)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"Total: {passed}/{len(results)} PASSED")
    failed_critical = [n for n, ok, c in results if (not ok and c)]
    failed_noncrit = [n for n, ok, c in results if (not ok and not c)]
    if failed_critical:
        print("\nCRITICAL FAILURES (these mean the recent fixes are NOT working):")
        for n in failed_critical:
            print(f"  - {n}")
    if failed_noncrit:
        print("\nNON-CRITICAL FAILURES (often LLM phrasing variance — review the log):")
        for n in failed_noncrit:
            print(f"  - {n}")
    if not failed_critical and not failed_noncrit:
        print("\nAll checks passed.")
    print(f"\nSession log:    {LOG1.relative_to(ROOT)}")
    if LOG2.exists():
        print(f"Save/load log:  {LOG2.relative_to(ROOT)}")
    sys.exit(0 if not failed_critical else 1)


if __name__ == "__main__":
    main()
