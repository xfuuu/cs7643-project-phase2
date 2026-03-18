from __future__ import annotations

from models import CaseBible, PlotPlan, PlotStep, ValidationReport


class PlotPlanRepairOperator:
    def repair(self, case_bible: CaseBible, plot_plan: PlotPlan, report: ValidationReport) -> PlotPlan:
        repaired_steps = list(plot_plan.steps)
        issue_codes = {issue.code for issue in report.issues}

        if "alibi_steps" in issue_codes:
            repaired_steps.append(
                PlotStep(
                    step_id=len(repaired_steps) + 1,
                    phase="investigation",
                    kind="alibi_check",
                    title="Late Added Alibi Verification",
                    summary="The detective adds a focused alibi verification step to close a missing validation requirement.",
                    location="Guest corridor",
                    participants=[plot_plan.investigator, case_bible.suspects[0].name],
                    reveals=["A second explicit alibi check is now on record."],
                    timeline_ref="1:10 AM",
                )
            )

        if "interference" in issue_codes:
            repaired_steps.append(
                PlotStep(
                    step_id=len(repaired_steps) + 1,
                    phase="midpoint",
                    kind="interference",
                    title="Recovered Interference Beat",
                    summary="A suspect tries to remove incriminating material, proving the investigation is being obstructed.",
                    location="Study",
                    participants=[plot_plan.investigator, case_bible.culprit.name],
                    evidence_ids=[case_bible.culprit_evidence_chain[0]],
                    reveals=["The culprit reacts to pressure by interfering."],
                    timeline_ref="1:12 AM",
                )
            )

        if "red_herring_arc" in issue_codes:
            repaired_steps.append(
                PlotStep(
                    step_id=len(repaired_steps) + 1,
                    phase="investigation",
                    kind="red_herring",
                    title="Recovered Red Herring",
                    summary="The detective follows a persuasive but false theory before separating side misconduct from murder.",
                    location="Salon",
                    participants=[plot_plan.investigator, case_bible.red_herrings[0].suspect_name],
                    evidence_ids=case_bible.red_herrings[0].misleading_evidence_ids,
                    reveals=[case_bible.red_herrings[0].explanation],
                    timeline_ref="1:14 AM",
                )
            )

        chain = set(case_bible.culprit_evidence_chain)
        referenced = {evidence_id for step in repaired_steps for evidence_id in step.evidence_ids}
        missing_chain = sorted(chain - referenced)
        if missing_chain:
            repaired_steps.append(
                PlotStep(
                    step_id=len(repaired_steps) + 1,
                    phase="reversal",
                    kind="evidence",
                    title="Recovered Missing Evidence Chain",
                    summary="The detective adds the remaining evidence links needed to support the culprit deterministically.",
                    location="Case board",
                    participants=[plot_plan.investigator, case_bible.culprit.name],
                    evidence_ids=missing_chain,
                    reveals=["The evidence chain is now complete."],
                    timeline_ref="1:16 AM",
                )
            )

        if "confrontation_evidence" in issue_codes or "confrontation" in issue_codes:
            key_evidence = case_bible.culprit_evidence_chain[:4]
            confrontation = next((step for step in repaired_steps if step.kind == "confrontation"), None)
            if confrontation is None:
                repaired_steps.append(
                    PlotStep(
                        step_id=len(repaired_steps) + 1,
                        phase="climax",
                        kind="confrontation",
                        title="Recovered Final Confrontation",
                        summary="The detective lays out the decisive evidence chain in front of every suspect.",
                        location="Map room",
                        participants=[plot_plan.investigator] + [suspect.name for suspect in case_bible.suspects],
                        evidence_ids=key_evidence,
                        reveals=["The culprit can no longer hide behind confusion."],
                        timeline_ref="1:20 AM",
                    )
                )
            else:
                confrontation.evidence_ids = sorted(set(confrontation.evidence_ids + key_evidence))

        repaired_steps.sort(key=lambda step: step.step_id)
        for index, step in enumerate(repaired_steps, start=1):
            step.step_id = index

        return PlotPlan(investigator=plot_plan.investigator, steps=repaired_steps)
