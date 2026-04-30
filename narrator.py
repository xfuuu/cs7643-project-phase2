from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "phase1"))
from llm_interface import LLMBackend
from models import PlotStep

from models_phase2 import ActionIntent, StateChange
from parser import _has_label
from world_state import WorldStateManager

_PROMPTS = Path(__file__).parent / "prompts"
_STYLE_TOKENS = 500 * 4  # ~500 tokens worth of chars


class OutputNarrator:
    def __init__(self, llm: LLMBackend, style_reference: str) -> None:
        self._llm = llm
        self._style_ref = style_reference[:_STYLE_TOKENS]

    def narrate(
        self,
        intent: ActionIntent,
        effects: list[StateChange],
        current_step: PlotStep | None,
        world_state: WorldStateManager,
    ) -> str:
        template = (_PROMPTS / "narrator.txt").read_text(encoding="utf-8")

        effects_summary = _format_effects(effects)
        plot_context = _format_step(current_step) if current_step else "The investigation continues."

        prompt = (
            template
            .replace("{style_reference}", self._style_ref)
            .replace("{investigator}", _extract_investigator(current_step))
            .replace("{verb}", intent.verb)
            .replace("{object}", intent.object_)
            .replace("{effects_summary}", effects_summary)
            .replace("{plot_context}", plot_context)
        )
        label = "narrator"
        try:
            response = self._llm.generate(prompt, label=label) if _has_label(self._llm) else self._llm.generate(prompt)
            return response.text.strip()
        except Exception as exc:
            return f"[{intent.verb} {intent.object_}] — {exc}"

    def narrate_system(self, message: str) -> str:
        return f"\n── {message} ──\n"


def _format_effects(effects: list[StateChange]) -> str:
    if not effects:
        return "No notable change to the world."
    lines = []
    for e in effects:
        if e.attribute == "known_to_player" and e.new_value:
            lines.append(f"You become aware of: {e.entity}")
        elif e.attribute == "exists" and not e.new_value:
            lines.append(f"{e.entity} no longer exists.")
        elif e.attribute == "location":
            lines.append(f"{e.entity} moved to {e.new_value}.")
        else:
            lines.append(f"{e.entity}.{e.attribute} → {e.new_value}")
    return "\n".join(lines)


def _format_step(step: PlotStep) -> str:
    return (
        f"Current investigation beat: [{step.kind}] {step.title}\n"
        f"Context: {step.summary}\n"
        f"Location: {step.location}"
    )


def _extract_investigator(step: PlotStep | None) -> str:
    if step and step.participants:
        return step.participants[0]
    return "The investigator"
