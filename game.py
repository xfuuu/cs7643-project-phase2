from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make phase1 importable
sys.path.insert(0, str(Path(__file__).parent / "phase1"))
from llm_interface import GeminiLLMBackend
from models import CaseBible, Character, EvidenceItem, FactTriple, PlotPlan, PlotStep, RedHerring, TimelineEvent

from action_classifier import ActionClassifier
from causal_spans import CausalSpanTracker
from drama_manager import DramaManager
from llm_logger import LoggedLLMBackend
from models_phase2 import ActionKind, WorldMap
from narrator import OutputNarrator
from parser import InputParser
from world_builder import WorldBuilder
from world_state import WorldStateManager

_SAVE_FILE = "savegame.json"
_WORLD_FILE = "world.json"
_BANNER = """
╔══════════════════════════════════════════════════════╗
║     THE BLACKWOOD MANOR MYSTERY — Investigation      ║
║     Type your action.  /save  /load  /look  /quit   ║
╚══════════════════════════════════════════════════════╝
"""


# ── asset loading ─────────────────────────────────────────────────────────────

def load_assets(phase1_output_dir: str) -> tuple[CaseBible, list[FactTriple], PlotPlan, str]:
    base = Path(phase1_output_dir)

    with open(base / "case_bible.json", encoding="utf-8") as f:
        cb_raw = json.load(f)
    case_bible = _deserialise_case_bible(cb_raw)

    with open(base / "fact_graph.json", encoding="utf-8") as f:
        fg_raw = json.load(f)
    fact_triples = [
        FactTriple(
            subject=t["subject"],
            relation=t["relation"],
            object=t["object"],
            time=t.get("time"),
            source=t.get("source", ""),
        )
        for t in fg_raw
    ]

    with open(base / "plot_plan.json", encoding="utf-8") as f:
        pp_raw = json.load(f)
    plot_plan = _deserialise_plot_plan(pp_raw)

    story_path = base / "story.txt"
    style_ref = story_path.read_text(encoding="utf-8") if story_path.exists() else ""

    return case_bible, fact_triples, plot_plan, style_ref


# ── save / load ───────────────────────────────────────────────────────────────

def save_game(
    world_state: WorldStateManager,
    classifier: ActionClassifier,
    drama: DramaManager,
    path: str = _SAVE_FILE,
) -> None:
    data = {
        "world_state": world_state.to_dict(),
        "completed_steps": [_step_to_dict(s) for s in classifier.completed_steps],
        "remaining_steps": [_step_to_dict(s) for s in classifier.remaining_steps],
        "accommodation_depth": drama.accommodation_depth,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_game(
    path: str,
    world_map: WorldMap,
) -> tuple[WorldStateManager, list[PlotStep], list[PlotStep], int]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    world_state = WorldStateManager.from_dict(data["world_state"], world_map)
    completed = [_dict_to_step(s) for s in data.get("completed_steps", [])]
    remaining = [_dict_to_step(s) for s in data.get("remaining_steps", [])]
    depth = data.get("accommodation_depth", 0)
    return world_state, completed, remaining, depth


# ── main ──────────────────────────────────────────────────────────────────────

def run(
    gemini_api_key: str,
    assets_dir: str = "phase1/outputs",
    world_json: str = _WORLD_FILE,
) -> None:
    print("Loading story assets…")
    case_bible, fact_triples, plot_plan, style_ref = load_assets(assets_dir)

    raw_backend = GeminiLLMBackend(api_key=gemini_api_key)
    llm = LoggedLLMBackend(raw_backend, log_path="phase2_llm.log")

    print("Building / loading world map…")
    builder = WorldBuilder(llm)
    world_map = builder.build(case_bible, plot_plan)
    builder.save(world_map, world_json)
    print(f"World saved to {world_json}")

    starting_room = plot_plan.steps[0].location if plot_plan.steps else next(iter(world_map.rooms))
    world_state = WorldStateManager(world_map, starting_room)
    tracker = CausalSpanTracker(fact_triples, plot_plan)
    classifier = ActionClassifier(tracker, plot_plan)
    drama = DramaManager(case_bible, llm)
    narrator = OutputNarrator(llm, style_ref)
    parser = InputParser(llm)

    print(_BANNER)
    _print_room(world_state)

    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nFarewell.")
            break

        if not raw:
            continue

        # ── built-in commands ──────────────────────────────────────────────
        if raw.lower() == "/quit":
            print("Farewell.")
            break

        if raw.lower() == "/save":
            save_game(world_state, classifier, drama)
            print(narrator.narrate_system(f"Game saved to {_SAVE_FILE}."))
            continue

        if raw.lower() == "/load":
            if not Path(_SAVE_FILE).exists():
                print(narrator.narrate_system("No save file found."))
                continue
            world_state, completed, remaining, depth = load_game(_SAVE_FILE, world_map)
            tracker = CausalSpanTracker(fact_triples, plot_plan)
            classifier = ActionClassifier(tracker, PlotPlan(investigator=plot_plan.investigator, steps=completed + remaining))
            for _ in completed:
                classifier.advance_step()
            drama = DramaManager(case_bible, llm)
            drama._depth = depth
            print(narrator.narrate_system("Game loaded."))
            _print_room(world_state)
            continue

        if raw.lower() in ("/look", "/l"):
            _print_room(world_state)
            continue

        if raw.lower() == "/hint":
            step = classifier.current_step
            if step:
                print(f"\n[Hint] Next beat: {step.title} — {step.location}")
            else:
                print("\n[Hint] The investigation has no more planned beats.")
            continue

        # ── movement shortcut: "go library" / "去图书馆" ──────────────────
        lower = raw.lower()
        if lower.startswith("go ") or lower.startswith("去"):
            dest = raw[3:].strip() if lower.startswith("go ") else raw[1:].strip()
            if world_state.move_player(dest):
                _print_room(world_state)
                _check_constituent_on_enter(classifier, world_state, narrator, drama)
            else:
                print(f"You cannot reach '{dest}' from here.")
            continue

        # ── LLM parse pipeline ────────────────────────────────────────────
        intent = parser.parse(raw, world_state)
        if intent is None:
            print("I didn't quite follow that. Could you describe your action more clearly?")
            continue

        # handle movement intents from parser
        if intent.verb == "go" and intent.target_location:
            if world_state.move_player(intent.target_location):
                _print_room(world_state)
                _check_constituent_on_enter(classifier, world_state, narrator, drama)
            else:
                print(f"You cannot reach '{intent.target_location}' from here.")
            continue

        classification = classifier.classify(intent)

        if classification.kind == ActionKind.EXCEPTIONAL:
            world_state.apply_effects(intent.predicted_effects)
            tracker.remove_spans_for_steps(
                [s.step_id for s in classifier.remaining_steps
                 if any(ev in {e for vs in classification.violated_spans for e in vs.span.evidence_ids}
                        for ev in s.evidence_ids)]
            )
            new_plan = drama.accommodate(
                classification.violated_spans,
                PlotPlan(investigator=plot_plan.investigator,
                         steps=classifier.completed_steps + classifier.remaining_steps),
                classifier.completed_steps,
            )
            classifier.update_plan(new_plan)
            narration = narrator.narrate(intent, intent.predicted_effects, classifier.current_step, world_state)
            print(f"\n{narration}")

        elif classification.kind == ActionKind.CONSTITUENT:
            world_state.apply_effects(intent.predicted_effects)
            narration = narrator.narrate(intent, intent.predicted_effects, classifier.current_step, world_state)
            print(f"\n{narration}")
            classifier.advance_step()
            drama.reset_depth()
            _check_game_over(classifier, narrator)

        else:  # CONSISTENT
            world_state.apply_effects(intent.predicted_effects)
            narration = narrator.narrate(intent, intent.predicted_effects, classifier.current_step, world_state)
            print(f"\n{narration}")


# ── helpers ───────────────────────────────────────────────────────────────────

def _print_room(world_state: WorldStateManager) -> None:
    view = world_state.get_room_view()
    print(f"\n{'─'*54}")
    print(f"  {view.get('room', '?')}")
    print(f"{'─'*54}")
    print(f"  {view.get('description', '')}")
    npcs = view.get("npcs", [])
    if npcs:
        print(f"\n  Present: {', '.join(npcs)}")
    ev = view.get("evidence", [])
    if ev:
        print(f"  Evidence visible: {', '.join(ev)}")
    items = view.get("items", [])
    if items:
        print(f"  Items: {', '.join(items)}")
    exits = view.get("exits", [])
    if exits:
        print(f"  Exits: {', '.join(exits)}")
    print()


def _check_constituent_on_enter(classifier, world_state, narrator, drama) -> None:
    step = classifier.current_step
    if step and world_state.player_room.lower() == step.location.lower():
        if step.kind == "discovery":
            classifier.advance_step()
            drama.reset_depth()
            _check_game_over(classifier, narrator)


def _check_game_over(classifier, narrator) -> None:
    if not classifier.remaining_steps:
        print(narrator.narrate_system(
            "The investigation is complete. The truth has come to light."
        ))
        print("\nThank you for playing. Farewell.\n")
        sys.exit(0)
    next_step = classifier.current_step
    if next_step and next_step.kind == "resolution":
        classifier.advance_step()
        print(narrator.narrate_system("The case is closed."))
        sys.exit(0)


# ── serialisation helpers ─────────────────────────────────────────────────────

def _step_to_dict(step: PlotStep) -> dict:
    return {
        "step_id": step.step_id,
        "phase": step.phase,
        "kind": step.kind,
        "title": step.title,
        "summary": step.summary,
        "location": step.location,
        "participants": step.participants,
        "evidence_ids": step.evidence_ids,
        "reveals": step.reveals,
        "timeline_ref": step.timeline_ref,
    }


def _dict_to_step(d: dict) -> PlotStep:
    return PlotStep(
        step_id=d["step_id"],
        phase=d["phase"],
        kind=d["kind"],
        title=d["title"],
        summary=d["summary"],
        location=d["location"],
        participants=d["participants"],
        evidence_ids=d.get("evidence_ids", []),
        reveals=d.get("reveals", []),
        timeline_ref=d.get("timeline_ref"),
    )


def _deserialise_case_bible(raw: dict) -> CaseBible:
    def char(d: dict) -> Character:
        return Character(
            name=d["name"], role=d["role"], description=d["description"],
            relationship_to_victim=d["relationship_to_victim"],
            means=d["means"], motive=d["motive"],
            opportunity=d["opportunity"], alibi=d["alibi"],
        )
    def ev(d: dict) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=d["evidence_id"], name=d["name"], description=d["description"],
            location_found=d["location_found"], implicated_person=d["implicated_person"],
            reliability=d["reliability"], planted=d.get("planted", False),
        )
    def tl(d: dict) -> TimelineEvent:
        return TimelineEvent(
            event_id=d["event_id"], time_marker=d["time_marker"], summary=d["summary"],
            participants=d["participants"], location=d["location"], public=d["public"],
        )
    def rh(d: dict) -> RedHerring:
        return RedHerring(
            herring_id=d["herring_id"], suspect_name=d["suspect_name"],
            misleading_evidence_ids=d["misleading_evidence_ids"],
            explanation=d["explanation"],
        )
    return CaseBible(
        setting=raw["setting"],
        investigator=raw["investigator"],
        victim=char(raw["victim"]),
        culprit=char(raw["culprit"]),
        suspects=[char(s) for s in raw["suspects"]],
        motive=raw["motive"],
        method=raw["method"],
        true_timeline=[tl(t) for t in raw["true_timeline"]],
        evidence_items=[ev(e) for e in raw["evidence_items"]],
        red_herrings=[rh(r) for r in raw["red_herrings"]],
        culprit_evidence_chain=raw["culprit_evidence_chain"],
    )


def _deserialise_plot_plan(raw: dict) -> PlotPlan:
    steps = [_dict_to_step(s) for s in raw["steps"]]
    return PlotPlan(investigator=raw["investigator"], steps=steps)


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Phase II — Interactive Mystery Game")
    ap.add_argument("--gemini-api-key", required=True, help="Gemini API key")
    ap.add_argument("--assets-dir", default="phase1/outputs", help="Path to Phase I outputs")
    ap.add_argument("--world-json", default=_WORLD_FILE, help="Path to world.json")
    args = ap.parse_args()
    run(
        gemini_api_key=args.gemini_api_key,
        assets_dir=args.assets_dir,
        world_json=args.world_json,
    )


if __name__ == "__main__":
    main()
