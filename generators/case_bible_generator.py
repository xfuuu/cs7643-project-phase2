from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from llm_interface import LLMBackend
from models import CaseBible, Character, EvidenceItem, RedHerring, TimelineEvent


class CaseBibleGenerator:
    def __init__(self, llm: LLMBackend) -> None:
        self.llm = llm
        self.setting_file = Path(__file__).with_name("setting.txt")

    def generate(self) -> CaseBible:
        setting = self.setting_file.read_text(encoding="utf-8").strip()
        blueprint = self._generate_case_blueprint(setting)
        investigator = self._require_string(blueprint, "investigator")
        victim = self._build_character(blueprint["victim"])
        suspects = [self._build_character(item) for item in blueprint["suspects"]]
        culprit = self._resolve_culprit(blueprint, suspects)
        motive = self._require_string(blueprint, "motive")
        method = self._require_string(blueprint, "method")
        timeline = [self._build_timeline_event(item) for item in blueprint["true_timeline"]]
        evidence_items = [self._build_evidence_item(item) for item in blueprint["evidence_items"]]
        red_herrings = [self._build_red_herring(item) for item in blueprint["red_herrings"]]
        culprit_evidence_chain = self._build_culprit_chain(blueprint, evidence_items)

        return CaseBible(
            setting=setting,
            investigator=investigator,
            victim=victim,
            culprit=culprit,
            suspects=suspects,
            motive=motive,
            method=method,
            true_timeline=timeline,
            evidence_items=evidence_items,
            red_herrings=red_herrings,
            culprit_evidence_chain=culprit_evidence_chain,
        )

    def _generate_case_blueprint(self, setting: str) -> dict[str, Any]:
        prompt = (
            "Generate a crime-mystery case bible as valid JSON.\n"
            "Return JSON only. Do not use markdown fences.\n"
            "The JSON must follow this schema exactly:\n"
            "{\n"
            '  "investigator": str,\n'
            '  "victim": {"name": str, "role": "victim", "description": str, "relationship_to_victim": str, "means": str, "motive": str, "opportunity": str, "alibi": str},\n'
            '  "suspects": [\n'
            '    {"name": str, "role": "suspect" or "culprit", "description": str, "relationship_to_victim": str, "means": str, "motive": str, "opportunity": str, "alibi": str}\n'
            "  ],\n"
            '  "culprit_name": str,\n'
            '  "motive": str,\n'
            '  "method": str,\n'
            '  "true_timeline": [\n'
            '    {"event_id": str, "time_marker": str, "summary": str, "participants": [str], "location": str, "public": bool}\n'
            "  ],\n"
            '  "evidence_items": [\n'
            '    {"evidence_id": str, "name": str, "description": str, "location_found": str, "implicated_person": str, "reliability": float, "planted": bool}\n'
            "  ],\n"
            '  "red_herrings": [\n'
            '    {"herring_id": str, "suspect_name": str, "misleading_evidence_ids": [str], "explanation": str}\n'
            "  ],\n"
            '  "culprit_evidence_chain": [str]\n'
            "}\n\n"
            "Requirements:\n"
            "- The investigator field must name the same lead investigator referenced anywhere in the timeline.\n"
            "- At least 4 suspects total, including exactly 1 culprit.\n"
            "- At least 8 evidence items.\n"
            "- At least 1 red herring.\n"
            "- Timeline and evidence must support the culprit clearly.\n"
            "- Keep all names, relationships, motives, methods, and clues consistent with the setting.\n"
            "- Avoid modern technology or forensic methods if the setting forbids them.\n"
            "- Make every required field non-empty.\n\n"
            "Quality constraints:\n"
            "- Design exactly one primary murder method. Do not use multiple competing true methods.\n"
            "- If there is a misleading wound, object, or apparent cause of death, it must be explicitly a red herring or staging detail, not a second true killing method.\n"
            "- Make the culprit's motive, means, opportunity, and alibi mutually coherent.\n"
            "- Give each non-culprit suspect a plausible private secret, tension, or compromising circumstance so they are not generic fillers.\n"
            "- Make at least 2 suspects have partially believable but ultimately flawed alibis.\n"
            "- The true_timeline should be rich enough to support a long investigation: include not only the murder itself, but also key pre-murder tensions, suspicious movements, concealment attempts, discovery events, and at least one misleading event.\n"
            "- Prefer 8-12 timeline events rather than a minimal sequence.\n"
            "- Evidence items should not be redundant. Mix direct, indirect, and misleading clues.\n"
            "- The culprit_evidence_chain must be a coherent chain of 3-5 evidence items that collectively identify the culprit through reasoning, not merely a list of all suspicious objects.\n"
            "- At least one red herring should be strong enough to support a plausible but ultimately false theory of the crime.\n"
            "- Keep the case fair-play: the hidden truth should make the final solution explainable from the evidence.\n\n"
            f"Setting constraints:\n{setting}"
        )
        raw = self.llm.generate(prompt).text
        data = self._extract_json_object(raw)
        self._validate_blueprint_shape(data)
        return data

    def _extract_json_object(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise RuntimeError(f"LLM did not return a JSON object: {raw}")

        candidate = text[start : end + 1]
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Failed to parse LLM JSON response: {candidate}") from exc

        if not isinstance(data, dict):
            raise RuntimeError(f"Expected top-level JSON object, got: {type(data).__name__}")
        return data

    def _validate_blueprint_shape(self, data: dict[str, Any]) -> None:
        required_keys = [
            "investigator",
            "victim",
            "suspects",
            "culprit_name",
            "motive",
            "method",
            "true_timeline",
            "evidence_items",
            "red_herrings",
            "culprit_evidence_chain",
        ]
        missing = [key for key in required_keys if key not in data]
        if missing:
            raise RuntimeError(f"LLM case blueprint is missing required keys: {missing}")

    def _build_character(self, data: dict[str, Any]) -> Character:
        return Character(
            name=self._require_string(data, "name"),
            role=self._require_string(data, "role"),
            description=self._require_string(data, "description"),
            relationship_to_victim=self._require_string(data, "relationship_to_victim"),
            means=self._require_string(data, "means"),
            motive=self._require_string(data, "motive"),
            opportunity=self._require_string(data, "opportunity"),
            alibi=self._require_string(data, "alibi"),
        )

    def _build_timeline_event(self, data: dict[str, Any]) -> TimelineEvent:
        participants = data.get("participants")
        if not isinstance(participants, list) or not all(isinstance(item, str) and item.strip() for item in participants):
            raise RuntimeError(f"Timeline event participants must be a non-empty list of strings: {data}")
        public = data.get("public")
        if not isinstance(public, bool):
            raise RuntimeError(f"Timeline event public must be boolean: {data}")
        return TimelineEvent(
            event_id=self._require_string(data, "event_id"),
            time_marker=self._require_string(data, "time_marker"),
            summary=self._require_string(data, "summary"),
            participants=[item.strip() for item in participants],
            location=self._require_string(data, "location"),
            public=public,
        )

    def _build_evidence_item(self, data: dict[str, Any]) -> EvidenceItem:
        reliability_raw = data.get("reliability")
        try:
            reliability = float(reliability_raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Evidence reliability must be numeric: {data}") from exc
        planted = data.get("planted", False)
        if not isinstance(planted, bool):
            raise RuntimeError(f"Evidence planted must be boolean: {data}")
        return EvidenceItem(
            evidence_id=self._require_string(data, "evidence_id"),
            name=self._require_string(data, "name"),
            description=self._require_string(data, "description"),
            location_found=self._require_string(data, "location_found"),
            implicated_person=self._require_string(data, "implicated_person"),
            reliability=reliability,
            planted=planted,
        )

    def _build_red_herring(self, data: dict[str, Any]) -> RedHerring:
        misleading_ids = data.get("misleading_evidence_ids")
        if not isinstance(misleading_ids, list) or not all(isinstance(item, str) and item.strip() for item in misleading_ids):
            raise RuntimeError(f"Red herring misleading_evidence_ids must be a list of strings: {data}")
        return RedHerring(
            herring_id=self._require_string(data, "herring_id"),
            suspect_name=self._require_string(data, "suspect_name"),
            misleading_evidence_ids=[item.strip() for item in misleading_ids],
            explanation=self._require_string(data, "explanation"),
        )

    def _resolve_culprit(self, data: dict[str, Any], suspects: list[Character]) -> Character:
        culprit_name = self._require_string(data, "culprit_name")
        for suspect in suspects:
            if suspect.name == culprit_name:
                suspect.role = "culprit"
                return suspect
        raise RuntimeError(f"Culprit name {culprit_name!r} was not found in suspects.")

    def _build_culprit_chain(self, data: dict[str, Any], evidence_items: list[EvidenceItem]) -> list[str]:
        chain = data.get("culprit_evidence_chain")
        if not isinstance(chain, list) or not all(isinstance(item, str) and item.strip() for item in chain):
            raise RuntimeError("culprit_evidence_chain must be a list of non-empty strings.")
        evidence_ids = {item.evidence_id for item in evidence_items}
        normalized_chain = [item.strip() for item in chain]
        missing = [item for item in normalized_chain if item not in evidence_ids]
        if missing:
            raise RuntimeError(f"Culprit evidence chain references unknown evidence ids: {missing}")
        return normalized_chain

    def _require_string(self, data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"Expected non-empty string for {key!r}, got: {value!r}")
        return value.strip()
