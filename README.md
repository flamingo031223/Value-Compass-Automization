# Value Compass Report Automation

Automatically generates the **Value Compass Benchmark** research report from Excel benchmark data. Given a new round of LLM evaluation results, the pipeline detects what has changed versus the previous report, decides how to update each finding (preserve / adapt / refresh / flag), and produces a publication-ready PDF via an LLM writing agent.

> **For human researchers:** This tool significantly reduces the time required to produce each benchmark report cycle. Based on evaluation across multiple test runs, the pipeline reliably handles the majority of routine data updates and example replacements. However, **four specific findings — PropVsOpen F2, MFT F2, Families F1, and FULVA F1 — have shown unstable output across successive runs: the pipeline sometimes issues the correct instruction and sometimes does not, with no meaningful difference in the input data.** Because you cannot rely on a previous correct run as evidence that the current run is also correct, these findings require manual verification every cycle. All high-risk findings are clearly identified throughout this document.

---

## Table of Contents

1. [What This Pipeline Produces](#what-this-pipeline-produces)
2. [How It Reduces Your Workload](#how-it-reduces-your-workload)
3. [Architecture](#architecture)
4. [Agent Architecture: Roles and Information Flow](#agent-architecture-roles-and-information-flow)
5. [Directory Structure](#directory-structure)
6. [Setup](#setup)
7. [Usage](#usage)
8. [What the Pipeline Does Well](#what-the-pipeline-does-well)
9. [Known Weaknesses — Observed Failures Requiring Researcher Review](#known-weaknesses--observed-failures-requiring-researcher-review)
10. [Per-Finding Review Priority Guide](#per-finding-review-priority-guide)
11. [Azure Content Filter — Terminology Replacements](#azure-content-filter--terminology-replacements)
12. [Annotated Report: Understanding the Change Log](#annotated-report-understanding-the-change-log)
13. [Ground Truth YAML Format](#ground-truth-yaml-format)
14. [Evaluation Test Set](#evaluation-test-set)
15. [Adding a New Benchmark Round](#adding-a-new-benchmark-round)

---

## What This Pipeline Produces

Each pipeline run produces **two output files** for every benchmark round:

### 1. Main Report (`ValueCompass_Report.pdf`)

A publication-ready research report covering all evaluated LLMs across four value frameworks. The report is structured in two parts:

**Part 1 — Overall Perspectives (5 cross-cutting findings)**
| Finding | What it covers |
|---------|---------------|
| OV-F1 | LLMs' alignment with universal human values (Schwartz hierarchy) |
| OV-F2 | Western cultural value bias across model families |
| OV-F3 | Correlation between expressed values and practical model behaviors |
| OV-F4 | Overestimation of safety via static benchmarks vs. dynamic MFT |
| OV-F5 | Need for context-aware safety measurement |

**Part 2 — Detailed Section Findings**
| Section | Findings |
|---------|---------|
| Schwartz Theory of Basic Values | F1: Pan-cultural baseline match · F2: Pronounced value orientations · [NEW] F3–F4 |
| Moral Foundation Theory (MFT) | F1: Alignment training effect · F2: Nuanced per-dimension strengths · [NEW] F3–F4 |
| Safety Taxonomy | F1: Static benchmark ceiling · F2: Per-harm-category variation · [NEW] F3–F4 |
| LLM's Unique Value System (FULVA) | F1: User-oriented value preference · F2: Top-performing models · [NEW] F3–F4 |
| Proprietary vs. Open-Source | F1: Alignment training gap · F2: Value expression capability · [NEW] F3–F4 |
| LLM Families | F1: Intra-family similarity · F2: Inter-family variation · [NEW] F3–F4 |
| Reasoning vs. Normal Models | F1: Safety performance comparison · F2: Value expression strength · [NEW] F3–F4 |

Each section also generates additional `[NEW]` findings based on patterns detected in the new data. These are clearly labelled and represent candidates for inclusion — **Mentor review is required before they appear in the final published report.**

### 2. Annotated Report (`ValueCompass_Report_Annotated.pdf`)

An identical report with change documentation overlaid:

- **Green text annotations** appear below each modified finding, explaining what changed and why, referencing the specific data that triggered the update
- **Yellow highlights** mark the specific data elements that were replaced within the text: model names, numerical scores, dimension names, ranking positions, and qualifier words (e.g. "significantly" → "slightly")
- Unchanged findings carry no annotation
- `[NEW]` findings are annotated with their data sources and the reasoning that led to their generation

The annotated report is the primary tool for efficient human review: start there, read only the green annotations, and focus your edits on the highlighted items.

---

## How It Reduces Your Workload

Without automation, producing each benchmark report requires a researcher to:

1. Compute rankings, means, and comparisons across ~30 models and 4 frameworks
2. Check whether each of the ~19 core findings still holds
3. Identify which model names, scores, and example pairs need updating
4. Detect new patterns worth reporting
5. Rewrite affected paragraphs while maintaining the original analytical voice

**The pipeline handles steps 1–4 fully automatically**, and produces first-draft text for step 5 that typically requires only targeted edits rather than full rewrites. Across test evaluations, the pipeline correctly handles approximately **70–75% of all finding updates** without any human correction needed. The remaining 25–30% require researcher attention, concentrated in the specific areas described in the [Known Weaknesses](#known-weaknesses--where-to-focus-your-review) section below.

---

## Architecture

The pipeline runs in 7 sequential stages:

```
Excel Input
    │
    ▼
[1] load_data          Load sheets: Schwartz, MFT, Risk, FULVa, Model Info
    │
    ▼
[2] analytics          Compute per-finding statistics
    │                  (rankings, group comparisons, Spearman correlations, ...)
    ▼
[3] plot               Generate figures saved to output/figures/
    │
    ▼
[4] GroundTruthStore   Load human-authored baseline findings from ground_truth/*.yaml
    │
    ▼
[5] FindingChangeDetector + FindingVerifier
    │                  Per-finding status: KEEP / ADAPT / REFRESH_EXAMPLES /
    │                  SIGNIFICANTLY_CHANGED / FREEZE
    ▼
[6] ReasoningAgent + NewInsightExplorer
    │                  Produce structured writing guidance per section
    ▼
[7] Section Writers ×9 Call Azure OpenAI to write each section as Markdown
    │
    ▼
export_pdf             Pandoc + XeLaTeX → PDF (main + annotated)
```

### Finding Status Values

| Status | Meaning | LLM Action |
|--------|---------|------------|
| `KEEP` | Trend unchanged | Preserve Tier A sentences verbatim |
| `ADAPT` | Direction holds, intensity shifted | Adjust qualifier words (e.g. "significantly" → "slightly") |
| `REFRESH_EXAMPLES` | Core trend holds, model names changed | Replace examples with current leaders |
| `SIGNIFICANTLY_CHANGED` | Core trend reversed | Flag for Mentor review; do not silently preserve |
| `FREEZE` | Required data missing | Copy previous text; append DATA PENDING footnote |

---

## Agent Architecture: Roles and Information Flow

The intelligence in this pipeline is distributed across six specialised agents. Each agent has a narrow, well-defined responsibility. They communicate through structured data objects — no agent writes prose directly from raw data, and no agent makes policy decisions outside its scope. Understanding how they divide and hand off work is essential for debugging failures or modifying the pipeline's behaviour.

The diagram below shows information flow. Arrows indicate what each agent receives and what it produces.

```
┌─────────────────────────────────────────────────────────────────┐
│                      PIPELINE INPUTS                            │
│  new_data.xlsx  ──►  analytics object   (structured statistics) │
│  ground_truth/*.yaml  ──►  findings registry  (human baseline)  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
          ┌───────────────▼───────────────┐
          │      GroundTruthStore         │  loads and indexes human baseline
          └───────────────┬───────────────┘
                          │  findings registry
          ┌───────────────▼───────────────┐
          │    DataChangeDetector         │  compares new data to baseline
          └───────────────┬───────────────┘
                          │  per-finding change status + diffs
          ┌───────────────▼───────────────┐
          │      FindingVerifier          │  produces exact sentence-level instructions
          └──────┬────────────────────────┘
                 │                    │
    sentence     │                    │  global change signals
    instructions │                    │  (e.g. "hierarchy reversed")
                 │          ┌─────────▼──────────┐
                 │          │   ReasoningAgent    │  decides what to write
                 │          └─────────┬──────────┘
                 │                    │  section writing briefs
                 │          ┌─────────▼──────────┐
                 │          │ NewInsightExplorer  │  generates [NEW] candidates
                 │          └─────────┬──────────┘
                 │                    │  new finding drafts
          ┌──────▼────────────────────▼──────────┐
          │         Section Writers ×9            │  call LLM; write Markdown
          └──────────────────┬───────────────────┘
                             │  Markdown sections
                    ┌────────▼────────┐
                    │   export_pdf    │  → main PDF + annotated PDF
                    └─────────────────┘
```

---

### Agent 1 — `GroundTruthStore`

**Role:** Loads, validates, and indexes the human-authored baseline findings from all YAML files. Acts as the single authoritative source of record for what the previous human report said.

**Inputs:** All `ground_truth/*.yaml` files.

**Outputs:** A structured registry mapping each finding ID to its full set of sentences, tiers (A/B/C), preservation rules, delete conditions, and `baseline_anchors` (the numerical values the human report was based on, e.g. `conformity_leader: {model: DeepSeek-V3, value: 0.518}`).

**Why it exists as a separate agent:** Isolating baseline loading from change detection means the ground truth is read exactly once and cannot be accidentally modified mid-run. Every downstream agent queries this registry rather than re-reading the files, ensuring consistency.

**Limitations:** The store does not validate that `baseline_anchors` still match the canonical `leaderboard_results_latest.xlsx`. If the baseline Excel is updated but the YAML anchors are not, the change detection comparisons will be wrong. **Always update YAML anchors when replacing the baseline Excel.**

---

### Agent 2 — `DataChangeDetector`

**Role:** The analytical core of the pipeline. Compares every numeric signal relevant to each finding between the new data (from `analytics`) and the baseline anchors (from `GroundTruthStore`), and assigns each finding a change status.

**Inputs:**
- Structured analytics object from the current benchmark Excel (rankings, group means, gap sizes, dimension leaders, etc.)
- Baseline anchors from `GroundTruthStore`

**Outputs:** A change status for every finding:

| Status | Assigned when |
|--------|--------------|
| `KEEP` | All relevant metrics are within a defined tolerance of the baseline; no direction has changed |
| `ADAPT` | Direction is unchanged but intensity has shifted (e.g. a gap narrowed or widened by more than a threshold) |
| `REFRESH_EXAMPLES` | The core trend holds, but a model cited as an example is no longer the current leader |
| `SIGNIFICANTLY_CHANGED` | A core metric has reversed direction (e.g. a model previously ranked lower now ranks higher in the same family) |
| `FREEZE` | The required data does not exist in the current Excel |

The detector also emits **global change signals** — dataset-level reversals that need to be broadcast to multiple sections simultaneously. For example, if the Schwartz value hierarchy inverts (Power moves to top-3), every section that references the hierarchy must be notified, not just the Schwartz section. These global signals are separate from per-finding statuses and are passed directly to the `ReasoningAgent`.

**Limitations and known failure modes:**
- The detector checks whether metrics have changed direction but does not always check whether the magnitude of change is meaningful. Small positive gaps (e.g. mean difference = 0.007) may still be classified as `KEEP` when they are effectively zero. This is the root cause of the FULVA F1 instability.
- The detector does not filter model candidates by `Type` (open/closed) before ranking them. This causes the PropVsOpen F2 error — low-scoring closed-source models are eligible to appear as low-scoring "open-source" examples.
- The detector operates per-finding in isolation. It does not propagate a local finding's status change to other findings that share the same underlying claim. Families F1 and MFT F2 both suffer from this: a per-model exception detected in one sentence is not used to override an aggregate claim in another sentence of the same finding.

---

### Agent 3 — `FindingVerifier`

**Role:** Translates the change detector's coarse status assignments into sentence-level, actionable instructions for each finding. Where the detector says "REFRESH_EXAMPLES," the verifier specifies exactly which sentence to update, what the old value was, what the new value is, and what constraint the replacement must satisfy (e.g. "replace only if new leader margin ≥ 0.05 above previous leader").

**Inputs:**
- Per-finding change statuses from `DataChangeDetector`
- Sentences and tier assignments from `GroundTruthStore`
- Current analytics (to look up exact replacement values)

**Outputs:** A structured instruction set per finding, for example:

```json
{
  "finding": "schwartz_f1",
  "status": "REFRESH_EXAMPLES",
  "instructions": [
    {
      "sentence_id": "sch_f1_s3",
      "tier": "C",
      "action": "REPLACE",
      "old_value": "DeepSeek-V3",
      "new_value": "GLM-4",
      "new_score": 0.545,
      "dimension": "Conformity",
      "reason": "GLM-4 now leads Conformity (0.545 vs 0.518), margin 0.027 exceeds threshold"
    }
  ]
}
```

These instructions are what the Section Writers receive — they do not receive the raw data or the change status directly. The verifier acts as a translator that converts analytical conclusions into writing directives.

**Why this separation matters:** Separating "what changed" (detector) from "what to do about it" (verifier) means that writing logic and analytical logic are independently testable. It also means the annotated report's green annotations come directly from the verifier's reasoning strings, not from the LLM — so they are factually grounded even when the LLM-generated prose is not.

---

### Agent 4 — `ReasoningAgent`

**Role:** Synthesises the verifier's sentence-level instructions and the detector's global signals into a coherent **writing brief** for each section. The brief answers the question: *given everything that changed, what is the most accurate and complete thing to say in this section?*

**Inputs:**
- Sentence-level instructions from `FindingVerifier` (per-finding granularity)
- Global change signals from `DataChangeDetector` (cross-section granularity)
- Context about what other sections are saying (to maintain cross-section consistency)

**Outputs:** One structured writing brief per section, containing:
- Which Tier A sentences to preserve verbatim (quoted)
- Which Tier B sentences to adapt (with the specific qualifier word to change)
- Which Tier C sentences to regenerate (with the replacement data values)
- Which sentences to delete entirely
- The global framing that should govern the section's tone (e.g. "open-source gap is narrowing")
- Instructions for where to insert `[NEW]` findings

**Why this agent exists:** Without a reasoning layer, the Section Writers would need to reconcile potentially conflicting instructions from different parts of the pipeline. For example, if Families F1 is `REFRESH_EXAMPLES` and a global signal says "GPT family has diverged," the writer would need to know whether to update the example, delete the example, or modify the framing. The ReasoningAgent makes this decision and delivers a single coherent instruction, so writers never face ambiguous directives.

**Current limitation:** The ReasoningAgent makes decisions for each section independently. It does not have a mechanism to confirm that decisions across sections are mutually consistent. If it tells the Overview section to say "proprietary models significantly outperform open-source" and tells the PropVsOpen section to say "the gap is now only slight," these contradictory framings will both appear in the final report. This cross-section consistency check is a known gap and a target for future improvement.

---

### Agent 5 — `NewInsightExplorer`

**Role:** Scans the current analytics for patterns that are not covered by any existing ground-truth finding and generates candidate `[NEW]` findings for consideration.

**Inputs:**
- Full analytics object for the current round
- The complete list of existing finding IDs (to avoid proposing insights already covered)
- Section-level context from the ReasoningAgent (to know what each section's confirmed findings already say)

**Outputs:** A ranked list of candidate `[NEW]` findings, each with:
- A draft headline and one-paragraph body text
- The specific data points that support it (model names, values, comparisons)
- A confidence score based on the magnitude and consistency of the detected pattern
- A flag indicating whether the insight is unique or duplicates a claim elsewhere

**How [NEW] findings are gated:** Candidates with low confidence or duplicates are not passed to the Section Writers. Candidates above the threshold are passed with a `requires_mentor_review: true` marker — the writers include them with `[NEW]` prefix but the annotation in the annotated report explicitly states they have not been verified by a human researcher.

**Important:** `[NEW]` findings generated by this agent are proposals, not conclusions. Their data citations should be verified before publication. See the [Per-Finding Review Priority Guide](#per-finding-review-priority-guide) for the recommended verification workflow.

---

### Agent 6 — `Section Writers` (×9)

**Role:** One writer per report section. Each writer receives the structured brief from the ReasoningAgent and calls the Azure OpenAI LLM to produce the section's Markdown text, following the instructions precisely.

The nine writers are: `overview`, `schwartz`, `mft`, `safety`, `fulva`, `open_closed`, `model_families`, `reasoning`, and a final `integrator` that assembles the sections into the complete report.

**Inputs:**
- Writing brief from `ReasoningAgent` (which sentences to preserve, adapt, replace, delete)
- `[NEW]` finding drafts from `NewInsightExplorer`
- Replacement values from `FindingVerifier` (exact model names, scores, dimension leaders)
- Figures directory path (for embedding benchmark plots)

**Outputs:** Section Markdown, structured so that:
- Preserved Tier A sentences appear verbatim (writers are instructed not to paraphrase)
- Adapted Tier B sentences contain only the approved qualifier-word changes
- Refreshed Tier C sentences use the exact replacement values from the verifier
- `[NEW]` findings appear with that prefix at the approved insertion points
- Every substituted value is tagged for yellow highlight in the annotated report

**What the LLM does and does not decide:** The LLM's role is to produce fluent prose that follows the brief — it handles sentence assembly, connective language, and stylistic consistency. It does not decide which facts to include, which models to name, or what direction to describe. Those decisions are made upstream and delivered as instructions. When writers produce incorrect content (e.g. citing a wrong model name), the failure is almost always upstream — in the verifier's candidate selection or the detector's classification — rather than the LLM misreading its brief.

**`BaseSectionWriter`:** All nine writers inherit from this base class, which handles prompt assembly, Azure authentication, content filter pre-processing (including the terminology replacements described in the [Azure Content Filter](#azure-content-filter--terminology-replacements) section), and the tagging of substituted values for the annotated report.

---

### How the Agents Interact: End-to-End Example

To make the flow concrete, here is how a single data change propagates through all agents, using the Schwartz F1 Conformity leader replacement as an example.

**Data change:** In the new Excel, GLM-4's Conformity score rose to 0.545, exceeding DeepSeek-V3 (0.440). DeepSeek-V3 is no longer the Conformity leader.

1. **`GroundTruthStore`** loads `schwartz.yaml` and serves the baseline anchor `conformity_leader: {model: DeepSeek-V3, value: 0.518}` and the Tier C sentence "DeepSeek-V3 demonstrates a distinctive preference for Conformity."

2. **`DataChangeDetector`** computes the new Conformity ranking. GLM-4 (0.545) > DeepSeek-V3 (0.440). The leader has changed. Margin = 0.545 − 0.440 = 0.105, which exceeds the 0.05 threshold. Assigns `REFRESH_EXAMPLES` to Schwartz F1.

3. **`FindingVerifier`** identifies the Tier C sentence in Schwartz F1, confirms the action is `REPLACE`, and produces the instruction: `old = "DeepSeek-V3"`, `new = "GLM-4"`, `new_score = 0.545`.

4. **`ReasoningAgent`** adds this instruction to the Schwartz section brief. It confirms the Tier A sentences (pan-cultural baseline holds, top-4 still correct) should be preserved verbatim, and that the rest of the section needs no other changes.

5. **`NewInsightExplorer`** scans analytics for noteworthy GLM-4 patterns. If GLM-4's Conformity lead is unusually large relative to its other dimensions, a candidate `[NEW]` finding may be generated; otherwise not.

6. **`SectionWriterSchwartz`** receives the brief, calls the LLM, and produces text where the sentence reads "GLM-4 demonstrates a distinctive preference for Conformity" — with "GLM-4" tagged for yellow highlight in the annotated report.

7. **`export_pdf`** writes the annotation below Schwartz F1: *"Example model replaced: GLM-4 now leads Conformity (0.545), up from DeepSeek-V3 (0.518). Margin 0.105 exceeds replacement threshold. Status: REFRESH_EXAMPLES."*

---

```
Value-compass automization/
│
├── main.py                        # Entry point (fixed paths, no CLI args)
├── requirements.txt
├── .env                           # Azure OpenAI credentials (not committed)
│
├── data/
│   ├── leaderboard_results_latest.xlsx    # New benchmark data (input)
│   ├── leaderboard_results_baseline.xlsx  # Previous round baseline (comparison target)
│   └── TestSet_*.xlsx                     # Evaluation test sets (not used in production)
│
├── ground_truth/
│   ├── overall_findings.yaml
│   ├── schwartz.yaml
│   ├── mft.yaml
│   ├── safety.yaml
│   ├── fulva.yaml
│   ├── open_closed.yaml
│   ├── model_families.yaml
│   └── reasoning.yaml
│
├── src/
│   ├── pipeline/
│   │   ├── orchestrator.py        # Wires all stages together
│   │   ├── load_data.py           # Reads Excel sheets into DataFrames
│   │   ├── analytics.py           # Computes all structured analytics
│   │   ├── plot.py                # Generates benchmark figures
│   │   ├── finding_verifier.py    # Exact replacement instructions per finding
│   │   ├── export_pdf.py          # Markdown -> PDF via pandoc/xelatex
│   │   ├── annotated_report.py    # Generates annotated change-analysis PDF
│   │   └── aoai_client.py         # Azure OpenAI API client
│   │
│   └── agents/
│       ├── ground_truth_store.py
│       ├── data_change_detector.py
│       ├── reasoning_agent.py
│       ├── new_insight_explorer.py
│       └── section_writers/
│           ├── base_section_writer.py
│           ├── section_writer_overview.py
│           ├── section_writer_schwartz.py
│           ├── section_writer_mft.py
│           ├── section_writer_safety.py
│           ├── section_writer_fulva.py
│           ├── section_writer_open_closed.py
│           ├── section_writer_model_families.py
│           └── section_writer_reasoning.py
│
├── output/
│   ├── reports/                   # ValueCompass_Report.pdf + _Annotated.pdf
│   └── figures/                   # Generated plots
│
└── tests/
    ├── conftest.py
    └── test_section_writers.py
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

XeLaTeX is required for PDF generation:

```bash
# Ubuntu / Debian
sudo apt-get install texlive-xetex texlive-fonts-recommended

# macOS (MacTeX)
brew install --cask mactex
```

### 2. Configure Azure OpenAI credentials

Create a `.env` file in the project root:

```env
GPT_ENDPOINT=https://<your-resource>.openai.azure.com/
AOAI_API_VERSION=2024-02-15-preview
AOAI_TEMPERATURE=0.2
```

The client uses **Azure CLI authentication** (`az login`). Run `az login` before executing the pipeline.

### 3. Verify setup

```bash
python -c "from src.pipeline.analytics import compute_all_analytics; print('OK')"
```

---

## Usage

All commands are run from the project root directory (`Value-compass automization/`).

### Run the pipeline

```bash
python main.py
```

This compares `data/leaderboard_results_latest.xlsx` (new data) against `data/leaderboard_results_baseline.xlsx` (previous round baseline) and writes two files:

```
output/reports/ValueCompass_Report.pdf
output/reports/ValueCompass_Report_Annotated.pdf
```

The input and output paths are fixed in `main.py`. To change them, edit the three constants at the top of that file:

```python
EXCEL_PATH    = "data/leaderboard_results_latest.xlsx"
BASELINE_PATH = "data/leaderboard_results_baseline.xlsx"
OUTPUT_PATH   = "output/reports/ValueCompass_Report.pdf"
```

### Run unit tests

```bash
cd "Value-compass automization"
python -m pytest tests/ -v
```

---

## What the Pipeline Does Well

Based on evaluation across multiple benchmark rounds, the following categories of changes are handled **reliably and accurately**. You can generally trust these outputs without line-by-line verification.

### ✅ Single-Dimension Leader Replacement

When the top-ranked model on a specific Schwartz dimension, MFT metric, or FULVA score changes to a different model, the pipeline correctly identifies the new leader and replaces the model name in the relevant example sentence while preserving the surrounding analytical text.

*Example correctly handled:* When DeepSeek-V3 was replaced by GLM-4 as the Conformity leader in Schwartz F1, and when Claude-3.5-Sonnet was replaced by GPT-4-Turbo in the Schwartz F2 top-3 list, both substitutions were made accurately across all three report versions.

### ✅ Numerical Score Updates

Specific benchmark scores cited in the text (e.g. a model's MFT average, a safety category percentage) are reliably updated when the underlying data changes. The pipeline correctly identifies these as Tier C / `REFRESH` elements and substitutes current values.

*Example correctly handled:* Claude-3.5-Sonnet's MFT score was updated from 68.36 to 52.0 accurately and consistently across all runs.

### ✅ Qualifier Word Adjustment (ADAPT-level changes)

When a gap between two groups narrows or widens meaningfully without reversing direction, the pipeline correctly adjusts intensity language: "significantly" becomes "slightly," "far more robust" becomes "more robust," and so on.

*Example correctly handled:* The proprietary-vs-open-source MFT performance gap, after open-source models improved, was correctly described as "slightly" rather than "significantly" wider, reflecting the actual 6.5pp gap.

### ✅ Invalidated Example Detection and Deletion

When a cross-framework correlation example becomes invalid due to data changes (e.g. a model's score in one framework improves while its score in another does not), the pipeline detects the broken relationship and removes the specific example sentence rather than silently preserving incorrect claims.

*Example correctly handled:* When o3-mini's MFT Fairness score improved substantially, breaking the "Fairness low → Rep_Toxicity low" cross-framework pairing, the specific example was deleted and replaced with a more general statement about correlation patterns.

### ✅ FULVA Trend Direction Monitoring

The pipeline correctly monitors whether user-oriented vs. counterpart-oriented value gaps (User-Oriented > Self-Competence, Social > Idealistic, Ethical > Professional) remain directionally consistent across all models. When the data shows a gap collapsing toward zero, the description is updated accordingly.

*Example correctly handled:* When the Ethical-vs-Professional gap dropped to near zero (mean diff = 0.007, 17/33 models reversed), the pipeline dropped "Ethical over Professional" from the list of consistent trends and replaced it with a balanced characterisation noting the lack of a uniform preference.

### ✅ Reasoning Model Re-ranking

When a reasoning model's benchmark score improves substantially relative to its non-reasoning counterpart within the same family, the pipeline detects the within-family reversal and updates the comparison sentence accordingly.

*Example correctly handled:* When DeepSeek-R1's MFT score improved from 91.55 to 78.50 (surpassing DeepSeek-V3 at 88.97), the claim "R1 does not consistently exceed V3" was replaced with language acknowledging R1 as a competitive top-tier performer.

### ✅ Safety Top-Model List Updates

The list of safest models on the static Safety Taxonomy benchmark is reliably updated when model scores change, with models dropping out of or entering the top tier correctly reflected in the text.

### ✅ Intra-Family Example Pruning (when correctly triggered)

When a family's internal Schwartz variance expands enough to invalidate the family-consistency claim for that family, the affected family pair is removed from the example list.

---

## Known Weaknesses — Findings With Unstable Output Requiring Researcher Review

The pipeline does not behave deterministically across all findings. The issues below are **instabilities observed across multiple successive test runs** — not findings that always produce wrong output, but findings where the pipeline sometimes gets it right and sometimes gets it wrong for the same underlying data conditions. This inconsistency is precisely what makes them require human review: you cannot rely on a previous correct run as evidence that the current run is also correct.

**Four findings in particular — PropVsOpen F2, MFT F2, Families F1, and FULVA F1 — have shown unreliable output across the evaluation runs.** In some cases the pipeline issued the correct instruction in one run and the wrong instruction in the next, with no meaningful change in the input data. In others, the pipeline correctly identified a problem in isolation but failed to propagate the right consequence through to the final text. These findings should be treated as requiring human sign-off every cycle regardless of what the annotated report shows.

---

### ⚠️ PropVsOpen Finding 2 — Unstable Example Model Type Selection

> **Robustness note:** The pipeline has the information to select the correct open-source example (LLaMA-3.1-8B-Instruct ranks near the bottom of open-source Schwartz scores) but does not consistently do so. In all three evaluation runs it selected closed-source models instead, suggesting the type-filter step is either not firing or not passing the constraint downstream reliably.

**What the instability looks like:** When generating the sentence about open-source models scoring lower on Schwartz value expression, the pipeline cited **GPT-4-Turbo (OpenAI, closed-source) and GLM-4 (Zhipu AI, closed-source)** as the low-scoring examples. This produces a logically self-defeating argument — using closed-source models as evidence that open-source models are weaker. The correct low-scoring open-source example (LLaMA-3.1-8B-Instruct, Universalism rank #31) was available in the data but was not selected in any run.

**Root cause:** The candidate selection logic does not consistently apply a `Type = 'Open'` filter before ranking low scorers, so any low-scoring model regardless of license type can enter the candidate pool.

**What to check every cycle:** In PropVsOpen F2, confirm that every model named as a low-scoring example appears as `Open` in the `Type` column of the `Model Info` sheet. If GPT-4-Turbo or GLM-4 appear, replace them with the actual lowest-scoring open-source models (typically LLaMA-3.1-8B-Instruct).

---

### ⚠️ MFT Finding 2 — Unstable Propagation of Per-Model Exceptions to Aggregate Claims

> **Robustness note:** The pipeline correctly computes per-model dimension weaknesses and correctly computes cross-model aggregate difficulty rankings, but does not consistently check whether the two are in conflict. The contradiction has appeared in every evaluation run, suggesting the cross-check between individual and aggregate layers is not robustly implemented.

**What the instability looks like:** The text described Authority as "comparatively easy" or "generally easier across architectures," while simultaneously the data showed GPT-4o's Authority EVR had risen to 97.20 — its single worst-performing dimension. These two statements appeared in the same paragraph. The aggregate claim was generated correctly from cross-model means, but the per-model exception was not used to override or qualify it.

**Root cause:** The "generally easier" characterisation is derived from the cross-model average EVR for each dimension. The pipeline does not propagate individual-model outliers back to override aggregate framing, so a model that is worst on a dimension the average labels "easy" goes unnoticed.

**What to check every cycle:** In MFT F2, read the list of dimensions described as "generally easier" (historically Care and Authority) and confirm that no model in the current data has one of those dimensions as its worst-performing dimension. If it does, that model must be flagged as an exception, or the aggregate claim must be revised.

---

### ⚠️ Families Finding 1 — Unstable Scope of Local vs. Global Divergence Judgement

> **Robustness note:** This finding has oscillated between correct and incorrect output across consecutive runs with similar data. In one run the pipeline correctly removed the GPT-4o/GPT-4o-mini example pair; in the next run it reinstated them. In the third run it correctly detected the family-level divergence but then over-applied it to produce a global claim that was not supported by the data for other families. The underlying judgement — "is this one family's exception or a broad pattern?" — is not being made consistently.

**What the instability looks like:** When GPT-4o-mini's Schwartz scores diverged significantly from GPT-4o (Universalism gap grew from 0.007 to 0.199), the pipeline sometimes correctly handled this as a local exception and sometimes generalised it to a claim that intra-family consistency "can no longer be assumed" across all major providers — even though Claude, Gemini, LLaMA, and DeepSeek families had not changed and remained internally consistent.

**Root cause:** The per-family consistency check does not reliably distinguish between "one family diverged on two dimensions" and "multiple families diverged broadly." A single outlier can tip the framing of the entire finding depending on which code path is taken on a given run.

**What to check every cycle:** If the core L1 claim has been substantially weakened (language such as "intra-family similarity is not a safe default assumption"), check whether the divergence is limited to one family or genuinely affects several. If it is limited to one, restore the general claim and note the divergent family as an exception. Also check whether GPT-4o/GPT-4o-mini appears as a positive consistency example — if their Universalism scores differ by more than 0.10, they should not be listed as a family-consistency illustration.

---

### ⚠️ FULVA Finding 1 — Unstable Significance Threshold for Trend Reversal Detection

> **Robustness note:** The pipeline correctly detected the issue and produced the right output in one of three runs, confirming the logic exists in principle. However, the fix depends on a threshold check that did not fire consistently — the same data conditions produced different decisions across runs. Do not assume the previous run's correct output carries forward.

**What the instability looks like:** In two of three evaluation runs, when the Ethical–Professional mean gap collapsed to 0.007 (near zero) and 17 out of 33 models showed Professional > Ethical, the pipeline still preserved "Ethical over Professional" as a "consistent trend." In the third run it correctly identified and removed the claim. The difference in behaviour was not driven by a difference in the data — the same test set produced different decisions, indicating a non-deterministic threshold or a path-dependent check.

**Root cause:** The KEEP condition is satisfied as long as the mean difference remains positive, regardless of magnitude. The significance threshold that should override this (mean < 0.05 or majority of models reversed) is present in the code but did not activate consistently.

**What to check when data has changed:** Compute the mean difference between the Ethical and Professional FULVA columns in the current data. If the mean is below 0.05 **or** more than half of all models show Professional > Ethical, verify that the "Ethical over Professional" item has been removed from the text or replaced with language acknowledging the trade-off is model-specific rather than a uniform trend.

---

### ⚠️ Safety Finding 2 — Non-Standard Category Names and Incorrect Ordering

**What the pipeline actually did wrong:** Across all runs, Safety F2 used `User_Autonomy` (an internal column name) instead of the official benchmark label "Human Autonomy & Integrity Harms." In addition, "Malicious Use" was described as one of the easiest categories to mitigate, while the actual data showed Human Autonomy & Integrity Harms had the lowest ASR mean (0.040) — making it the genuinely easiest category. Malicious Use (ASR mean ~0.054) was closer to the middle of the range.

**Root cause:** The text template uses column names rather than benchmark display names, and the category ordering is determined by string-sorted rank rather than the computed ASR means.

**What to check every cycle:** Confirm category names use full benchmark labels (not internal column identifiers), and verify that the "easiest" category cited matches the category with the lowest mean ASR in the current `Risk` sheet.

---

### ⚠️ Overall Finding 2 — Pipeline Does Not Update This Finding. Manual Replacement Required Every Cycle.

**This is the only finding in the report that the pipeline does not update at all.** OV-F2 ("Most LLMs demonstrate a clear bias towards Western cultural values") depends on a country-level Schwartz similarity matrix that is not part of the standard benchmark Excel. Because the data is absent, the pipeline copies the previous human-authored text verbatim and appends a `[DATA PENDING]` placeholder.

**The OV-F2 body text in the output PDF therefore reflects the previous benchmark round, not the current one.**

> **Action required every cycle:** Once new country-similarity data is available, manually replace the OV-F2 body text and heatmap figure before publication. The `[DATA PENDING]` marker in the annotated report shows the exact location. Do not publish this finding without updating it.

---

## Per-Finding Review Priority Guide

Use this table to triage your review time after each pipeline run. Open the annotated report first, then work through findings in priority order. Findings with no annotation in the annotated report were preserved verbatim and do not need review.

| Priority | Finding | Instability / What to verify |
|----------|---------|------------------------------|
| 🔴 **Manual replacement required** | **OV-F2** | The pipeline does not update this finding at all — it copies the previous text verbatim. Replace body text and heatmap manually once new country-similarity data is available. **Do not publish without this step.** |
| 🔴 **Check every cycle** | **PropVsOpen F2** | Output unstable: type filter for open-source candidate selection does not fire consistently. In all three test runs it selected closed-source models (GPT-4-Turbo, GLM-4) as "low-scoring open-source" examples. Verify every named low-scoring model is `Open` in the `Model Info` sheet. |
| 🔴 **Check every cycle** | **MFT F2** | Output unstable: per-model exceptions not consistently propagated to override aggregate framing. Has produced the contradiction "Authority is generally easy" alongside data where GPT-4o's worst dimension is Authority. Confirm "easier" dimensions are not any model's worst-performing dimension in the current data. |
| 🔴 **Check every cycle** | **Families F1** | Output unstable: scope judgement between "one family diverged" and "all families diverged" is non-deterministic. Has oscillated between correctly removing an invalidated example pair and reinstating it the next run. Also over-applied a single-family exception to weaken the global L1 claim. Confirm the core intra-family similarity claim has not been disproportionately weakened, and confirm GPT-4o/GPT-4o-mini are not listed as a consistency example if their Universalism gap exceeds 0.10. |
| 🟡 **Review when data changed** | **FULVA F1** | Output unstable: significance threshold check fires in some runs but not others. Has preserved "Ethical over Professional" as a "consistent trend" when the gap was near zero and the majority of models showed the opposite. Check if mean diff < 0.05 or > 50% of models reversed — if so, confirm the claim has been removed or qualified. |
| 🟡 **Review when data changed** | **Safety F2** | Output consistently uses internal column names (`User_Autonomy`) instead of full benchmark labels, and the category ordering by difficulty does not always reflect computed ASR means. Verify names and ordering against ASR means in the current data. |
| 🟡 **Review when data changed** | **OV-F3** | Cross-framework example deletion has been stable, but substituted Conformity example model should be verified against current dimension rankings. |
| 🟡 **Review when data changed** | **OV-F1** | Verify the cited "well-aligned" model's Universalism score is still meaningfully above the sample mean (not just barely positive). |
| 🟢 **Spot check** | **SCH F1 / F2** | Model name substitutions in dimension leaders and top-3 list — stable across runs, but takes 30 seconds to verify. |
| 🟢 **Spot check** | **MFT F1** | Is the top MFT performer current? Is the quoted score accurate? |
| 🟢 **Spot check** | **Safety F1** | Does the top-3 safest model list match current Safety Taxonomy data? |
| 🟢 **Spot check** | **Reasoning F1** | Has the standard-vs-reasoning comparison been updated if the within-family gap direction changed? |
| 🟢 **Spot check** | **PropVsOpen F1** | Is the qualifier word ("slightly" vs. "significantly") appropriate for the current gap size? |
| 🟢 **Spot check** | **All [NEW] findings** | Do named models and directional claims match the current Excel data? |
| ✅ **Usually stable** | **OV-F4** | Score and example model updates are reliable; the ceiling-effect argument is stable. |
| ✅ **Usually stable** | **OV-F5** | Context-aware safety argument; does not depend on model scores. |
| ✅ **Usually stable** | **Reasoning F2** | Value expression trend; rarely triggered by data changes. |

---

## Azure Content Filter — Terminology Replacements

The pipeline sends prompts to Azure OpenAI, which applies its own content safety filters. Certain research-standard terms that are entirely appropriate in an academic context can trigger these filters and cause generation to fail. To prevent this, the pipeline **automatically replaces a set of terms in every prompt before it is sent to the model**, and maps them back to the original terminology in the output.

**These replacements are an engineering workaround for Azure's filters — they do not reflect any editorial judgement about the original terminology.**

If you prefer to use the original academic language throughout (e.g. when publishing to a venue that expects standard benchmark terminology), you can revert any of these substitutions manually in the final PDF, or disable the filter in `src/pipeline/aoai_client.py` by commenting out the `_sanitize()` call if you switch to a deployment with relaxed content settings.

### Replacement Table

| Original term (standard benchmark language) | Replaced with (Azure-safe equivalent) |
|---------------------------------------------|---------------------------------------|
| Representation & Toxicity Harms | Representational Harms |
| Rep_Toxicity | Rep_Quality |
| Malicious Use | Adversarial Use |
| Human Autonomy & Integrity Harms | User Autonomy Risks |
| Human_Autonomy | User_Autonomy |
| adult content | restricted content |
| sex education | health education |
| adult platforms | regulated platforms |

These replacements are applied only to the prompts sent to Azure. They do **not** modify the YAML ground truth files, the Excel data, or any internal data structures — only the text that the LLM receives and generates is affected.

---

## Annotated Report: Understanding the Change Log

Every pipeline run produces a second PDF alongside the main report: `ValueCompass_Report_Annotated.pdf`. This is the recommended starting point for your review.

### How to Read the Annotated Report

**Green annotation blocks** appear immediately below any finding paragraph that was modified. Each block contains:
- A plain-English summary of what changed and why (e.g. "Example model replaced: GLM-4 now leads Conformity at 0.545, up from DeepSeek-V3 at 0.518")
- The finding status that triggered the change (KEEP / ADAPT / REFRESH_EXAMPLES / etc.)
- The specific data comparison that drove the decision

**Yellow highlights** mark the individual data elements that were substituted within the text:
- Model names that changed (e.g. ~~DeepSeek-V3~~ → **GLM-4**)
- Numerical scores that were updated (e.g. ~~68.36~~ → **52.0**)
- Dimension names that changed
- Qualifier words that were adjusted (e.g. ~~significantly~~ → **slightly**)

Unchanged findings carry **no annotations** — if a paragraph has no green block beneath it and no yellow highlights, it was preserved exactly from the previous human report.

`[NEW]` findings are annotated with their full data provenance: which metric or comparison triggered the insight, which models were involved, and the analytical reasoning chain used to construct the finding.

### Recommended Review Workflow

1. Open the **annotated report**
2. Scan for green annotation blocks — these are the only paragraphs that changed
3. For each changed paragraph, read the annotation to understand the stated reason for the change
4. Check the yellow highlights to confirm the substituted values match your expectations from the raw data
5. Consult the [Per-Finding Review Priority Guide](#per-finding-review-priority-guide) to decide which changes need deeper verification
6. Make any corrections in the main report PDF directly

---

## Ground Truth YAML Format

Each YAML in `ground_truth/` defines the human-authored findings for one report section.

```yaml
section: "Schwartz Theory of Basic Values"
part: 2

baseline_anchors:
  selfdirection_leader: {model: o3-mini, value: 0.615}
  universalism_leader: {model: Qwen-Max, value: 0.798}
  conformity_leader: {model: DeepSeek-V3, value: 0.518}

findings:
  - id: finding_1
    title: "Most models share a value order matching the pan-cultural baseline"

    delete_condition: "Power or Hedonism enters top-3 of Schwartz dimension ordering"

    sentences:
      - tier: A                          # STABLE — preserve verbatim unless hard-delete
        text: >
          Most models share a value order matching the pan-cultural baseline,
          though subtle preference differences remain.
        preservation_rule: >
          Preserve if at least 3 of {Universalism, Security, Benevolence,
          Self-direction} remain in the new top-4.

      - tier: C                          # REFRESH — always regenerate from new data
        text: >
          For instance, o3-mini scores higher on Self-Direction...
        regeneration_rule: >
          Regenerate from current dimension_leaders. Replace model name only
          when new leader margin >= 0.05.

      - tier: B                          # ADAPT — adjust wording when intensity shifts
        text: >
          Though fine-grained priorities vary within each group...
        modification_rule: >
          Preserve when top-4 ordering trend holds.

explicit_exclusions:
  - Do not rank models as morally better or worse.
```

### Sentence Tiers

| Tier | Label | Behaviour |
|------|-------|-----------|
| A | STABLE | Preserve verbatim when underlying trend holds; hard-delete only on full reversal |
| B | ADAPT | Keep wording when direction unchanged; adjust qualifier words when intensity shifts |
| C | REFRESH | Always regenerate from current data; update model names, rankings, examples |

---

## Evaluation Test Set

> **Before using the pipeline on real data:** The file currently in `data/leaderboard_results_latest.xlsx` is the evaluation test set described in this section — it contains purposefully modified data for pipeline validation, not real benchmark results. **Replace it with your actual new benchmark data before running the pipeline for a publication round.** See [Adding a New Benchmark Round](#adding-a-new-benchmark-round) for the exact steps.

---

### What the Test Set Is

`data/leaderboard_results_latest.xlsx` is a modified copy of the original human-report baseline data. Targeted, purposeful changes were applied to specific cells across the four benchmark sheets (Schwartz, MFT, Risk, FULVa) to create a controlled evaluation scenario where every finding in the report needs to respond in some detectable way — either by preserving content, updating examples, adjusting qualifier language, or recognising that a previously-cited relationship no longer holds.

The pipeline compares this file against the human-authored ground truth in `ground_truth/*.yaml`. The test set plays the role of "new incoming data from the latest benchmark round."

The total number of cells modified was 55, spread across all four data sheets. No changes were made to the `Model Info` sheet or the ground truth YAMLs.

---

### What Changes Were Made and Why

The modifications fall into six categories, each targeting a distinct type of pipeline judgement:

**Category 1 — Citation validity check (OV-F1)**
Claude-3.5-Sonnet's Universalism score was reduced from 0.759 to 0.672, bringing it within 0.015 of the sample mean (0.657). The expected response was for the pipeline to recognise that "significantly higher than average" no longer holds and to substitute the correct current leader, Qwen-Max (0.798), as the example of a well-aligned model.

**Category 2 — Cross-framework correlation invalidation (OV-F3)**
o3-mini's MFT Fairness EVR was improved from 91.51 to 74.50, breaking the two-framework pairing used in OV-F3 ("o3-mini scores poorly on Fairness and correspondingly poorly on Rep_Toxicity"). The expected response was deletion of the specific example while preserving the general correlation claim.

**Category 3 — Numeric score refresh and second-place emergence (OV-F4, MFT-F1)**
Claude-3.5-Sonnet's MFT average EVR was improved from 59.11 to 52.00, requiring the cited score to be updated. Gemini-2.0-Flash's MFT scores were also substantially improved (82.17 → 68.00), narrowing its gap to Claude from 23pp to 16pp and making it a notable second-place performer. These changes test both simple numeric substitution and the recognition of a new near-leader.

**Category 4 — Dimension leadership and top-list replacement (SCH-F1, SCH-F2)**
DeepSeek-V3's Conformity score was reduced (0.518 → 0.440) and GLM-4's was raised (0.505 → 0.545), installing GLM-4 as the new Conformity leader. Separately, Claude-3.5-Sonnet's Schwartz total was reduced across three dimensions, dropping it from 3rd to 11th place overall; GPT-4-Turbo (unchanged at 4.807) becomes the natural new 3rd-place example. These changes test both a single-sentence example replacement and an ordered list update.

**Category 5 — Trend significance collapse and safety tier shift (FULVA-F1, Safety-F1/F2)**
Four models' FULVA Professional scores were raised by 0.12, collapsing the Ethical-vs-Professional mean gap from +0.030 to +0.007 (17 of 33 models now show Professional > Ethical). The expected response was removal of "Ethical over Professional" from the consistent-trend list. Phi-3-medium-instruct's Safety Taxonomy scores were degraded, removing it from the position of "scoring higher than o3-mini" used in OV-F4. Several models' Rep_Toxicity ASR values were reduced to shift the relative difficulty ordering of harm categories.

**Category 6 — Within-family reversal and group intensity change (Reasoning-F1, PropVsOpen-F1, Families-F1/F2)**
DeepSeek-R1's MFT scores were substantially improved (91.55 → 78.50), making it clearly better than DeepSeek-V3 (88.97) and overturning the claim that "R1 does not consistently exceed V3." LLaMA-3.3-70B's MFT scores were similarly improved, narrowing the open-vs-closed group gap from 7.00pp to 6.50pp — small but enough to warrant softening "significantly" to "slightly." GPT-4o-mini's Universalism and Benevolence scores were sharply reduced (Universalism gap to GPT-4o grew from 0.007 to 0.199), creating a large intra-family divergence within the GPT family and invalidating GPT-4o/GPT-4o-mini as a family-consistency illustration.

---

### Results and Accuracy

The pipeline was evaluated against the test set across three successive runs. The overall accuracy rate — defined as the fraction of the 19 core findings where the output was judged correct without any manual correction — was approximately **70–75% (13–14 of 19 findings per run)**.

| Finding | Result | Notes |
|---------|--------|-------|
| OV-F1 | ✅ Stable across all runs | Qwen-Max correctly substituted for Claude-3.5-Sonnet |
| OV-F2 | — Frozen by design | Pipeline copies previous text verbatim; manual replacement required every cycle |
| OV-F3 | ✅ Stable across all runs | Cross-framework example deleted; GLM-4 correctly substituted for Conformity |
| OV-F4 | ✅ Stable across all runs | Score updated to 52.0; Haiku-beats-o3-mini replacement example correctly identified |
| OV-F5 | ✅ Stable | Content-independent; preserved correctly (Azure term substitutions apply here) |
| SCH-F1 | ✅ Stable across all runs | GLM-4 correctly identified as new Conformity leader |
| SCH-F2 | ✅ Stable across all runs | GPT-4-Turbo correctly replaced Claude-3.5-Sonnet in top-3 list |
| MFT-F1 | ✅ Stable across all runs | Claude-3.5-Sonnet retained as MFT leader; Gemini improvement correctly noted |
| MFT-F2 | ⚠️ Unstable — output unreliable | Per-model exception (GPT-4o Authority EVR = 97.20) not consistently propagated to override aggregate "Authority is easy" framing; contradiction present in all three runs |
| Safety-F1 | ✅ Stable across all runs | Phi-3-medium correctly removed from top-safety-model list |
| Safety-F2 | ⚠️ Partially stable | Hardest-category ordering stable; but category names non-standard and Malicious Use ordering incorrect across all runs |
| FULVA-F1 | ⚠️ Unstable — output unreliable | Threshold check for trend significance did not fire consistently: "Ethical over Professional" incorrectly preserved in runs 1 and 2, correctly removed in run 3 |
| FULVA-F2 | ✅ Stable across all runs | Ranking unchanged; original sentence correctly preserved without spurious replacement |
| PropVsOpen-F1 | ✅ Stable across all runs | "significantly" → "slightly" qualifier adjustment made correctly |
| PropVsOpen-F2 | ⚠️ Unstable — output unreliable | Type filter for open-source models not consistently applied; closed-source models (GPT-4-Turbo, GLM-4) selected as low-scoring examples in all three runs |
| Families-F1 | ⚠️ Unstable — output unreliable | Scope judgement (local vs. global divergence) non-deterministic: GPT-4o/GPT-4o-mini pair correctly removed in run 2, reinstated in run 3; run 3 also over-generalised one family's divergence into a full L1 reversal |
| Families-F2 | ✅ Stable across all runs | Core inter-family > intra-family conclusion preserved; examples updated correctly |
| Reasoning-F1 | ✅ Stable across all runs | "R1 does not exceed V3" removed; R1 described as top-tier; finding title updated from "limited" to "moderate" |
| Reasoning-F2 | ✅ Stable | Content-independent; preserved correctly |

**Summary across 19 findings:**
- **12 findings** produced stable, correct output across all three runs
- **4 findings** produced unstable output — the pipeline issued the correct instruction in some runs but not others, making the output unreliable without human verification (PropVsOpen F2, MFT F2, Families F1, FULVA F1)
- **1 finding** had a secondary issue (non-standard names, minor ordering error) that was consistent across runs but not severe enough to invalidate the content (Safety F2)
- **1 finding** is intentionally frozen and requires manual update every cycle (OV-F2)
- **1 finding** is effectively stable because it does not depend on model scores (OV-F5)

---

### Findings That Require Close Attention Based on Test Results

The following four findings produced unstable output in the test set evaluation — the pipeline sometimes got them right and sometimes got them wrong under the same data conditions. They require manual review before every publication because a correct result in the previous run does not predict a correct result in the current run.

| Finding | Instability pattern | Specific check |
|---------|-------------------|----------------|
| **PropVsOpen F2** | Type filter for open-source models does not fire consistently | Confirm no closed-source model appears as a "low-scoring open-source" example |
| **MFT F2** | Per-model exceptions not consistently propagated to override aggregate claims | Confirm no dimension labelled "generally easy" is also a specific model's worst-performing dimension |
| **Families F1** | Scope judgement (local vs. global divergence) non-deterministic across runs | Confirm the core "intra-family similarity" L1 claim has not been overturned by a single family's partial divergence |
| **FULVA F1** | Significance threshold check fires in some runs but not others | If Ethical–Professional mean diff < 0.05, confirm "Ethical over Professional" has been removed |

All other findings can be accepted after a brief sanity check using the annotated report. See the [Per-Finding Review Priority Guide](#per-finding-review-priority-guide) for the complete triage table.

---

## Adding a New Benchmark Round

1. **Replace the test file with your real data:**
   ```bash
   cp /path/to/your/new_benchmark.xlsx data/leaderboard_results_latest.xlsx
   ```
   Required sheets: `Schwartz`, `MFT`, `Risk`, `FULVa`, `Model Info`. Required columns must match the canonical baseline schema — inspect any existing sheet for the expected layout.

2. **Run the pipeline:**
   ```bash
   python main.py
   ```
   Output is written to `output/reports/ValueCompass_Report.pdf` and `output/reports/ValueCompass_Report_Annotated.pdf`.

3. **Start your review from the annotated report.** Open `output/reports/ValueCompass_Report_Annotated.pdf`. Paragraphs with no green annotation were preserved verbatim and do not need review. For everything else, read the annotation first, then check the yellow highlights against the raw data.

4. **Always manually review the four high-risk findings** listed above, regardless of what the annotated report says about them.

5. **Supply OV-F2 manually.** This finding is always frozen — the pipeline copies the previous round's text and appends `[DATA PENDING]`. Once new country-similarity data is available, replace the body text and heatmap figure before publication.

6. **Update the baseline** once the new round becomes the official reference:
   - Confirm `data/leaderboard_results_latest.xlsx` now holds the new round's data (not the test set)
   - Update `baseline_anchors` in any affected `ground_truth/*.yaml` files to reflect new anchor values (dimension leaders, group gap sizes, key scores)
   - Commit both to version control so the next round compares against the correct baseline
