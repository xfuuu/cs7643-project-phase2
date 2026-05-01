"""
Regression tests for bugs found in static review and patched together.

Core fixes (commit ff7d4db):

1. ``DramaManager._renumber`` used to clobber step_ids after accommodation,
   silently invalidating ``ActionClassifier._completed`` and the
   ``CausalSpanTracker.until_step_id`` references.
2. ``game._check_constituent_on_enter`` previously only advanced ``discovery``
   beats on entry, so location-only beats like Step 7 (alibi_check at The
   Terrace) had no in-game trigger and the plot would stall.
3. ``/load`` rebuilt the ``CausalSpanTracker`` from the ORIGINAL
   ``plot_plan``, which is wrong if the saved game already underwent
   accommodation.
4. The ``discovery`` shortcut in ``ActionClassifier._is_constituent`` did not
   verify the player was actually in the step's room — any "examine" anywhere
   would fire it.

End-of-game and emergency-path coverage (added later):

5. ``_check_game_over`` must call ``sys.exit(0)`` when the next step is
   ``kind="resolution"`` or when no remaining steps exist. Neither path was
   ever exercised against a real LLM, so an offline assertion is the
   cheapest safety net.
6. ``DramaManager.accommodate`` must dispatch to the deterministic
   ``_emergency_resolution`` path (no LLM call) once depth reaches
   ``MAX_DEPTH``. New climax steps must keep ids strictly above the
   completed-step max so they cannot collide with classifier bookkeeping.

All tests are fully offline (mock LLMs only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_interface import LLMBackend, LLMResponse
from models import CaseBible, Character, EvidenceItem, FactTriple, PlotPlan, PlotStep, TimelineEvent

from action_classifier import ActionClassifier
from causal_spans import CausalSpanTracker
from drama_manager import DramaManager
from models_phase2 import (
    ActionIntent,
    ActionKind,
    Room,
    StateChange,
    WorldMap,
)
from world_state import WorldStateManager


# ── fixtures ──────────────────────────────────────────────────────────────────

class _StubLLM(LLMBackend):
    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        steps = [
            {
                "step_id": 99,  # accommodation must overwrite this with max+1
                "phase": "investigation",
                "kind": "analysis",
                "title": "A New Angle",
                "summary": "Arthur finds another way to implicate Eleanor.",
                "location": "The Library",
                "participants": ["Arthur Penhaligon", "Eleanor Vance"],
                "evidence_ids": ["EV-GLOVE"],
                "reveals": ["Eleanor remains the prime suspect."],
                "timeline_ref": None,
            }
        ]
        return LLMResponse(text=json.dumps(steps))


def _case_bible() -> CaseBible:
    culprit = Character(
        name="Eleanor Vance", role="culprit", description="Botanist.",
        relationship_to_victim="Associate", means="Poison",
        motive="Protect husband", opportunity="Slipped away", alibi="Powder room",
    )
    victim = Character(
        name="Sir Alistair", role="victim", description="Industrialist.",
        relationship_to_victim="Self",
        means="N/A", motive="N/A", opportunity="N/A", alibi="N/A",
    )
    poison = EvidenceItem(
        evidence_id="EV-POISON", name="Poison Bottle", description="Aconitine.",
        location_found="Conservatory", implicated_person="Eleanor Vance",
        reliability=1.0,
    )
    glove = EvidenceItem(
        evidence_id="EV-GLOVE", name="Stained Glove", description="Plant residue.",
        location_found="Conservatory Bin", implicated_person="Eleanor Vance",
        reliability=0.9,
    )
    timeline = TimelineEvent(
        event_id="T01", time_marker="21:45",
        summary="Eleanor retrieves the poison.",
        participants=["Eleanor Vance"], location="Conservatory", public=False,
    )
    return CaseBible(
        setting="Manor", investigator="Arthur Penhaligon",
        victim=victim, culprit=culprit, suspects=[culprit],
        motive="Protect husband", method="Poisoned brandy",
        true_timeline=[timeline],
        evidence_items=[poison, glove], red_herrings=[],
        culprit_evidence_chain=["EV-POISON", "EV-GLOVE"],
    )


def _plot_plan() -> PlotPlan:
    """Five steps: discovery, EV-POISON search, alibi_check (presence-only),
    EV-GLOVE analysis, resolution."""
    return PlotPlan(
        investigator="Arthur Penhaligon",
        steps=[
            PlotStep(
                step_id=1, phase="Discovery", kind="discovery",
                title="Body Found", summary="Arthur finds the body.",
                location="The Study", participants=["Arthur Penhaligon"],
                evidence_ids=[], reveals=["Victim is dead."], timeline_ref=None,
            ),
            PlotStep(
                step_id=2, phase="Sweep", kind="search",
                title="Find the Poison", summary="Arthur finds the poison.",
                location="Conservatory", participants=["Arthur Penhaligon"],
                evidence_ids=["EV-POISON"], reveals=["Poison found."], timeline_ref=None,
            ),
            PlotStep(
                step_id=3, phase="Verify", kind="alibi_check",
                title="The Muddy Terrace",
                summary="No footprints in the mud — Julian's alibi fails.",
                location="The Terrace",
                participants=["Arthur Penhaligon"],
                evidence_ids=[],
                reveals=["Julian's alibi is impossible."], timeline_ref=None,
            ),
            PlotStep(
                step_id=4, phase="Investigation", kind="analysis",
                title="Trace the Glove", summary="Arthur links glove to Eleanor.",
                location="Conservatory",
                participants=["Arthur Penhaligon", "Eleanor Vance"],
                evidence_ids=["EV-GLOVE"], reveals=["Glove is Eleanor's."],
                timeline_ref=None,
            ),
            PlotStep(
                step_id=5, phase="Climax", kind="resolution",
                title="Resolution", summary="Eleanor confesses.",
                location="Drawing Room",
                participants=["Arthur Penhaligon", "Eleanor Vance"],
                evidence_ids=[], reveals=["Case closed."], timeline_ref=None,
            ),
        ],
    )


def _fact_triples() -> list[FactTriple]:
    return [
        FactTriple(subject="EV-POISON", relation="found_at", object="Conservatory",
                   time=None, source="evidence"),
        FactTriple(subject="EV-GLOVE", relation="found_at", object="Conservatory Bin",
                   time=None, source="evidence"),
    ]


def _world_map() -> WorldMap:
    return WorldMap(rooms={
        "The Study": Room(
            name="The Study", description="A book-lined study.",
            adjacent_rooms=["The Library", "The Terrace"],
            npc_names=[], evidence_ids=[], item_names=[],
        ),
        "The Library": Room(
            name="The Library", description="A quiet library.",
            adjacent_rooms=["The Study"],
            npc_names=[], evidence_ids=[], item_names=[],
        ),
        "The Terrace": Room(
            name="The Terrace", description="A muddy terrace.",
            adjacent_rooms=["The Study"],
            npc_names=[], evidence_ids=[], item_names=[],
        ),
        "Conservatory": Room(
            name="Conservatory", description="Glass and ferns.",
            adjacent_rooms=["The Study"],
            npc_names=[], evidence_ids=["EV-POISON", "EV-GLOVE"], item_names=[],
        ),
        "Drawing Room": Room(
            name="Drawing Room", description="A formal drawing room.",
            adjacent_rooms=["The Study"],
            npc_names=[], evidence_ids=[], item_names=[],
        ),
    })


# ── tests ─────────────────────────────────────────────────────────────────────

def test_step_ids_remain_stable_after_accommodation() -> None:
    """Bug 1: ``_renumber`` used to reset step_ids 1..N after accommodation,
    which silently corrupted ActionClassifier._completed bookkeeping. After
    the fix, surviving steps must keep their original ids and new steps must
    be assigned ids strictly greater than max(remaining)."""
    cb = _case_bible()
    plan = _plot_plan()
    tracker = CausalSpanTracker(_fact_triples(), plan)
    classifier = ActionClassifier(tracker, plan)

    # Player completes step 1 normally.
    classifier.advance_step()
    assert [s.step_id for s in classifier.completed_steps] == [1]

    destroy_poison = StateChange(
        entity="EV-POISON", attribute="exists", old_value=True, new_value=False,
    )
    violations = tracker.check_violation([destroy_poison])
    assert violations, "destroying EV-POISON should violate a span"

    drama = DramaManager(case_bible=cb, llm=_StubLLM())
    new_plan = drama.accommodate(
        violated_spans=violations,
        current_plan=PlotPlan(
            investigator=plan.investigator,
            steps=classifier.completed_steps + classifier.remaining_steps,
        ),
        completed_steps=classifier.completed_steps,
    )

    surviving = [s.step_id for s in new_plan.steps]
    # Step 1 (completed) must keep id 1.
    assert 1 in surviving, "completed step must keep its original id"
    # Steps 3, 4, 5 didn't reference EV-POISON — they must keep their ids.
    assert 3 in surviving
    assert 4 in surviving
    assert 5 in surviving
    # Step 2 referenced EV-POISON — it must be gone.
    assert 2 not in surviving
    # The new step must have an id strictly greater than every original id
    # so it can't collide with completed-step bookkeeping.
    original_ids = {1, 2, 3, 4, 5}
    new_ids = [sid for sid in surviving if sid not in original_ids]
    assert new_ids, "drama should have inserted at least one new step"
    assert min(new_ids) > 5, (
        f"new step ids should sit above max original id; got new_ids={new_ids}"
    )

    # Now verify update_plan keeps completed-step bookkeeping intact.
    classifier.update_plan(new_plan)
    assert [s.step_id for s in classifier.completed_steps] == [1], (
        "completed list must not be re-keyed by update_plan"
    )
    # The new current step must not be the already-completed step 1.
    assert classifier.current_step is not None
    assert classifier.current_step.step_id != 1


def test_presence_only_beat_advances_on_room_entry() -> None:
    """Bug 2: location-only beats (alibi_check at The Terrace, no evidence,
    only the investigator) had no trigger. After the fix, walking into the
    room should advance the beat."""
    from game import _check_constituent_on_enter

    plan = _plot_plan()
    tracker = CausalSpanTracker(_fact_triples(), plan)
    classifier = ActionClassifier(tracker, plan)
    world_state = WorldStateManager(_world_map(), starting_room="The Study")

    # Burn through steps 1 and 2 to reach step 3 (the alibi_check).
    classifier.advance_step()  # step 1
    classifier.advance_step()  # step 2
    assert classifier.current_step is not None
    assert classifier.current_step.step_id == 3
    assert classifier.current_step.location == "The Terrace"

    drama = DramaManager(case_bible=_case_bible(), llm=_StubLLM())

    class _NopNarrator:
        def narrate_system(self, msg: str) -> str:
            return msg

    # Player walks Study -> Terrace.
    assert world_state.move_player("The Terrace")
    _check_constituent_on_enter(classifier, world_state, _NopNarrator(), drama)

    # The alibi_check should have advanced.
    assert classifier.current_step is not None, (
        "step 3 should have advanced; some step should still remain"
    )
    assert classifier.current_step.step_id == 4, (
        f"expected to advance past alibi_check to step 4; "
        f"current is {classifier.current_step.step_id}"
    )


def test_load_rebuilds_tracker_from_saved_plan() -> None:
    """Bug 3: a saved game whose plan has been mutated by accommodation must
    rebuild its tracker against the SAVED plan. Otherwise spans for new
    inserted steps are missing and spans for removed steps linger."""
    cb = _case_bible()
    original = _plot_plan()
    fact_triples = _fact_triples()

    # Simulate a session that accommodated and then was saved.
    tracker = CausalSpanTracker(fact_triples, original)
    classifier = ActionClassifier(tracker, original)
    classifier.advance_step()  # complete step 1

    violations = tracker.check_violation([
        StateChange(entity="EV-POISON", attribute="exists",
                    old_value=True, new_value=False)
    ])
    drama = DramaManager(case_bible=cb, llm=_StubLLM())
    new_plan = drama.accommodate(
        violated_spans=violations,
        current_plan=PlotPlan(
            investigator=original.investigator,
            steps=classifier.completed_steps + classifier.remaining_steps,
        ),
        completed_steps=classifier.completed_steps,
    )
    classifier.update_plan(new_plan)

    saved_completed = list(classifier.completed_steps)
    saved_remaining = list(classifier.remaining_steps)

    # Now simulate /load using the FIXED logic: rebuild from saved plan,
    # then replay completed advance_step calls.
    saved_plan = PlotPlan(
        investigator=original.investigator,
        steps=saved_completed + saved_remaining,
    )
    rebuilt_tracker = CausalSpanTracker(fact_triples, saved_plan)
    rebuilt = ActionClassifier(rebuilt_tracker, saved_plan)
    for _ in saved_completed:
        rebuilt.advance_step()

    # The rebuilt tracker must NOT have any spans referencing step ids that
    # were removed by accommodation (bug: the original-plan tracker would
    # still hold an EV-POISON span tied to the now-deleted step 2).
    live_step_ids = {s.step_id for s in saved_plan.steps}
    for span in rebuilt_tracker.active_spans:
        assert span.until_step_id in live_step_ids or span.until_step_id is None, (
            f"span {span.span_id} -> until_step_id={span.until_step_id} "
            f"is not present in the saved plan's step ids {live_step_ids}"
        )

    # The rebuilt classifier's remaining list must match the saved one.
    assert [s.step_id for s in rebuilt.remaining_steps] == \
           [s.step_id for s in saved_remaining]


def test_discovery_shortcut_requires_correct_room() -> None:
    """Bug 4: discovery beats used to fire on any "examine" verb regardless
    of the player's location. Now the player must be in the step's room."""
    plan = _plot_plan()  # step 1 is a discovery in The Study
    tracker = CausalSpanTracker(_fact_triples(), plan)
    classifier = ActionClassifier(tracker, plan)
    world_state = WorldStateManager(_world_map(), starting_room="The Library")

    intent = ActionIntent(
        raw_text="examine bookshelf",
        verb="examine",
        object_="bookshelf",
        target_location=None,
        confidence=0.9,
        predicted_effects=[],
    )

    # In The Library — wrong room for the Study discovery — must NOT fire.
    classification = classifier.classify(intent, world_state)
    assert classification.kind != ActionKind.CONSTITUENT, (
        f"discovery shortcut should not fire from a wrong room; "
        f"got {classification.kind}"
    )

    # Move to The Study via The Study's adjacency. The Library connects to
    # The Study, so a one-hop move is enough.
    assert world_state.move_player("The Study")
    classification = classifier.classify(intent, world_state)
    assert classification.kind == ActionKind.CONSTITUENT
    assert classification.triggered_step_id == 1


# ── end-of-game + emergency-path tests (P1-B + P2-D) ──────────────────────────


def test_check_game_over_exits_on_resolution_kind() -> None:
    """When the next step is ``kind='resolution'``, ``_check_game_over``
    advances past it and calls ``sys.exit(0)``. This path is never reached
    in the Layer-2 playthrough, so an offline assertion is the safety net."""
    from game import _check_game_over

    plan = _plot_plan()  # step 5 is the resolution
    tracker = CausalSpanTracker(_fact_triples(), plan)
    classifier = ActionClassifier(tracker, plan)
    # Burn through steps 1–4 so the resolution is up next.
    for _ in range(4):
        classifier.advance_step()
    assert classifier.current_step is not None
    assert classifier.current_step.kind == "resolution"

    class _NopNarrator:
        def narrate_system(self, msg: str) -> str:
            return msg

    try:
        _check_game_over(classifier, _NopNarrator())
    except SystemExit as exc:
        assert exc.code == 0, f"expected exit code 0, got {exc.code}"
    else:
        raise AssertionError("expected _check_game_over to call sys.exit(0)")


def test_check_game_over_exits_on_empty_remaining() -> None:
    """When ``remaining_steps`` is empty, ``_check_game_over`` calls
    ``sys.exit(0)``. The other terminal path."""
    from game import _check_game_over

    plan = _plot_plan()
    tracker = CausalSpanTracker(_fact_triples(), plan)
    classifier = ActionClassifier(tracker, plan)
    for _ in range(len(plan.steps)):
        classifier.advance_step()
    assert classifier.remaining_steps == []

    class _NopNarrator:
        def narrate_system(self, msg: str) -> str:
            return msg

    try:
        _check_game_over(classifier, _NopNarrator())
    except SystemExit as exc:
        assert exc.code == 0, f"expected exit code 0, got {exc.code}"
    else:
        raise AssertionError("expected _check_game_over to call sys.exit(0)")


def test_emergency_resolution_at_max_depth() -> None:
    """Once ``DramaManager._depth >= MAX_DEPTH``, ``accommodate`` must use
    the deterministic ``_emergency_resolution`` path: NO LLM calls, and the
    new plan must terminate with ``confrontation`` then ``resolution`` steps
    whose ids are strictly above the completed-step max."""

    class _RecordingLLM(LLMBackend):
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, prompt: str, **kwargs) -> LLMResponse:
            self.calls += 1
            return LLMResponse(text="[]")

    cb = _case_bible()
    plan = _plot_plan()
    tracker = CausalSpanTracker(_fact_triples(), plan)
    classifier = ActionClassifier(tracker, plan)
    classifier.advance_step()  # complete step 1

    llm = _RecordingLLM()
    drama = DramaManager(case_bible=cb, llm=llm)
    # Pre-set the depth so the very next accommodate trips the emergency rule.
    # MAX_DEPTH is a class attribute (3); _depth gets +=1 inside accommodate
    # before the comparison, so depth == MAX_DEPTH-1 makes the next call
    # cross the threshold.
    drama._depth = DramaManager.MAX_DEPTH - 1

    violations = tracker.check_violation([
        StateChange(entity="EV-POISON", attribute="exists",
                    old_value=True, new_value=False),
    ])
    assert violations, "destroying EV-POISON must violate a span"

    new_plan = drama.accommodate(
        violated_spans=violations,
        current_plan=PlotPlan(
            investigator=plan.investigator,
            steps=classifier.completed_steps + classifier.remaining_steps,
        ),
        completed_steps=classifier.completed_steps,
    )

    assert llm.calls == 0, (
        "emergency path must not call the LLM; "
        f"got {llm.calls} call(s)"
    )

    kinds = [s.kind for s in new_plan.steps]
    assert "confrontation" in kinds, (
        f"emergency plan must contain a confrontation; got kinds={kinds}"
    )
    assert kinds[-1] == "resolution", (
        f"emergency plan must end with a resolution step; got kinds={kinds}"
    )

    # Completed steps must remain at the front with their original ids.
    completed_id = classifier.completed_steps[0].step_id
    assert new_plan.steps[0].step_id == completed_id, (
        "completed step must be preserved at the head of the emergency plan"
    )

    # New climax steps must have ids above the completed-step max so they
    # cannot collide with ActionClassifier._completed bookkeeping.
    completed_max = max(s.step_id for s in classifier.completed_steps)
    climax_ids = [s.step_id for s in new_plan.steps
                  if s.kind in ("confrontation", "resolution")]
    assert climax_ids and min(climax_ids) > completed_max, (
        f"emergency climax ids must sit above completed_max={completed_max}; "
        f"got {climax_ids}"
    )


# ── runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Running regression tests…")
    test_step_ids_remain_stable_after_accommodation()
    print("  ✓ test_step_ids_remain_stable_after_accommodation")
    test_presence_only_beat_advances_on_room_entry()
    print("  ✓ test_presence_only_beat_advances_on_room_entry")
    test_load_rebuilds_tracker_from_saved_plan()
    print("  ✓ test_load_rebuilds_tracker_from_saved_plan")
    test_discovery_shortcut_requires_correct_room()
    print("  ✓ test_discovery_shortcut_requires_correct_room")
    test_check_game_over_exits_on_resolution_kind()
    print("  ✓ test_check_game_over_exits_on_resolution_kind")
    test_check_game_over_exits_on_empty_remaining()
    print("  ✓ test_check_game_over_exits_on_empty_remaining")
    test_emergency_resolution_at_max_depth()
    print("  ✓ test_emergency_resolution_at_max_depth")
    print("All regression tests passed.")
