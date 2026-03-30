# main.py
from dotenv import load_dotenv
load_dotenv()

from src.pipeline.orchestrator import run_pipeline

EXCEL_PATH    = "data/leaderboard_results_latest.xlsx"
BASELINE_PATH = "data/leaderboard_results_baseline.xlsx"
OUTPUT_PATH   = "output/reports/ValueCompass_Report.pdf"

if __name__ == "__main__":
    print(f"Input  : {EXCEL_PATH}")
    print(f"Baseline: {BASELINE_PATH}")
    print(f"Output : {OUTPUT_PATH}\n")
    run_pipeline(
        excel_path=EXCEL_PATH,
        output_path=OUTPUT_PATH,
        baseline_path=BASELINE_PATH,
    )
    print(f"\nDone -> {OUTPUT_PATH}")
