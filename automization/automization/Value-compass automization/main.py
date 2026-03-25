# main.py
import argparse
import time
from dotenv import load_dotenv
load_dotenv()

from src.pipeline.orchestrator import run_pipeline

# 5 test sets — each is run with leaderboard_results_latest.xlsx as ground
# truth baseline, and the test set file as the "new data" input.
TEST_SETS = [
    {
        "name": "TestSet_1_L1_Stability",
        "excel": "data/TestSet_1_L1_Stability.xlsx",
        "output": "output/reports/ValueCompass_Report_TestSet1_L1_Stability.pdf",
    },
    {
        "name": "TestSet_2_L2_Flexibility",
        "excel": "data/TestSet_2_L2_Flexibility.xlsx",
        "output": "output/reports/ValueCompass_Report_TestSet2_L2_Flexibility.pdf",
    },
    {
        "name": "TestSet_3_Trend_Reversal",
        "excel": "data/TestSet_3_Trend_Reversal.xlsx",
        "output": "output/reports/ValueCompass_Report_TestSet3_Trend_Reversal.pdf",
    },
    {
        "name": "TestSet_4_Cross_Framework",
        "excel": "data/TestSet_4_Cross_Framework.xlsx",
        "output": "output/reports/ValueCompass_Report_TestSet4_Cross_Framework.pdf",
    },
    {
        "name": "TestSet_5_Group_Comparison",
        "excel": "data/TestSet_5_Group_Comparison.xlsx",
        "output": "output/reports/ValueCompass_Report_TestSet5_Group_Comparison.pdf",
    },
]


def main():
    parser = argparse.ArgumentParser(description="Value Compass Report Generator")
    parser.add_argument(
        "--testset", type=int, choices=[1, 2, 3, 4, 5],
        help="Run a single test set (1-5). Omit to run all 5.",
    )
    parser.add_argument(
        "--excel", type=str, default=None,
        help="Path to a custom Excel input file.",
    )
    parser.add_argument(
        "--output", type=str, default="output/reports/ValueCompass_Report.pdf",
        help="Output PDF path (used with --excel).",
    )
    args = parser.parse_args()

    # Custom single-file mode
    if args.excel:
        print(f"Running with custom input: {args.excel}")
        run_pipeline(excel_path=args.excel, output_path=args.output)
        print(f"Done -> {args.output}")
        return

    # Single test set mode
    if args.testset:
        ts = TEST_SETS[args.testset - 1]
        print(f"\n=== Running {ts['name']} ===")
        run_pipeline(excel_path=ts["excel"], output_path=ts["output"])
        print(f"Done -> {ts['output']}")
        return

    # Default: run all 5 test sets
    print("Running all 5 test sets...\n")
    for i, ts in enumerate(TEST_SETS, start=1):
        print(f"[{i}/5] {ts['name']}")
        t0 = time.time()
        try:
            run_pipeline(excel_path=ts["excel"], output_path=ts["output"])
            elapsed = time.time() - t0
            print(f"      Done in {elapsed:.0f}s -> {ts['output']}\n")
        except Exception as exc:
            print(f"      ERROR: {exc}\n")

    print("All test sets complete.")


if __name__ == "__main__":
    main()
