from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "phase1"))
from llm_interface import LLMBackend

from models_phase2 import ActionIntent, StateChange
from world_state import WorldStateManager

_PROMPTS = Path(__file__).parent / "prompts"
CONFIDENCE_THRESHOLD = 0.7


class InputParser:
    def __init__(
        self,
        llm: LLMBackend,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
    ) -> None:
        self._llm = llm
        self._threshold = confidence_threshold

    def parse(
        self,
        raw_input: str,
        world_state: WorldStateManager,
    ) -> ActionIntent | None:
        intent_data = self._extract_intent(raw_input)
        # Normalise None values from the LLM up-front so downstream string
        # operations (.replace, .lower, ...) never see them.
        intent_data = _coerce_strings(intent_data)
        intent_data = _apply_raw_overrides(raw_input, intent_data)
        confidence = float(intent_data.get("confidence", 0.0) or 0.0)
        if confidence < self._threshold:
            return None

        verb = intent_data.get("verb", "")
        object_ = intent_data.get("object", "")
        target_location = intent_data.get("target_location") or None

        direct_effects = _sanitize_effects(
            intent_data,
            self._predict_effects(intent_data, world_state),
        )
        implied_effects = _sanitize_effects(
            intent_data,
            self._infer_commonsense(intent_data, direct_effects),
        )
        all_effects = direct_effects + implied_effects

        return ActionIntent(
            raw_text=raw_input,
            verb=verb,
            object_=object_,
            target_location=target_location,
            confidence=confidence,
            predicted_effects=all_effects,
        )

    # ── internal ──────────────────────────────────────────────────────────

    def _extract_intent(self, raw_input: str) -> dict:
        template = (_PROMPTS / "parser_intent.txt").read_text(encoding="utf-8")
        prompt = template.replace("{raw_input}", raw_input)
        response = self._llm.generate(prompt, label="parser_intent") if _has_label(self._llm) else self._llm.generate(prompt)
        return _parse_json_obj(response.text) or {"verb": "", "object": "", "target_location": None, "confidence": 0.0}

    def _predict_effects(
        self, intent: dict, world_state: WorldStateManager
    ) -> list[StateChange]:
        template = (_PROMPTS / "parser_effects.txt").read_text(encoding="utf-8")
        room_view = world_state.get_room_view()
        prompt = (
            template
            .replace("{verb}", intent.get("verb", ""))
            .replace("{object}", intent.get("object", ""))
            .replace("{player_room}", world_state.player_room)
            .replace("{room_view}", json.dumps(room_view, ensure_ascii=False))
        )
        response = self._llm.generate(prompt, label="parser_effects") if _has_label(self._llm) else self._llm.generate(prompt)
        return _parse_state_changes(response.text)

    def _infer_commonsense(
        self, intent: dict, direct_effects: list[StateChange]
    ) -> list[StateChange]:
        template = (_PROMPTS / "parser_commonsense.txt").read_text(encoding="utf-8")
        effects_repr = json.dumps(
            [e.to_dict() for e in direct_effects], ensure_ascii=False
        )
        prompt = (
            template
            .replace("{verb}", intent.get("verb", ""))
            .replace("{object}", intent.get("object", ""))
            .replace("{direct_effects}", effects_repr)
        )
        response = self._llm.generate(prompt, label="parser_commonsense") if _has_label(self._llm) else self._llm.generate(prompt)
        return _parse_state_changes(response.text)


def _has_label(llm: LLMBackend) -> bool:
    import inspect
    try:
        sig = inspect.signature(llm.generate)
        return "label" in sig.parameters
    except Exception:
        return False


def _coerce_strings(data: dict) -> dict:
    # Convert None values for known string-like keys to "" so .replace / .lower
    # never blow up. Leave target_location as None (it is allowed to be absent).
    string_keys = ("verb", "object")
    out = dict(data)
    for k in string_keys:
        if out.get(k) is None:
            out[k] = ""
    return out


def _apply_raw_overrides(raw_input: str, intent_data: dict) -> dict:
    ev_match = re.search(r"\bEV-\d+\b", raw_input, flags=re.IGNORECASE)
    if not ev_match:
        return intent_data

    out = dict(intent_data)
    raw_lower = raw_input.lower().strip()
    if raw_lower.startswith(("examine ", "look ", "search ", "check ", "read ")):
        out["verb"] = raw_lower.split(maxsplit=1)[0]
        out["object"] = ev_match.group(0).upper()
        out["confidence"] = max(float(out.get("confidence") or 0.0), 0.99)
    return out


def _sanitize_effects(intent: dict, effects: list[StateChange]) -> list[StateChange]:
    """Keep noisy LLM effects inside the physical bounds of the verb."""
    verb = (intent.get("verb") or "").lower().strip()
    observation_verbs = (
        "examine", "look", "search", "check", "read",
        "ask", "talk", "interview", "question", "speak",
    )
    if verb in observation_verbs:
        sanitized: list[StateChange] = []
        seen_known: set[str] = set()
        for effect in effects:
            if effect.attribute == "known_to_player":
                sanitized.append(effect)
                seen_known.add(effect.entity)
        for effect in effects:
            if effect.attribute == "known_to_player":
                continue
            if _looks_like_evidence_id(effect.entity) and effect.entity not in seen_known:
                sanitized.append(StateChange(
                    entity=effect.entity,
                    attribute="known_to_player",
                    old_value=False,
                    new_value=True,
                ))
                seen_known.add(effect.entity)
        return sanitized
    return effects


def _looks_like_evidence_id(entity: str) -> bool:
    entity = (entity or "").upper()
    if not entity.startswith("EV-"):
        return False
    suffix = entity[3:]
    return bool(suffix) and suffix.replace("-", "").isalnum()


def _parse_json_obj(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


def _parse_state_changes(text: str) -> list[StateChange]:
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        return []
    try:
        items = json.loads(text[start:end])
    except json.JSONDecodeError:
        return []
    result = []
    for item in items:
        if isinstance(item, dict) and "entity" in item and "attribute" in item:
            result.append(StateChange.from_dict(item))
    return result
