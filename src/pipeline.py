import json
import time
from pathlib import Path

from src.loader import load_function_from_file
from src.parser import extract_context
from src.prompt_builder import build_prompt, build_chunked_prompt
from src.llm_generator import generate_tests
from src.test_runner import run_tests
from src.metrics import compute_mutation_score, analyze_assertions, compute_coverage
from src.failure_analyzer import classify_failures, summarize_failures


def _generate_and_save(func, source, function_name, mode, root, import_path=None):
    """Run LLM generation and save test file. Returns Path."""
    context = extract_context(func, source)
    kwargs = {"import_path": import_path} if import_path else {}
    prompt = build_prompt(context, **kwargs)
    test_code = generate_tests(prompt)
    test_dir = root / "generated_tests" / mode
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / f"test_{function_name}.py"
    test_file.write_text(test_code, encoding="utf-8")
    return test_file


def _collect_metrics(source_file, function_name, test_file, project_root, run_result, coverage_path):
    """Aggregate all metrics into a flat dict."""
    cov = compute_coverage(coverage_path, function_name, source_file)
    mutation = compute_mutation_score(source_file, function_name, str(test_file), project_root)
    assertion_stats = analyze_assertions(str(test_file))
    failures = classify_failures(run_result["stdout"], run_result["stderr"])

    return {
        "passed_count": run_result["passed_count"],
        "failed_count": run_result["failed_count"],
        "total_count": run_result["total_count"],
        "execution_success_rate": run_result["execution_success_rate"],
        "function_coverage_pct": cov["function_coverage_pct"],
        "module_coverage_pct": cov["module_coverage_pct"],
        "branch_coverage_pct": cov["branch_coverage_pct"],
        "mutation_score": mutation["mutation_score"],
        "killed": mutation["killed"],
        "total_mutants": mutation["total"],
        "total_assertions": assertion_stats["total_assertions"],
        "assertions_per_test": assertion_stats["assertions_per_test"],
        "value_assertion_ratio": assertion_stats["value_assertion_ratio"],
        "failures": failures,
        "failure_summary": summarize_failures(failures),
    }


def _print_header(mode, function_name):
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  MODE: {mode.upper()}  |  FUNCTION: {function_name}")
    print(sep)


def _print_results(run_result, cov_info, mutation_info, failures):
    print("\n" + run_result["stdout"])
    if run_result["stderr"] and "warning" not in run_result["stderr"].lower():
        print("STDERR:", run_result["stderr"])
    status = "PASSED" if run_result["passed"] else "FAILED"
    print(f"Result: {status}  |  {run_result['passed_count']}/{run_result['total_count']} tests passed")
    print(f"       Function coverage : {cov_info['function_coverage_pct']}%"
          f"  |  Module: {cov_info['module_coverage_pct']}%"
          f"  |  Branch: {cov_info.get('branch_coverage_pct')}%")
    print(f"       Mutation score    : {mutation_info['mutation_score']}"
          f"  ({mutation_info['killed']}/{mutation_info['total']} killed)")
    if failures:
        print(f"       Failures classified: {summarize_failures(failures)}")


def _resolve_paths(root: Path, mode: str, function_name: str, run_index):
    """Return (test_dir_name, results_dir, coverage_path, header_tag) for a run."""
    run_tag = f"run{run_index}" if run_index is not None else None
    subdir  = f"{mode}/{run_tag}" if run_tag else mode
    results_dir  = root / "results" / "benchmark" / "raw" / subdir
    results_dir.mkdir(parents=True, exist_ok=True)
    coverage_path = str(results_dir / f"coverage_{function_name}.json")
    header_tag    = f"{mode} [run {run_index}]" if run_index is not None else mode
    return subdir, results_dir, coverage_path, header_tag


def _resolve_test_file(func, source, function_name, test_dir_name, root,
                       test_file_override, verbose, import_path=None):
    if test_file_override:
        if verbose:
            print(f"[LLM skipped] Using human-written tests: {test_file_override}")
        return Path(test_file_override)
    if verbose:
        print("[1/6] Load  [2/6] Context  [3/6] Prompt  [4/6] Generate")
    test_file = _generate_and_save(func, source, function_name, test_dir_name, root,
                                   import_path=import_path)
    if verbose:
        print(f"       Saved -> {test_file}")
    return test_file


def _generate_and_save_chunked(
    source_file: str, target: str, chunk_mode_str: str,
    test_dir_name: str, root: Path, import_path: str,
) -> tuple[Path, dict]:
    """Chunked generation path. Returns (test_file, chunk_metadata)."""
    from src.chunker import ChunkMode, SmartChunker

    chunk_mode = ChunkMode(chunk_mode_str)
    chunker = SmartChunker(source_file)
    chunk = chunker.build(target, chunk_mode, import_path=import_path or "module")

    prompt = build_chunked_prompt(chunk)
    test_code = generate_tests(prompt)

    func_name = chunk.function_name
    test_dir = root / "generated_tests" / f"{test_dir_name}"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / f"test_{func_name}.py"
    test_file.write_text(test_code, encoding="utf-8")

    meta = {
        "chunk_mode": chunk_mode_str,
        "tokens_used": chunk.tokens_used,
        "cost_estimate_usd": chunk.cost_estimate_usd,
    }
    return test_file, meta


def run_pipeline(
    source_file: str,
    function_name: str,
    project_root: str,
    mode: str = "source_aware",
    test_file_override: str = None,
    verbose: bool = True,
    run_index: int = None,
    import_path: str = None,
    cov_target: str = None,
    chunking_mode: str = None,
    log_callback=None,
) -> dict:
    """
    Execute the full test-generation and evaluation pipeline.

    Parameters
    ----------
    chunking_mode : One of the ChunkMode values (e.g. "function_only",
                    "function_plus_deps", "class_context",
                    "hierarchical_summary", "token_budget", "full_source").
                    When set the SmartChunker is used instead of the legacy
                    loader+parser path.  Supports "ClassName.method" targets
                    via *function_name*.
    run_index     : When set (1-based), files are stored under run{n}/ subdirs.
    """
    root = Path(project_root)

    # Bare function name for directory/file naming (strip class prefix)
    bare_name = function_name.split(".")[-1] if "." in function_name else function_name

    test_dir_name, results_dir, coverage_path, header_tag = _resolve_paths(
        root, mode, bare_name, run_index
    )

    if verbose:
        _print_header(header_tag, function_name)

    chunk_meta: dict = {}
    t0 = time.monotonic()

    def _cb(msg):
        if log_callback:
            log_callback(msg)

    if chunking_mode:
        # --- Chunked path ---------------------------------------------------
        if verbose:
            print(f"[1/5] SmartChunker  [2/5] Prompt  [3/5] Generate  (chunk={chunking_mode})")
        if not test_file_override:
            _cb("  → building context chunk…")
            _cb("  → calling LLM (gemini-2.5-flash)…")
            test_file, chunk_meta = _generate_and_save_chunked(
                source_file, function_name, chunking_mode,
                test_dir_name, root, import_path or "",
            )
        else:
            test_file = Path(test_file_override)
    else:
        # --- Legacy path (backward compatible) ------------------------------
        func, source = load_function_from_file(source_file, bare_name)
        _cb("  → calling LLM (gemini-2.5-flash)…")
        test_file = _resolve_test_file(
            func, source, bare_name, test_dir_name, root,
            test_file_override, verbose, import_path=import_path,
        )

    latency_s = round(time.monotonic() - t0, 3)

    effective_cov = cov_target or "dataset"
    _cb("  → running pytest + coverage…")
    if verbose:
        print("[+] Running pytest + coverage")
    run_result = run_tests(str(test_file), project_root,
                           coverage_output=coverage_path, cov_target=effective_cov)

    _cb("  → computing coverage & mutation score…")
    if verbose:
        print("[+] Mutation + assertions + failure analysis")
    metrics = _collect_metrics(
        source_file, bare_name, test_file, project_root, run_result, coverage_path
    )

    if verbose:
        cov_info = {"function_coverage_pct": metrics["function_coverage_pct"],
                    "module_coverage_pct": metrics["module_coverage_pct"],
                    "branch_coverage_pct": metrics["branch_coverage_pct"]}
        mut_info = {"mutation_score": metrics["mutation_score"],
                    "killed": metrics["killed"], "total": metrics["total_mutants"]}
        _print_results(run_result, cov_info, mut_info, metrics["failures"])

    result = {
        "mode": mode,
        "function": function_name,
        "test_file": str(test_file),
        "latency_s": latency_s,
        **chunk_meta,
        **metrics,
    }

    (results_dir / f"metrics_{bare_name}.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )

    return result
