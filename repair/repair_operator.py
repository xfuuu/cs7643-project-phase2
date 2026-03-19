from __future__ import annotations

from models import CaseBible, PlotPlan, PlotStep, ValidationReport


class PlotPlanRepairOperator:
    def repair(self, case_bible: CaseBible, plot_plan: PlotPlan, report: ValidationReport) -> PlotPlan:
        repaired_steps = self._clone_steps(plot_plan.steps)
        issue_codes = {issue.code for issue in report.issues}
        valid_evidence_ids = {item.evidence_id for item in case_bible.evidence_items}

        self._clean_unknown_evidence(repaired_steps, valid_evidence_ids)

        if "alibi_steps" in issue_codes:
            self._add_missing_alibi_steps(case_bible, plot_plan, repaired_steps)

        if "red_herring_arc" in issue_codes:
            self._add_red_herring_step(case_bible, plot_plan, repaired_steps)

        if "interference" in issue_codes:
            self._add_interference_step(case_bible, plot_plan, repaired_steps)

        if "evidence_chain" in issue_codes:
            self._add_evidence_chain_step(case_bible, plot_plan, repaired_steps)

        if "culprit_support" in issue_codes:
            self._add_culprit_support_step(case_bible, plot_plan, repaired_steps)

        if "confrontation" in issue_codes or "confrontation_evidence" in issue_codes:
            self._ensure_confrontation(case_bible, plot_plan, repaired_steps)

        if "min_plot_steps" in issue_codes:
            self._extend_to_minimum_steps(case_bible, plot_plan, repaired_steps)

        self._normalize_step_ids(repaired_steps)
        if "step_order" in issue_codes or "timeline" in issue_codes or any(step.timeline_ref is None for step in repaired_steps):
            self._normalize_times(repaired_steps)

        return PlotPlan(investigator=plot_plan.investigator, steps=repaired_steps)

    def _clone_steps(self, steps: list[PlotStep]) -> list[PlotStep]:
        return [
            PlotStep(
                step_id=step.step_id,
                phase=step.phase,
                kind=step.kind,
                title=step.title,
                summary=step.summary,
                location=step.location,
                participants=list(step.participants),
                evidence_ids=list(step.evidence_ids),
                reveals=list(step.reveals),
                timeline_ref=step.timeline_ref,
            )
            for step in steps
        ]

    def _clean_unknown_evidence(self, steps: list[PlotStep], valid_evidence_ids: set[str]) -> None:
        for step in steps:
            step.evidence_ids = [evidence_id for evidence_id in step.evidence_ids if evidence_id in valid_evidence_ids]

    def _add_missing_alibi_steps(
        self,
        case_bible: CaseBible,
        plot_plan: PlotPlan,
        steps: list[PlotStep],
    ) -> None:
        existing_names = {
            participant
            for step in steps
            if step.kind == "alibi_check"
            for participant in step.participants
        }
        needed = max(0, 2 - sum(1 for step in steps if step.kind == "alibi_check"))
        for suspect in case_bible.suspects:
            if needed == 0:
                break
            if suspect.name in existing_names:
                continue
            steps.append(
                self._new_step(
                    steps,
                    phase="investigation",
                    kind="alibi_check",
                    title=f"Testing {suspect.name}'s Alibi",
                    summary=f"{plot_plan.investigator} cross-checks {suspect.name}'s stated movements against the known timeline: {suspect.alibi}",
                    location=self._best_location_for_name(case_bible, suspect.name),
                    participants=[plot_plan.investigator, suspect.name],
                    evidence_ids=self._evidence_for_name(case_bible, suspect.name, limit=2),
                    reveals=[f"{suspect.name}'s alibi is measured against the available witness and timing evidence."],
                )
            )
            needed -= 1

    def _add_red_herring_step(
        self,
        case_bible: CaseBible,
        plot_plan: PlotPlan,
        steps: list[PlotStep],
    ) -> None:
        if not case_bible.red_herrings:
            return
        used_names = {
            participant
            for step in steps
            if step.kind == "red_herring"
            for participant in step.participants
        }
        chosen = next((item for item in case_bible.red_herrings if item.suspect_name not in used_names), case_bible.red_herrings[0])
        steps.append(
            self._new_step(
                steps,
                phase="investigation",
                kind="red_herring",
                title=f"The Case Against {chosen.suspect_name}",
                summary=f"{plot_plan.investigator} follows a persuasive false line of suspicion centered on {chosen.suspect_name}.",
                location=self._best_location_for_name(case_bible, chosen.suspect_name),
                participants=[plot_plan.investigator, chosen.suspect_name],
                evidence_ids=list(chosen.misleading_evidence_ids),
                reveals=[chosen.explanation],
            )
        )

    def _add_interference_step(
        self,
        case_bible: CaseBible,
        plot_plan: PlotPlan,
        steps: list[PlotStep],
    ) -> None:
        chain_ids = case_bible.culprit_evidence_chain[:2]
        steps.append(
            self._new_step(
                steps,
                phase="midpoint",
                kind="interference",
                title="Evidence of Interference",
                summary=(
                    f"As pressure mounts, {plot_plan.investigator} finds signs that someone tried to distort the case after the murder, "
                    f"consistent with {case_bible.culprit.name}'s opportunity and method."
                ),
                location=self._best_location_for_name(case_bible, case_bible.culprit.name),
                participants=[plot_plan.investigator, case_bible.culprit.name],
                evidence_ids=chain_ids,
                reveals=["The investigation is being actively or retrospectively obstructed by someone tied to the true sequence of events."],
            )
        )

    def _add_evidence_chain_step(
        self,
        case_bible: CaseBible,
        plot_plan: PlotPlan,
        steps: list[PlotStep],
    ) -> None:
        referenced = {evidence_id for step in steps for evidence_id in step.evidence_ids}
        missing_chain = [evidence_id for evidence_id in case_bible.culprit_evidence_chain if evidence_id not in referenced]
        if not missing_chain:
            return
        names = self._evidence_names(case_bible, missing_chain)
        steps.append(
            self._new_step(
                steps,
                phase="reversal",
                kind="evidence",
                title="The Missing Links",
                summary=f"{plot_plan.investigator} brings the missing evidence into the investigation, tightening the chain around {case_bible.culprit.name}: {names}.",
                location=self._best_location_for_name(case_bible, case_bible.culprit.name),
                participants=[plot_plan.investigator, case_bible.culprit.name],
                evidence_ids=missing_chain,
                reveals=["The crucial evidence chain is now explicitly represented in the plan."],
            )
        )

    def _add_culprit_support_step(
        self,
        case_bible: CaseBible,
        plot_plan: PlotPlan,
        steps: list[PlotStep],
    ) -> None:
        steps.append(
            self._new_step(
                steps,
                phase="reversal",
                kind="analysis",
                title=f"The Case Narrows to {case_bible.culprit.name}",
                summary=(
                    f"{plot_plan.investigator} compares motive, means, and opportunity across the household and shows why "
                    f"{case_bible.culprit.name} fits the strongest emerging theory."
                ),
                location=self._best_location_for_name(case_bible, case_bible.culprit.name),
                participants=[plot_plan.investigator, case_bible.culprit.name],
                evidence_ids=case_bible.culprit_evidence_chain[:3],
                reveals=[f"{case_bible.culprit.name} is now directly supported by the developing evidence pattern."],
            )
        )

    def _ensure_confrontation(
        self,
        case_bible: CaseBible,
        plot_plan: PlotPlan,
        steps: list[PlotStep],
    ) -> None:
        key_evidence = case_bible.culprit_evidence_chain[:4]
        confrontation = next((step for step in steps if step.kind == "confrontation"), None)
        if confrontation is None:
            steps.append(
                self._new_step(
                    steps,
                    phase="climax",
                    kind="confrontation",
                    title=f"The Accusation of {case_bible.culprit.name}",
                    summary=f"{plot_plan.investigator} gathers the suspects and lays out the decisive case against {case_bible.culprit.name}.",
                    location=self._best_location_for_name(case_bible, case_bible.victim.name),
                    participants=[plot_plan.investigator] + [suspect.name for suspect in case_bible.suspects],
                    evidence_ids=key_evidence,
                    reveals=[f"The confrontation finally binds the key evidence chain to {case_bible.culprit.name}."],
                )
            )
            return
        existing = set(confrontation.evidence_ids)
        confrontation.evidence_ids = list(dict.fromkeys(confrontation.evidence_ids + [item for item in key_evidence if item not in existing]))
        if case_bible.culprit.name not in confrontation.summary:
            confrontation.summary += f" The accusation ultimately centers on {case_bible.culprit.name}."
        if not any(case_bible.culprit.name in reveal for reveal in confrontation.reveals):
            confrontation.reveals.append(f"The assembled clues now point squarely to {case_bible.culprit.name}.")

    def _extend_to_minimum_steps(
        self,
        case_bible: CaseBible,
        plot_plan: PlotPlan,
        steps: list[PlotStep],
    ) -> None:
        while len(steps) < 15:
            offset = len(steps) % max(1, len(case_bible.evidence_items))
            evidence = case_bible.evidence_items[offset]
            steps.append(
                self._new_step(
                    steps,
                    phase="investigation",
                    kind="evidence",
                    title=f"Reassessing {evidence.name}",
                    summary=f"{plot_plan.investigator} revisits {evidence.name} to clarify how it fits within the broader pattern of suspicion.",
                    location=evidence.location_found,
                    participants=[plot_plan.investigator, evidence.implicated_person],
                    evidence_ids=[evidence.evidence_id],
                    reveals=[f"{evidence.name} is integrated more clearly into the investigation."],
                )
            )

    def _new_step(
        self,
        steps: list[PlotStep],
        *,
        phase: str,
        kind: str,
        title: str,
        summary: str,
        location: str,
        participants: list[str],
        evidence_ids: list[str],
        reveals: list[str],
    ) -> PlotStep:
        return PlotStep(
            step_id=len(steps) + 1,
            phase=phase,
            kind=kind,
            title=title,
            summary=summary,
            location=location,
            participants=participants,
            evidence_ids=evidence_ids,
            reveals=reveals,
            timeline_ref=None,
        )

    def _best_location_for_name(self, case_bible: CaseBible, name: str) -> str:
        for event in case_bible.true_timeline:
            if name in event.participants:
                return event.location
        if name == case_bible.victim.name:
            return case_bible.evidence_items[0].location_found if case_bible.evidence_items else "Drawing Room"
        return "Drawing Room"

    def _evidence_for_name(self, case_bible: CaseBible, name: str, limit: int) -> list[str]:
        ids = [item.evidence_id for item in case_bible.evidence_items if item.implicated_person == name]
        return ids[:limit]

    def _evidence_names(self, case_bible: CaseBible, evidence_ids: list[str]) -> str:
        mapping = {item.evidence_id: item.name for item in case_bible.evidence_items}
        return ", ".join(mapping[evidence_id] for evidence_id in evidence_ids if evidence_id in mapping)

    def _normalize_step_ids(self, steps: list[PlotStep]) -> None:
        steps.sort(key=lambda step: step.step_id)
        for index, step in enumerate(steps, start=1):
            step.step_id = index

    def _normalize_times(self, steps: list[PlotStep]) -> None:
        start_minutes = self._first_parseable_time(steps)
        if start_minutes is None:
            start_minutes = 22 * 60
        for index, step in enumerate(steps):
            step.timeline_ref = self._display_time(start_minutes + index * 10)

    def _first_parseable_time(self, steps: list[PlotStep]) -> int | None:
        for step in steps:
            minutes = self._parse_time(step.timeline_ref)
            if minutes is not None:
                return minutes
        return None

    def _parse_time(self, value: str | None) -> int | None:
        if value is None:
            return None
        value = value.strip()
        if " " not in value:
            return None
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

    def _display_time(self, minutes: int) -> str:
        normalized = minutes % (24 * 60)
        hour = normalized // 60
        minute = normalized % 60
        meridiem = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        return f"{display_hour}:{minute:02d} {meridiem}"
