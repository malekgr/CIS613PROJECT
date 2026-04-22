"""
rebuild_results.py — reconstruct all_results.json from existing test files.

Re-runs pytest + failure classifier on every generated_tests/{mode}/test_{func}.py
that exists, loads mutation scores from the raw metrics JSONs, and regenerates all
output artefacts without calling the LLM.

Usage:
    python rebuild_results.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.test_runner import run_tests
from src.metrics import compute_coverage, analyze_assertions
from src.failure_analyzer import classify_failures, summarize_failures
from src.report_generator import (
    save_csv, save_json, save_mode_summary_csv,
    save_category_summary_csv, save_failure_summary,
    generate_markdown, compute_mode_summary, compute_wins,
    METRIC_KEYS,
)

FUNCTIONS = [
    "classify_triangle", "factorial", "is_prime", "gcd",
    "reverse_string", "is_palindrome", "max_in_list", "count_vowels",
]
MODES = ["source_aware", "spec_only"]
HUMAN_FUNCTIONS = FUNCTIONS  # all 8 functions have human baselines now

SOURCE_FILE = str(ROOT / "dataset" / "sample_functions.py")
RESULTS_DIR = ROOT / "results" / "benchmark"
OUTPUT_DIR  = ROOT / "results" / "benchmark" / "output"


_AVG_KEYS = [
    "passed_count", "failed_count", "total_count",
    "execution_success_rate", "function_coverage_pct", "module_coverage_pct",
    "mutation_score", "killed", "total_mutants",
    "total_assertions", "assertions_per_test", "value_assertion_ratio",
]


def _load_raw_metrics(mode: str, func: str, run_tag: str = "") -> dict:
    subdir = f"{mode}/{run_tag}" if run_tag else mode
    path = RESULTS_DIR / "raw" / subdir / f"metrics_{func}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _run_tags(mode: str) -> list:
    """Return sorted runN subdirectory names if they exist, else empty list."""
    raw_dir = RESULTS_DIR / "raw" / mode
    tags = sorted(d.name for d in raw_dir.iterdir() if d.is_dir() and d.name.startswith("run"))
    return tags


def _avg_dicts(records: list) -> dict:
    avg: dict = {}
    for k in _AVG_KEYS:
        vals = [r[k] for r in records if r.get(k) is not None]
        avg[k] = round(sum(vals) / len(vals), 4) if vals else None
    failures = [f for r in records for f in r.get("failures", [])]
    avg["failures"]        = failures
    avg["failure_summary"] = summarize_failures(failures)
    avg["n_runs"]          = len(records)
    return avg


def _rerun_and_classify(test_file: Path, mode: str, func: str, run_tag: str = "") -> dict:
    subdir = f"{mode}/{run_tag}" if run_tag else mode
    coverage_path = str(RESULTS_DIR / "raw" / subdir / f"coverage_{func}.json")
    run = run_tests(str(test_file), str(ROOT), coverage_output=coverage_path)

    cov = compute_coverage(coverage_path, func)
    failures = classify_failures(run["stdout"], run["stderr"])
    assertion_stats = analyze_assertions(str(test_file))

    return {
        "passed_count":           run["passed_count"],
        "failed_count":           run["failed_count"],
        "total_count":            run["total_count"],
        "execution_success_rate": run["execution_success_rate"],
        "function_coverage_pct":  cov["function_coverage_pct"],
        "module_coverage_pct":    cov["module_coverage_pct"],
        "total_assertions":       assertion_stats["total_assertions"],
        "assertions_per_test":    assertion_stats["assertions_per_test"],
        "value_assertion_ratio":  assertion_stats["value_assertion_ratio"],
        "failures":               failures,
        "failure_summary":        summarize_failures(failures),
    }


def _attach_mutation(entry: dict, mode: str, func: str, run_tag: str = "") -> None:
    raw = _load_raw_metrics(mode, func, run_tag)
    entry["mutation_score"] = raw.get("mutation_score")
    entry["killed"]         = raw.get("killed")
    entry["total_mutants"]  = raw.get("total_mutants")


def _build_entry(mode: str, func: str) -> dict:
    tags = _run_tags(mode)

    if tags:
        # Multi-run: average across all run subdirectories
        records = []
        for tag in tags:
            test_file = ROOT / "generated_tests" / mode / tag / f"test_{func}.py"
            if not test_file.exists():
                continue
            rec = _rerun_and_classify(test_file, mode, func, tag)
            _attach_mutation(rec, mode, func, tag)
            records.append(rec)
        if not records:
            print(f"  [skip] {mode}/{func} — no run test files found")
            return {}
        entry = _avg_dicts(records)
        n_runs = entry["n_runs"]
        print(f"  [{mode}] {func} … averaged {n_runs} runs, "
              f"mut={entry['mutation_score']}")
        return entry

    # Single run
    test_file = ROOT / "generated_tests" / mode / f"test_{func}.py"
    if not test_file.exists():
        print(f"  [skip] {mode}/{func} — test file missing")
        return {}

    print(f"  [{mode}] {func} … ", end="", flush=True)
    fresh = _rerun_and_classify(test_file, mode, func)
    _attach_mutation(fresh, mode, func)

    passed = fresh["passed_count"]
    total  = fresh["total_count"]
    n_fail = len(fresh["failures"])
    print(f"{passed}/{total} passed, {n_fail} failures classified, "
          f"mut={fresh['mutation_score']}")
    return fresh


def rebuild() -> dict:
    all_results: dict = {}

    print("\n=== Rebuilding LLM mode results ===")
    for func in FUNCTIONS:
        all_results[func] = {}
        for mode in MODES:
            entry = _build_entry(mode, func)
            if entry:
                all_results[func][mode] = entry

    print("\n=== Rebuilding human baseline results ===")
    for func in HUMAN_FUNCTIONS:
        test_file = ROOT / "generated_tests" / "human" / f"test_{func}.py"
        if not test_file.exists():
            print(f"  [skip] human/{func} — test file missing")
            continue
        print(f"  [human] {func} … ", end="", flush=True)
        entry = _rerun_and_classify(test_file, "human", func)
        _attach_mutation(entry, "human", func)
        passed = entry["passed_count"]
        total  = entry["total_count"]
        print(f"{passed}/{total} passed")
        all_results[func]["human"] = entry

    # Remove empty function entries
    all_results = {f: m for f, m in all_results.items() if m}
    return all_results


def _mode_winner(sa: int, so: int) -> str:
    if sa > so:
        return "source_aware"
    if so > sa:
        return "spec_only"
    return "tie"


def _failure_totals(all_results: dict) -> dict:
    totals: dict = {}
    for modes in all_results.values():
        for d in modes.values():
            for f in d.get("failures", []):
                totals[f["category"]] = totals.get(f["category"], 0) + 1
    return totals


def _print_mode_row(row: dict) -> None:
    print(f"\n  Mode: {row['mode']}")
    pr = row["avg_pass_rate"]
    print("    Avg pass rate       : " + (f"{pr:.1f}%" if pr is not None else "N/A"))
    ms = row["avg_mutation_score"]
    print("    Avg mutation score  : " + (f"{ms:.4f}" if ms is not None else "N/A"))


def _print_summary(all_results: dict) -> None:
    mode_sum = compute_mode_summary(all_results)
    wins     = compute_wins(all_results)

    total_funcs = sum(1 for modes in all_results.values() for m in modes if m in MODES)
    sep = "=" * 60
    print(f"\n{sep}")
    print("  BENCHMARK SUMMARY")
    print(sep)
    print(f"  Functions completed : {total_funcs} of {len(FUNCTIONS) * len(MODES)} "
          f"({len(FUNCTIONS)} funcs x {len(MODES)} modes)")

    for row in mode_sum:
        _print_mode_row(row)

    totals = _failure_totals(all_results)
    if totals:
        top_cat = max(totals, key=totals.__getitem__)
        print(f"\n  Most common failure : {top_cat} ({totals[top_cat]} occurrences)")
    else:
        print("\n  Most common failure : none recorded")

    print("\n  Mode wins (source_aware vs spec_only):")
    for mk in METRIC_KEYS:
        sa = wins["source_aware"][mk]
        so = wins["spec_only"][mk]
        print(f"    {mk:<25} source_aware={sa}  spec_only={so}  -> {_mode_winner(sa, so)}")
    print()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_results = rebuild()

    print("\n=== Saving output files ===")
    save_json(all_results,              str(OUTPUT_DIR / "all_results.json"))
    save_csv(all_results,               str(OUTPUT_DIR / "results_table.csv"))
    save_mode_summary_csv(all_results,  str(OUTPUT_DIR / "mode_summary.csv"))
    save_category_summary_csv(all_results, str(OUTPUT_DIR / "category_summary.csv"))
    save_failure_summary(all_results,   str(OUTPUT_DIR / "failure_summary.json"))
    generate_markdown(all_results,      str(OUTPUT_DIR / "report.md"))

    _print_summary(all_results)


if __name__ == "__main__":
    main()
