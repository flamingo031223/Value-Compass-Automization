# Copilot / AI Agent Instructions — Value Compass (concise)

Purpose: quick, actionable guidance to get an AI coding agent productive in this repo.

## Big picture
- Entrypoint: `python main.py` calls `run_pipeline()` (expected entry function).
- Pipeline steps (implemented in `src/pipeline/`):
  1. Load Excel data — `src/pipeline/load_data.py` (coerces datetimes to strings)
  2. Generate plots — `src/pipeline/plot.py` → `output/plots/`
  3. Convert to JSON — `src/pipeline/preprocess.py`
  4. Build chat messages — expected `build_messages` in `src/prompts/*` or `src/prompt.py`
  5. Call LLM — `src/pipeline/aoai_client.py` / `src/pipeline/llm_report.py`
  6. Export PDF — `src/pipeline/export_pdf.py` → `output/reports/`

**Quick note:** there is an import/path inconsistency: `main.py` imports `from src.orchestrator import run_pipeline` while the orchestrator implementation lives at `src/pipeline/orchestrator.py`. Verify imports or add an `src/orchestrator.py` shim if you hit import errors.

## Environment & run (local)
- Python 3.10+. Install deps: `pip install -r requirements.txt`.
- Required env vars: `GPT_ENDPOINT`, `AOAI_DEPLOYMENT`. Optional: `AOAI_API_VERSION`, `AOAI_TEMPERATURE`.
- Azure auth: code uses `AzureCliCredential` (run `az login`) or provide an SPN.
- PDF export requires OS-level tools: `pandoc` + TeX engine (e.g., `texlive-xetex`).
- Run locally:
  ```bash
  export GPT_ENDPOINT="https://<your-endpoint>"
  export AOAI_DEPLOYMENT="<your-deployment>"
  az login
  python main.py
  ```

## CI / workflows
- Workflow: `.github/workflows/generate-report.yml` runs `python main.py` on schedule and push to `main`.
- CI exposes `OPENAI_API_KEY` currently — **code expects Azure vars** (`GPT_ENDPOINT`/`AOAI_DEPLOYMENT`). If you change provider or CI, either set the Azure vars or add a mapping layer in `main.py`.

## Prompts & message format
- Chat messages: list of dicts [{"role":"system|user|assistant","content":"..."}]. Output should be Markdown (used as the report).
- Ground-truth guidance files: `ground_truth/*.yaml` are authoritative sources used by section writers (see `src/agents/section_writers/`).
- Rule of thumb: **do not change prompt structure lightly** — any prompt edit must include a test example and rationale in the PR.

## Patterns & conventions (examples)
- Section writers follow a template: e.g., `SectionWriterSchwartz.build_prompt(...)` embeds human-authored ground truth and strict retention rules — follow its structure when adding new sections.
- Data handling: `load_data` coerces datetimes → strings to avoid JSON serialization errors.
- Keep stable signatures for orchestration points: `run_pipeline()` and `save_as_pdf(markdown_text, output_path)`.

## Testing & dev workflow
- Tests: run `pytest -q` (see `tests/`). Add small, focused tests for new prompt behavior or data transformations.
- When modifying prompts or model calls, include a unit test that verifies message shape and a small integration-style test that runs `generate_report` with a mocked AOAI client.

## Integration points & gotchas
- AOAI client (`src/pipeline/aoai_client.py`) uses `AzureCliCredential` and expects `GPT_ENDPOINT` + `AOAI_DEPLOYMENT`.
- PDF export depends on `pypandoc` and system `pandoc` + TeX.
- Watch for inconsistent env var names across files (`ENDPOINT_URL` / `DEPLOYMENT_NAME` seen in examples).

## Quick checklist for PRs
- Small, focused changes
- If prompt changes: add example input/output (markdown) and a test
- Document env var or CI changes in PR description
- Preserve public function signatures unless coordinated in the same PR

---
If anything here is unclear or you'd like me to add short examples (e.g., a `--dry-run` flag, a mock AOAI client for tests, or a small shim to make `main.py` import reliable), say which item to expand and I’ll update the document and add tests/PR-ready changes.