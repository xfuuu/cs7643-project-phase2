# Phase II — Interactive Mystery Game Engine: Implementation Plan

## 0. Phase I Data Structures (Reused, Read-Only)

Reused from `phase1/models.py`, **without any modification**:

| Type | Key Fields | Phase II Usage |
|------|-----------|---------------|
| `CaseBible` | investigator, victim, culprit, suspects, motive, method, true_timeline, evidence_items, red_herrings, culprit_evidence_chain | Read-only ground-truth database; never modified |
| `FactTriple` | subject, relation, object, time, source | Compilation source for `CausalSpanTracker` |
| `PlotStep` | step_id, phase, kind, title, summary, location, participants, evidence_ids, reveals, timeline_ref | Smallest unit of game progress |
| `PlotPlan` | investigator, steps | The currently-remaining plot plan |
| `PlotPlanRepairOperator` | repair() | Base-class that `RuntimeRepairOperator` adapts |

Reused from `phase1/llm_interface.py`:
- `LLMBackend` (abstract class)
- `GeminiLLMBackend` (instantiated directly)

**Input assets** (under `phase1/outputs/`, loaded at game start):
- `case_bible.json`
- `fact_graph.json`
- `plot_plan.json`
- `story.txt` (first ~500 tokens used as a style reference)

---

## 1. New File Inventory

```
crime-mystery-planner/            ← Phase II root directory
├── models_phase2.py              ← Phase II-specific data classes
├── llm_logger.py                 ← Debug wrapper around LLM calls
├── world_builder.py              ← One-shot world generation
├── world_state.py                ← WorldStateManager
├── causal_spans.py               ← CausalSpanTracker
├── parser.py                     ← Two-stage input parsing
├── action_classifier.py          ← Three-way classifier
├── drama_manager.py              ← Accommodation engine
├── narrator.py                   ← Narrative output
├── game.py                       ← Main CLI loop
├── prompts/
│   ├── world_adjacency.txt       ← Room adjacency-graph generation
│   ├── world_room_desc.txt       ← Room description generation
│   ├── parser_intent.txt         ← Stage 1: intent extraction
│   ├── parser_effects.txt        ← Stage 2: effect prediction
│   ├── parser_commonsense.txt    ← Stage 3: commonsense inference
│   ├── drama_runtime_repair.txt  ← RuntimeRepairOperator
│   └── narrator.txt              ← Narrative generation
└── tests/
    └── test_accommodation.py     ← Accommodation integration tests
```

---

## 2. `models_phase2.py` — Phase II Data Classes

```python
@dataclass
class Room:
    name: str
    description: str
    adjacent_rooms: list[str]
    npc_names: list[str]          # NPCs initially in this room
    evidence_ids: list[str]       # Evidence initially present in this room
    item_names: list[str]         # Ordinary interactable items

@dataclass
class WorldMap:
    rooms: dict[str, Room]        # room_name -> Room

@dataclass
class StateChange:
    entity: str                   # NPC name / evidence_id / item name / room name
    attribute: str                # "location" | "state" | "accessible" | "exists"
    old_value: Any
    new_value: Any

@dataclass
class CausalSpan:
    span_id: str
    variable: str                 # "{entity}.{attribute}", e.g. "EV-01.exists"
    required_value: Any           # The value this variable must keep
    from_step_id: int             # Activation step (inclusive)
    until_step_id: int | None     # Deactivation step (None = until game ends)
    evidence_ids: list[str]       # Evidence protected by this span
    description: str              # Human-readable description, used in error reports

@dataclass
class ViolatedSpan:
    span: CausalSpan
    triggering_change: StateChange
    description: str

@dataclass
class ActionIntent:
    raw_text: str
    verb: str
    object_: str
    target_location: str | None
    confidence: float             # 0.0–1.0; below threshold triggers a re-prompt
    predicted_effects: list[StateChange]

class ActionKind(str, Enum):
    CONSTITUENT = "constituent"   # Advances the plot
    EXCEPTIONAL  = "exceptional"  # Violates a causal span
    CONSISTENT   = "consistent"   # Ordinary world interaction

@dataclass
class ActionClassification:
    kind: ActionKind
    triggered_step: PlotStep | None          # Non-null when CONSTITUENT
    violated_spans: list[ViolatedSpan]       # Non-empty when EXCEPTIONAL
```

---

## 3. `llm_logger.py` — Debug Logging Wrapper

```python
class LoggedLLMBackend(LLMBackend):
    def __init__(
        self,
        inner: LLMBackend,
        log_path: str = "phase2_llm.log",
    ) -> None

    def generate(self, prompt: str) -> LLMResponse
    # Each call records: ISO timestamp, call_label, prompt char count,
    # response char count, estimated token count (chars/4), and elapsed ms.
    # Format: JSON Lines, one record per line.
```

**All other modules** invoke the LLM indirectly through `LoggedLLMBackend`; they never use the raw backend directly.

---

## 4. `world_builder.py` — WorldBuilder

**Responsibility**: One-shot construction of a `WorldMap` from Phase I outputs, serialized to `world.json`. The game loads the saved file at startup and does not regenerate it.

```python
class WorldBuilder:
    def __init__(self, llm: LLMBackend) -> None

    def build(
        self,
        case_bible: CaseBible,
        plot_plan: PlotPlan,
    ) -> WorldMap
    # Full pipeline: extract → assign → adjacency → describe

    def save(self, world_map: WorldMap, path: str) -> None
    # Serialize to world.json (dataclass → dict → json.dump)

    def load(self, path: str) -> WorldMap
    # Deserialize world.json → WorldMap

    # ── Internal methods ──────────────────────────────────────

    def _extract_rooms(self, plot_plan: PlotPlan) -> list[str]
    # Walk PlotStep.location, deduplicate, preserve first-occurrence order

    def _assign_contents(
        self,
        case_bible: CaseBible,
        rooms: list[str],
    ) -> dict[str, dict]
    # Use EvidenceItem.location_found and TimelineEvent.location to assign
    # NPCs, evidence, and ordinary items to rooms; unmatched items go to the
    # nearest room.

    def _build_adjacency(self, rooms: list[str]) -> dict[str, list[str]]
    # 1. Apply commonsense direct connections (Study↔Library, Ballroom↔Drawing Room, ...)
    # 2. If the graph is not connected, make 1 LLM call to generate intermediate
    #    transition rooms and insert them.
    # Ensures the room graph is fully connected.

    def _generate_descriptions(
        self,
        rooms: list[str],
        contents: dict[str, dict],
        adjacency: dict[str, list[str]],
    ) -> dict[str, str]
    # One LLM call per room (prompt: world_room_desc.txt).
    # Generates a 2-3 sentence description in 1920s English-manor style.
```

**LLM call count**: 1 (adjacency completion) + N (room descriptions, where N = number of unique rooms, roughly 8–12).

---

## 5. `world_state.py` — WorldStateManager

**Responsibility**: The authoritative runtime world state, the sole entry point for any state mutation.

```python
class WorldStateManager:
    def __init__(self, world_map: WorldMap) -> None
    # Initialization: player_room = location of the first PlotStep.
    # Populate npc_locations, item_states, evidence_states from WorldMap.

    # ── Public API ────────────────────────────────────────────

    @property
    def player_room(self) -> str

    def apply_effects(self, effects: list[StateChange]) -> None
    # Apply each StateChange in order; no validation here
    # (validation happens in CausalSpanTracker).

    def move_player(self, destination: str) -> bool
    # Check the adjacency graph; if reachable, return True and update,
    # otherwise return False.

    def get_room_view(self, room_name: str) -> dict
    # Returns {description, npcs, evidence, items, exits},
    # used to inject context into the parser's Stage 2 prompt.

    def to_dict(self) -> dict
    # Serialize the full state (used by save_game).

    @classmethod
    def from_dict(cls, data: dict, world_map: WorldMap) -> WorldStateManager
    # Deserialize (used by load_game).
```

---

## 6. `causal_spans.py` — CausalSpanTracker

**Responsibility**: Compile causal spans from `FactTriple`s, detect violations at runtime, and manage span lifecycles as the plot advances.

**Span compilation rules** (derived from `fact_graph.json`):
- For every `EV-xx`, until the first `PlotStep` in `plot_plan.json` that references it, its `exists=True` and `location=<original location>` must remain unchanged → compiled into one `CausalSpan`.
- Span activation: at game start (step_id=0).
- Span deactivation: when the first `PlotStep` referencing that evidence completes.

```python
class CausalSpanTracker:
    def __init__(
        self,
        fact_triples: list[FactTriple],
        plot_plan: PlotPlan,
    ) -> None
    # Calls _compile_spans() to populate the initial active_spans.

    # ── Public API ────────────────────────────────────────────

    def check_violation(
        self,
        predicted_effects: list[StateChange],
    ) -> list[ViolatedSpan]
    # For each active span, check whether predicted_effects touches its variable.
    # If new_value ≠ required_value → record as a ViolatedSpan.

    def complete_step(self, step_id: int) -> None
    # Deactivate every span whose until_step_id == step_id.

    def add_span(self, span: CausalSpan) -> None
    # Used by DramaManager when injecting a new step that activates a new span.

    def remove_spans_for_steps(self, step_ids: list[int]) -> None
    # Used by DramaManager to revoke spans synchronously when steps are deleted.

    # ── Internal methods ──────────────────────────────────────

    def _compile_spans(
        self,
        fact_triples: list[FactTriple],
        plot_plan: PlotPlan,
    ) -> list[CausalSpan]
    # Walk all evidence_ids; for each, find the first step_id in plot_plan that
    # references it. Generate one CausalSpan for that evidence's `exists` and one
    # for its `location`.
```

---

## 7. `parser.py` — InputParser (Three-Stage LLM Pipeline)

```python
CONFIDENCE_THRESHOLD: float = 0.7

class InputParser:
    def __init__(
        self,
        llm: LLMBackend,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
    ) -> None

    def parse(
        self,
        raw_input: str,
        world_state: WorldStateManager,
    ) -> ActionIntent | None
    # Returning None means confidence is too low — caller should ask the player to rephrase.
    # Calls the three stages in order and assembles the result into an ActionIntent.

    # ── Internal methods ──────────────────────────────────────

    def _extract_intent(self, raw_input: str) -> dict
    # Stage 1 (prompt: parser_intent.txt)
    # Input: free-form text
    # Output JSON: {verb, object, target_location, confidence}

    def _predict_effects(
        self,
        intent: dict,
        world_state: WorldStateManager,
    ) -> list[StateChange]
    # Stage 2 (prompt: parser_effects.txt)
    # Input: intent dict + a snapshot from get_room_view()
    # Output JSON array: [{entity, attribute, old_value, new_value}, ...]

    def _infer_commonsense(
        self,
        intent: dict,
        direct_effects: list[StateChange],
    ) -> list[StateChange]
    # Stage 3 (prompt: parser_commonsense.txt)
    # Input: intent + already-known direct effects
    # Output: a list of additional StateChanges representing implicit physical consequences.
    # Example: {verb:"bar", object:"door"} → {entity:"door", attribute:"accessible", new_value:False}
```

---

## 8. `action_classifier.py` — ActionClassifier

**Priority**: exceptional > constituent > consistent

```python
class ActionClassifier:
    def __init__(
        self,
        causal_tracker: CausalSpanTracker,
        plot_plan_ref: PlotPlan,     # Mutable reference, updated by accommodation
    ) -> None

    # ── Public API ────────────────────────────────────────────

    def classify(self, intent: ActionIntent) -> ActionClassification
    # Decide by priority: check exceptional first, then constituent;
    # everything else is consistent.

    def advance_step(self) -> None
    # Called after a constituent action completes:
    # 1. Move the current step into completed_steps.
    # 2. Call causal_tracker.complete_step(step_id).
    # 3. Point current_step at remaining_steps[0] (if any).

    def update_plan(self, new_plan: PlotPlan) -> None
    # After accommodation, replace remaining_steps (completed steps are unchanged).

    @property
    def current_step(self) -> PlotStep | None

    @property
    def completed_steps(self) -> list[PlotStep]

    @property
    def remaining_steps(self) -> list[PlotStep]

    # ── Internal methods ──────────────────────────────────────

    def _is_constituent(
        self,
        effects: list[StateChange],
        step: PlotStep,
    ) -> bool
    # True if at least one StateChange has an entity that is in step.evidence_ids,
    # or its entity is an NPC in step.participants and attribute=="location"
    # matches step.location.

    def _get_violated_spans(
        self,
        effects: list[StateChange],
    ) -> list[ViolatedSpan]
    # Forwards to causal_tracker.check_violation(effects).
```

---

## 9. `drama_manager.py` — DramaManager (Accommodation Engine)

```python
class DramaManager:
    MAX_DEPTH: int = 3

    def __init__(
        self,
        case_bible: CaseBible,     # Read-only
        llm: LLMBackend,
    ) -> None
    # accommodation_depth starts at 0.

    # ── Public API ────────────────────────────────────────────

    def accommodate(
        self,
        violated_spans: list[ViolatedSpan],
        current_plan: PlotPlan,
        completed_steps: list[PlotStep],
    ) -> PlotPlan
    # Main entry point:
    #   depth < MAX_DEPTH  → run the standard accommodation flow.
    #   depth >= MAX_DEPTH → call _emergency_resolution().
    # accommodation_depth is incremented by 1 per call.

    def reset_depth(self) -> None
    # Called when a step completes successfully without exception; resets the counter.

    @property
    def accommodation_depth(self) -> int

    # ── Internal methods ──────────────────────────────────────

    def _find_dependent_steps(
        self,
        plan: PlotPlan,
        violated_spans: list[ViolatedSpan],
    ) -> list[int]
    # Find all step_ids that depend on the violated spans (transitively).
    # Dependency: step.evidence_ids ∩ span.evidence_ids ≠ ∅.

    def _runtime_repair(
        self,
        plan: PlotPlan,
        completed_steps: list[PlotStep],
        available_evidence_ids: list[str],
    ) -> PlotPlan
    # Calls the LLM (prompt: drama_runtime_repair.txt).
    # Prompt injects: CaseBible truth, completed steps (no retconning allowed),
    # and the still-available evidence.
    # The LLM produces a new list of PlotSteps that still points to the same culprit.
    # Phase I PlotPlanRepairOperator is then used for structural validation & patching.

    def _emergency_resolution(
        self,
        completed_steps: list[PlotStep],
    ) -> PlotPlan
    # Triggered when depth >= MAX_DEPTH: build minimal endgame steps directly
    # from CaseBible.culprit_evidence_chain (confrontation + resolution),
    # forcing the game to a conclusion.
```

---

## 10. `narrator.py` — OutputNarrator

```python
class OutputNarrator:
    def __init__(
        self,
        llm: LLMBackend,
        style_reference: str,    # First ~500 tokens of story.txt
    ) -> None

    def narrate(
        self,
        intent: ActionIntent,
        effects: list[StateChange],
        current_step: PlotStep | None,
        world_state: WorldStateManager,
    ) -> str
    # Calls the LLM (prompt: narrator.txt).
    # Generates this turn's narrative: action result + world changes + current
    # plot-beat context. style_reference is prepended to the prompt.

    def narrate_system(self, message: str) -> str
    # For system messages (save/load/error/hints), produce a short narrative reply.
    # Does not call the LLM; formats and returns the string directly.
```

---

## 11. `game.py` — Main CLI Loop

```python
def load_assets(phase1_output_dir: str) -> tuple[CaseBible, list[FactTriple], PlotPlan, str]
# Load case_bible.json, fact_graph.json, plot_plan.json, and story.txt.
# Deserialize into Phase I data classes; return the first ~500 tokens of story.txt.

def save_game(
    world_state: WorldStateManager,
    classifier: ActionClassifier,
    drama: DramaManager,
    path: str,
) -> None
# Serialize: world_state.to_dict() + classifier progress + drama.accommodation_depth.
# Write to a JSON file.

def load_game(
    path: str,
    world_map: WorldMap,
) -> tuple[WorldStateManager, dict]
# Deserialize a save file; return the world_state plus a progress dict.

def run(
    gemini_api_key: str,
    assets_dir: str = "phase1/outputs",
    world_json: str = "world.json",
    save_path: str | None = None,
) -> None
# Main function:
# 1. load_assets()
# 2. If world.json does not exist → WorldBuilder.build() + save(); otherwise load().
# 3. Initialize all components.
# 4. Main loop:
#    stdin → parser.parse()
#      → None: prompt to rephrase
#      → ActionIntent → classifier.classify()
#        → CONSISTENT:   apply_effects + narrate
#        → CONSTITUENT:  apply_effects + advance_step + narrate
#        → EXCEPTIONAL:  drama.accommodate() + classifier.update_plan()
#                        + causal_tracker.remove/add spans + narrate
#    If remaining_steps is empty → print ending and exit.
#    "/save" → save_game(); "/load" → load_game(); "/quit" → exit.
```

---

## 12. `tests/test_accommodation.py`

Uses a **mock CaseBible** (reusing the Phase I example case structure) and **does not call a real LLM** (uses `MockLLMBackend` plus a stubbed `DramaManager._runtime_repair`).

```python
def _make_mock_case_bible() -> CaseBible
# Minimal case: 1 culprit, 1 victim, 1 piece of evidence EV-POISON (poison bottle).
# culprit_evidence_chain = ["EV-POISON"]

def _make_mock_plot_plan(case_bible: CaseBible) -> PlotPlan
# Four steps: discovery → search(EV-POISON) → confrontation → resolution

def test_accommodation_triggered() -> None
# Action: "pour the poison bottle down the drain"
# Build predicted_effects = [StateChange("EV-POISON", "exists", True, False)]
# Assert: causal_tracker.check_violation(effects) returns a non-empty list.
# Assert: drama_manager.accommodate() is called (accommodation_depth goes 0 → 1).

def test_affected_steps_removed() -> None
# Building on test_accommodation_triggered:
# Assert: the new PlotPlan.steps no longer contains the search step that referenced EV-POISON.

def test_new_steps_target_same_culprit() -> None
# For the output of _runtime_repair (mocked to return fixed new steps):
# Assert: the new steps still include case_bible.culprit.name in participants.
# Assert: the new steps' evidence_ids do not include the destroyed EV-POISON.
```

---

## 13. Data Flow Overview

```
stdin
  └─► InputParser.parse()
        ├─ Stage 1: LLM → {verb, object, confidence}
        ├─ Stage 2: LLM → list[StateChange]
        └─ Stage 3: LLM → additional implied StateChanges
              └─► ActionClassifier.classify()
                    ├─ EXCEPTIONAL ──► DramaManager.accommodate()
                    │                    ├─ _find_dependent_steps()
                    │                    ├─ _runtime_repair() [LLM]
                    │                    └─ new PlotPlan
                    │                         └─► classifier.update_plan()
                    │                         └─► causal_tracker.remove/add_spans()
                    ├─ CONSTITUENT ──► WorldStateManager.apply_effects()
                    │                 classifier.advance_step()
                    │                 causal_tracker.complete_step()
                    └─ CONSISTENT  ──► WorldStateManager.apply_effects()
                          └─► OutputNarrator.narrate() [LLM]
                                └─► stdout
```

---

## 14. Inter-Module Dependencies

```
game.py
  ├── world_builder.py     (WorldBuilder)
  ├── world_state.py       (WorldStateManager)
  ├── causal_spans.py      (CausalSpanTracker)
  ├── parser.py            (InputParser)
  ├── action_classifier.py (ActionClassifier)
  ├── drama_manager.py     (DramaManager)
  └── narrator.py          (OutputNarrator)

All modules access the LLM through llm_logger.LoggedLLMBackend.
All modules read the CaseBible only (never write).
Files in prompts/ are read via pathlib.Path(__file__).parent / "prompts".
Phase I modules are accessed through sys.path injection
(game.py prepends phase1/ to sys.path on startup).
```

---

## 15. LLM Call Statistics (Per Turn)

| Stage | Calls | Prompt File |
|-------|-------|-------------|
| World generation (one-shot) | 1 + N_rooms | world_adjacency.txt, world_room_desc.txt |
| Per turn — Stage 1 | 1 | parser_intent.txt |
| Per turn — Stage 2 | 1 | parser_effects.txt |
| Per turn — Stage 3 | 1 | parser_commonsense.txt |
| Per turn — narration | 1 | narrator.txt |
| accommodation (when triggered) | 1 | drama_runtime_repair.txt |
| **Normal turn total** | **4** | |
| **Turn with accommodation** | **5** | |

---

## Open Questions

1. Should `world.json` be force-regenerated for every new case run (or detected via a `case_bible` hash)?
2. The `InputParser` confidence threshold defaults to 0.7 — should it be configurable (CLI flag)?
3. The save-file path defaults to `savegame.json` — should multiple save slots be supported?
4. After `_emergency_resolution` triggers, should we surface that to the player (OOC notice), or handle it purely at the narrative layer?
