from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "phase1"))
from models import FactTriple, PlotPlan

from models_phase2 import CausalSpan, StateChange, ViolatedSpan


class CausalSpanTracker:
    def __init__(
        self,
        fact_triples: list[FactTriple],
        plot_plan: PlotPlan,
    ) -> None:
        self._active_spans: list[CausalSpan] = self._compile_spans(
            fact_triples, plot_plan
        )

    # ── public API ────────────────────────────────────────────────────────

    def check_violation(
        self, predicted_effects: list[StateChange]
    ) -> list[ViolatedSpan]:
        violations: list[ViolatedSpan] = []
        for change in predicted_effects:
            for span in self._active_spans:
                if self._matches_span(change, span) and change.new_value != span.required_value:
                    violations.append(
                        ViolatedSpan(
                            span=span,
                            triggering_change=change,
                            description=(
                                f"Action would set {change.entity}.{change.attribute}="
                                f"{change.new_value!r} but span {span.span_id} requires "
                                f"{span.required_value!r} until step {span.until_step_id}. "
                                f"({span.description})"
                            ),
                        )
                    )
        return violations

    def complete_step(self, step_id: int) -> None:
        self._active_spans = [
            s for s in self._active_spans if s.until_step_id != step_id
        ]

    def add_span(self, span: CausalSpan) -> None:
        self._active_spans.append(span)

    def remove_spans_for_steps(self, step_ids: list[int]) -> None:
        id_set = set(step_ids)
        self._active_spans = [
            s for s in self._active_spans if s.until_step_id not in id_set
        ]

    @property
    def active_spans(self) -> list[CausalSpan]:
        return list(self._active_spans)

    # ── internal ──────────────────────────────────────────────────────────

    def _compile_spans(
        self,
        fact_triples: list[FactTriple],
        plot_plan: PlotPlan,
    ) -> list[CausalSpan]:
        evidence_locations: dict[str, str] = {}
        for triple in fact_triples:
            if triple.relation == "found_at":
                evidence_locations[triple.subject] = triple.object

        first_reference: dict[str, int] = {}
        for step in plot_plan.steps:
            for ev_id in step.evidence_ids:
                if ev_id not in first_reference:
                    first_reference[ev_id] = step.step_id

        spans: list[CausalSpan] = []
        for ev_id, first_step_id in first_reference.items():
            loc = evidence_locations.get(ev_id, "unknown")

            spans.append(
                CausalSpan(
                    span_id=f"{ev_id}.exists",
                    variable=f"{ev_id}.exists",
                    required_value=True,
                    from_step_id=0,
                    until_step_id=first_step_id,
                    evidence_ids=[ev_id],
                    description=f"{ev_id} must exist until step {first_step_id} (first reference)",
                )
            )
            if loc != "unknown":
                spans.append(
                    CausalSpan(
                        span_id=f"{ev_id}.location",
                        variable=f"{ev_id}.location",
                        required_value=loc,
                        from_step_id=0,
                        until_step_id=first_step_id,
                        evidence_ids=[ev_id],
                        description=f"{ev_id} must remain at '{loc}' until step {first_step_id}",
                    )
                )
        return spans

    def _matches_span(self, change: StateChange, span: CausalSpan) -> bool:
        expected_variable = f"{change.entity}.{change.attribute}"
        return expected_variable == span.variable
