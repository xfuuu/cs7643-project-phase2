"""
Accommodation integration test.

Scenario: Player pours the only poison bottle (EV-POISON) down the drain.
Asserts:
  (a) CausalSpanTracker.check_violation() fires
  (b) DramaManager removes steps that depend on EV-POISON
  (c) New steps still point to the same culprit
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "phase1"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_interface import LLMBackend, LLMResponse
from models import CaseBible, Character, EvidenceItem, PlotPlan, PlotStep, RedHerring, TimelineEvent

from causal_spans import CausalSpanTracker
from drama_manager import DramaManager
from models_phase2 import StateChange


# ── mock helpers ──────────────────────────────────────────────────────────────

class _StubLLM(LLMBackend):
    """Returns a minimal valid JSON PlotStep array for runtime repair."""

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        import json
        steps = [
            {
                "step_id": 99,
                "phase": "investigation",
                "kind": "analysis",
                "title": "A New Angle",
                "summary": "The investigator finds another way to implicate Eleanor Vance.",
                "location": "The Library",
                "participants": ["Arthur Penhaligon", "Eleanor Vance"],
                "evidence_ids": ["EV-GLOVE"],
                "reveals": ["Eleanor Vance is still the prime suspect."],
                "timeline_ref": None,
            }
        ]
        return LLMResponse(text=json.dumps(steps))


def _make_mock_case_bible() -> CaseBible:
    culprit = Character(
        name="Eleanor Vance",
        role="culprit",
        description="Amateur botanist.",
        relationship_to_victim="Associate",
        means="Poison",
        motive="Protect husband",
        opportunity="Left masquerade briefly",
        alibi="Powder room",
    )
    victim = Character(
        name="Sir Alistair Thorne",
        role="victim",
        description="Industrialist.",
        relationship_to_victim="Self",
        means="N/A", motive="N/A", opportunity="N/A", alibi="N/A",
    )
    poison = EvidenceItem(
        evidence_id="EV-POISON",
        name="Poison Bottle",
        description="Concentrated aconitine.",
        location_found="Conservatory",
        implicated_person="Eleanor Vance",
        reliability=1.0,
    )
    glove = EvidenceItem(
        evidence_id="EV-GLOVE",
        name="Stained Glove",
        description="Gardening glove with plant residue.",
        location_found="Conservatory Bin",
        implicated_person="Eleanor Vance",
        reliability=0.9,
    )
    timeline_event = TimelineEvent(
        event_id="T01",
        time_marker="21:45",
        summary="Eleanor retrieves the poison.",
        participants=["Eleanor Vance"],
        location="Conservatory",
        public=False,
    )
    return CaseBible(
        setting="Manor mystery",
        investigator="Arthur Penhaligon",
        victim=victim,
        culprit=culprit,
        suspects=[culprit],
        motive="Protect husband from blackmail",
        method="Poisoned brandy flask",
        true_timeline=[timeline_event],
        evidence_items=[poison, glove],
        red_herrings=[],
        culprit_evidence_chain=["EV-POISON", "EV-GLOVE"],
    )


def _make_mock_plot_plan(case_bible: CaseBible) -> PlotPlan:
    return PlotPlan(
        investigator=case_bible.investigator,
        steps=[
            PlotStep(
                step_id=1, phase="Discovery", kind="discovery",
                title="Body Found", summary="Arthur finds the body.",
                location="The Study", participants=["Arthur Penhaligon"],
                evidence_ids=[], reveals=["Victim is dead."], timeline_ref=None,
            ),
            PlotStep(
                step_id=2, phase="Initial Sweep", kind="search",
                title="Find the Poison",
                summary="Arthur finds the poison bottle in the conservatory.",
                location="Conservatory", participants=["Arthur Penhaligon"],
                evidence_ids=["EV-POISON"],
                reveals=["Poison bottle found."], timeline_ref=None,
            ),
            PlotStep(
                step_id=3, phase="Investigation", kind="analysis",
                title="Trace the Glove",
                summary="Arthur links the glove to Eleanor.",
                location="Conservatory", participants=["Arthur Penhaligon", "Eleanor Vance"],
                evidence_ids=["EV-GLOVE"],
                reveals=["Glove belongs to Eleanor."], timeline_ref=None,
            ),
            PlotStep(
                step_id=4, phase="Climax", kind="confrontation",
                title="Confrontation",
                summary="Arthur confronts Eleanor with the evidence.",
                location="Drawing Room",
                participants=["Arthur Penhaligon", "Eleanor Vance"],
                evidence_ids=["EV-POISON", "EV-GLOVE"],
                reveals=["Eleanor Vance is the culprit."], timeline_ref=None,
            ),
            PlotStep(
                step_id=5, phase="Climax", kind="resolution",
                title="Resolution",
                summary="Eleanor confesses.",
                location="Drawing Room",
                participants=["Arthur Penhaligon", "Eleanor Vance"],
                evidence_ids=[], reveals=["Case closed."], timeline_ref=None,
            ),
        ],
    )


# ── tests ──────────────────────────────────────────────────────────────────────

def test_accommodation_triggered() -> None:
    """(a) Destroying EV-POISON triggers a causal span violation."""
    case_bible = _make_mock_case_bible()
    plot_plan = _make_mock_plot_plan(case_bible)

    from models import FactTriple
    fact_triples = [
        FactTriple(subject="EV-POISON", relation="found_at", object="Conservatory", time=None, source="evidence"),
        FactTriple(subject="EV-POISON", relation="is_evidence", object="Poison Bottle", time=None, source="evidence"),
        FactTriple(subject="EV-GLOVE", relation="found_at", object="Conservatory Bin", time=None, source="evidence"),
    ]

    tracker = CausalSpanTracker(fact_triples, plot_plan)
    destroy_poison = StateChange(
        entity="EV-POISON",
        attribute="exists",
        old_value=True,
        new_value=False,
    )

    violations = tracker.check_violation([destroy_poison])
    assert len(violations) > 0, "Expected at least one causal span violation"
    violated_span_ids = [v.span.span_id for v in violations]
    assert "EV-POISON.exists" in violated_span_ids


def test_affected_steps_removed() -> None:
    """(b) Steps referencing EV-POISON are removed from the new plan."""
    case_bible = _make_mock_case_bible()
    plot_plan = _make_mock_plot_plan(case_bible)

    from models import FactTriple
    fact_triples = [
        FactTriple(subject="EV-POISON", relation="found_at", object="Conservatory", time=None, source="evidence"),
        FactTriple(subject="EV-GLOVE", relation="found_at", object="Conservatory Bin", time=None, source="evidence"),
    ]

    tracker = CausalSpanTracker(fact_triples, plot_plan)
    destroy_poison = StateChange(entity="EV-POISON", attribute="exists", old_value=True, new_value=False)
    violations = tracker.check_violation([destroy_poison])

    drama = DramaManager(case_bible=case_bible, llm=_StubLLM())
    completed_steps = [plot_plan.steps[0]]
    new_plan = drama.accommodate(
        violated_spans=violations,
        current_plan=plot_plan,
        completed_steps=completed_steps,
    )

    new_evidence_ids = {ev for step in new_plan.steps for ev in step.evidence_ids}
    assert "EV-POISON" not in new_evidence_ids, (
        f"EV-POISON should be absent from new plan evidence. Found in: "
        f"{[s.title for s in new_plan.steps if 'EV-POISON' in s.evidence_ids]}"
    )


def test_new_steps_target_same_culprit() -> None:
    """(c) New steps generated by accommodation still point to Eleanor Vance."""
    case_bible = _make_mock_case_bible()
    plot_plan = _make_mock_plot_plan(case_bible)

    from models import FactTriple
    fact_triples = [
        FactTriple(subject="EV-POISON", relation="found_at", object="Conservatory", time=None, source="evidence"),
        FactTriple(subject="EV-GLOVE", relation="found_at", object="Conservatory Bin", time=None, source="evidence"),
    ]

    tracker = CausalSpanTracker(fact_triples, plot_plan)
    destroy_poison = StateChange(entity="EV-POISON", attribute="exists", old_value=True, new_value=False)
    violations = tracker.check_violation([destroy_poison])

    drama = DramaManager(case_bible=case_bible, llm=_StubLLM())
    completed = [plot_plan.steps[0]]
    new_plan = drama.accommodate(
        violated_spans=violations,
        current_plan=plot_plan,
        completed_steps=completed,
    )

    culprit_name = case_bible.culprit.name
    non_completed_ids = {s.step_id for s in completed}
    new_steps = [s for s in new_plan.steps if s.step_id not in non_completed_ids]

    culprit_appears = any(
        culprit_name in step.participants
        or any(culprit_name in r for r in step.reveals)
        or culprit_name in step.summary
        for step in new_steps
    )
    assert culprit_appears, (
        f"Expected '{culprit_name}' to appear in at least one new step's "
        f"participants/reveals/summary. Steps: {[s.title for s in new_steps]}"
    )


if __name__ == "__main__":
    print("Running accommodation tests…")
    test_accommodation_triggered()
    print("  ✓ test_accommodation_triggered")
    test_affected_steps_removed()
    print("  ✓ test_affected_steps_removed")
    test_new_steps_target_same_culprit()
    print("  ✓ test_new_steps_target_same_culprit")
    print("All tests passed.")
