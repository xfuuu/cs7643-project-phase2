from __future__ import annotations

from models import CaseBible, PlotPlan, ValidationIssue, ValidationReport


class PlotPlanValidator:
    def validate(self, case_bible: CaseBible, plot_plan: PlotPlan) -> ValidationReport:
        issues: list[ValidationIssue] = []
        steps = plot_plan.steps

        suspect_names = [suspect.name for suspect in case_bible.suspects]
        evidence_ids = {item.evidence_id for item in case_bible.evidence_items}
        referenced_evidence = {evidence_id for step in steps for evidence_id in step.evidence_ids}
        alibi_steps = [step for step in steps if step.kind == "alibi_check"]
        interference_steps = [step for step in steps if step.kind == "interference"]
        red_herring_steps = [step for step in steps if step.kind == "red_herring"]
        confrontation_steps = [step for step in steps if step.kind == "confrontation"]

        if len(case_bible.suspects) < 4:
            issues.append(ValidationIssue("min_suspects", "Case bible must include at least four suspects."))
        if len(case_bible.evidence_items) < 8:
            issues.append(ValidationIssue("min_evidence", "Case bible must include at least eight evidence items."))
        if len(steps) < 15:
            issues.append(ValidationIssue("min_plot_steps", "Plot plan must contain at least fifteen substantial steps."))
        if len(alibi_steps) < 2:
            issues.append(ValidationIssue("alibi_steps", "Plot plan must include at least two explicit alibi verification steps."))
        if not red_herring_steps:
            issues.append(ValidationIssue("red_herring_arc", "Plot plan must include a red herring arc."))
        if not interference_steps:
            issues.append(ValidationIssue("interference", "Plot plan must include at least one suspect interference event."))
        if not set(case_bible.culprit_evidence_chain).issubset(referenced_evidence):
            issues.append(ValidationIssue("evidence_chain", "The culprit evidence chain is not fully represented in the plot plan."))
        if not confrontation_steps:
            issues.append(ValidationIssue("confrontation", "Plot plan must include a final confrontation."))

        if confrontation_steps:
            confrontation_evidence = set(confrontation_steps[-1].evidence_ids)
            required = set(case_bible.culprit_evidence_chain[:3])
            if not required.issubset(confrontation_evidence):
                issues.append(
                    ValidationIssue(
                        "confrontation_evidence",
                        "The final confrontation must reference key evidence from the culprit chain.",
                        confrontation_steps[-1].step_id,
                    )
                )

        culprit_name = case_bible.culprit.name
        culprit_steps = [
            step
            for step in steps
            if culprit_name in step.participants or culprit_name in " ".join(step.reveals + [step.summary])
        ]
        if len(culprit_steps) < 3:
            issues.append(ValidationIssue("culprit_support", "The culprit is not sufficiently supported across the investigation."))

        if sorted(step.step_id for step in steps) != list(range(1, len(steps) + 1)):
            issues.append(ValidationIssue("step_order", "Plot steps must use contiguous step ids starting at 1."))

        for step in steps:
            for evidence_id in step.evidence_ids:
                if evidence_id not in evidence_ids:
                    issues.append(
                        ValidationIssue(
                            "unknown_evidence",
                            f"Plot step references unknown evidence id {evidence_id}.",
                            step.step_id,
                        )
                    )

        if not self._timeline_is_consistent(steps):
            issues.append(ValidationIssue("timeline", "Plot steps contain a major timeline inconsistency."))

        metrics = {
            "suspect_count": len(suspect_names),
            "evidence_count": len(case_bible.evidence_items),
            "plot_step_count": len(steps),
            "alibi_step_count": len(alibi_steps),
            "interference_step_count": len(interference_steps),
            "red_herring_step_count": len(red_herring_steps),
            "referenced_evidence_count": len(referenced_evidence),
        }
        return ValidationReport(is_valid=not issues, issues=issues, metrics=metrics)

    def _timeline_is_consistent(self, steps: list) -> bool:
        seen_times: list[int] = []
        day_offset = 0
        previous_minutes: int | None = None
        for step in steps:
            minutes = self._parse_time(step.timeline_ref)
            if minutes is None:
                continue
            if previous_minutes is not None and minutes < previous_minutes:
                day_offset += 24 * 60
            normalized = minutes + day_offset
            seen_times.append(normalized)
            previous_minutes = minutes
        return seen_times == sorted(seen_times)

    def _parse_time(self, value: str | None) -> int | None:
        if value is None:
            return None
        time_str, meridiem = value.split()
        hour_str, minute_str = time_str.split(":")
        hour = int(hour_str)
        minute = int(minute_str)
        if meridiem == "AM":
            if hour == 12:
                hour = 0
        elif meridiem == "PM":
            if hour != 12:
                hour += 12
        return hour * 60 + minute
