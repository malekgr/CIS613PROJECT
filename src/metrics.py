from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Coverage parsing
# ---------------------------------------------------------------------------

def _function_line_coverage(source_file: str, func_name: str, file_data: dict) -> float | None:
    """
    Compute line-coverage % for a single function using AST line ranges.

    coverage.py's JSON output does not include a per-function breakdown, so we
    compute it manually: find all source lines that belong to the target
    function definition, then check how many of those lines appear in
    executed_lines.
    """
    try:
        source = Path(source_file).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return None

    func_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            func_node = node
            break

    if func_node is None:
        return None

    func_lines = {
        node.lineno
        for node in ast.walk(func_node)
        if hasattr(node, "lineno")
    }
    if not func_lines:
        return None

    executed = set(file_data.get("executed_lines", []))
    covered = len(func_lines & executed)
    return round(covered / len(func_lines) * 100, 2)


def compute_coverage(coverage_json: str, func_name: str, source_file: str = None) -> dict:
    """
    Extract target-function coverage, module line coverage, and branch coverage
    from a pytest-cov JSON report.  Returns all three as percentages.

    Function-level coverage is computed via AST line-range intersection because
    coverage.py's JSON format does not include a per-function breakdown.
    """
    try:
        data = json.loads(Path(coverage_json).read_text())
    except Exception:
        return {"function_coverage_pct": None, "module_coverage_pct": None,
                "branch_coverage_pct": None}

    match_key = Path(source_file).stem if source_file else "sample_functions"

    for _path, file_data in data.get("files", {}).items():
        if match_key in _path:
            summary = file_data.get("summary", {})
            module_pct = round(summary.get("percent_covered", 0.0), 2)

            func_pct = (
                _function_line_coverage(source_file, func_name, file_data)
                if source_file else None
            )

            branch_pct = None
            num_branches = summary.get("num_branches", 0)
            if num_branches:
                covered_branches = summary.get("covered_branches", 0)
                branch_pct = round(covered_branches / num_branches * 100, 2)

            return {
                "function_coverage_pct": func_pct,
                "module_coverage_pct": module_pct,
                "branch_coverage_pct": branch_pct,
            }

    return {"function_coverage_pct": None, "module_coverage_pct": None,
            "branch_coverage_pct": None}


# ---------------------------------------------------------------------------
# Mutation testing — mutmut 3.x
# ---------------------------------------------------------------------------

def run_mutmut(source_file: str, test_file: str, project_root: str) -> None:
    """Run `mutmut run` in project_root so that .meta results are available.

    Writes a setup.cfg configured for this source/test pair, then runs
    mutmut. The .meta file is written to mutants/<source_file>.meta and
    is read by compute_mutation_score().
    """
    project_path = Path(project_root)
    src_rel = str(Path(source_file).relative_to(project_path)
                  if Path(source_file).is_absolute() else Path(source_file))

    test_path = Path(test_file)
    tests_rel = str(test_path.relative_to(project_path)
                    if test_path.is_absolute() else test_path)

    src_pkg = str(Path(src_rel).parent)
    also_copy_lines = []
    init = project_path / src_pkg / "__init__.py"
    if init.exists():
        also_copy_lines.append(f"    {src_pkg}/__init__.py")
    also_copy_lines.append(f"    {tests_rel}")

    cfg_content = (
        "[mutmut]\n"
        f"paths_to_mutate = {src_rel}\n"
        f"tests_dir = {tests_rel}\n"
        "also_copy =\n"
        + "\n".join(also_copy_lines)
        + "\n\n"
        "[tool:pytest]\n"
        "addopts = -p no:anyio\n"
    )
    (project_path / "setup.cfg").write_text(cfg_content)

    subprocess.run(
        [sys.executable, "-m", "mutmut", "run"],
        capture_output=True, cwd=project_root,
    )


def _read_mutmut_meta(project_root: str, source_file: str) -> dict | None:
    """Load .meta JSON from mutants/<source_file>.meta, return exit_code_by_key or None."""
    try:
        rel = Path(source_file).relative_to(Path(project_root))
    except ValueError:
        rel = Path(source_file)
    meta_path = Path(project_root) / "mutants" / (str(rel) + ".meta")
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text())["exit_code_by_key"]
    except Exception:
        return None


def _mutmut_score_from_meta(exit_codes: dict, func_name: str) -> dict | None:
    """Extract per-function mutation score from mutmut's exit_code_by_key dict.

    mutmut 3.x names mutants as:
        <module>.x_<func>__mutmut_<n>   (top-level function)
        <module>.x__<Class>__<method>__mutmut_<n>  (method)
    We filter by the mangled function name prefix.
    """
    in_scope = [
        code for key, code in exit_codes.items()
        if (suffix := key.split(".")[-1]) and (
            suffix.startswith(f"x_{func_name}__mutmut_")          # top-level function
            or f"ǁ{func_name}__mutmut_" in suffix            # class method (xǁClassǁmethod)
        )
    ]
    if not in_scope:
        return None
    total = len(in_scope)
    # mutmut exit codes 1 and 3 = killed
    killed = sum(1 for c in in_scope if c in (1, 3))
    return {
        "mutation_score": round(killed / total, 4),
        "killed": killed,
        "total": total,
    }


def compute_mutation_score(source_file: str, func_name: str, project_root: str) -> dict:
    """Compute mutation score for func_name using mutmut 3.x.

    Reads results from the pre-generated mutants/<source>.meta file produced by
    running `python3 -m mutmut run` in the project root. If the meta file is
    missing or has no entries for this function, returns null scores.

    mutmut must be run once (or re-run when source changes) before this is
    called. The pipeline triggers it automatically before computing metrics.
    """
    exit_codes = _read_mutmut_meta(project_root, source_file)
    if exit_codes is None:
        return {"mutation_score": None, "killed": 0, "total": 0}
    result = _mutmut_score_from_meta(exit_codes, func_name)
    if result is None:
        return {"mutation_score": None, "killed": 0, "total": 0}
    return result


# ---------------------------------------------------------------------------
# Assertion quality
# ---------------------------------------------------------------------------

def _is_value_assertion(test_node) -> bool:
    """Return True if the assertion checks a value rather than mere truthiness/type."""
    # any comparison operator (==, !=, <, <=, >, >=, in, not in) is a value check
    if isinstance(test_node, ast.Compare):
        return True
    # pytest.approx(...) or similar call-based value checks
    if isinstance(test_node, ast.Call):
        return True
    return False


def analyze_assertions(test_file: str) -> dict:
    """Count tests and evaluate oracle quality from the test file's AST."""
    try:
        source = Path(test_file).read_text()
        tree = ast.parse(source)
    except Exception:
        return {
            "total_tests": 0,
            "total_assertions": 0,
            "assertions_per_test": 0.0,
            "value_assertion_ratio": 0.0,
        }

    test_funcs = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]
    total_tests = len(test_funcs)
    total_assertions = 0
    value_assertions = 0

    for func in test_funcs:
        for node in ast.walk(func):
            if isinstance(node, ast.Assert):
                total_assertions += 1
                if _is_value_assertion(node.test):
                    value_assertions += 1

    return {
        "total_tests": total_tests,
        "total_assertions": total_assertions,
        "assertions_per_test": round(total_assertions / total_tests, 2) if total_tests else 0.0,
        "value_assertion_ratio": round(value_assertions / total_assertions, 4) if total_assertions else 0.0,
    }
