from __future__ import annotations

from models import CaseBible, FactTriple


class FactGraphBuilder:
    def build(self, case_bible: CaseBible) -> list[FactTriple]:
        facts: list[FactTriple] = [
            FactTriple("case", "set_in", case_bible.setting, None, "case_bible", 1.0),
            FactTriple(case_bible.victim.name, "is_victim", "true", "9:12 PM", "case_bible", 1.0),
            FactTriple(case_bible.culprit.name, "is_culprit", "true", "9:12 PM", "case_bible", 1.0),
            FactTriple(case_bible.culprit.name, "has_motive", case_bible.motive, None, "case_bible", 0.99),
            FactTriple(case_bible.culprit.name, "used_method", case_bible.method, "9:12 PM", "case_bible", 0.99),
        ]

        for suspect in case_bible.suspects:
            facts.extend(
                [
                    FactTriple(suspect.name, "role", suspect.role, None, "case_bible", 1.0),
                    FactTriple(suspect.name, "relationship_to_victim", suspect.relationship_to_victim, None, "case_bible", 0.95),
                    FactTriple(suspect.name, "means", suspect.means, None, "case_bible", 0.93),
                    FactTriple(suspect.name, "motive", suspect.motive, None, "case_bible", 0.9),
                    FactTriple(suspect.name, "opportunity", suspect.opportunity, "9:00 PM-9:15 PM", "case_bible", 0.9),
                    FactTriple(suspect.name, "alibi", suspect.alibi, "9:00 PM-9:15 PM", "case_bible", 0.88),
                ]
            )

        for event in case_bible.true_timeline:
            facts.append(
                FactTriple(
                    subject=event.event_id,
                    relation="timeline_event",
                    object=event.summary,
                    time=event.time_marker,
                    source="timeline",
                    confidence=0.97,
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
                        confidence=0.85,
                    )
                )

        for evidence in case_bible.evidence_items:
            facts.extend(
                [
                    FactTriple(evidence.evidence_id, "is_evidence", evidence.name, None, "evidence", 1.0),
                    FactTriple(evidence.evidence_id, "found_at", evidence.location_found, None, "evidence", evidence.reliability),
                    FactTriple(evidence.evidence_id, "implicates", evidence.implicated_person, None, "evidence", evidence.reliability),
                    FactTriple(evidence.evidence_id, "description", evidence.description, None, "evidence", evidence.reliability),
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
                    0.82,
                )
            )
        return facts
