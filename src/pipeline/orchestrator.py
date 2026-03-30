# src/pipeline/orchestrator.py

import os
import json
from src.pipeline.load_data import load_excel
from src.pipeline.preprocess import dataframe_to_json
from src.pipeline.analytics import (
    compute_all_analytics,
    extract_model_set,
    compute_intensity_metrics,
)
from src.pipeline.plot import generate_all_plots
from src.pipeline.export_pdf import save_as_pdf
from src.pipeline.annotated_report import save_annotated_pdf

from src.agents.ground_truth_store import (
    GroundTruthStore,
    PART1_SECTIONS,
    PART2_SECTIONS,
)
from src.agents.data_change_detector import FindingChangeDetector
from src.agents.reasoning_agent import ReasoningAgent
from src.pipeline.finding_verifier import FindingVerifier
from src.agents.new_insight_explorer import NewInsightExplorer

from src.agents.section_writers.section_writer_overview import OverviewSectionWriter
from src.agents.section_writers.section_writer_schwartz import SchwartzSectionWriter
from src.agents.section_writers.section_writer_mft import MFTSectionWriter
from src.agents.section_writers.section_writer_safety import SafetySectionWriter
from src.agents.section_writers.section_writer_fulva import FULVASectionWriter
from src.agents.section_writers.section_writer_open_closed import OpenClosedSectionWriter
from src.agents.section_writers.section_writer_model_families import ModelFamiliesSectionWriter
from src.agents.section_writers.section_writer_reasoning import ReasoningSectionWriter


# Maps section YAML keys to their writer classes
SECTION_WRITER_MAP = {
    "overall_findings": OverviewSectionWriter,
    "schwartz":         SchwartzSectionWriter,
    "mft":              MFTSectionWriter,
    "safety":           SafetySectionWriter,
    "fulva":            FULVASectionWriter,
    "open_closed":      OpenClosedSectionWriter,
    "model_families":   ModelFamiliesSectionWriter,
    "reasoning":        ReasoningSectionWriter,
}

# Canonical baseline path — always compared against new data
BASELINE_EXCEL_PATH = "data/leaderboard_results_baseline.xlsx"


def run_pipeline(
    excel_path: str = "data/leaderboard_results_latest.xlsx",
    output_path: str = "output/reports/ValueCompass_Report.pdf",
    baseline_path: str = BASELINE_EXCEL_PATH,
):
    # -------------------------------------------------------------------------
    # 1. Load Excel benchmark data
    # -------------------------------------------------------------------------
    df_dict = load_excel(excel_path)

    # -------------------------------------------------------------------------
    # 2. Load baseline data for comparison (detect new models, measure drift)
    # -------------------------------------------------------------------------
    baseline_df_dict  = None
    baseline_analytics = None
    newly_added_models: set = set()

    is_baseline_run = os.path.abspath(excel_path) == os.path.abspath(baseline_path)

    if not is_baseline_run:
        try:
            baseline_df_dict = load_excel(baseline_path)
            baseline_analytics = compute_all_analytics(baseline_df_dict)

            # Detect new models not present in baseline
            new_model_set      = extract_model_set(df_dict)
            baseline_model_set = extract_model_set(baseline_df_dict)
            newly_added_models = new_model_set - baseline_model_set
        except Exception as exc:
            print(f"[orchestrator] Warning: could not load baseline data: {exc}")

    # -------------------------------------------------------------------------
    # 3. Compute structured, finding-specific analytics for the new data
    # -------------------------------------------------------------------------
    analytics = compute_all_analytics(df_dict)

    # Attach newly-added model list to analytics for section writers
    if newly_added_models:
        analytics["newly_added_models"] = sorted(newly_added_models)

    # -------------------------------------------------------------------------
    # 4. Generate plots
    # -------------------------------------------------------------------------
    generate_all_plots(df_dict)

    # -------------------------------------------------------------------------
    # 5. Load ground truth for all sections
    # -------------------------------------------------------------------------
    gt_store = GroundTruthStore()
    all_gt   = gt_store.load_all()

    # -------------------------------------------------------------------------
    # 6. Detect per-finding data changes (with baseline comparison when available)
    # -------------------------------------------------------------------------
    detector = FindingChangeDetector()
    finding_changes = detector.detect(analytics, old_analytics=baseline_analytics)

    # -------------------------------------------------------------------------
    # 6b. Run finding-specific verifier for precise replacement instructions
    # -------------------------------------------------------------------------
    new_model_set = extract_model_set(df_dict)
    verifier = FindingVerifier()
    verifications = verifier.verify_all(analytics, new_model_set)

    # Merge verifications into finding_changes (verifier takes precedence)
    finding_changes = detector.detect_with_verifications(
        analytics,
        old_analytics=baseline_analytics,
        verifications=verifications,
    )

    # -------------------------------------------------------------------------
    # 7. Extract global signals that must broadcast to ALL section writers
    # -------------------------------------------------------------------------
    global_signals = detector.extract_global_signals(finding_changes)
    global_signals["newly_added_models"] = sorted(newly_added_models)

    # Attach intensity metrics when baseline is available
    if baseline_analytics is not None:
        try:
            intensity = compute_intensity_metrics(analytics, baseline_analytics)
            global_signals["intensity_metrics"] = intensity
            # Also embed intensity_metrics inside analytics so prop/reasoning detectors can use it
            analytics["intensity_metrics"] = intensity
        except Exception as exc:
            print(f"[orchestrator] Warning: intensity metrics failed: {exc}")

    # -------------------------------------------------------------------------
    # 8. Reasoning agent + insight explorer
    # -------------------------------------------------------------------------
    reasoning_agent  = ReasoningAgent()
    insight_explorer = NewInsightExplorer()

    # -------------------------------------------------------------------------
    # 9. Build report section by section
    # -------------------------------------------------------------------------
    report_sections = []
    report_sections.append("# Insights about LLMs Values from the Value Compass Benchmarks\n")
    section_map: dict = {}   # {section_key: section_md} — for annotated report

    # Part 1: Overall findings
    for section_key in PART1_SECTIONS:
        gt       = all_gt.get(section_key, {})
        reasoning = reasoning_agent.reason_for_section(
            section_key, analytics, finding_changes
        )
        new_insights = insight_explorer.explore(analytics)

        writer_cls = SECTION_WRITER_MAP[section_key]
        writer = writer_cls(
            ground_truth=gt,
            data_summary={},
            reasoning_summary=reasoning,
            new_insights=new_insights,
            analytics=analytics,
            global_signals=global_signals,
        )

        section_md = writer.write()
        report_sections.append(section_md)
        section_map[section_key] = section_md

    # Part 2: Detailed Evaluation Results
    report_sections.append("## 2. Detailed Evaluation Results on Diverse Value Systems and LLMs\n")

    for section_key in PART2_SECTIONS:
        gt       = all_gt.get(section_key, {})
        reasoning = reasoning_agent.reason_for_section(
            section_key, analytics, finding_changes
        )
        new_insights = insight_explorer.explore(analytics)

        writer_cls = SECTION_WRITER_MAP[section_key]
        writer = writer_cls(
            ground_truth=gt,
            data_summary={},
            reasoning_summary=reasoning,
            new_insights=new_insights,
            analytics=analytics,
            global_signals=global_signals,
        )

        section_md = writer.write()
        report_sections.append(section_md)
        section_map[section_key] = section_md

    # -------------------------------------------------------------------------
    # 10. Assemble full report
    # -------------------------------------------------------------------------
    report_md = "\n\n".join(report_sections)

    # -------------------------------------------------------------------------
    # 11. Export main report
    # -------------------------------------------------------------------------
    save_as_pdf(report_md, output_path)

    # -------------------------------------------------------------------------
    # 12. Export annotated change-analysis report (separate PDF)
    # -------------------------------------------------------------------------
    annotated_path = output_path.replace(".pdf", "_Annotated.pdf")
    try:
        save_annotated_pdf(
            section_map=section_map,
            all_gt=all_gt,
            finding_changes=finding_changes,
            output_path=annotated_path,
        )
    except Exception as exc:
        print(f"[orchestrator] Warning: annotated report failed: {exc}")

    return report_md


# REQUIRED entry point
if __name__ == "__main__":
    run_pipeline()
