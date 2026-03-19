from __future__ import annotations

import re
from dataclasses import dataclass

from models import CaseBible, FactTriple


@dataclass
class _TimedEvent:
    event_id: str
    time_marker: str
    minutes: int
    summary: str
    participants: list[str]
    location: str


class FactGraphBuilder:
    def build(self, case_bible: CaseBible) -> list[FactTriple]:
        timed_events = self._sorted_events(case_bible)
        victim_time = self._infer_victim_time(case_bible, timed_events)
        method_time = self._infer_method_time(case_bible, timed_events, victim_time)
        facts: list[FactTriple] = [
            FactTriple("case", "set_in", case_bible.setting, None, "case_bible"),
            FactTriple(case_bible.victim.name, "is_victim", "true", victim_time, "case_bible"),
            FactTriple(case_bible.culprit.name, "is_culprit", "true", method_time or victim_time, "case_bible"),
            FactTriple(case_bible.culprit.name, "has_motive", case_bible.motive, None, "case_bible"),
            FactTriple(case_bible.culprit.name, "used_method", case_bible.method, method_time or victim_time, "case_bible"),
        ]

        for suspect in case_bible.suspects:
            suspect_time = self._infer_character_time_window(timed_events, suspect.name, victim_time)
            facts.extend(
                [
                    FactTriple(suspect.name, "role", suspect.role, None, "case_bible"),
                    FactTriple(suspect.name, "relationship_to_victim", suspect.relationship_to_victim, None, "case_bible"),
                    FactTriple(suspect.name, "means", suspect.means, None, "case_bible"),
                    FactTriple(suspect.name, "motive", suspect.motive, None, "case_bible"),
                    FactTriple(suspect.name, "opportunity", suspect.opportunity, suspect_time, "case_bible"),
                    FactTriple(suspect.name, "alibi", suspect.alibi, suspect_time, "case_bible"),
                ]
            )

        for event in timed_events:
            facts.append(
                FactTriple(
                    subject=event.event_id,
                    relation="timeline_event",
                    object=event.summary,
                    time=event.time_marker,
                    source="timeline",
                )
            )
            for participant in event.participants:
                facts.append(
                    FactTriple(
                        subject=participant,
                        relation="present_at",
                        object=event.location,
                        time=event.time_marker,
                        source="timeline",
                    )
                )

        for evidence in case_bible.evidence_items:
            facts.extend(
                [
                    FactTriple(evidence.evidence_id, "is_evidence", evidence.name, None, "evidence"),
                    FactTriple(evidence.evidence_id, "found_at", evidence.location_found, None, "evidence"),
                    FactTriple(evidence.evidence_id, "implicates", evidence.implicated_person, None, "evidence"),
                    FactTriple(evidence.evidence_id, "description", evidence.description, None, "evidence"),
                ]
            )

        for herring in case_bible.red_herrings:
            facts.append(
                FactTriple(
                    herring.suspect_name,
                    "red_herring_explained_by",
                    herring.explanation,
                    None,
                    "red_herring",
                )
            )
        return facts

    def _sorted_events(self, case_bible: CaseBible) -> list[_TimedEvent]:
        timed_events: list[_TimedEvent] = []
        for event in case_bible.true_timeline:
            minutes = self._parse_time(event.time_marker)
            if minutes is None:
                continue
            timed_events.append(
                _TimedEvent(
                    event_id=event.event_id,
                    time_marker=event.time_marker,
                    minutes=minutes,
                    summary=event.summary,
                    participants=event.participants,
                    location=event.location,
                )
            )
        timed_events.sort(key=lambda item: item.minutes)
        return timed_events

    def _infer_victim_time(self, case_bible: CaseBible, timed_events: list[_TimedEvent]) -> str | None:
        death_events = [
            event
            for event in timed_events
            if self._is_victim_death_event(event, case_bible.victim.name)
        ]
        if death_events:
            return death_events[0].time_marker
        return self._last_time_for_participant(timed_events, case_bible.victim.name)

    def _infer_method_time(
        self,
        case_bible: CaseBible,
        timed_events: list[_TimedEvent],
        victim_time: str | None,
    ) -> str | None:
        victim_minutes = self._parse_time(victim_time)
        method_events = [
            event
            for event in timed_events
            if self._is_method_execution_event(event, case_bible)
        ]
        if victim_minutes is not None:
            method_events = [event for event in method_events if event.minutes <= victim_minutes]
        if method_events:
            return method_events[-1].time_marker
        if victim_time is not None:
            return victim_time
        return self._last_time_for_participant(timed_events, case_bible.culprit.name)

    def _infer_character_time_window(
        self,
        timed_events: list[_TimedEvent],
        name: str,
        victim_time: str | None,
    ) -> str | None:
        relevant_events = [
            event
            for event in timed_events
            if any(self._names_match(name, participant) for participant in event.participants)
        ]
        if not relevant_events:
            return None
        victim_minutes = self._parse_time(victim_time)
        if victim_minutes is not None:
            focused_events = [
                event
                for event in relevant_events
                if victim_minutes - 90 <= event.minutes <= victim_minutes + 15
            ]
            if focused_events:
                relevant_events = focused_events
        if len(relevant_events) == 1:
            return relevant_events[0].time_marker
        return f"{relevant_events[0].time_marker} to {relevant_events[-1].time_marker}"

    def _last_time_for_participant(self, timed_events: list[_TimedEvent], name: str) -> str | None:
        matches = [
            event.time_marker
            for event in timed_events
            if any(self._names_match(name, participant) for participant in event.participants)
        ]
        if not matches:
            return None
        return matches[-1]

    def _is_victim_death_event(self, event: _TimedEvent, victim_name: str) -> bool:
        summary = event.summary.lower()
        mentions_victim = any(self._names_match(victim_name, participant) for participant in event.participants)
        mentions_victim = mentions_victim or self._summary_mentions_name(summary, victim_name)
        if not mentions_victim:
            return False
        direct_death_markers = {
            "collapses",
            "collapsed",
            "dies",
            "died",
            "succumbs",
            "gasping for air",
            "gasping",
            "stops breathing",
            "is dead",
        }
        discovery_markers = {"discovers", "discovered", "finds", "found", "body", "corpse"}
        threat_markers = {"threatens", "threatened", "threat", "see him dead", "wants him dead"}
        if any(marker in summary for marker in discovery_markers | threat_markers):
            return False
        return any(marker in summary for marker in direct_death_markers)

    def _is_method_execution_event(self, event: _TimedEvent, case_bible: CaseBible) -> bool:
        summary = event.summary.lower()
        if not any(self._names_match(case_bible.culprit.name, participant) for participant in event.participants):
            return False
        action_markers = {
            "adds",
            "added",
            "poison",
            "poisoned",
            "spike",
            "spiked",
            "spikes",
            "serve",
            "deliver",
            "delivers",
            "delivered",
            "administer",
            "administers",
            "administered",
            "slip",
            "slips",
            "slipped",
            "dissolve",
            "dissolved",
            "mix",
            "mixed",
            "hide",
            "hides",
            "stole",
            "steals",
        }
        method_tokens = {
            token
            for token in re.findall(r"[a-z]+", case_bible.method.lower())
            if token not in {"with", "via", "the", "and", "a", "an", "of", "to", "by", "followed", "post", "mortem", "during", "alone", "specific", "vintage"}
        }
        concrete_method_tokens = {
            token
            for token in method_tokens
            if token in {"cyanide", "digitalis", "arsenic", "poisoning", "poison", "brandy", "snifter", "decanter", "toxin"}
        }
        if any(marker in summary for marker in {"threatens", "threatened", "argument", "argues", "shouting match"}):
            return False
        return any(marker in summary for marker in action_markers) or any(token in summary for token in concrete_method_tokens)

    def _summary_mentions_name(self, summary: str, name: str) -> bool:
        summary_tokens = set(re.findall(r"[a-z]+", summary.lower()))
        name_tokens = self._normalize_name(name)
        return bool(name_tokens) and name_tokens.issubset(summary_tokens)

    def _parse_time(self, value: str | None) -> int | None:
        if not value:
            return None
        value = value.strip()
        am_pm_match = re.fullmatch(r"(\d{1,2}):(\d{2})\s*([AP]M)", value, re.IGNORECASE)
        if am_pm_match:
            hour = int(am_pm_match.group(1))
            minute = int(am_pm_match.group(2))
            meridiem = am_pm_match.group(3).upper()
            if meridiem == "AM" and hour == 12:
                hour = 0
            elif meridiem == "PM" and hour != 12:
                hour += 12
            return hour * 60 + minute
        twenty_four_match = re.fullmatch(r"(\d{1,2}):(\d{2})", value)
        if twenty_four_match:
            hour = int(twenty_four_match.group(1))
            minute = int(twenty_four_match.group(2))
            return hour * 60 + minute
        return None

    def _names_match(self, left: str, right: str) -> bool:
        left_tokens = self._normalize_name(left)
        right_tokens = self._normalize_name(right)
        if not left_tokens or not right_tokens:
            return False
        return left_tokens == right_tokens or left_tokens.issubset(right_tokens) or right_tokens.issubset(left_tokens)

    def _normalize_name(self, value: str) -> set[str]:
        honorifics = {"lord", "lady", "dr", "doctor", "mr", "mrs", "ms", "miss", "sir"}
        tokens = re.findall(r"[a-z]+", value.lower())
        return {token for token in tokens if token not in honorifics}
