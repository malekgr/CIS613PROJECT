import time
from pathlib import Path

from src.pipeline import run_pipeline
from src.failure_analyzer import summarize_failures

# All functions in the benchmark dataset
BENCHMARK_FUNCTIONS = [
    "classify_triangle",
    "factorial",
    "is_prime",
    "gcd",
    "reverse_string",
    "is_palindrome",
    "max_in_list",
    "count_vowels",
]

# Functions that have a hand-written human baseline
HUMAN_BASELINE_FUNCTIONS = BENCHMARK_FUNCTIONS

LLM_MODES = ["source_aware"]

# Seconds to wait between LLM calls to respect rate limits
_INTER_CALL_DELAY = 8

_NUMERIC_KEYS = [
    "passed_count", "failed_count", "total_count",
    "execution_success_rate", "function_coverage_pct", "module_coverage_pct",
    "branch_coverage_pct", "mutation_score", "killed", "total_mutants",
    "total_assertions", "assertions_per_test", "value_assertion_ratio",
    "latency_s", "tokens_used", "cost_estimate_usd",
]


def _average_runs(results: list) -> dict:
    """Merge N per-run metric dicts into one averaged entry."""
    avg: dict = {}
    for k in _NUMERIC_KEYS:
        vals = [r[k] for r in results if r.get(k) is not None]
        avg[k] = round(sum(vals) / len(vals), 4) if vals else None
    failures = [f for r in results for f in r.get("failures", [])]
    avg["failures"]       = failures
    avg["failure_summary"] = summarize_failures(failures)
    avg["n_runs"]         = len(results)
    avg["mode"]           = results[0]["mode"]
    avg["function"]       = results[0]["function"]
    avg["test_file"]      = results[0]["test_file"]
    return avg


def _run_one(source_file, func_name, project_root, mode, run_index):
    """Execute a single pipeline run and return the metrics dict."""
    try:
        return run_pipeline(
            source_file=source_file,
            function_name=func_name,
            project_root=project_root,
            mode=mode,
            verbose=True,
            run_index=run_index,
        )
    except Exception as exc:
        print(f"  [ERROR] {func_name}/{mode}: {exc}")
        return _error_record(func_name, mode, str(exc))


def _run_mode(source_file, func_name, project_root, mode, n_runs, call_num, total_calls):
    """Run all repetitions for one (func, mode) pair; return averaged entry and updated call_num."""
    run_results = []
    for run_idx in range(1, n_runs + 1):
        idx_tag = f"run {run_idx}/{n_runs}" if n_runs > 1 else ""
        print(f"\n{'#'*60}")
        print(f"# [{call_num}/{total_calls}]  {func_name}  ·  {mode}  {idx_tag}")
        print(f"{'#'*60}")

        run_index = run_idx if n_runs > 1 else None
        run_results.append(_run_one(source_file, func_name, project_root, mode, run_index))
        call_num += 1
        if call_num <= total_calls:
            time.sleep(_INTER_CALL_DELAY)

    entry = _average_runs(run_results) if n_runs > 1 else run_results[0]
    return entry, call_num


def run_benchmark(
    source_file: str,
    project_root: str,
    functions: list = None,
    modes: list = None,
    include_human: bool = True,
    n_runs: int = 1,
) -> dict:
    """
    Run every (function, mode) combination and return a nested results dict:
      results[function_name][mode] = metrics_dict

    n_runs > 1: runs the LLM generation n_runs times and averages the metrics.
    """
    root = Path(project_root)
    functions = functions or BENCHMARK_FUNCTIONS
    modes = modes or LLM_MODES

    all_results: dict = {fn: {} for fn in functions}
    total_calls = len(functions) * len(modes) * n_runs
    call_num = 1

    for func_name in functions:
        for mode in modes:
            entry, call_num = _run_mode(
                source_file, func_name, project_root, mode, n_runs, call_num, total_calls
            )
            all_results[func_name][mode] = entry

    if include_human:
        _run_human_baselines(all_results, source_file, project_root, root)

    return all_results


def _run_human_baselines(all_results, source_file, project_root, root):
    """Run all human-written tests through the same metric pipeline (single run)."""
    human_test_dir = root / "dataset" / "human_tests"
    dest_dir = root / "generated_tests" / "human"
    dest_dir.mkdir(parents=True, exist_ok=True)

    for func_name in HUMAN_BASELINE_FUNCTIONS:
        test_file = human_test_dir / f"test_{func_name}.py"
        if not test_file.exists():
            print(f"\n[human] Skipping {func_name}: no test file at {test_file}")
            continue

        print(f"\n{'#'*60}")
        print(f"# [human baseline]  {func_name}")
        print(f"{'#'*60}")

        dest = dest_dir / f"test_{func_name}.py"
        dest.write_text(test_file.read_text(), encoding="utf-8")

        try:
            metrics = run_pipeline(
                source_file=source_file,
                function_name=func_name,
                project_root=project_root,
                mode="human",
                test_file_override=str(dest),
                verbose=True,
            )
            all_results[func_name]["human"] = metrics
        except Exception as exc:
            print(f"  [ERROR] {func_name}/human: {exc}")
            all_results[func_name]["human"] = _error_record(func_name, "human", str(exc))


def _error_record(func_name: str, mode: str, error: str) -> dict:
    return {
        "mode": mode, "function": func_name, "test_file": "", "error": error,
        "passed_count": 0, "failed_count": 0, "total_count": 0,
        "execution_success_rate": None, "function_coverage_pct": None,
        "module_coverage_pct": None, "mutation_score": None,
        "killed": 0, "total_mutants": 0, "total_assertions": 0,
        "assertions_per_test": None, "value_assertion_ratio": None,
        "failures": [], "failure_summary": {},
    }
