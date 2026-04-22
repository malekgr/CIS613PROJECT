import ast
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Coverage parsing
# ---------------------------------------------------------------------------

def compute_coverage(coverage_json: str, func_name: str, source_file: str = None) -> dict:
    """
    Extract target-function coverage, module line coverage, and branch coverage
    from a pytest-cov JSON report.  Returns all three as percentages.
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

            func_data = file_data.get("functions", {}).get(func_name, {})
            func_pct = func_data.get("summary", {}).get("percent_covered")
            if func_pct is not None:
                func_pct = round(func_pct, 2)

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
# Mutation testing (function-scoped)
# ---------------------------------------------------------------------------

_FLIP_MAP = {
    ast.LtE: ast.Lt,
    ast.Lt:  ast.LtE,
    ast.GtE: ast.Gt,
    ast.Gt:  ast.GtE,
    ast.Eq:  ast.NotEq,
    ast.NotEq: ast.Eq,
}

_ARITH_FLIP_MAP = {
    ast.Add:      ast.Sub,
    ast.Sub:      ast.Add,
    ast.Mult:     ast.FloorDiv,
    ast.FloorDiv: ast.Mult,
    ast.Mod:      ast.Mult,
}

_BOOLOP_FLIP_MAP = {
    ast.And: ast.Or,
    ast.Or:  ast.And,
}


class _ScopedCompareFlip(ast.NodeTransformer):
    """Flip one comparison operator inside the target function."""

    def __init__(self, target_idx: int, func_name: str):
        self.target_idx = target_idx
        self.func_name = func_name
        self._idx = 0
        self._in_scope = False
        self.mutated = False

    def visit_FunctionDef(self, node):
        if node.name == self.func_name:
            self._in_scope = True
            self.generic_visit(node)
            self._in_scope = False
        return node

    def visit_Compare(self, node):
        if not self._in_scope:
            return node
        self.generic_visit(node)
        new_ops = []
        for op in node.ops:
            if not self.mutated and self._idx == self.target_idx and type(op) in _FLIP_MAP:
                new_ops.append(_FLIP_MAP[type(op)]())
                self.mutated = True
            else:
                new_ops.append(op)
            self._idx += 1
        node.ops = new_ops
        return node


class _ScopedReturnFlip(ast.NodeTransformer):
    """Rotate one string return value inside the target function."""

    def __init__(self, target_idx: int, func_name: str, cycle: dict):
        self.target_idx = target_idx
        self.func_name = func_name
        self.cycle = cycle
        self._idx = 0
        self._in_scope = False
        self.mutated = False

    def visit_FunctionDef(self, node):
        if node.name == self.func_name:
            self._in_scope = True
            self.generic_visit(node)
            self._in_scope = False
        return node

    def visit_Return(self, node):
        if (
            self._in_scope
            and not self.mutated
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and node.value.value in self.cycle
        ):
            if self._idx == self.target_idx:
                node.value = ast.Constant(value=self.cycle[node.value.value])
                self.mutated = True
            self._idx += 1
        return node


class _ScopedBinOpFlip(ast.NodeTransformer):
    """Flip one arithmetic BinOp inside the target function."""

    def __init__(self, target_idx: int, func_name: str):
        self.target_idx = target_idx
        self.func_name  = func_name
        self._idx       = 0
        self._in_scope  = False
        self.mutated    = False

    def visit_FunctionDef(self, node):
        if node.name == self.func_name:
            self._in_scope = True
            self.generic_visit(node)
            self._in_scope = False
        return node

    def visit_BinOp(self, node):
        if not self._in_scope:
            return node
        self.generic_visit(node)
        if not self.mutated and self._idx == self.target_idx and type(node.op) in _ARITH_FLIP_MAP:
            node.op = _ARITH_FLIP_MAP[type(node.op)]()
            self.mutated = True
        self._idx += 1
        return node


class _ScopedBoolOpFlip(ast.NodeTransformer):
    """Flip And↔Or inside the target function."""

    def __init__(self, target_idx: int, func_name: str):
        self.target_idx = target_idx
        self.func_name  = func_name
        self._idx       = 0
        self._in_scope  = False
        self.mutated    = False

    def visit_FunctionDef(self, node):
        if node.name == self.func_name:
            self._in_scope = True
            self.generic_visit(node)
            self._in_scope = False
        return node

    def visit_BoolOp(self, node):
        if not self._in_scope:
            return node
        self.generic_visit(node)
        if not self.mutated and self._idx == self.target_idx and type(node.op) in _BOOLOP_FLIP_MAP:
            node.op = _BOOLOP_FLIP_MAP[type(node.op)]()
            self.mutated = True
        self._idx += 1
        return node


class _ScopedNotRemove(ast.NodeTransformer):
    """Remove one 'not' operator (replace UnaryOp(Not, x) with x) inside the target function."""

    def __init__(self, target_idx: int, func_name: str):
        self.target_idx = target_idx
        self.func_name  = func_name
        self._idx       = 0
        self._in_scope  = False
        self.mutated    = False

    def visit_FunctionDef(self, node):
        if node.name == self.func_name:
            self._in_scope = True
            self.generic_visit(node)
            self._in_scope = False
        return node

    def visit_UnaryOp(self, node):
        if not self._in_scope:
            return node
        self.generic_visit(node)
        if not self.mutated and self._idx == self.target_idx and isinstance(node.op, ast.Not):
            self.mutated = True
            self._idx += 1
            return node.operand  # strip the 'not'
        self._idx += 1
        return node


class _ScopedConstantOffByOne(ast.NodeTransformer):
    """Decrement one integer constant by 1 inside the target function."""

    def __init__(self, target_idx: int, func_name: str):
        self.target_idx = target_idx
        self.func_name  = func_name
        self._idx       = 0
        self._in_scope  = False
        self.mutated    = False

    def visit_FunctionDef(self, node):
        if node.name == self.func_name:
            self._in_scope = True
            self.generic_visit(node)
            self._in_scope = False
        return node

    def visit_Constant(self, node):
        if not self._in_scope:
            return node
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            if not self.mutated and self._idx == self.target_idx:
                node.value = node.value - 1
                self.mutated = True
            self._idx += 1
        return node


def _count_scoped_ops(tree, func_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return sum(
                1 for n in ast.walk(node)
                if isinstance(n, ast.Compare)
                for op in n.ops
                if type(op) in _FLIP_MAP
            )
    return 0


def _collect_scoped_string_returns(tree, func_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return [
                n.value.value
                for n in ast.walk(node)
                if isinstance(n, ast.Return)
                and isinstance(n.value, ast.Constant)
                and isinstance(n.value.value, str)
            ]
    return []


def _count_scoped_binops(tree, func_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return sum(
                1 for n in ast.walk(node)
                if isinstance(n, ast.BinOp) and type(n.op) in _ARITH_FLIP_MAP
            )
    return 0


def _count_scoped_boolops(tree, func_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return sum(
                1 for n in ast.walk(node)
                if isinstance(n, ast.BoolOp) and type(n.op) in _BOOLOP_FLIP_MAP
            )
    return 0


def _count_scoped_nots(tree, func_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return sum(
                1 for n in ast.walk(node)
                if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not)
            )
    return 0


def _count_scoped_int_constants(tree, func_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return sum(
                1 for n in ast.walk(node)
                if isinstance(n, ast.Constant)
                and isinstance(n.value, int)
                and not isinstance(n.value, bool)
            )
    return 0


def _apply_transformer(tree, transformer_cls, *args) -> Optional[str]:
    t = copy.deepcopy(tree)
    tf = transformer_cls(*args)
    tf.visit(t)
    if not tf.mutated:
        return None
    ast.fix_missing_locations(t)
    try:
        return ast.unparse(t)
    except Exception:
        return None


def _apply_n(tree, func_name, transformer_cls, count, extra_args=()):
    """Apply transformer_cls for each index in range(count); return generated mutant strings."""
    return [
        m for i in range(count)
        if (m := _apply_transformer(tree, transformer_cls, i, func_name, *extra_args))
    ]


def _string_return_mutants(tree, func_name):
    str_returns = _collect_scoped_string_returns(tree, func_name)
    unique = list(dict.fromkeys(str_returns))
    if len(unique) < 2:
        return []
    cycle = {unique[i]: unique[(i + 1) % len(unique)] for i in range(len(unique))}
    return _apply_n(tree, func_name, _ScopedReturnFlip, len(str_returns), extra_args=(cycle,))


def _generate_mutants(source: str, func_name: str) -> list:
    tree = ast.parse(source)
    return [
        *_apply_n(tree, func_name, _ScopedCompareFlip,       _count_scoped_ops(tree, func_name)),
        *_string_return_mutants(tree, func_name),
        *_apply_n(tree, func_name, _ScopedBinOpFlip,         _count_scoped_binops(tree, func_name)),
        *_apply_n(tree, func_name, _ScopedBoolOpFlip,        _count_scoped_boolops(tree, func_name)),
        *_apply_n(tree, func_name, _ScopedNotRemove,         _count_scoped_nots(tree, func_name)),
        *_apply_n(tree, func_name, _ScopedConstantOffByOne,  _count_scoped_int_constants(tree, func_name)),
    ]


def _run_pytest(test_file: str, project_root: str) -> int:
    """Run pytest and return the number of failing tests (0 = all passed)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "-q", "--tb=no", "--no-header"],
        capture_output=True, text=True, cwd=project_root,
    )
    # exit code 5 = no tests collected; treat as 0 failures
    if result.returncode == 5:
        return 0
    # parse "X failed" from pytest summary line
    import re
    m = re.search(r"(\d+) failed", result.stdout)
    if m:
        return int(m.group(1))
    return 1 if result.returncode != 0 else 0


def compute_mutation_score(source_file: str, func_name: str, test_file: str, project_root: str) -> dict:
    """Mutate only the target function and check whether test_file catches each mutant."""
    source_path = Path(source_file)
    original = source_path.read_text()
    backup = source_path.with_suffix(".bak")

    mutants = _generate_mutants(original, func_name)
    if not mutants:
        return {"mutation_score": None, "killed": 0, "total": 0}

    # Establish baseline failures on original code so pre-existing failures
    # are not counted as the tests killing a mutant.
    baseline_failures = _run_pytest(test_file, project_root)

    shutil.copy(source_path, backup)
    killed = 0
    try:
        for mutant in mutants:
            source_path.write_text(mutant)
            mutant_failures = _run_pytest(test_file, project_root)
            if mutant_failures > baseline_failures:
                killed += 1
    finally:
        shutil.copy(backup, source_path)
        backup.unlink(missing_ok=True)

    return {
        "mutation_score": round(killed / len(mutants), 4),
        "killed": killed,
        "total": len(mutants),
    }


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
