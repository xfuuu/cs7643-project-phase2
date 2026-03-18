from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from builders.fact_graph_builder import FactGraphBuilder
from generators.case_bible_generator import CaseBibleGenerator
from llm_interface import GeminiLLMBackend, MockLLMBackend
from models import PlotPlan, ValidationReport
from planners.plot_planner import PlotPlanner
from realization.story_realizer import StoryRealizer
from repair.repair_operator import PlotPlanRepairOperator
from validators.validator import PlotPlanValidator


class CrimeMysteryPipeline:
    def __init__(self, output_dir: str = "outputs", seed: int = 7) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.mock_llm = MockLLMBackend(seed=seed)
        self.gemini_llm = GeminiLLMBackend()
        self.case_generator = CaseBibleGenerator(llm=self.gemini_llm, seed=seed + 1)
        self.fact_builder = FactGraphBuilder()
        self.plot_planner = PlotPlanner(llm=self.gemini_llm)
        self.validator = PlotPlanValidator()
        self.repair_operator = PlotPlanRepairOperator()
        self.story_realizer = StoryRealizer(llm=self.gemini_llm)

    def run(self) -> dict[str, object]:
        case_bible = self.case_generator.generate()
        fact_graph = self.fact_builder.build(case_bible)
        initial_plot_plan = self.plot_planner.build_plan(case_bible, fact_graph)
        # initial_report = self.validator.validate(case_bible, initial_plot_plan)

        final_plot_plan: PlotPlan = initial_plot_plan
        # final_report: ValidationReport = initial_report
        # if not initial_report.is_valid:
        #     final_plot_plan = self.repair_operator.repair(case_bible, initial_plot_plan, initial_report)
        #     final_report = self.validator.validate(case_bible, final_plot_plan)

        # story_text = self.story_realizer.realize(case_bible, final_plot_plan)
        self._save_json("case_bible.json", asdict(case_bible))
        self._save_json("fact_graph.json", [asdict(fact) for fact in fact_graph])
        self._save_json("plot_plan.json", asdict(final_plot_plan))
        # self._save_json("validation_report.json", asdict(final_report))
        # self._save_text("story.txt", story_text)
        quit()

        return {
            "case_bible": case_bible,
            "fact_graph": fact_graph,
            "plot_plan": final_plot_plan,
            "validation_report": final_report,
            "story_text": story_text,
            "output_dir": str(self.output_dir.resolve()),
        }

    def _save_json(self, file_name: str, payload: object) -> None:
        path = self.output_dir / file_name
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _save_text(self, file_name: str, content: str) -> None:
        path = self.output_dir / file_name
        path.write_text(content, encoding="utf-8")
