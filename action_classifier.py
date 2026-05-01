from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "phase1"))
from models import PlotPlan, PlotStep

from causal_spans import CausalSpanTracker
from models_phase2 import (
    ActionClassification,
    ActionIntent,
    ActionKind,
    StateChange,
    ViolatedSpan,
)
from world_state import WorldStateManager


class ActionClassifier:
    def __init__(
        self,
        causal_tracker: CausalSpanTracker,
        plot_plan: PlotPlan,
    ) -> None:
        self._tracker = causal_tracker
        self._completed: list[PlotStep] = []
        self._remaining: list[PlotStep] = list(plot_plan.steps)

    # ── public API ────────────────────────────────────────────────────────

    def classify(
        self,
        intent: ActionIntent,
        world_state: WorldStateManager | None = None,
    ) -> ActionClassification:
        effects = intent.predicted_effects

        # 1. exceptional check (highest priority)
        violated = self._tracker.check_violation(effects)
        if violated:
            return ActionClassification(
                kind=ActionKind.EXCEPTIONAL,
                violated_spans=violated,
            )

        # 2. constituent check
        next_step = self.current_step
        if next_step is not None and self._is_constituent(effects, intent, next_step, world_state):
            return ActionClassification(
                kind=ActionKind.CONSTITUENT,
                triggered_step_id=next_step.step_id,
            )

        # 3. consistent
        return ActionClassification(kind=ActionKind.CONSISTENT)

    def advance_step(self) -> None:
        if not self._remaining:
            return
        done = self._remaining.pop(0)
        self._completed.append(done)
        self._tracker.complete_step(done.step_id)

    def update_plan(self, new_plan: PlotPlan) -> None:
        completed_ids = {s.step_id for s in self._completed}
        self._remaining = [s for s in new_plan.steps if s.step_id not in completed_ids]

    @property
    def current_step(self) -> PlotStep | None:
        return self._remaining[0] if self._remaining else None

    @property
    def completed_steps(self) -> list[PlotStep]:
        return list(self._completed)

    @property
    def remaining_steps(self) -> list[PlotStep]:
        return list(self._remaining)

    # ── internal ──────────────────────────────────────────────────────────

    def _is_constituent(
        self,
        effects: list[StateChange],
        intent: ActionIntent,
        step: PlotStep,
        world_state: WorldStateManager | None = None,
    ) -> bool:
        # Match by evidence: player examines/takes evidence referenced in next step
        for change in effects:
            if change.entity in step.evidence_ids:
                return True

        # Match by location: player moves to the step's location
        if intent.verb in ("go", "move", "walk", "enter") and intent.target_location:
            if _normalise(intent.target_location) == _normalise(step.location):
                return True

        # Match by NPC interaction: player talks to a participant in next step
        if intent.verb in ("ask", "talk", "interview", "question", "speak"):
            for participant in step.participants:
                if _normalise(intent.object_) in _normalise(participant):
                    return True

        # Match by kind: discovery steps trigger on any "examine"-style verb,
        # but only when the player is actually in the step's room. Without the
        # room check, idly examining furniture in any room would fire a
        # discovery beat for somewhere else (e.g. a Study-located discovery
        # firing while the player examines a chair in the Library).
        if step.kind == "discovery" and intent.verb in ("examine", "look", "search", "check"):
            if world_state is None:
                return True  # no spatial context available; preserve old behavior
            if _normalise(world_state.player_room) == _normalise(step.location):
                return True

        return False


def _normalise(s: str) -> str:
    return s.lower().strip()
