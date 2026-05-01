from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "phase1"))
from llm_interface import LLMBackend
from models import CaseBible, PlotPlan, PlotStep

from models_phase2 import ViolatedSpan
from parser import _has_label

_PROMPTS = Path(__file__).parent / "prompts"


class DramaManager:
    MAX_DEPTH: int = 3

    def __init__(self, case_bible: CaseBible, llm: LLMBackend) -> None:
        self._case_bible = case_bible
        self._llm = llm
        self._depth: int = 0

    # ── public API ────────────────────────────────────────────────────────

    def accommodate(
        self,
        violated_spans: list[ViolatedSpan],
        current_plan: PlotPlan,
        completed_steps: list[PlotStep],
    ) -> PlotPlan:
        self._depth += 1
        if self._depth >= self.MAX_DEPTH:
            return self._emergency_resolution(current_plan, completed_steps)
        return self._standard_accommodate(violated_spans, current_plan, completed_steps)

    def reset_depth(self) -> None:
        self._depth = 0

    @property
    def accommodation_depth(self) -> int:
        return self._depth

    # ── internal ──────────────────────────────────────────────────────────

    def _standard_accommodate(
        self,
        violated_spans: list[ViolatedSpan],
        current_plan: PlotPlan,
        completed_steps: list[PlotStep],
    ) -> PlotPlan:
        dependent_ids = self._find_dependent_steps(current_plan, violated_spans)
        removed = [s for s in current_plan.steps if s.step_id in dependent_ids]
        remaining = [s for s in current_plan.steps if s.step_id not in dependent_ids]

        destroyed_evidence: set[str] = set()
        for vs in violated_spans:
            destroyed_evidence.update(vs.span.evidence_ids)

        available_evidence = [
            ev for ev in self._case_bible.evidence_items
            if ev.evidence_id not in destroyed_evidence
        ]
        available_ids = [ev.evidence_id for ev in available_evidence]

        n_steps = max(len(removed), 2)
        new_steps = self._runtime_repair(
            remaining_steps=remaining,
            completed_steps=completed_steps,
            removed_steps=removed,
            available_evidence_ids=available_ids,
            n_steps=n_steps,
        )

        # Keep step_ids stable across accommodation. Surviving steps retain
        # their original ids; brand-new steps were already assigned ids above
        # max(remaining) by `_runtime_repair`. Renumbering 1..N would silently
        # break ActionClassifier._completed (which keys on the original ids)
        # and CausalSpanTracker.until_step_id references after update_plan().
        merged = remaining + new_steps
        merged.sort(key=lambda s: s.step_id)
        return PlotPlan(investigator=current_plan.investigator, steps=merged)

    def _find_dependent_steps(
        self,
        plan: PlotPlan,
        violated_spans: list[ViolatedSpan],
    ) -> set[int]:
        blocked_evidence: set[str] = set()
        for vs in violated_spans:
            blocked_evidence.update(vs.span.evidence_ids)

        dependent: set[int] = set()
        changed = True
        while changed:
            changed = False
            for step in plan.steps:
                if step.step_id in dependent:
                    continue
                if any(ev in blocked_evidence for ev in step.evidence_ids):
                    dependent.add(step.step_id)
                    changed = True
        return dependent

    def _runtime_repair(
        self,
        remaining_steps: list[PlotStep],
        completed_steps: list[PlotStep],
        removed_steps: list[PlotStep],
        available_evidence_ids: list[str],
        n_steps: int,
    ) -> list[PlotStep]:
        template = (_PROMPTS / "drama_runtime_repair.txt").read_text(encoding="utf-8")
        cb = self._case_bible

        available_detail = []
        for ev in cb.evidence_items:
            if ev.evidence_id in available_evidence_ids:
                available_detail.append(f"{ev.evidence_id}: {ev.name} — {ev.description}")

        prompt = (
            template
            .replace("{culprit_name}", cb.culprit.name)
            .replace("{culprit_motive}", cb.motive)
            .replace("{culprit_method}", cb.method)
            .replace("{evidence_chain}", ", ".join(cb.culprit_evidence_chain))
            .replace("{completed_steps}", _steps_summary(completed_steps))
            .replace("{removed_steps}", _steps_summary(removed_steps))
            .replace("{available_evidence}", "\n".join(available_detail))
            .replace("{n_steps}", str(n_steps))
            .replace("{investigator}", cb.investigator)
        )

        label = "drama_repair"
        response = self._llm.generate(prompt, label=label) if _has_label(self._llm) else self._llm.generate(prompt)

        new_steps = _parse_plot_steps(response.text)
        if not new_steps:
            new_steps = self._fallback_steps(cb, available_evidence_ids, n_steps)

        start_id = max((s.step_id for s in remaining_steps), default=0) + 1
        for i, step in enumerate(new_steps):
            step.step_id = start_id + i

        return new_steps

    def _emergency_resolution(
        self, current_plan: PlotPlan, completed_steps: list[PlotStep]
    ) -> PlotPlan:
        cb = self._case_bible
        chain_ids = cb.culprit_evidence_chain
        base_id = max((s.step_id for s in completed_steps), default=0) + 1

        confrontation = PlotStep(
            step_id=base_id,
            phase="climax",
            kind="confrontation",
            title=f"The Truth About {cb.culprit.name}",
            summary=(
                f"{cb.investigator} draws the remaining threads together and confronts "
                f"{cb.culprit.name} with the evidence still in hand."
            ),
            location=completed_steps[-1].location if completed_steps else "Drawing Room",
            participants=[cb.investigator, cb.culprit.name],
            evidence_ids=chain_ids,
            reveals=[f"{cb.culprit.name} is the culprit. Motive: {cb.motive}"],
            timeline_ref=None,
        )
        resolution = PlotStep(
            step_id=base_id + 1,
            phase="climax",
            kind="resolution",
            title="The Case Closed",
            summary=(
                f"{cb.culprit.name} confesses as the storm breaks. "
                f"The investigation concludes with the truth of {cb.method}."
            ),
            location=confrontation.location,
            participants=[cb.investigator, cb.culprit.name],
            evidence_ids=[],
            reveals=["The mystery is solved."],
            timeline_ref=None,
        )
        return PlotPlan(
            investigator=current_plan.investigator,
            steps=completed_steps + [confrontation, resolution],
        )

    def _fallback_steps(
        self,
        case_bible: CaseBible,
        available_evidence_ids: list[str],
        n_steps: int,
    ) -> list[PlotStep]:
        steps = []
        chain = [e for e in case_bible.culprit_evidence_chain if e in available_evidence_ids]
        for i in range(min(n_steps, max(len(chain), 1))):
            ev_id = chain[i] if i < len(chain) else (available_evidence_ids[0] if available_evidence_ids else "")
            ev_name = next(
                (e.name for e in case_bible.evidence_items if e.evidence_id == ev_id), ev_id
            )
            steps.append(
                PlotStep(
                    step_id=900 + i,
                    phase="investigation",
                    kind="analysis",
                    title=f"Re-examining {ev_name}",
                    summary=(
                        f"{case_bible.investigator} turns attention to {ev_name}, "
                        f"finding a connection to {case_bible.culprit.name}."
                    ),
                    location=case_bible.culprit.opportunity or "Drawing Room",
                    participants=[case_bible.investigator, case_bible.culprit.name],
                    evidence_ids=[ev_id] if ev_id else [],
                    reveals=[f"The evidence points toward {case_bible.culprit.name}."],
                    timeline_ref=None,
                )
            )
        return steps

def _steps_summary(steps: list[PlotStep]) -> str:
    if not steps:
        return "(none)"
    lines = []
    for s in steps:
        lines.append(f"Step {s.step_id} [{s.kind}] {s.title}: {s.summary[:100]}")
    return "\n".join(lines)


def _parse_plot_steps(text: str) -> list[PlotStep]:
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        return []
    try:
        items = json.loads(text[start:end])
    except json.JSONDecodeError:
        return []
    steps = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            steps.append(
                PlotStep(
                    step_id=int(item.get("step_id", 0)),
                    phase=item.get("phase", "investigation"),
                    kind=item.get("kind", "analysis"),
                    title=item.get("title", ""),
                    summary=item.get("summary", ""),
                    location=item.get("location", "Drawing Room"),
                    participants=item.get("participants", []),
                    evidence_ids=item.get("evidence_ids", []),
                    reveals=item.get("reveals", []),
                    timeline_ref=item.get("timeline_ref"),
                )
            )
        except Exception:
            continue
    return steps
