# AI Crime Mystery — Intervention and Accommodation

**Team Name:** Dreamy Whales  
**System Name:** Intervention and Accommodation  
**Project Template:** Template 3 — Story Planning with LLMs, extended with an interactive game engine that uses real-time plan repair (accommodation) to handle unexpected player actions.

---

## 1. Project Summary

This project has two phases that work in sequence:

**Phase I** generates a closed-circle crime mystery as a set of structured JSON assets using a planning → validation → repair pipeline.

**Phase II** consumes those assets and turns them into a playable CLI text-adventure game. The player investigates the manor in free text. An LLM pipeline interprets every action, classifies it, and — when the player does something that would break the story (e.g. destroying a key piece of evidence before it is examined) — the system surgically repairs the plot plan in real time while keeping the true culprit and motive unchanged.

---

## 2. How to Run

### Requirements

- Python 3.10+
- A Gemini API key (starts with `AIza…`). Get one free at [https://aistudio.google.com](https://aistudio.google.com)
- Internet access for API calls
- No third-party Python packages — only the standard library is used

### Step 1 — Generate the story assets (Phase I)

If you want to generate a fresh case, run Phase I first:

```bash
cd phase1
python main.py --gemini-api-key "YOUR_GEMINI_API_KEY"
cd ..
```

This writes five files to `phase1/outputs/`:
`case_bible.json`, `fact_graph.json`, `plot_plan.json`, `validation_report.json`, `story.txt`

A pre-generated example is already committed in `phase1/outputs/` so you can skip this step and go straight to Phase II.

### Step 2 — Play the game (Phase II)

From the project root:

```bash
python game.py --gemini-api-key "YOUR_GEMINI_API_KEY"
```

Optional flags:

```bash
python game.py \
  --gemini-api-key "YOUR_GEMINI_API_KEY" \
  --assets-dir phase1/outputs \   # path to Phase I output files (default)
  --world-json world.json          # where to save/load the world map (default)
```

On the **first run** the system builds and saves `world.json` (takes ~60 s, ~14 LLM calls). Every subsequent run loads it instantly.

### Running the tests

```bash
python tests/test_accommodation.py
```

All three accommodation tests should pass with no LLM calls (uses a stub backend).

---

## 3. Runtime and Cost

| Stage | Calls | Tokens (est.) | Time |
|-------|-------|---------------|------|
| Room adjacency graph | 1 | 543 | ~10 s |
| Room descriptions (9 rooms) | 9 | 2,099 | ~40 s |
| **Total** | **10** | **2,642** | **~60 s** |

Estimated cost: **~$0.003**

### Phase II — per player turn

Each turn makes 4 LLM calls (measured):

| Call | Tokens (est.) | Time |
|------|---------------|------|
| Stage 1 — intent extraction | 204 | ~2.5 s |
| Stage 2 — effect prediction | 415 | ~2.1 s |
| Stage 3 — commonsense inference | 207 | ~4.6 s |
| Narration | 912 | ~9.3 s |
| **Total** | **~1,738** | **~18–20 s** |

If an accommodation fires, one additional call is made (~500–800 tokens, ~5–10 s).

Estimated cost per turn: **~$0.002**

---

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE I — Story Generation Pipeline                                    │
│                                                                         │
│  setting.txt                                                            │
│      │                                                                  │
│      ▼                                                                  │
│  CaseBibleGenerator ──LLM──► CaseBible (JSON)                          │
│      │                           │                                      │
│      │                           ▼                                      │
│      │                   FactGraphBuilder ──► fact_graph (JSON)         │
│      │                           │                                      │
│      │                           ▼                                      │
│      │                   PlotPlanner ──LLM──► PlotPlan (JSON)           │
│      │                           │                                      │
│      │                           ▼                                      │
│      │                      Validator                                   │
│      │                      │       │                                   │
│      │                 valid │   invalid │                              │
│      │                      │           ▼                               │
│      │                      │    RepairOperator ──► repaired PlotPlan   │
│      │                      │           │                               │
│      │                      └─────┬─────┘                              │
│      │                            ▼                                     │
│      └──────────────────► StoryRealizer ──LLM──► story.txt             │
│                                                                         │
│  Outputs: case_bible.json  fact_graph.json  plot_plan.json  story.txt  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    (loaded as read-only assets)
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE II — Interactive Game Engine                                     │
│                                                                         │
│  Startup                                                                │
│  ──────────────────────────────────────────────────────                 │
│  case_bible.json ──► CaseBible (read-only throughout game)             │
│  fact_graph.json ──► CausalSpanTracker (compile evidence spans)        │
│  plot_plan.json  ──► ActionClassifier  (remaining plot beats)          │
│  story.txt       ──► OutputNarrator    (style reference)               │
│  world.json      ──► WorldStateManager (room graph, NPC positions)     │
│        ▲                                                                │
│        │ (built once by WorldBuilder if not found)                     │
│                                                                         │
│  Per-Turn Game Loop                                                     │
│  ──────────────────────────────────────────────────────                 │
│                                                                         │
│  stdin ──► InputParser                                                  │
│                │                                                        │
│         ┌──── Stage 1: intent extraction (LLM)                         │
│         │     {verb, object, target_location, confidence}              │
│         │                                                               │
│         ├──── Stage 2: effect prediction (LLM)                         │
│         │     [{entity, attribute, old_value, new_value}, …]           │
│         │                                                               │
│         └──── Stage 3: commonsense inference (LLM)                     │
│               (implied physical consequences)                           │
│                        │                                                │
│                        ▼                                                │
│               ActionClassifier                                          │
│               ┌─────────┬─────────────┬──────────┐                    │
│               │         │             │          │                     │
│          EXCEPTIONAL  CONSTITUENT  CONSISTENT    │                     │
│          (violates    (advances    (world        │                     │
│           causal span) plot beat)  interaction)  │                     │
│               │         │             │          │                     │
│               ▼         │             │          │                     │
│         DramaManager    │             │          │                     │
│         (accommodation) │             │          │                     │
│          │              │             │          │                     │
│    ┌─────┴──────┐       │             │          │                     │
│    │            │       │             │          │                     │
│  depth       depth      │             │          │                     │
│  < MAX       ≥ MAX      │             │          │                     │
│    │            │       │             │          │                     │
│    ▼            ▼       │             │          │                     │
│  LLM repair  Emergency  │             │          │                     │
│  new steps   resolution │             │          │                     │
│    │            │       │             │          │                     │
│    └────────────┘       │             │          │                     │
│         new PlotPlan    │             │          │                     │
│               │         │             │          │                     │
│               └─────────┴──────┬──────┘          │                    │
│                                │                  │                    │
│                    WorldStateManager.apply_effects()                   │
│                                │                                        │
│                                ▼                                        │
│                         OutputNarrator ──LLM──► stdout                 │
│                                                                         │
│                    (loop until resolution step)                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. File Map

| File | Purpose |
|------|---------|
| `models_phase2.py` | `Room`, `WorldMap`, `StateChange`, `CausalSpan`, `ActionIntent`, `ActionClassification` |
| `llm_logger.py` | `LoggedLLMBackend` — debug wrapper for all LLM calls |
| `world_builder.py` | One-time world generation from plot assets |
| `world_state.py` | `WorldStateManager` — authoritative runtime state |
| `causal_spans.py` | `CausalSpanTracker` — span compilation and violation detection |
| `parser.py` | `InputParser` — three-stage LLM parsing pipeline |
| `action_classifier.py` | `ActionClassifier` — CONSTITUENT / EXCEPTIONAL / CONSISTENT |
| `drama_manager.py` | `DramaManager` — accommodation engine with depth limit |
| `narrator.py` | `OutputNarrator` — period-voice narration |
| `game.py` | Main CLI game loop, save/load |
| `prompts/` | Seven LLM prompt template files |
| `tests/test_accommodation.py` | Three accommodation integration tests |
| `world.json` | Serialised world map (generated on first run) |
| `phase2_llm.log` | JSON-Lines debug log of every LLM call |
