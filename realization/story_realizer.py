from __future__ import annotations

from llm_interface import GeminiLLMBackend, LLMBackend, MockLLMBackend
from models import CaseBible, PlotPlan


class StoryRealizer:
    def __init__(self, llm: LLMBackend) -> None:
        self.llm = llm

    def realize(self, case_bible: CaseBible, plot_plan: PlotPlan) -> str:
        if isinstance(self.llm, MockLLMBackend):
            return self._realize_with_mock(case_bible, plot_plan)
        if isinstance(self.llm, GeminiLLMBackend):
            return self._realize_with_gemini(case_bible, plot_plan)
        return self._realize_with_mock(case_bible, plot_plan)

    def _realize_with_mock(self, case_bible: CaseBible, plot_plan: PlotPlan) -> str:
        title = self._generate_title(case_bible)
        opening = (
            f"{title}\n\n"
            f"{case_bible.setting} was supposed to culminate in a tense private revelation, and Detective Lena Marlowe had already been invited to witness it before the storm sealed the estate. "
            f"{case_bible.victim.name} lay dead, the road was swallowed by snow, and every face in the hall carried some private fear.\n"
        )

        body_parts: list[str] = []
        for step in plot_plan.steps:
            participants = ", ".join(step.participants)
            evidence = ", ".join(step.evidence_ids) if step.evidence_ids else "no physical exhibit yet"
            paragraph = (
                f"\n[{step.step_id}] {step.title}\n"
                f"At {step.timeline_ref or 'an uncertain hour'}, in the {step.location.lower()}, {step.summary} "
                f"The active participants were {participants}. "
                f"The step centered on {evidence}. "
                f"What emerged was this: {'; '.join(step.reveals) if step.reveals else 'the pressure inside the estate increased.'}"
            )
            body_parts.append(paragraph)

        closing = (
            "\n\nBy the final reconstruction, the case no longer depended on rumor. "
            f"The deleted footage, the message to the map room, the digitalis trace, and the staged outage formed a single chain that pointed to {case_bible.culprit.name}. "
            f"He had used his control over security to create opportunity, his grudge to supply motive, and a poisoned spike to provide method. "
            f"{self.llm.generate('Generate story closing line').text}"
        )
        return opening + "".join(body_parts) + closing

    def _realize_with_gemini(self, case_bible: CaseBible, plot_plan: PlotPlan) -> str:
        step_lines: list[str] = []
        for step in plot_plan.steps:
            evidence = ", ".join(step.evidence_ids) if step.evidence_ids else "none"
            reveals = "; ".join(step.reveals) if step.reveals else "none"
            participants = ", ".join(step.participants)
            step_lines.append(
                f"Step {step.step_id} | phase={step.phase} | kind={step.kind} | time={step.timeline_ref} | "
                f"location={step.location} | title={step.title} | participants={participants} | "
                f"evidence={evidence} | summary={step.summary} | reveals={reveals}"
            )

        prompt = (
            "You are writing a polished, readable crime-mystery short story based strictly on a structured investigation plan.\n"
            "Your job is not merely to list events, but to transform the plan into a cohesive, scene-driven narrative.\n"
            "The final story must remain fully consistent with the hidden truth and plot steps, but it should read like an actual mystery story rather than a report.\n\n"

            "Hard constraints:\n"
            "- Do not contradict the hidden truth.\n"
            "- Do not change the culprit, motive, method, or evidence chain.\n"
            "- Do not invent major new plot events that are not supported by the plan.\n"
            "- Do not omit the key investigative developments in the plot steps.\n"
            "- The final confrontation and resolution must clearly rely on the key evidence chain.\n\n"
            "- The lead investigator was already present at the estate before the murder because the victim had invited them to witness or advise on a coming revelation; do not write the investigator as conveniently arriving from outside after the crime.\n\n"

            "Writing goals:\n"
            "- Make the story immersive, smooth, and highly readable.\n"
            "- Turn each plot step into a short narrative scene or beat, not a dry summary.\n"
            "- Use natural transitions so that one discovery leads smoothly into the next.\n"
            "- Maintain suspense by revealing clues gradually.\n"
            "- Let dialogue, observation, suspicion, and emotional reactions help connect the scenes.\n"
            "- Make the setting feel vivid and atmospheric.\n"
            "- Keep the prose clear and elegant rather than overly flowery.\n"
            "- Preserve logical clarity: the reader should be able to follow how the investigation progresses.\n\n"

            "Narrative style instructions:\n"
            "- Write in polished third-person mystery prose.\n"
            "- Use paragraphs, not bullet points or step-by-step labels.\n"
            "- Do not explicitly mention 'Step 1', 'Step 2', or any structured field names.\n"
            "- Integrate evidence naturally into the narration through discovery, discussion, or inference.\n"
            "- When moving from one plot step to another, add brief connective narration so the story flows naturally.\n"
            "- Make suspects feel like people under pressure, not just names in a plan.\n"
            "- Include moments of uncertainty, misdirection, and reconsideration where appropriate.\n"
            "- The ending should feel satisfying: the final explanation should gather the clues into a coherent resolution.\n\n"

            "Recommended story shape:\n"
            "1. Opening: establish the manor, atmosphere, social setting, and discovery of the crime.\n"
            "2. Investigation progression: unfold clue discovery, interviews, alibi checks, red herrings, and rising suspicion in a natural sequence.\n"
            "3. Final confrontation: assemble the key evidence, expose the false leads, and reveal the culprit through reasoning.\n"
            "4. Ending: provide a short but effective resolution after the reveal.\n\n"

            f"Setting: {case_bible.setting}\n"
            f"Victim: {case_bible.victim.name} - {case_bible.victim.description}\n"
            f"Culprit: {case_bible.culprit.name}\n"
            f"True motive: {case_bible.motive}\n"
            f"True method: {case_bible.method}\n"
            f"Key evidence chain: {', '.join(case_bible.culprit_evidence_chain)}\n"
            "Plot steps:\n"
            f"{chr(10).join(step_lines)}\n\n"

            "First, write a fitting mystery title on its own line. "
            "Then write the final story as a cohesive short mystery narrative. "
            "Make it substantially more readable than a procedural summary, while staying faithful to the structured plan."
        )
        return self.llm.generate(prompt).text

    def _generate_title(self, case_bible: CaseBible) -> str:
        prompt = (
            "Generate a concise mystery story title based on this case.\n"
            f"Setting: {case_bible.setting}\n"
            f"Victim: {case_bible.victim.name}\n"
            f"Culprit: {case_bible.culprit.name}\n"
            f"Method: {case_bible.method}"
        )
        return self.llm.generate(prompt).text.strip()
