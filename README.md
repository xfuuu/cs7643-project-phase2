# AI Crime Mystery Story Generation System

**Team Name:** Dreamy Whales  
**System Name:** AI Crime Mystery Story Generation System  
**Project Template / Framework:** Template 3 — Story Planning with LLMs (planning → validation → repair/backtracking).


## 1. Project Summary

This project is a structured AI story-planning system for generating closed-circle crime mysteries.  
Instead of asking an LLM to directly write a full story in one step, the system separates generation into multiple explicit stages:

1. Generate a hidden **Case Bible** (ground truth).
2. Compile the case into a machine-checkable **fact graph**.
3. Generate a structured **investigation plot plan** with 15+ plot beats.
4. Validate the plan with deterministic checks.
5. Repair the plan if validation fails.
6. Realize the validated plan as a readable story.

The system is designed to emphasize:

- hidden truth vs. revealed investigation
- structure before prose
- explicit evidence chains
- deterministic validation and repair

## 2. System Architecture

The pipeline is centered on three structured intermediate representations:

- **CaseBible**
  - The hidden truth of the case.
  - Includes investigator, victim, culprit, suspects, motive, method, timeline, evidence, red herrings, and culprit evidence chain.

- **FactTriple**
  - A fact-graph representation compiled from the Case Bible.
  - Used to make the generated case more machine-checkable.

- **PlotPlan**
  - A structured investigation plan made of `PlotStep` objects.
  - Represents how the investigator gradually uncovers the truth.

Final story text is produced only after these representations are created and checked.

### End-to-end flow

```text
setting.txt
  ->
CaseBibleGenerator
  ->
CaseBible
  ->
FactGraphBuilder
  ->
fact_graph
  ->
PlotPlanner
  ->
PlotPlan
  ->
Validator
  ->
Repair (if needed)
  ->
StoryRealizer
  ->
story.txt + JSON outputs
```

## 3. Main Files

- `main.py`
  - CLI entry point.
  - Parses arguments and runs the full pipeline.

- `pipeline.py`
  - Main orchestration file.
  - Connects generation, fact compilation, planning, validation, repair, realization, and saving outputs.

- `models.py`
  - Defines all major dataclasses:
    - `Character`
    - `EvidenceItem`
    - `TimelineEvent`
    - `RedHerring`
    - `CaseBible`
    - `FactTriple`
    - `PlotStep`
    - `PlotPlan`
    - `ValidationReport`

- `llm_interface.py`
  - Defines the LLM abstraction layer.
  - Includes:
    - `MockLLMBackend`
    - `GeminiLLMBackend`

- `generators/case_bible_generator.py`
  - Generates the hidden Case Bible from the external setting file and the LLM.

- `builders/fact_graph_builder.py`
  - Converts the Case Bible into fact triples.

- `planners/plot_planner.py`
  - Produces the investigation plan.
  - Uses an LLM-first strategy with a rule-based fallback.

- `validators/validator.py`
  - Runs deterministic checks on the plot plan.

- `repair/repair_operator.py`
  - Dynamically patches a plot plan when validation fails.

- `realization/story_realizer.py`
  - Converts the final structured plan into readable story text.

- `generators/setting.txt`
  - External setting and task constraints for case generation.

## 4. How to Run

### Requirements

- Python 3.10+
- Internet access for Gemini API calls if using the default pipeline

### Run command

From the project root:

```bash
python main.py --gemini-api-key "YOUR_GEMINI_API_KEY"
```

Optional:

```bash
python main.py --gemini-api-key "YOUR_GEMINI_API_KEY" --output-dir outputs
```

### Expected result

After a successful run, the system writes:

- `outputs/case_bible.json`
- `outputs/fact_graph.json`
- `outputs/plot_plan.json`
- `outputs/validation_report.json`
- `outputs/story.txt`

It also prints basic status information in the terminal, including whether validation passed.

## 5. Runtime and API Notes

### Typical runtime

Typical runtime for one complete run is approximately:

- **20-60 seconds** for a normal run
- potentially longer if API latency is high

This depends mainly on:

- Gemini API response time
- prompt length
- story realization length

### API usage

The current default pipeline uses the Gemini backend for:

1. Case Bible generation
2. Plot plan generation
3. Story realization

So a typical run makes **three text-generation API calls**.

### Cost estimation

For this project, a full run uses three Gemini text calls:

1. Case Bible generation
2. Plot plan generation
3. Story realization

To make the estimate concrete, this README uses the **current code prompts** and the **current example outputs in `outputs/`**.

#### Pricing basis

The code calls:

- `gemini-flash-latest`

For a concrete paid-tier estimate, we use the current **Gemini 2.0 Flash Standard** pricing listed by Google AI for Developers:

- **Input:** `$0.10 / 1,000,000 tokens`
- **Output:** `$0.40 / 1,000,000 tokens`

Official references:

- Pricing page: https://ai.google.dev/pricing
- Model page: https://ai.google.dev/gemini-api/docs/models

#### Token estimation method

The current code does not record token usage metadata from the API response, so the estimate below uses a common approximation:

- **estimated tokens ≈ characters / 4**

This is not exact tokenizer accounting, but it is close enough for a submission-level cost estimate and is based on the actual prompts and outputs used by the current system.

#### Measured prompt sizes from the current system

Using the current code and current generated artifacts:

- **Case Bible prompt**
  - `5,170` characters
  - estimated tokens: `5,170 / 4 = 1,292`

- **Plot plan prompt**
  - `14,444` characters
  - estimated tokens: `14,444 / 4 = 3,611`

- **Story realization prompt**
  - `13,345` characters
  - estimated tokens: `13,345 / 4 = 3,336`

Total estimated input tokens:

- `1,292 + 3,611 + 3,336 = 8,239`

#### Measured output sizes from the current run

Using the current saved outputs:

- **Case Bible JSON**
  - compact JSON length: `11,076` characters
  - estimated tokens: `11,076 / 4 = 2,769`

- **Plot plan JSON**
  - compact JSON length: `8,081` characters
  - estimated tokens: `8,081 / 4 = 2,020`

- **Final story text**
  - `7,603` characters
  - estimated tokens: `7,603 / 4 = 1,901`

Total estimated output tokens:

- `2,769 + 2,020 + 1,901 = 6,690`

#### Cost calculation

Input cost:

- `8,239 / 1,000,000 * $0.10 = $0.0008239`

Output cost:

- `6,690 / 1,000,000 * $0.40 = $0.0026760`

Estimated total cost per complete run:

- `$0.0008239 + $0.0026760 = $0.0034999`

Rounded practical estimate:

- **about $0.0035 per run**
- equivalently, **about 0.35 cents for 100 runs**
- or **about $3.50 for 1,000 runs**

If the run is covered by a free tier, the effective cost may be `$0`, but the paid-tier estimate above reflects the current system much more precisely than a generic “very low cost” statement.

These numbers can be reproduced directly in this repository with:

```bash
python3 count_cost_chars.py
```

### API key note

The pipeline now expects the Gemini API key as a command-line argument:

```bash
python main.py --gemini-api-key "YOUR_GEMINI_API_KEY"
```

A Gemini API key typically looks like a long alphanumeric string beginning with `AIza`, for example:

```text
AIzaSy................................
```

The exact length may vary, but it is usually a long single-line token.  
The backend implementation is in `llm_interface.py`.

## 6. Output Files

- **`case_bible.json`**
  - Hidden truth layer.
  - Contains the actual culprit, motive, method, and true sequence of events.

- **`fact_graph.json`**
  - Structured fact representation compiled from the Case Bible.

- **`plot_plan.json`**
  - Structured investigation plan with ordered plot steps.

- **`validation_report.json`**
  - Validation result for the final plot plan.

- **`story.txt`**
  - Final realized mystery story in natural language.

## 7. Representative Example Output

This repository includes a complete example run in `outputs/`.

### Example story

- Story file: `outputs/story.txt`
- Current example title: **The Monkshood Masquerade**

### Example plot plan

The current example plan contains **16 structured plot points**, satisfying the rubric requirement of 15+ substantial plot beats.

Representative plot points from `outputs/plot_plan.json`:

1. **The Witness Fails to Appear**  
   Arthur Penhaligon discovers Sir Alistair Thorne dead in the study.
2. **A Room Disturbed**  
   Arthur finds the poisoned silver flask and a torn ribbon.
3. **The Household Gathers**  
   The suspects assemble and early reactions are observed.
4. **The Silent Library**  
   Lady Elspeth's alibi is checked and shown to be false.
5. **The Weapon in the Ashes**  
   A hunting knife is found in the study hearth.
6. **The Heir's Panic**  
   Julian is questioned about the knife and ribbon.
7. **The Muddy Terrace**  
   Julian's terrace alibi is physically tested and rejected.
8. **The Motive of Debt**  
   Julian's gambling debt ledger creates a strong false theory.
9. **The Bloodless Wound**  
   Arthur realizes the stabbing happened after death.
10. **The Doctor's Deception**  
    Dr. Vance is caught hiding a blackmail note.
11. **The Loyal Wife**  
    Eleanor is interviewed and presents a controlled, incomplete story.
12. **The Gardener's Secret**  
    A stained glove in the conservatory links the poison to plant handling.
13. **The Beaded Handbag**  
    A monkshood petal is found in Eleanor's handbag.
14. **The Midnight Reckoning**  
    Arthur reconstructs the true sequence and motive.
15. **The Final Mask Removed**  
    The confrontation assembles the key evidence chain.
16. **A Bitter Vintage**  
    Eleanor confesses and the case resolves.

This example demonstrates:

- at least 4 suspects
- at least 8 evidence items
- at least 2 explicit alibi checks
- a red herring arc
- an interference event
- a final confrontation grounded in evidence

## 8. Validation and Repair

The system does not rely only on LLM output. It also includes deterministic post-processing:

- **Validation**
  - checks minimum suspects, evidence count, plot-step count
  - checks presence of alibi checks, red herring, interference, and confrontation
  - checks whether the culprit evidence chain appears in the plan
  - checks basic time ordering

- **Repair**
  - dynamically adds missing plot beats if validation fails
  - can patch missing alibi steps, red herring steps, confrontation steps, and missing evidence-chain coverage

This makes the pipeline more robust than a single-shot generation approach.

## 9. Code Completion and Inspectability

The code is organized so that an instructor can trace the architecture directly in the repository:

- generation logic: `generators/case_bible_generator.py`
- fact compilation: `builders/fact_graph_builder.py`
- planning logic: `planners/plot_planner.py`
- validation logic: `validators/validator.py`
- repair logic: `repair/repair_operator.py`
- story realization: `realization/story_realizer.py`
- orchestration: `pipeline.py`

Representative architectural flow is therefore easy to inspect in code.

## 10. Summary

This submission implements a complete structured mystery-generation pipeline that:

- runs end-to-end
- uses explicit intermediate representations
- validates and repairs its own plan
- produces both machine-readable outputs and a readable final story

It is intended as a compact but functional course-project system for AI-assisted crime-mystery story planning and generation.
