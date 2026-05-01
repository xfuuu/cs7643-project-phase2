#!/usr/bin/env python3
"""
Targeted Gemini test for the EXCEPTIONAL → DramaManager.accommodate
pipeline. The Layer-2 playthrough never destroys evidence, so the entire
EXCEPTIONAL branch in ``game.py`` (line ~218: tracker.remove_spans_for_steps,
drama.accommodate, classifier.update_plan, narrator.narrate) is otherwise
unverified against a real LLM.

What this runner does
---------------------
1. Boots ``game.py`` (cached ``world.json`` keeps boot cost at zero).
2. Confirms the start ``/hint`` matches the original plot's first step.
3. Sends a single destructive command against EV-01 (the silver flask,
   which has an active ``EV-01.exists`` span until step 2).
4. Calls ``/hint`` and asserts the next beat is **a title that does NOT
   appear in the original ``phase1/outputs/plot_plan.json``** — i.e.
   accommodation produced new content.
5. Verifies no ``[The line went dead]`` / ``[The narrator hesitates]``
   guard messages appeared, which would mean the EXCEPTIONAL path threw
   somewhere instead of running cleanly.

What "PASS" means
-----------------
A new ``/hint`` title proves end-to-end that:
  - the parser produced a destructive ``StateChange``,
  - ``CausalSpanTracker.check_violation`` flagged it,
  - ``classifier.classify`` returned ``ActionKind.EXCEPTIONAL``,
  - ``drama.accommodate`` ran and returned a fresh ``PlotPlan``,
  - ``classifier.update_plan`` swapped the live plan,
  - ``ActionClassifier.current_step`` now points to a brand-new beat.

If the LLM happens to interpret the command non-destructively, ``/hint``
will still match an original title and this script reports FAIL with the
cause clearly labeled — you can rerun with a different phrase.

Cost
----
Roughly 5–8 Gemini calls (parser intent + parser effects + parser
commonsense + drama_runtime_repair + narrator). Boot reuses world.json
so it costs nothing.

Usage
-----
    GEMINI_API_KEY=... python3 tests/run_exception.py
    python3 tests/run_exception.py --api-key <key>

Exit code
---------
    0 — accommodate produced a new beat (PASS)
    1 — anything else (FAIL)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _session import ERROR_LINE_RE, ROOT, GameSession  # noqa: E402

LOG = ROOT / "tests" / "exception_run.log"
PLOT_PATH = ROOT / "phase1" / "outputs" / "plot_plan.json"

DESTRUCTIVE_COMMAND = "smash the silver flask on the marble floor and shatter it"


def _load_original_titles() -> set[str]:
    raw = json.loads(PLOT_PATH.read_text(encoding="utf-8"))
    return {step["title"].strip() for step in raw["steps"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY", ""))
    ap.add_argument(
        "--command",
        default=DESTRUCTIVE_COMMAND,
        help=("destructive command to send (default: %(default)r). "
              "If the default phrasing isn't recognized as destructive by "
              "the parser LLM, try a more explicit alternative such as "
              "'destroy the silver flask completely'."),
    )
    args = ap.parse_args()
    if not args.api_key:
        sys.exit("Provide a Gemini API key via $GEMINI_API_KEY or --api-key")

    print(f"Loading original plot from {PLOT_PATH.relative_to(ROOT)}…")
    original_titles = _load_original_titles()
    print(f"  {len(original_titles)} original step titles loaded.\n")

    print("Booting game…")
    session = GameSession(args.api_key, log_path=LOG)
    try:
        boot_out = session.read_until_idle(idle_secs=4, total_timeout=180)
        if "Loading existing world map" not in boot_out:
            print("  WARNING: world.json missing; world is being built (extra LLM cost).")
        print("Booted.\n")

        # ── 1. baseline: starting hint matches the original plan ───────────
        h0 = session.hint()
        if h0 is None:
            print("FAIL: no /hint at game start.")
            sys.exit(1)
        starting_title = h0[0]
        print(f"Baseline /hint: {starting_title!r}")
        if starting_title not in original_titles:
            print("FAIL: starting /hint does not match the original plan; "
                  "an earlier accommodation may have already mutated state.")
            sys.exit(1)
        print("  ✓ baseline matches the original plan.\n")

        # ── 2. fire the destructive turn ──────────────────────────────────
        print(f"→ destructive turn: {args.command!r}")
        try:
            out = session.send(args.command)
        except (RuntimeError, TimeoutError) as exc:
            print(f"FAIL: subprocess error during destructive turn: {exc}")
            sys.exit(1)

        guard_lines = [l for l in out.splitlines() if ERROR_LINE_RE.search(l)]
        for line in guard_lines:
            print(f"  !! {line.strip()}")

        # ── 3. read the new hint and decide ───────────────────────────────
        h1 = session.hint()
        new_title = h1[0] if h1 else None
        new_location = h1[1] if h1 else None
        print(f"  /hint -> title={new_title!r} location={new_location!r}\n")

        if guard_lines:
            print("FAIL: one or more guard messages appeared during the "
                  "EXCEPTIONAL turn. The accommodate / narrate pipeline "
                  "raised an exception. Review the session log:")
            print(f"  {LOG.relative_to(ROOT)}")
            sys.exit(1)
        if new_title is None:
            print("FAIL: /hint did not return a parseable title after the "
                  "destructive turn.")
            sys.exit(1)
        if new_title in original_titles:
            print("FAIL: /hint title still matches the ORIGINAL plot.")
            print("  This usually means the parser LLM did not interpret the "
                  "command as a destructive StateChange (so no span "
                  "violation, no accommodate). Rerun with --command set to "
                  "a more explicit phrasing, e.g.:")
            print('    --command "destroy the silver flask completely"')
            sys.exit(1)

        # ── 4. PASS ──────────────────────────────────────────────────────
        print("=" * 72)
        print(f"PASS: post-accommodation /hint title {new_title!r}")
        print("      is NOT present in the original plot. This means:")
        print("        - parser produced a destructive StateChange;")
        print("        - CausalSpanTracker.check_violation flagged it;")
        print("        - classifier returned ActionKind.EXCEPTIONAL;")
        print("        - DramaManager.accommodate ran (no exception);")
        print("        - classifier.update_plan swapped to the new plan.")
        print(f"\nSession log: {LOG.relative_to(ROOT)}")
        sys.exit(0)
    finally:
        session.quit_and_wait()


if __name__ == "__main__":
    main()
