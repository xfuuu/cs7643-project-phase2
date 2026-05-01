# AI Crime Mystery Story Generation System

A runnable, "structured crime-mystery story generation system" intended for course-project submission.

This README is **not** a marketing document for end users. It is written for developers / the student themselves, and explains **what this repository actually implements, how to run it, how the data flows, where the implementation has been simplified, and where it is still limited**.

The text below is written strictly against the current repository code. It does not describe modules, interfaces, or behaviors that are not in the codebase.

---

## 1. Project Overview

### 1.1 What problem this project tries to solve

The problem this project tries to solve is **not** "have a large language model directly write a detective novel." Instead it is:

- First generate a **hidden case ground truth**.
- Compile that ground truth into **structured facts**.
- Generate a **structured investigation plan**.
- Run a **deterministic check** against the plan.
- When necessary, **locally repair** the plan.
- Finally render the structured plan as a **readable story text**.

The system cares not just about whether the output "reads like a novel," but also about:

- whether the truth is structurally clear,
- whether the evidence chain is explicit,
- whether the investigation process is verifiable, and
- whether the output can be consumed by downstream modules.

### 1.2 The overall idea behind the system

The main pipeline consists of three layers of structured intermediate representations:

1. `CaseBible`
   - Hidden-truth layer.
   - Stores the ground truth of the case: investigator, victim, culprit, suspects, motive, method, true_timeline, evidence_items, red_herrings, culprit_evidence_chain.

2. `FactTriple`
   - Fact-graph layer.
   - Compiles the `CaseBible` into machine-checkable fact triples.

3. `PlotPlan`
   - Investigation-process layer.
   - Uses a sequence of structured `PlotStep` objects to represent "how the detective gradually approaches the truth."

Finally, the `StoryRealizer` converts the `PlotPlan` into natural-language story text.

### 1.3 Why this is not just text generation

The system is not a single-hop prompt → prose generator, because:

- The upstream stage first generates a structured `CaseBible`.
- A structured `FactTriple` set is then generated.
- The investigation process is first expressed as a structured `PlotPlan`.
- `validator.py` checks that the plan satisfies the project requirements.
- `repair_operator.py` can patch the plan locally on failure.
- Text is only the final realization step.

So the core idea is:

**Structured generation + deterministic validation + local repair + final narrative realization.**

---

## 2. End-to-End Project Flow

### 2.1 Full flow from entry to output

The actual execution order of the current system is:

```text
python main.py
  ->
main.py parses CLI arguments
  ->
CrimeMysteryPipeline(...)
  ->
pipeline.run()
  ->
CaseBibleGenerator.generate()
  ->
CaseBible
  ->
FactGraphBuilder.build(case_bible)
  ->
fact_graph
  ->
PlotPlanner.build_plan(case_bible, fact_graph)
  ->
initial_plot_plan
  ->
PlotPlanValidator.validate(case_bible, initial_plot_plan)
  ->
if invalid:
    PlotPlanRepairOperator.repair(case_bible, initial_plot_plan, report)
    ->
    PlotPlanValidator.validate(case_bible, repaired_plan)
  ->
StoryRealizer.realize(case_bible, final_plot_plan)
  ->
save outputs/*.json and outputs/story.txt
```

### 2.2 Understanding it as "input → intermediate representation → validation → repair → output"

The whole pipeline can be read as:

```text
Inputs
  - generators/setting.txt
  - Gemini / Mock LLM backend

Hidden-truth layer
  - CaseBible

Structured-fact layer
  - fact_graph: list[FactTriple]

Investigation-plan layer
  - PlotPlan

Validation layer
  - ValidationReport

Repair layer
  - repaired PlotPlan (when the initial plan does not pass validation)

Final-output layer
  - story.txt
  - several structured JSON files
```

### 2.3 How `main.py` and `pipeline.py` drive the whole flow

[main.py](/Users/yuezhao/Documents/New%20project/main.py) is intentionally light. It only:

- parses `--output-dir` and `--seed`,
- creates a `CrimeMysteryPipeline` and calls `run()`.

[pipeline.py](/Users/yuezhao/Documents/New%20project/pipeline.py) is the real orchestration center. It:

- initializes the Gemini / Mock backends,
- initializes the generation, building, planning, validation, repair, and realization modules,
- orchestrates the call order, and
- saves intermediate results to `outputs/`.

### 2.4 What the current version actually does

The current version is no longer the early "debug mode." It runs the full pipeline:

- `CaseBible` generation
- `fact_graph` construction
- `plot_plan` generation
- `validator` checks
- conditional `repair`
- story realization
- saving of all output files

This is different from earlier debug-only stages; this README reflects the current code.

---

## 3. Source-Tree Layout

```text
.
├── builders/
│   └── fact_graph_builder.py
├── generators/
│   ├── case_bible_generator.py
│   └── setting.txt
├── planners/
│   └── plot_planner.py
├── realization/
│   └── story_realizer.py
├── repair/
│   └── repair_operator.py
├── validators/
│   └── validator.py
├── outputs/
│   ├── case_bible.json
│   ├── fact_graph.json
│   ├── plot_plan.json
│   ├── validation_report.json
│   └── story.txt
├── llm_interface.py
├── main.py
├── models.py
├── pipeline.py
└── README.md
```

### [models.py](/Users/yuezhao/Documents/New%20project/models.py)

The schema center of the project.
Almost every data object passed between major modules is defined here, including:

- `Character`
- `EvidenceItem`
- `TimelineEvent`
- `RedHerring`
- `CaseBible`
- `FactTriple`
- `PlotStep`
- `PlotPlan`
- `ValidationIssue`
- `ValidationReport`

If you want to understand the project's data flow, this file is one of the most important starting points.

### [llm_interface.py](/Users/yuezhao/Documents/New%20project/llm_interface.py)

Unified LLM interface layer.

This file defines:

- `LLMBackend`
  - Abstract interface
- `MockLLMBackend`
  - A locally-runnable mock backend
- `GeminiLLMBackend`
  - Backend that calls the real Gemini API

This way, upstream modules only depend on `generate(prompt) -> LLMResponse` and not on any concrete provider.

### [generators/case_bible_generator.py](/Users/yuezhao/Documents/New%20project/generators/case_bible_generator.py)

Generates the hidden-truth `CaseBible`.

The current implementation no longer hard-codes cases. Instead it:

1. Reads [setting.txt](/Users/yuezhao/Documents/New%20project/generators/setting.txt).
2. Builds a strict-JSON prompt.
3. Calls the LLM to generate a case blueprint.
4. Locally parses the JSON.
5. Converts it into a `CaseBible` dataclass.

This is the most upstream generator in the system.

### [generators/setting.txt](/Users/yuezhao/Documents/New%20project/generators/setting.txt)

External setting file.

It is not a one-line setting description but a constraint specification for case generation, including:

- era and technology limits,
- closed-circle / sealed-manor setting,
- detective must already be on-site, invited prior to the crime,
- fair-play deduction style,
- requirements for at least 4 suspects, 8 evidence items, 1 red herring, a long investigation arc, etc.

### [builders/fact_graph_builder.py](/Users/yuezhao/Documents/New%20project/builders/fact_graph_builder.py)

Compiles the `CaseBible` into a list of `FactTriple`s.

It does not do free-form generation but a deterministic transformation:

- character facts,
- motive / method facts,
- timeline facts,
- evidence facts,
- red-herring facts.

It also infers a few key times from `true_timeline`, e.g.:

- the victim's time of death,
- the time the culprit executed their method,
- each suspect's activity time window.

### [planners/plot_planner.py](/Users/yuezhao/Documents/New%20project/planners/plot_planner.py)

Generates the `PlotPlan`.

The current implementation is not single-mode. It is:

- **LLM first**
  - Asks Gemini to output a structured JSON plot plan first.
- **Rule-based fallback**
  - Falls back to the rule-based planner when the LLM fails, the JSON is invalid, or parsing throws.

To prevent LLM time-marker drift, this file now also includes **local time post-processing** that re-anchors step times to around the case-discovery time, fixing cases where an overnight crime was written as `AM`.

### [validators/validator.py](/Users/yuezhao/Documents/New%20project/validators/validator.py)

Performs deterministic structural validation.

It does not judge literary quality; it checks:

- number of suspects,
- number of evidence items,
- number of plot steps,
- presence of `alibi_check` / `red_herring` / `interference`,
- presence of a `confrontation` and that it references the key evidence,
- whether `evidence_id`s are valid,
- whether the timeline is monotonically increasing.

### [repair/repair_operator.py](/Users/yuezhao/Documents/New%20project/repair/repair_operator.py)

Applies dynamic patches when validation fails.

It does not rewrite the plot from scratch. Instead, given:

- the `CaseBible`,
- the existing `PlotPlan`, and
- the `ValidationReport`,

it patches the missing pieces, e.g.:

- missing alibi check,
- missing red herring,
- missing interference,
- culprit evidence chain not covered,
- missing confrontation,
- not enough steps.

### [realization/story_realizer.py](/Users/yuezhao/Documents/New%20project/realization/story_realizer.py)

Realizes the structured plan as story text.

It supports two paths:

- `MockLLMBackend`
  - Simply concatenates structured information.
- `GeminiLLMBackend`
  - Uses a prompt to convert `CaseBible + PlotPlan` into a more natural short-form mystery narrative.

### [pipeline.py](/Users/yuezhao/Documents/New%20project/pipeline.py)

The orchestration center.

The current real behavior is:

- `CaseBibleGenerator` uses `GeminiLLMBackend`.
- `PlotPlanner` uses `GeminiLLMBackend`.
- `StoryRealizer` uses `GeminiLLMBackend`.
- `MockLLMBackend` is still instantiated to make future switching or debugging easy.

### [main.py](/Users/yuezhao/Documents/New%20project/main.py)

Command-line entry point.

It only:

- parses arguments,
- creates the pipeline,
- calls `run()`,
- prints the resulting paths and basic info.

---

## 4. Core Data Structures / Schema

### 4.1 `Character`

Defined in [models.py](/Users/yuezhao/Documents/New%20project/models.py).

Fields:

- `name`
  - Person's name.
- `role`
  - `victim` / `suspect` / `culprit`.
- `description`
  - Character profile.
- `relationship_to_victim`
  - Relationship to the victim.
- `means`
  - Method or potential method.
- `motive`
  - Motive.
- `opportunity`
  - Opportunity to commit the crime.
- `alibi`
  - Alibi statement.

Used in:

- `CaseBibleGenerator` (constructed during generation).
- `FactGraphBuilder` (extracts character facts).
- `PlotPlanner` (organizes the order in which suspects are investigated).
- `StoryRealizer` (converts character info into narrative tension).

### 4.2 `EvidenceItem`

Fields:

- `evidence_id`
- `name`
- `description`
- `location_found`
- `implicated_person`
- `reliability`
- `planted`

Role:

- Represents structured evidence.
- Converted into triples in `fact_graph`.
- Referenced by `evidence_ids` in `plot_plan`.
- Forms the key evidence chain in the confrontation.

### 4.3 `TimelineEvent`

Fields:

- `event_id`
- `time_marker`
- `summary`
- `participants`
- `location`
- `public`

Role:

- Represents the real timeline of the hidden-truth layer.
- `FactGraphBuilder` infers times from these events.
- `PlotPlanner` extracts discovery / death / concealment / tension events from this layer.

### 4.4 `RedHerring`

Fields:

- `herring_id`
- `suspect_name`
- `misleading_evidence_ids`
- `explanation`

Role:

- Explicitly represents a misleading arc.
- `PlotPlanner` tries to fold it into the investigation plan.
- `validator` ensures at least one `red_herring` exists.
- `repair` can add a red-herring step when one is missing.

### 4.5 `CaseBible`

The most central data object in the project.

Fields:

- `setting`
- `investigator`
- `victim`
- `culprit`
- `suspects`
- `motive`
- `method`
- `true_timeline`
- `evidence_items`
- `red_herrings`
- `culprit_evidence_chain`

Meaning:

- Stores the hidden truth of the case.
- Strictly distinct from the final investigation process and story text.

Position in the data flow:

```text
setting.txt + LLM
  ->
CaseBibleGenerator
  ->
CaseBible
  ->
FactGraphBuilder / PlotPlanner / StoryRealizer / Validator / Repair
```

### 4.6 `FactTriple`

Fields:

- `subject`
- `relation`
- `object`
- `time`
- `source`

Notes:

- The earlier `confidence` field has been removed in the current version.
- `FactTriple` is now leaner and emphasizes structure over scoring.

Role:

- Provides a machine-processable fact-graph layer.
- Currently used mainly by `PlotPlanner` as an evidence-existence helper rather than a deep reasoning engine.

### 4.7 `PlotStep`

Fields:

- `step_id`
- `phase`
- `kind`
- `title`
- `summary`
- `location`
- `participants`
- `evidence_ids`
- `reveals`
- `timeline_ref`

Role:

- Represents a structured plot beat in the investigation.
- The basic unit of `PlotPlan`.
- The direct subject of `validator` checks.

### 4.8 `PlotPlan`

Fields:

- `investigator`
- `steps`

Role:

- Represents the detective's structured investigation plan.
- The direct input of `StoryRealizer`.
- The direct subject of `validator` / `repair`.

### 4.9 `ValidationIssue` and `ValidationReport`

`ValidationIssue`:

- `code`
- `message`
- `step_id`

`ValidationReport`:

- `is_valid`
- `issues`
- `metrics`

Role:

- Reports whether the `PlotPlan` meets the course requirements.
- Provides the basis on which `repair_operator.py` repairs the plan.

---

## 5. Per-Module Detail

### 5.1 `models.py`

Main responsibilities:

- Defines all the data structures used across the project.

Inputs:

- None at runtime; this file provides the schema only.

Outputs:

- All dataclass type definitions.

Internal logic:

- No complex logic; mostly schema definitions.
- Includes a `to_data()` helper to recursively convert a dataclass to plain Python data.

Dependencies:

- Standard library `dataclasses`, `typing`.

Called by:

- Almost every module.

System position:

- The data foundation of the project.

### 5.2 `llm_interface.py`

Main responsibilities:

- Provides a unified LLM-call interface for the project.

Key classes:

- `LLMBackend`
- `LLMResponse`
- `MockLLMBackend`
- `GeminiLLMBackend`

Inputs:

- A prompt string.

Outputs:

- `LLMResponse(text=...)`.

Internal logic:

- `MockLLMBackend` returns preset short text based on prompt keywords.
- `GeminiLLMBackend` calls the Gemini API via `urllib.request`.

Dependencies:

- Standard library `json`, `urllib`, `os`.

Called by:

- `CaseBibleGenerator`
- `PlotPlanner`
- `StoryRealizer`
- `pipeline.py`

System position:

- Model-call infrastructure layer.

Implementation notes:

- The current `GeminiLLMBackend` constructor still has a hard-coded API key for local convenience; this is not a production-grade pattern.
- A more reasonable approach would be to read it from an environment variable first.

### 5.3 `generators/case_bible_generator.py`

Main responsibilities:

- Generates the hidden-truth `CaseBible`.

Inputs:

- `setting.txt`
- An `LLMBackend`.

Outputs:

- `CaseBible`.

Core internal logic:

1. Reads `setting.txt`.
2. Builds a strict-JSON prompt.
3. Calls `llm.generate(prompt)`.
4. Extracts a JSON object from the returned text.
5. Verifies the top-level shape is complete.
6. Builds the following piece by piece:
   - `Character`
   - `TimelineEvent`
   - `EvidenceItem`
   - `RedHerring`
7. Assembles them into a `CaseBible`.

Dependencies:

- `llm_interface.py`
- `models.py`

Called by:

- `pipeline.py`

System position:

- The most upstream generation module in the system.

Implementation notes:

- This is not free-form text generation; it is "LLM emits a JSON blueprint + local parsing."
- This design lets upstream output be consumed structurally by downstream modules.

### 5.4 `builders/fact_graph_builder.py`

Main responsibilities:

- Compiles the `CaseBible` into a list of `FactTriple`s.

Inputs:

- `CaseBible`.

Outputs:

- `list[FactTriple]`.

Core internal logic:

1. Sorts `true_timeline` chronologically.
2. Infers:
   - victim's time,
   - method's time,
   - suspect time windows.
3. Generates:
   - case-setting facts,
   - culprit / victim facts,
   - suspect attribute facts,
   - timeline facts,
   - evidence facts,
   - red-herring facts.

Dependencies:

- `models.py`
- Standard library `re`.

Called by:

- `pipeline.py`

System position:

- The structured-fact layer between `CaseBible` and `PlotPlanner`.

Implementation notes:

- Time inference is still heuristic, not LLM- or theorem-prover-based reasoning.
- It is, however, more reasonable than the earliest hard-coded version.

### 5.5 `planners/plot_planner.py`

Main responsibilities:

- Generates a `PlotPlan`.

Inputs:

- `CaseBible`
- Optional `fact_graph`.

Outputs:

- `PlotPlan`.

Core internal logic:

#### LLM branch

1. Builds a plot prompt from the `CaseBible` and parts of `fact_graph`.
2. Asks the model to emit strict JSON whose top-level form is `{"steps": [...]}`.
3. Parses each `step` locally.
4. Filters out invalid `evidence_ids`.
5. Normalizes `step_id`s.
6. Performs time post-processing to fix unreasonable `AM/PM` markers.

#### Fallback branch

If the LLM branch fails, the rule-based planner takes over:

- Extracts discovery / death / concealment / tension events from `true_timeline`.
- Combines suspects / red herrings / culprit evidence chain.
- Generates a `PlotPlan` whose skeleton is fixed but whose contents are filled dynamically.

Dependencies:

- `llm_interface.py`
- `models.py`

Called by:

- `pipeline.py`

System position:

- The core module that bridges the truth layer to the investigation-process layer.

Implementation notes:

- This is a hybrid planner, not a pure-LLM or pure-rule system.
- Its strengths are higher readability while keeping fallback stability.

### 5.6 `validators/validator.py`

Main responsibilities:

- Performs deterministic structural validation on a `PlotPlan`.

Inputs:

- `CaseBible`
- `PlotPlan`

Outputs:

- `ValidationReport`.

Core internal logic:

- Checks number of suspects.
- Checks number of evidence items.
- Checks number of plot steps.
- Checks number of `alibi_check`s.
- Checks that at least one `red_herring` exists.
- Checks that at least one `interference` exists.
- Checks that the culprit evidence chain is referenced.
- Checks that a `confrontation` exists and references the key evidence.
- Checks that `step_id`s are contiguous.
- Checks that all `evidence_id`s actually exist.
- Checks that timeline order is monotonic.

Dependencies:

- `models.py`

Called by:

- `pipeline.py`
- A precondition for `repair_operator.py` to be invoked.

System position:

- The quality gate between `PlotPlan` and `Repair`.

Implementation notes:

- Strong at structural checks.
- Weaker at deep narrative semantics or fine-grained fact drift.

### 5.7 `repair/repair_operator.py`

Main responsibilities:

- Patches a plan dynamically when validation fails.

Inputs:

- `CaseBible`
- The original `PlotPlan`
- `ValidationReport`

Outputs:

- A repaired `PlotPlan`.

Core internal logic:

- First removes invalid evidence ids.
- Then dynamically patches based on issue codes:
  - alibi steps,
  - red herring,
  - interference,
  - evidence-chain step,
  - culprit-support step,
  - confrontation,
  - minimum step count.
- Finally renumbers and, when necessary, re-orders times.

Dependencies:

- `models.py`

Called by:

- `pipeline.py`

System position:

- The local-repair layer right after `Validator`.

Implementation notes:

- It is no longer a fixed-template patcher as in earlier versions.
- It is still a heuristic patcher, not a re-planner.

### 5.8 `realization/story_realizer.py`

Main responsibilities:

- Converts a structured plan into story text.

Inputs:

- `CaseBible`
- `PlotPlan`

Outputs:

- The final story string.

Core internal logic:

#### Mock branch

- Concatenates `PlotStep`s paragraph by paragraph.
- Generates a simple title.
- Produces structured but unnatural exposition text.

#### Gemini branch

- Builds a long prompt.
- Hands the `CaseBible`'s hidden truth and the `PlotPlan` steps together to the model.
- Explicitly requires:
  - the culprit must not be changed,
  - the motive, method, and key evidence chain must not be changed,
  - the structured plan must be realized as natural narrative.

Dependencies:

- `llm_interface.py`
- `models.py`

Called by:

- `pipeline.py`

System position:

- The most downstream text-realization layer of the pipeline.

Implementation notes:

- The current quality of `story.txt` is mainly determined by the Gemini branch.
- The Mock branch exists primarily as a runnable placeholder when no external API is available.

### 5.9 `pipeline.py`

Main responsibilities:

- Orchestrates the entire pipeline.

Inputs:

- `output_dir`
- `seed`

Outputs:

- A dictionary holding all result objects.

Core internal logic:

1. Initializes the modules.
2. Generates the `CaseBible`.
3. Builds the `fact_graph`.
4. Generates the `PlotPlan`.
5. Validates.
6. Repairs and re-validates if needed.
7. Generates the story text.
8. Saves all output files.

Called by:

- `main.py`

System position:

- The orchestration layer of the whole application.

### 5.10 `main.py`

Main responsibilities:

- CLI entry point.

Key functions:

- `parse_args()`
- `main()`

Inputs:

- Command-line arguments.

Outputs:

- A short status printout to the terminal.

System position:

- The outermost launcher.

---

## 6. What Actually Happens During One Run

If you execute:

```bash
python main.py
```

the program proceeds in the following order:

1. [main.py](/Users/yuezhao/Documents/New%20project/main.py) parses arguments.
   - Default `output_dir = outputs`.
   - Default `seed = 7`.

2. `CrimeMysteryPipeline` is created.
   - `MockLLMBackend` is initialized.
   - `GeminiLLMBackend` is initialized.
   - All module instances are initialized.

3. `pipeline.run()` begins execution.

4. `CaseBibleGenerator.generate()` is called.
   - Reads [setting.txt](/Users/yuezhao/Documents/New%20project/generators/setting.txt).
   - Builds a strict-JSON case-generation prompt.
   - Calls Gemini.
   - Parses the response.
   - Converts it into a `CaseBible`.

5. `FactGraphBuilder.build(case_bible)` is called.
   - Reads the `CaseBible`.
   - Sorts `true_timeline`.
   - Infers key times.
   - Builds a `FactTriple` list.

6. `PlotPlanner.build_plan(case_bible, fact_graph)` is called.
   - If the LLM branch succeeds:
     - Gemini emits structured plot steps.
     - JSON is parsed.
     - Evidence ids are filtered.
     - Step ids are normalized.
     - `timeline_ref`s are corrected.
   - If it fails:
     - Falls back to the rule-based plan.

7. `PlotPlanValidator.validate(case_bible, initial_plot_plan)` is called.
   - Checks structural constraints.
   - Produces a `ValidationReport`.

8. If `ValidationReport.is_valid == False`:
   - `PlotPlanRepairOperator.repair(...)` is called.
   - The repaired `PlotPlan` is returned.
   - `validate()` is re-run.

9. `StoryRealizer.realize(case_bible, final_plot_plan)` is called.
   - The current main flow uses the Gemini branch.
   - Converts `CaseBible + PlotPlan` into a natural-language story.

10. The save functions are called:
    - `case_bible.json`
    - `fact_graph.json`
    - `plot_plan.json`
    - `validation_report.json`
    - `story.txt`

11. `main.py` prints the result info.

---

## 7. Output File Reference

The main files in the current `outputs/` directory:

### [case_bible.json](/Users/yuezhao/Documents/New%20project/outputs/case_bible.json)

Role:

- Stores the hidden-truth layer.

Contents include:

- investigator
- victim
- culprit
- suspects
- motive
- method
- true_timeline
- evidence_items
- red_herrings
- culprit_evidence_chain

This is the system's "most authoritative" version of the case; downstream modules treat it as the upstream source of truth.

### [fact_graph.json](/Users/yuezhao/Documents/New%20project/outputs/fact_graph.json)

Role:

- Stores the structured fact graph compiled from the `CaseBible`.

Better suited to:

- rule-based retrieval,
- structural checks,
- future extensibility for reasoning support.

### [plot_plan.json](/Users/yuezhao/Documents/New%20project/outputs/plot_plan.json)

Role:

- Stores the structured investigation plan.

This is not the final story; it is the intermediate layer. It contains the phase / kind / summary / evidence / reveals / timeline_ref of every investigation step.

### [validation_report.json](/Users/yuezhao/Documents/New%20project/outputs/validation_report.json)

Role:

- Stores the `validator`'s findings on the final plan.

It indicates:

- whether the plan passes,
- which checks failed (if any),
- basic statistics.

### [story.txt](/Users/yuezhao/Documents/New%20project/outputs/story.txt)

Role:

- Stores the final natural-language story text.

This is the most downstream readable output of the pipeline.

### Relationship between these files

Conceptually:

```text
case_bible.json
  -> truth layer

fact_graph.json
  -> structured compilation of the truth layer

plot_plan.json
  -> investigation-process layer

validation_report.json
  -> rule-based check report on the investigation layer

story.txt
  -> final narrative output based on the investigation plan
```

---

## 8. Validator and Repair Mechanism in Detail

### 8.1 Rules the validator checks

The current validator checks:

- at least 4 suspects,
- at least 8 evidence items,
- at least 15 plot steps,
- at least 2 `alibi_check`s,
- at least 1 `red_herring`,
- at least 1 `interference`,
- the culprit evidence chain is referenced in the plan,
- a `confrontation` step exists,
- the confrontation references the first 3 items of the key evidence chain,
- the culprit is supported in enough steps,
- `step_id`s are contiguous,
- all `evidence_id`s actually exist,
- `timeline_ref`s are monotonically increasing.

### 8.2 Why these rules matter

These rules map directly to the core requirements of the course project:

- It is not just a short, ad-hoc case.
- There must be an investigation structure.
- There must be a red herring.
- There must be alibi verification.
- The final reveal must be supported by an evidence chain.

### 8.3 How `repair` fixes the plan

If the plan does not pass, `repair` patches gaps based on `ValidationReport.issues`, e.g.:

- Insufficient alibi checks → fill in from suspects.
- Missing red herring → fill from `CaseBible.red_herrings`.
- Missing interference → add one centered on the culprit.
- Missing key evidence chain → add evidence-chain steps.
- Missing confrontation → add a confrontation.
- Not enough steps → add additional evidence/analysis steps.

### 8.4 Nature of the repair strategy

These repairs are essentially:

- **heuristic**,
- **structural-compliance-oriented**,
- **not a full re-planning of the investigation arc**.

So the goal of `repair` is "fix it just enough to pass," not "fix it for the best literary effect."

### 8.5 Limits of the current mechanism

- Does not rewrite the entire LLM plan.
- Does not optimize prose.
- Does not actively fix every subtle factual drift.
- Mostly focuses on "missing required items."

---

## 9. LLM / Mock Mechanism in Detail

### 9.1 What `llm_interface.py` actually does

It provides a unified interface to the rest of the project:

```python
class LLMBackend:
    def generate(self, prompt: str) -> LLMResponse:
        ...
```

This means upstream modules do not need to know whether the backend is:

- mock,
- Gemini,
- or some future model.

### 9.2 Role of the Mock backend

`MockLLMBackend` is still kept around. Its main roles are:

- to allow part of the logic to run without an external API,
- to act as an interface placeholder, and
- to simplify debugging flows that do not need real generation quality.

### 9.3 Why Gemini is the default

In the current `pipeline.py`:

- `CaseBibleGenerator` uses Gemini.
- `PlotPlanner` uses Gemini.
- `StoryRealizer` uses Gemini.

Reasons:

- `CaseBible` already depends on a real LLM emitting a JSON blueprint.
- `PlotPlan` now also has a dynamic LLM branch.
- `StoryRealizer` needs more natural prose.

### 9.4 What to change to swap in another model

The main change point is [llm_interface.py](/Users/yuezhao/Documents/New%20project/llm_interface.py):

- Add a new backend that implements `LLMBackend`.
- Switch the injected backend in [pipeline.py](/Users/yuezhao/Documents/New%20project/pipeline.py).

Upstream modules require no major changes because they only depend on the unified `generate(prompt)` interface.

---

## 10. Design Ideas Embodied in This Project

### 10.1 Hidden Truth vs Revealed Investigation

This is one of the most important design ideas in the current project.

- `CaseBible`
  - The hidden truth.
- `PlotPlan`
  - How the investigation gradually reveals the truth.

In other words:

- The truth is not directly exposed to the reader.
- What the reader sees is the investigation process, not the ground truth itself.

### 10.2 Structure Before Prose

The project first generates:

- `CaseBible`,
- `FactTriple`,
- `PlotPlan`.

Only at the very end is the story text generated.

This guarantees:

- The system does not "paper over" gaps with prose.
- The structure can be validated, repaired, and persisted.

### 10.3 Deterministic Validation

`validator.py` embodies the "rule-checking first" idea:

- Do not let the model judge itself.
- Explicitly check whether the project requirements are satisfied.

### 10.4 Local Repair Instead of Full Regeneration

`repair_operator.py` embodies the principle:

- Do not regenerate the whole plan on every failure.
- Instead, patch it locally.

This is more stable and more aligned with engineering practice.

### 10.5 Separation of Concerns

The project has clear responsibility boundaries:

- generator → hidden truth,
- builder → fact graph,
- planner → investigation plan,
- validator → rule checks,
- repair → patching,
- realizer → text output,
- pipeline → orchestration.

This is one of the most valuable structural strengths to keep.

---

## 11. Simplifications and Limitations of the Current Implementation

This section is important and should be honest in a course-project submission.

### 11.1 `FactGraphBuilder` is still heuristic

Although it has moved past the original hard-coded times, it still relies on:

- summary keywords,
- person names and action descriptions in the timeline.

It is not a strict semantic-reasoning system.

### 11.2 The validator focuses on structure, not deep semantics

It can detect:

- not enough steps,
- invalid evidence ids,
- missing confrontation.

It cannot necessarily detect:

- subtle fact drift between the plan text and the `CaseBible`,
- small natural-language details quietly rewritten by the LLM.

### 11.3 Repair is a heuristic patcher, not a re-planner

`repair` can patch gaps, but it does not guarantee:

- the most natural pacing,
- the most elegant narrative,
- realignment of every subtle fact.

### 11.4 The PlotPlanner's LLM output may still drift factually

Even with:

- a fallback,
- time post-processing,
- the validator,

the LLM may still:

- invent scene details not explicitly in the `CaseBible`,
- approximate rather than precisely reproduce certain time points.

### 11.5 `StoryRealizer` may inherit upstream drift

If the `PlotPlan` has slight drift, `story.txt` tends to narrativize that drift.

### 11.6 The Gemini backend is course-project grade

Strengths:

- minimal dependencies,
- runnable.

Limitations:

- no retry logic,
- timeout handling is simple,
- the API key is currently hard-coded as a default value, which is not best practice.

### 11.7 The Mock branch's quality is clearly weaker than the Gemini branch

This is not a bug; it is by design:

- Mock exists primarily to keep things runnable.
- Gemini is the main quality source in the current version.

---

## 12. How to Read This Project

If you are reading this repository for the first time, the recommended order is:

### Step 1: Read [pipeline.py](/Users/yuezhao/Documents/New%20project/pipeline.py)

Why:

- It tells you what the actual main flow is.
- You immediately learn the call order across modules.
- It is easier to build a global picture than reading any single file.

### Step 2: Read [models.py](/Users/yuezhao/Documents/New%20project/models.py)

Why:

- The project is heavily structure-driven.
- Without first understanding the schema, it is easy to miss the point in later modules.

### Step 3: Read [generators/case_bible_generator.py](/Users/yuezhao/Documents/New%20project/generators/case_bible_generator.py)

Why:

- This is the most upstream module.
- It explains "where the truth comes from."

### Step 4: Read [builders/fact_graph_builder.py](/Users/yuezhao/Documents/New%20project/builders/fact_graph_builder.py)

Why:

- It explains how the structured-fact layer is compiled from the truth layer.

### Step 5: Read [planners/plot_planner.py](/Users/yuezhao/Documents/New%20project/planners/plot_planner.py)

Why:

- It is currently one of the most complex modules.
- It contains an LLM planner, a fallback planner, and time-correction logic.

### Step 6: Read [validators/validator.py](/Users/yuezhao/Documents/New%20project/validators/validator.py) and [repair/repair_operator.py](/Users/yuezhao/Documents/New%20project/repair/repair_operator.py)

Why:

- Together they explain why this system is more than pure text generation.

### Step 7: Read [realization/story_realizer.py](/Users/yuezhao/Documents/New%20project/realization/story_realizer.py) last

Why:

- It is the output layer.
- Reading it last makes it easier to understand why it is "just the final hop."

---

## 13. How to Run

### 13.1 Environment requirements

- Python 3.10+
- Use a local Python environment compatible with the current repository.

The project has no heavy third-party dependencies; it relies mainly on the standard library.

### 13.2 Run command

From the project root, run:

```bash
python main.py
```

or:

```bash
python3 main.py
```

### 13.3 Optional arguments

```bash
python main.py --output-dir outputs --seed 7
```

Argument reference:

- `--output-dir`
  - Output directory.
- `--seed`
  - Seed for mock / random-related logic.

### 13.4 Configuration requirements

The current main flow uses `GeminiLLMBackend` by default.

So before running, make sure:

- the API key is available,
- the network can reach the Gemini API.

### 13.5 Mock-mode notes

Although `MockLLMBackend` is kept in the system, **the current main flow does not default to mock mode**. The current pipeline's main generation path uses Gemini.

---

## 14. Understanding the System Through One Example

The current `outputs/` directory already contains a real generated example.

### 14.1 Hidden-truth layer

In [case_bible.json](/Users/yuezhao/Documents/New%20project/outputs/case_bible.json) you can see:

- investigator: `Arthur Penhaligon`
- victim: `Sir Alistair Thorne`
- culprit: `Eleanor Vance`
- true method: poisoning a brandy flask with `Aconitine`
- red herring: `Julian Thorne`
- culprit evidence chain: `EV-03`, `EV-07`, `EV-01`

This represents "what the system actually believes is true about the case."

### 14.2 Investigation-plan layer

[plot_plan.json](/Users/yuezhao/Documents/New%20project/outputs/plot_plan.json) shows:

- how Arthur discovers the body,
- how he first suspects Julian,
- how he runs alibi checks,
- how he turns toward Eleanor through clues such as the conservatory / handbag / glove,
- how he closes the evidence chain in the confrontation.

This is not the final story; it is the investigation skeleton.

### 14.3 Text-realization layer

[story.txt](/Users/yuezhao/Documents/New%20project/outputs/story.txt) realizes the structured plan above as a more natural mystery narrative.

### 14.4 A real-world reminder about this example

The current example is broadly usable, but may still contain:

- minor approximate rewrites of times or details from `case_bible` in `plot_plan` or `story`.

This is exactly where the current system shows its course-project (rather than production) status.

---

## 15. Quick-Read Guide

If you want to understand the project as quickly as possible, open the files in this order:

### 1: [pipeline.py](/Users/yuezhao/Documents/New%20project/pipeline.py)

Read it first because it tells you:

- which modules the system actually runs,
- the actual execution order,
- which backend is currently the default.

### 2: [models.py](/Users/yuezhao/Documents/New%20project/models.py)

Read it second because the project is "data-structure driven." Only after understanding `CaseBible`, `FactTriple`, and `PlotPlan` can you really read the later modules.

### 3: [generators/case_bible_generator.py](/Users/yuezhao/Documents/New%20project/generators/case_bible_generator.py)

It explains:

- where the truth comes from,
- how the LLM is constrained at the top of the pipeline to emit JSON.

### 4: [planners/plot_planner.py](/Users/yuezhao/Documents/New%20project/planners/plot_planner.py)

This is one of the most important implementation files to focus on. It contains:

- LLM-driven plot generation,
- a fallback planner,
- local time correction.

### 5: [validators/validator.py](/Users/yuezhao/Documents/New%20project/validators/validator.py) and [repair/repair_operator.py](/Users/yuezhao/Documents/New%20project/repair/repair_operator.py)

Read these together — they explain why this project is not pure text generation.

### 6: [realization/story_realizer.py](/Users/yuezhao/Documents/New%20project/realization/story_realizer.py)

Read it last because it is mainly about turning the already-built structured content into prose.

---

## 16. Summary

The current version already has the core characteristics expected of a course-project submission:

- a clear set of structured intermediate representations,
- separation between the hidden-truth layer and the investigation-process layer,
- deterministic validation,
- local repair,
- real LLM integration,
- a complete output-file pipeline.

It also remains honest about its limitations:

- fact-graph time inference is still heuristic,
- the validator emphasizes structure rather than semantic review,
- the planner / realizer can still produce mild factual drift,
- the Gemini backend is course-project grade rather than production grade.

Positioned as:

**"a runnable, well-structured course-project prototype that demonstrates LLM + structured validation + local repair,"**

the current version stands up.
