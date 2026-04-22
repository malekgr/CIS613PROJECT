"""
run_benchmark.py — full multi-function experiment entry point.

Usage:
    GEMINI_API_KEY=... python run_benchmark.py
    GEMINI_API_KEY=... python run_benchmark.py --functions classify_triangle factorial
    GEMINI_API_KEY=... python run_benchmark.py --modes source_aware
    GEMINI_API_KEY=... python run_benchmark.py --no-human
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).parent.resolve())
sys.path.insert(0, PROJECT_ROOT)

from src.benchmark_runner import run_benchmark, BENCHMARK_FUNCTIONS, LLM_MODES
from src.report_generator import (
    save_csv, save_json, save_failure_summary, generate_markdown,
    save_mode_summary_csv, save_category_summary_csv,
    compute_mode_summary,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Run the full LLM test-generation benchmark.")
    parser.add_argument(
        "--functions", nargs="+", default=None,
        metavar="FUNC",
        help=f"Functions to benchmark (default: all {len(BENCHMARK_FUNCTIONS)})",
    )
    parser.add_argument(
        "--modes", nargs="+", choices=LLM_MODES, default=None,
        help="Generation modes to run (default: source_aware)",
    )
    parser.add_argument(
        "--no-human", action="store_true",
        help="Skip human baseline tests",
    )
    parser.add_argument(
        "--runs", type=int, default=1, metavar="N",
        help="Number of independent LLM generations per function/mode (default: 1)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    source_file = str(Path(PROJECT_ROOT) / "dataset" / "sample_functions.py")

    print("\n" + "=" * 70)
    print("  LLM Unit Test Generation — Benchmark Experiment")
    print("=" * 70)

    all_results = run_benchmark(
        source_file=source_file,
        project_root=PROJECT_ROOT,
        functions=args.functions,
        modes=args.modes,
        include_human=not args.no_human,
        n_runs=args.runs,
    )

    # ------------------------------------------------------------------ #
    # Save all outputs
    # ------------------------------------------------------------------ #
    summaries_dir = Path(PROJECT_ROOT) / "results" / "benchmark" / "summaries"

    print("\n" + "=" * 70)
    print("  Saving results")
    print("=" * 70)

    save_json(
        all_results,
        str(summaries_dir / "all_results.json"),
    )
    save_csv(
        all_results,
        str(summaries_dir / "results_table.csv"),
    )
    save_failure_summary(all_results, str(summaries_dir / "failure_summary.json"))
    save_mode_summary_csv(all_results, str(summaries_dir / "mode_summary.csv"))
    save_category_summary_csv(all_results, str(summaries_dir / "category_summary.csv"))
    generate_markdown(all_results, str(summaries_dir / "report.md"))

    print("\n--- Mode summary ---")
    for row in compute_mode_summary(all_results):
        pr  = row["avg_pass_rate"]
        ms  = row["avg_mutation_score"]
        print(f"  {row['mode']:<14} pass={pr:.1f}%  mut={ms:.4f}" if pr and ms
              else f"  {row['mode']}")

    print("\nDone. Results saved to results/benchmark/summaries/")


if __name__ == "__main__":
    main()
