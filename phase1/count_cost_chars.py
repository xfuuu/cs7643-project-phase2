from __future__ import annotations

import json
from pathlib import Path

from generators.case_bible_generator import CaseBibleGenerator
from llm_interface import GeminiLLMBackend, LLMBackend, LLMResponse
from models import CaseBible, Character, EvidenceItem, FactTriple, PlotPlan, PlotStep, RedHerring, TimelineEvent
from planners.plot_planner import PlotPlanner
from realization.story_realizer import StoryRealizer


def estimate_tokens(text: str) -> int:
    return round(len(text) / 4)


class CaptureBackend(LLMBackend):
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.last_prompt: str | None = None

    def generate(self, prompt: str) -> LLMResponse:
        self.last_prompt = prompt
        return LLMResponse(text=self.response_text)


class CaptureGeminiBackend(GeminiLLMBackend):
    def __init__(self) -> None:
        self.last_prompt: str | None = None

    def generate(self, prompt: str) -> LLMResponse:
        self.last_prompt = prompt
        return LLMResponse(text="DUMMY")


def load_case_bible(path: Path) -> CaseBible:
    data = json.loads(path.read_text(encoding="utf-8"))
    return CaseBible(
        setting=data["setting"],
        investigator=data["investigator"],
        victim=Character(**data["victim"]),
        culprit=Character(**data["culprit"]),
        suspects=[Character(**item) for item in data["suspects"]],
        motive=data["motive"],
        method=data["method"],
        true_timeline=[TimelineEvent(**item) for item in data["true_timeline"]],
        evidence_items=[EvidenceItem(**item) for item in data["evidence_items"]],
        red_herrings=[RedHerring(**item) for item in data["red_herrings"]],
        culprit_evidence_chain=data["culprit_evidence_chain"],
    )


def load_fact_graph(path: Path) -> list[FactTriple]:
    return [FactTriple(**item) for item in json.loads(path.read_text(encoding="utf-8"))]


def load_plot_plan(path: Path) -> PlotPlan:
    data = json.loads(path.read_text(encoding="utf-8"))
    return PlotPlan(
        investigator=data["investigator"],
        steps=[PlotStep(**item) for item in data["steps"]],
    )


def main() -> None:
    root = Path(__file__).resolve().parent
    outputs = root / "outputs"

    case_bible_path = outputs / "case_bible.json"
    fact_graph_path = outputs / "fact_graph.json"
    plot_plan_path = outputs / "plot_plan.json"
    story_path = outputs / "story.txt"

    case_bible = load_case_bible(case_bible_path)
    fact_graph = load_fact_graph(fact_graph_path)
    plot_plan = load_plot_plan(plot_plan_path)
    story_text = story_path.read_text(encoding="utf-8")

    case_data = json.loads(case_bible_path.read_text(encoding="utf-8"))
    plot_data = json.loads(plot_plan_path.read_text(encoding="utf-8"))

    blueprint = {
        "investigator": case_data["investigator"],
        "victim": case_data["victim"],
        "suspects": case_data["suspects"],
        "culprit_name": case_data["culprit"]["name"],
        "motive": case_data["motive"],
        "method": case_data["method"],
        "true_timeline": case_data["true_timeline"],
        "evidence_items": case_data["evidence_items"],
        "red_herrings": case_data["red_herrings"],
        "culprit_evidence_chain": case_data["culprit_evidence_chain"],
    }

    case_backend = CaptureBackend(json.dumps(blueprint))
    CaseBibleGenerator(llm=case_backend).generate()
    case_prompt = case_backend.last_prompt or ""

    planner = PlotPlanner()
    evidence_ids = sorted(planner._available_evidence_ids(case_bible, fact_graph))
    plot_prompt = planner._plot_prompt(case_bible, fact_graph, evidence_ids)

    story_backend = CaptureGeminiBackend()
    StoryRealizer(story_backend).realize(case_bible, plot_plan)
    story_prompt = story_backend.last_prompt or ""

    compact_case = json.dumps(case_data, separators=(",", ":"))
    compact_plot = json.dumps(plot_data, separators=(",", ":"))

    case_prompt_tokens = estimate_tokens(case_prompt)
    plot_prompt_tokens = estimate_tokens(plot_prompt)
    story_prompt_tokens = estimate_tokens(story_prompt)
    case_output_tokens = estimate_tokens(compact_case)
    plot_output_tokens = estimate_tokens(compact_plot)
    story_output_tokens = estimate_tokens(story_text)

    total_input_tokens = case_prompt_tokens + plot_prompt_tokens + story_prompt_tokens
    total_output_tokens = case_output_tokens + plot_output_tokens + story_output_tokens
    input_cost = total_input_tokens / 1_000_000 * 0.30
    output_cost = total_output_tokens / 1_000_000 * 2.50
    total_cost = input_cost + output_cost

    print("Prompt character counts")
    print(f"case_prompt_chars={len(case_prompt)}")
    print(f"plot_prompt_chars={len(plot_prompt)}")
    print(f"story_prompt_chars={len(story_prompt)}")
    print()
    print("Prompt token estimates")
    print(f"case_prompt_tokens_est={case_prompt_tokens}")
    print(f"plot_prompt_tokens_est={plot_prompt_tokens}")
    print(f"story_prompt_tokens_est={story_prompt_tokens}")
    print()
    print("Output character counts")
    print(f"case_output_chars_compact={len(compact_case)}")
    print(f"plot_output_chars_compact={len(compact_plot)}")
    print(f"story_output_chars={len(story_text)}")
    print()
    print("Output token estimates")
    print(f"case_output_tokens_est={case_output_tokens}")
    print(f"plot_output_tokens_est={plot_output_tokens}")
    print(f"story_output_tokens_est={story_output_tokens}")
    print()
    print("Totals")
    print(f"total_input_tokens_est={total_input_tokens}")
    print(f"total_output_tokens_est={total_output_tokens}")
    print()
    print("Cost estimate (Gemini 2.5 Flash standard pricing)")
    print(f"input_cost_usd_est={input_cost:.8f}")
    print(f"output_cost_usd_est={output_cost:.8f}")
    print(f"total_cost_usd_est={total_cost:.8f}")


if __name__ == "__main__":
    main()
