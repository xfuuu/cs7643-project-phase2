from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from llm_interface import LLMBackend
from models import CaseBible, FactTriple, PlotPlan, PlotStep, TimelineEvent


@dataclass
class _TimedTimelineEvent:
    event: TimelineEvent
    minutes: int


class PlotPlanner:
    def __init__(self, llm: LLMBackend | None = None) -> None:
        self.llm = llm

    def build_plan(self, case_bible: CaseBible, fact_graph: list[FactTriple] | None = None) -> PlotPlan:
        if self.llm is not None:
            try:
                return self._build_plan_with_llm(case_bible, fact_graph)
            except Exception:
                pass
        return self._build_plan_with_rules(case_bible, fact_graph)

    def _build_plan_with_llm(self, case_bible: CaseBible, fact_graph: list[FactTriple] | None) -> PlotPlan:
        evidence_ids = sorted(self._available_evidence_ids(case_bible, fact_graph))
        prompt = self._plot_prompt(case_bible, fact_graph, evidence_ids)
        raw = self.llm.generate(prompt).text
        payload = self._extract_json_object(raw)
        steps_data = payload.get("steps")
        if not isinstance(steps_data, list) or len(steps_data) < 15:
            raise RuntimeError("LLM plot plan must include at least 15 structured steps.")

        steps: list[PlotStep] = []
        for index, step_data in enumerate(steps_data, start=1):
            steps.append(self._build_step(step_data, index, evidence_ids))

        self._normalize_step_ids(steps)
        self._normalize_llm_step_times(case_bible, steps)
        return PlotPlan(investigator=case_bible.investigator, steps=steps)

    def _build_plan_with_rules(self, case_bible: CaseBible, fact_graph: list[FactTriple] | None) -> PlotPlan:
        investigator = case_bible.investigator
        timed_events = self._sorted_events(case_bible.true_timeline)
        evidence_ids = self._available_evidence_ids(case_bible, fact_graph)
        evidence_by_person = self._evidence_by_person(case_bible)

        discovery_event = self._find_discovery_event(timed_events) or timed_events[-1].event
        death_event = self._find_death_event(timed_events, case_bible.victim.name) or timed_events[-1].event
        opening_event = timed_events[0].event
        concealment_event = self._find_concealment_event(timed_events, case_bible.culprit.name)
        culprit_chain = [item for item in case_bible.culprit_evidence_chain if item in evidence_ids]

        suspects = case_bible.suspects
        interview_order = self._ordered_suspects(case_bible, evidence_by_person)
        suspect_one = interview_order[0]
        suspect_two = interview_order[1] if len(interview_order) > 1 else interview_order[0]
        suspect_three = interview_order[2] if len(interview_order) > 2 else interview_order[-1]
        suspect_four = interview_order[3] if len(interview_order) > 3 else interview_order[-1]

        timeline_ref = self._step_times(discovery_event.time_marker, count=17)
        red_herring_one = case_bible.red_herrings[0] if case_bible.red_herrings else None
        red_herring_two = case_bible.red_herrings[1] if len(case_bible.red_herrings) > 1 else None
        pre_murder_tension = self._find_pre_murder_tension_event(timed_events, case_bible.victim.name) or opening_event
        misdirection_event = self._find_misdirection_event(timed_events) or concealment_event or discovery_event
        investigator_setup = self._investigator_setup(investigator, case_bible.victim.name, discovery_event.location)
        pivot_title = self._pivot_title(case_bible.method)
        confrontation_title = self._confrontation_title(red_herring_one, case_bible.culprit.name)

        steps = [
            PlotStep(
                1,
                "setup",
                "discovery",
                "A Guest Becomes the Investigator",
                f"{investigator_setup} When {discovery_event.summary.lower()}, she is already inside the sealed estate and takes charge before anyone can slip away.",
                discovery_event.location,
                [investigator, case_bible.victim.name] + [suspect.name for suspect in suspects],
                self._pick_ids(evidence_ids, culprit_chain[:1]),
                ["The investigation begins as a closed-circle inquiry."],
                timeline_ref[0],
            ),
            PlotStep(
                2,
                "setup",
                "survey",
                "The First Scene Review",
                f"The detective studies the room where {case_bible.victim.name} died and notes that the apparent cause of death must be tested against the physical evidence.",
                death_event.location,
                [investigator],
                self._pick_ids(evidence_ids, culprit_chain[:2] or self._first_ids(evidence_ids, 2)),
                ["The death scene may have been arranged to hide the true method."],
                timeline_ref[1],
            ),
            PlotStep(
                3,
                "setup",
                "interview",
                "The Promise of a Reckoning",
                f"The detective reconstructs the mood of the evening from {pre_murder_tension.summary.lower()}, realizing that {case_bible.victim.name} had gathered the household on the edge of a private reckoning.",
                pre_murder_tension.location,
                [investigator] + [suspect.name for suspect in suspects],
                self._pick_ids(evidence_ids, self._first_ids(evidence_ids, 1)),
                ["Every major suspect had some reason to fear or resent the victim."],
                timeline_ref[2],
            ),
            PlotStep(
                4,
                "investigation",
                "interview",
                f"Questioning {suspect_one.name}",
                f"{investigator} presses {suspect_one.name} on motive, means, and movements, drawing out the claim: {suspect_one.opportunity}",
                self._best_location_for_person(case_bible, suspect_one.name),
                [investigator, suspect_one.name],
                self._pick_ids(evidence_ids, evidence_by_person.get(suspect_one.name, [])[:2]),
                [f"{suspect_one.name} offers a version of events that demands verification."],
                timeline_ref[3],
            ),
            PlotStep(
                5,
                "investigation",
                "alibi_check",
                f"Testing {suspect_one.name}'s Alibi",
                f"The detective checks the timeline against {suspect_one.name}'s own statement: {suspect_one.alibi}",
                self._best_location_for_person(case_bible, suspect_one.name),
                [investigator, suspect_one.name],
                self._pick_ids(evidence_ids, evidence_by_person.get(suspect_one.name, [])[:2]),
                [f"{suspect_one.name}'s alibi is plausible in outline but strained in detail."],
                timeline_ref[4],
            ),
            PlotStep(
                6,
                "investigation",
                "interview",
                f"Questioning {suspect_two.name}",
                f"{investigator} interviews {suspect_two.name} and learns how private pressure around the victim fed a credible secondary theory of the crime.",
                self._best_location_for_person(case_bible, suspect_two.name),
                [investigator, suspect_two.name],
                self._pick_ids(evidence_ids, evidence_by_person.get(suspect_two.name, [])[:2]),
                [f"{suspect_two.name} had both motive and a vulnerable story about the evening."],
                timeline_ref[5],
            ),
            PlotStep(
                7,
                "investigation",
                "alibi_check",
                f"Testing {suspect_two.name}'s Alibi",
                f"The detective checks witnesses, room access, and timing against the claim that {suspect_two.name} {suspect_two.alibi.lower()}",
                self._best_location_for_person(case_bible, suspect_two.name),
                [investigator, suspect_two.name],
                self._pick_ids(evidence_ids, evidence_by_person.get(suspect_two.name, [])[:2]),
                [f"{suspect_two.name} cannot fully close the critical window around the murder."],
                timeline_ref[6],
            ),
            PlotStep(
                8,
                "investigation",
                "interview",
                f"Questioning {suspect_three.name}",
                f"The detective turns to {suspect_three.name}, whose private grievance and means change the emotional balance of the inquiry and force a new reading of the household tensions.",
                self._best_location_for_person(case_bible, suspect_three.name),
                [investigator, suspect_three.name],
                self._pick_ids(evidence_ids, evidence_by_person.get(suspect_three.name, [])[:2]),
                [f"{suspect_three.name} becomes a serious but incomplete theory of the case."],
                timeline_ref[7],
            ),
            PlotStep(
                9,
                "investigation",
                "interview",
                f"Questioning {suspect_four.name}",
                f"{investigator} interviews {suspect_four.name}, separating personal secrecy from the stronger evidence pointing elsewhere.",
                self._best_location_for_person(case_bible, suspect_four.name),
                [investigator, suspect_four.name],
                self._pick_ids(evidence_ids, evidence_by_person.get(suspect_four.name, [])[:2]),
                [f"{suspect_four.name} is suspicious, but the case against them remains indirect."],
                timeline_ref[8],
            ),
            PlotStep(
                10,
                "investigation",
                "red_herring",
                "The Strongest False Lead",
                self._red_herring_summary(red_herring_one, case_bible),
                self._red_herring_location(red_herring_one, case_bible),
                [investigator, self._red_herring_name(red_herring_one, suspect_two.name)],
                self._pick_ids(
                    evidence_ids,
                    red_herring_one.misleading_evidence_ids if red_herring_one is not None else evidence_by_person.get(suspect_two.name, [])[:1],
                ),
                [self._red_herring_reveal(red_herring_one)],
                timeline_ref[9],
            ),
            PlotStep(
                11,
                "investigation",
                "forensics",
                pivot_title,
                f"Close analysis of the scene and the victim's final movements points away from surface appearances and toward the true method: {case_bible.method}",
                death_event.location,
                [investigator],
                self._pick_ids(evidence_ids, culprit_chain[:3] or self._first_ids(evidence_ids, 3)),
                ["The method is now tied to the hidden truth rather than the most obvious suspicion."],
                timeline_ref[10],
            ),
            PlotStep(
                12,
                "midpoint",
                "interference",
                self._interference_title(concealment_event),
                self._interference_summary(misdirection_event, case_bible),
                misdirection_event.location if misdirection_event is not None else death_event.location,
                [investigator, case_bible.culprit.name],
                self._pick_ids(evidence_ids, culprit_chain[1:3] or culprit_chain[:1]),
                ["Someone involved in the crime also tried to distort how the truth would later be read."],
                timeline_ref[11],
            ),
            PlotStep(
                13,
                "reversal",
                "analysis",
                "False Theories Fall Away",
                self._false_theory_summary(red_herring_one, red_herring_two, case_bible),
                discovery_event.location,
                [investigator] + [suspect.name for suspect in suspects],
                self._pick_ids(
                    evidence_ids,
                    (red_herring_one.misleading_evidence_ids if red_herring_one is not None else [])
                    + (red_herring_two.misleading_evidence_ids if red_herring_two is not None else []),
                ),
                ["The detective separates side secrets and opportunistic misconduct from the murder itself."],
                timeline_ref[12],
            ),
            PlotStep(
                14,
                "reversal",
                "evidence",
                "The Evidence Chain Tightens",
                f"The detective lines up the decisive chain around {case_bible.culprit.name}, showing how separate clues reinforce one another.",
                death_event.location,
                [investigator, case_bible.culprit.name],
                self._pick_ids(evidence_ids, culprit_chain),
                [f"The case now coheres around {case_bible.culprit.name} rather than around generalized suspicion."],
                timeline_ref[13],
            ),
            PlotStep(
                15,
                "reversal",
                "analysis",
                "Means, Motive, and Opportunity",
                f"By reconstructing the timeline from {self._display_time(opening_event.time_marker)} to {self._display_time(discovery_event.time_marker)}, the detective shows that only {case_bible.culprit.name} fully satisfies means, motive, and opportunity.",
                discovery_event.location,
                [investigator, case_bible.culprit.name],
                self._pick_ids(evidence_ids, culprit_chain[:3] or self._first_ids(evidence_ids, 2)),
                [f"{case_bible.culprit.name}'s alibi collapses when set against the physical sequence of the night."],
                timeline_ref[14],
            ),
            PlotStep(
                16,
                "climax",
                "confrontation",
                confrontation_title,
                f"In front of the assembled suspects, {investigator} reconstructs the murder and ties the key evidence directly to {case_bible.culprit.name}.",
                discovery_event.location,
                [investigator] + [suspect.name for suspect in suspects],
                self._pick_ids(evidence_ids, culprit_chain[:4] or culprit_chain),
                [f"The confrontation turns the scattered clues into one coherent accusation against {case_bible.culprit.name}."],
                timeline_ref[15],
            ),
            PlotStep(
                17,
                "resolution",
                "confession",
                "The Hidden Truth Confirmed",
                f"Pressed with the completed chain of reasoning, {case_bible.culprit.name}'s guilt is confirmed, along with the true motive and method behind {case_bible.victim.name}'s death.",
                discovery_event.location,
                [investigator, case_bible.culprit.name],
                self._pick_ids(evidence_ids, culprit_chain),
                ["The case resolves into a fair-play explanation grounded in the evidence."],
                timeline_ref[16],
            ),
        ]

        return PlotPlan(investigator=investigator, steps=steps)

    def _plot_prompt(
        self,
        case_bible: CaseBible,
        fact_graph: list[FactTriple] | None,
        evidence_ids: list[str],
    ) -> str:
        suspects_block = "\n".join(
            f"- {suspect.name} | role={suspect.role} | relation={suspect.relationship_to_victim} | motive={suspect.motive} | opportunity={suspect.opportunity} | alibi={suspect.alibi}"
            for suspect in case_bible.suspects
        )
        timeline_block = "\n".join(
            f"- {event.time_marker} | {event.location} | participants={', '.join(event.participants)} | {event.summary}"
            for event in case_bible.true_timeline
        )
        evidence_block = "\n".join(
            f"- {item.evidence_id} | {item.name} | implicates={item.implicated_person} | found_at={item.location_found} | {item.description}"
            for item in case_bible.evidence_items
        )
        red_herring_block = "\n".join(
            f"- {item.suspect_name} | evidence={', '.join(item.misleading_evidence_ids)} | {item.explanation}"
            for item in case_bible.red_herrings
        )
        fact_block = ""
        if fact_graph:
            sample_facts = fact_graph[:20]
            fact_block = "Fact graph sample:\n" + "\n".join(
                f"- ({fact.subject}, {fact.relation}, {fact.object}, time={fact.time}, source={fact.source})"
                for fact in sample_facts
            ) + "\n\n"

        return (
            "Generate a structured investigation plot plan as valid JSON only. Do not use markdown fences.\n"
            f"The lead investigator is {case_bible.investigator}, who was already present at the estate before the murder because the victim invited them to witness or advise on a coming revelation.\n"
            "Return JSON with exactly this top-level shape:\n"
            '{\n  "steps": [\n'
            '    {"step_id": int, "phase": str, "kind": str, "title": str, "summary": str, "location": str, "participants": [str], "evidence_ids": [str], "reveals": [str], "timeline_ref": str}\n'
            "  ]\n}\n\n"
            "Hard constraints:\n"
            "- Produce 15 to 18 substantial steps.\n"
            "- Include at least 2 steps with kind='alibi_check'.\n"
            "- Include at least 1 step with kind='red_herring'.\n"
            "- Include at least 1 step with kind='interference'.\n"
            "- Include 1 final step with kind='confrontation' or a late climax confrontation before the last step.\n"
            "- Include a final resolution/confession step.\n"
            "- The culprit must not dominate the first half of the investigation too openly; allow at least one serious false theory.\n"
            "- The confrontation must cite key evidence from the culprit evidence chain.\n"
            "- Do not invent evidence IDs beyond this set: "
            f"{', '.join(evidence_ids)}.\n"
            "- Keep all names, motives, method, and timeline consistent with the case bible.\n"
            "- Make the plan readable and scene-like, not repetitive or mechanically formulaic.\n"
            "- Vary the sequence naturally: let the order of interviews, reversals, and evidence turns follow the case rather than a rigid template.\n"
            "- Timeline refs should be readable clock times like '11:15 PM' and should increase across steps.\n\n"
            f"Setting:\n{case_bible.setting}\n\n"
            f"Victim:\n- {case_bible.victim.name} | {case_bible.victim.description}\n\n"
            f"Culprit:\n- {case_bible.culprit.name}\n- motive: {case_bible.motive}\n- method: {case_bible.method}\n\n"
            f"Suspects:\n{suspects_block}\n\n"
            f"True timeline:\n{timeline_block}\n\n"
            f"Evidence:\n{evidence_block}\n\n"
            f"Red herrings:\n{red_herring_block}\n\n"
            f"Culprit evidence chain:\n- {', '.join(case_bible.culprit_evidence_chain)}\n\n"
            f"{fact_block}"
            "Write the plan so it feels like a plausible detective investigation with mounting suspense and clearer mid-course turns than a simple checklist."
        )

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
        data = json.loads(candidate)
        if not isinstance(data, dict):
            raise RuntimeError("Top-level plot payload must be an object.")
        return data

    def _build_step(self, data: dict[str, Any], fallback_step_id: int, evidence_ids: list[str]) -> PlotStep:
        participants = data.get("participants")
        if not isinstance(participants, list) or not all(isinstance(item, str) and item.strip() for item in participants):
            raise RuntimeError(f"Invalid participants in step: {data}")
        reveals = data.get("reveals")
        if not isinstance(reveals, list) or not all(isinstance(item, str) and item.strip() for item in reveals):
            raise RuntimeError(f"Invalid reveals in step: {data}")
        raw_evidence_ids = data.get("evidence_ids", [])
        if not isinstance(raw_evidence_ids, list) or not all(isinstance(item, str) and item.strip() for item in raw_evidence_ids):
            raise RuntimeError(f"Invalid evidence_ids in step: {data}")
        filtered_evidence_ids = [item.strip() for item in raw_evidence_ids if item.strip() in evidence_ids]
        step_id = data.get("step_id")
        if not isinstance(step_id, int):
            step_id = fallback_step_id
        timeline_ref = data.get("timeline_ref")
        if not isinstance(timeline_ref, str) or not timeline_ref.strip():
            timeline_ref = None
        return PlotStep(
            step_id=step_id,
            phase=self._require_string(data, "phase"),
            kind=self._require_string(data, "kind"),
            title=self._require_string(data, "title"),
            summary=self._require_string(data, "summary"),
            location=self._require_string(data, "location"),
            participants=[item.strip() for item in participants],
            evidence_ids=filtered_evidence_ids,
            reveals=[item.strip() for item in reveals],
            timeline_ref=timeline_ref.strip() if isinstance(timeline_ref, str) else None,
        )

    def _normalize_step_ids(self, steps: list[PlotStep]) -> None:
        steps.sort(key=lambda step: step.step_id)
        for index, step in enumerate(steps, start=1):
            step.step_id = index

    def _normalize_llm_step_times(self, case_bible: CaseBible, steps: list[PlotStep]) -> None:
        if not steps:
            return
        timed_events = self._sorted_events(case_bible.true_timeline)
        discovery_event = self._find_discovery_event(timed_events) if timed_events else None
        anchor_minutes = self._parse_time(discovery_event.time_marker) if discovery_event is not None else None
        if anchor_minutes is None:
            parseable = [self._parse_time(step.timeline_ref) for step in steps if self._parse_time(step.timeline_ref) is not None]
            anchor_minutes = parseable[0] if parseable else 23 * 60

        step_minutes = [self._parse_time(step.timeline_ref) for step in steps]
        if self._llm_times_need_repair(anchor_minutes, step_minutes):
            normalized_times = self._step_times(self._display_time_from_minutes(anchor_minutes), len(steps))
            for step, normalized_time in zip(steps, normalized_times):
                step.timeline_ref = normalized_time
            return

        normalized_minutes: list[int] = []
        day_offset = 0
        previous_raw: int | None = None
        minimum_allowed = anchor_minutes
        for raw_minutes in step_minutes:
            if raw_minutes is None:
                base_minutes = normalized_minutes[-1] + 10 if normalized_minutes else minimum_allowed
                normalized_minutes.append(max(base_minutes, minimum_allowed))
                continue
            if previous_raw is not None and raw_minutes < previous_raw:
                day_offset += 24 * 60
            candidate = raw_minutes + day_offset
            if candidate < minimum_allowed:
                candidate = minimum_allowed if not normalized_minutes else max(minimum_allowed, normalized_minutes[-1] + 10)
            elif normalized_minutes and candidate <= normalized_minutes[-1]:
                candidate = normalized_minutes[-1] + 10
            normalized_minutes.append(candidate)
            previous_raw = raw_minutes

        for step, minutes in zip(steps, normalized_minutes):
            step.timeline_ref = self._display_time_from_minutes(minutes)

    def _llm_times_need_repair(self, anchor_minutes: int, step_minutes: list[int | None]) -> bool:
        parseable = [minutes for minutes in step_minutes if minutes is not None]
        if not parseable:
            return True
        if any(minutes < anchor_minutes - 60 for minutes in parseable):
            return True
        if any(abs(current - previous) > 180 for previous, current in zip(parseable, parseable[1:])):
            return True
        if parseable[0] < anchor_minutes:
            return True
        return False

    def _require_string(self, data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"Expected non-empty string for {key!r}, got: {value!r}")
        return value.strip()

    def _available_evidence_ids(self, case_bible: CaseBible, fact_graph: list[FactTriple] | None) -> set[str]:
        case_ids = {item.evidence_id for item in case_bible.evidence_items}
        if fact_graph is None:
            return case_ids
        graph_ids = {
            fact.subject
            for fact in fact_graph
            if fact.relation == "is_evidence" and fact.subject in case_ids
        }
        return graph_ids or case_ids

    def _evidence_by_person(self, case_bible: CaseBible) -> dict[str, list[str]]:
        mapping: dict[str, list[str]] = {}
        for item in case_bible.evidence_items:
            mapping.setdefault(item.implicated_person, []).append(item.evidence_id)
        return mapping

    def _sorted_events(self, events: list[TimelineEvent]) -> list[_TimedTimelineEvent]:
        timed: list[_TimedTimelineEvent] = []
        for event in events:
            minutes = self._parse_time(event.time_marker)
            if minutes is None:
                continue
            timed.append(_TimedTimelineEvent(event=event, minutes=minutes))
        timed.sort(key=lambda item: item.minutes)
        return timed

    def _find_discovery_event(self, timed_events: list[_TimedTimelineEvent]) -> TimelineEvent | None:
        for item in timed_events:
            summary = item.event.summary.lower()
            if any(word in summary for word in {"discover", "discovers", "discovered", "finds", "found", "body"}):
                return item.event
        return timed_events[-1].event if timed_events else None

    def _find_death_event(self, timed_events: list[_TimedTimelineEvent], victim_name: str) -> TimelineEvent | None:
        for item in timed_events:
            summary = item.event.summary.lower()
            has_victim = any(self._names_match(victim_name, participant) for participant in item.event.participants)
            if not has_victim:
                continue
            if any(word in summary for word in {"dies", "died", "killed", "murdered", "poisoned", "collapses", "dead"}):
                if not any(word in summary for word in {"discover", "discovers", "discovered", "finds", "found"}):
                    return item.event
        return None

    def _find_concealment_event(
        self,
        timed_events: list[_TimedTimelineEvent],
        culprit_name: str,
    ) -> TimelineEvent | None:
        for item in timed_events:
            summary = item.event.summary.lower()
            has_culprit = any(self._names_match(culprit_name, participant) for participant in item.event.participants)
            if not has_culprit:
                continue
            if any(word in summary for word in {"wipe", "wipes", "swap", "swaps", "dispose", "disposes", "hide", "hides", "burn", "burns", "steal", "steals"}):
                return item.event
        return None

    def _find_pre_murder_tension_event(
        self,
        timed_events: list[_TimedTimelineEvent],
        victim_name: str,
    ) -> TimelineEvent | None:
        for item in timed_events:
            if not any(self._names_match(victim_name, participant) for participant in item.event.participants):
                continue
            summary = item.event.summary.lower()
            if any(word in summary for word in {"argument", "berates", "threatens", "accuses", "demands", "quarrel", "discrepancy"}):
                return item.event
        return timed_events[0].event if timed_events else None

    def _find_misdirection_event(self, timed_events: list[_TimedTimelineEvent]) -> TimelineEvent | None:
        for item in timed_events:
            summary = item.event.summary.lower()
            if any(word in summary for word in {"distraction", "crash", "outage", "false", "staged", "noise"}):
                return item.event
        return None

    def _ordered_suspects(
        self,
        case_bible: CaseBible,
        evidence_by_person: dict[str, list[str]],
    ) -> list:
        red_herring_names = {item.suspect_name for item in case_bible.red_herrings}
        culprit_name = case_bible.culprit.name

        def sort_key(suspect) -> tuple[int, int, int, str]:
            is_culprit = 1 if suspect.name == culprit_name else 0
            is_red_herring = 0 if suspect.name in red_herring_names else 1
            evidence_rank = -len(evidence_by_person.get(suspect.name, []))
            return (is_culprit, is_red_herring, evidence_rank, suspect.name)

        return sorted(case_bible.suspects, key=sort_key)

    def _investigator_setup(self, investigator: str, victim_name: str, location: str) -> str:
        return (
            f"{investigator} had already been invited to the manor by {victim_name}, "
            f"who meant to stage a private revelation before select witnesses in the {location.lower()}."
        )

    def _pivot_title(self, method: str) -> str:
        method_lower = method.lower()
        if "poison" in method_lower or "cyanide" in method_lower or "arsenic" in method_lower or "digitalis" in method_lower:
            return "The Poison Theory Hardens"
        if "knife" in method_lower or "dagger" in method_lower or "stab" in method_lower:
            return "The Weapon Is Reinterpreted"
        return "The True Method Emerges"

    def _confrontation_title(self, herring, culprit_name: str) -> str:
        if herring is None:
            return "The Final Confrontation"
        return f"From {herring.suspect_name} to {culprit_name}"

    def _best_location_for_person(self, case_bible: CaseBible, name: str) -> str:
        for event in case_bible.true_timeline:
            if any(self._names_match(name, participant) for participant in event.participants):
                return event.location
        return "Drawing Room"

    def _pick_ids(self, available_ids: set[str], candidate_ids: list[str]) -> list[str]:
        picked = [item for item in candidate_ids if item in available_ids]
        seen: set[str] = set()
        ordered: list[str] = []
        for item in picked:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered

    def _first_ids(self, available_ids: set[str], count: int) -> list[str]:
        return sorted(available_ids)[:count]

    def _red_herring_summary(self, herring, case_bible: CaseBible) -> str:
        if herring is None:
            return "The detective follows the most persuasive false lead long enough to see why it cannot explain the full crime."
        return (
            f"The investigation turns toward {herring.suspect_name} when a persuasive clue suggests a direct path to murder, "
            f"but the detective keeps testing that theory against the rest of the case."
        )

    def _red_herring_reveal(self, herring) -> str:
        if herring is None:
            return "A plausible theory emerges, but it does not explain the whole sequence."
        return herring.explanation

    def _red_herring_name(self, herring, fallback_name: str) -> str:
        if herring is None:
            return fallback_name
        return herring.suspect_name

    def _red_herring_location(self, herring, case_bible: CaseBible) -> str:
        if herring is None:
            return "Drawing Room"
        return self._best_location_for_person(case_bible, herring.suspect_name)

    def _interference_title(self, event: TimelineEvent | None) -> str:
        if event is None:
            return "Evidence of Deliberate Interference"
        return "A Concealment Attempt Comes to Light"

    def _interference_summary(self, event: TimelineEvent | None, case_bible: CaseBible) -> str:
        if event is None:
            return (
                f"The detective finds signs that someone tried to obscure the truth after the killing, "
                f"strengthening the case against {case_bible.culprit.name}."
            )
        return (
            f"By revisiting the timeline, the detective recognizes that {event.summary.lower()} "
            "This is treated as active interference rather than an innocent detail."
        )

    def _false_theory_summary(self, herring_one, herring_two, case_bible: CaseBible) -> str:
        if herring_one and herring_two:
            return (
                f"The detective explains why the apparent cases against {herring_one.suspect_name} and {herring_two.suspect_name} "
                f"cannot account for the full sequence of motive, method, and timing that points to {case_bible.culprit.name}."
            )
        if herring_one:
            return (
                f"The detective demonstrates why the theory centered on {herring_one.suspect_name} is attractive but incomplete, "
                f"clearing the way for the stronger case against {case_bible.culprit.name}."
            )
        return (
            f"Competing suspicions are dismantled one by one until the evidence points cleanly toward {case_bible.culprit.name}."
        )

    def _step_times(self, start_time: str, count: int) -> list[str]:
        start_minutes = self._parse_time(start_time)
        if start_minutes is None:
            start_minutes = 23 * 60
        return [self._display_time_from_minutes(start_minutes + index * 10) for index in range(count)]

    def _display_time(self, value: str) -> str:
        minutes = self._parse_time(value)
        if minutes is None:
            return value
        return self._display_time_from_minutes(minutes)

    def _display_time_from_minutes(self, minutes: int) -> str:
        normalized = minutes % (24 * 60)
        hour = normalized // 60
        minute = normalized % 60
        meridiem = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        return f"{display_hour}:{minute:02d} {meridiem}"

    def _parse_time(self, value: str | None) -> int | None:
        if value is None:
            return None
        value = value.strip()
        if " " in value:
            time_part, meridiem = value.split()
            hour_str, minute_str = time_part.split(":")
            hour = int(hour_str)
            minute = int(minute_str)
            meridiem = meridiem.upper()
            if meridiem == "AM" and hour == 12:
                hour = 0
            elif meridiem == "PM" and hour != 12:
                hour += 12
            return hour * 60 + minute
        hour_str, minute_str = value.split(":")
        return int(hour_str) * 60 + int(minute_str)

    def _names_match(self, left: str, right: str) -> bool:
        left_tokens = self._normalize_name(left)
        right_tokens = self._normalize_name(right)
        if not left_tokens or not right_tokens:
            return False
        return left_tokens == right_tokens or left_tokens.issubset(right_tokens) or right_tokens.issubset(left_tokens)

    def _normalize_name(self, value: str) -> set[str]:
        tokens = {
            token
            for token in "".join(character.lower() if character.isalpha() else " " for character in value).split()
            if token not in {"lord", "lady", "sir", "dr", "doctor", "mr", "mrs", "ms", "miss", "major", "all", "none"}
        }
        return tokens
