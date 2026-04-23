"""
Failure analyzer — classifies pytest failure blocks into precise research categories.

Parsing strategy:
  1. Extract only the FAILURES section from pytest stdout (avoids false positives).
  2. Split that section into per-test blocks delimited by _____ test_name _____ lines.
  3. Classify each block using ordered rule matching.
"""
import re

ORACLE_ERROR            = "oracle_error"           # wrong hardcoded expected value
HALLUCINATED_BEHAVIOR   = "hallucinated_behavior"   # behavior absent from the spec
TYPE_ASSUMPTION_ERROR   = "type_assumption_error"   # LLM assumed type restriction not in spec
EXPECTED_EXCEPTION_MISSING = "expected_exception_missing"  # pytest.raises but nothing raised
WRONG_EXCEPTION_TYPE    = "wrong_exception_type"    # wrong exception class raised
SYNTAX_ERROR            = "syntax_error"            # test file has a SyntaxError
IMPORT_ERROR            = "import_error"            # import / attribute lookup failed
UNSUPPORTED_EDGE_CASE   = "unsupported_edge_case"   # edge case not covered by the spec
FLAKY_GENERATION        = "flaky_generation"        # non-deterministic or ambiguous assertion


def classify_failures(pytest_stdout: str, pytest_stderr: str) -> list:
    """
    Return a list of failure dicts, each with:
      test_name, assertion, actual, expected, category, detail
    """
    # Handle collection errors first (test file never ran)
    collection = _parse_collection_errors(pytest_stdout, pytest_stderr)
    if collection:
        return collection

    failures_text = _extract_failures_section(pytest_stdout)
    if not failures_text:
        return []

    blocks, names = _split_into_blocks(failures_text)
    return [_classify_block(name, block) for name, block in zip(names, blocks)]


def summarize_failures(failures: list) -> dict:
    counts: dict = {}
    for f in failures:
        counts[f["category"]] = counts.get(f["category"], 0) + 1
    return counts


def _extract_failures_section(stdout: str) -> str:
    """Pull just the text between '=== FAILURES ===' and the very next '===' banner.

    Uses explicit string slicing so the match stops at the FIRST subsequent
    banner (e.g. 'tests coverage'), not the last one in the file.
    """
    header = re.search(r"={3,}\s*FAILURES\s*={3,}\n", stdout)
    if not header:
        return ""
    start = header.end()
    next_banner = re.search(r"\n={3,}", stdout[start:])
    end = start + next_banner.start() if next_banner else len(stdout)
    # Prepend newline so the first ___block___ separator matches \n_{5,}
    return "\n" + stdout[start:end]


# Matches pytest test names; filters out coverage/platform lines pytest-cov injects.
_TEST_NAME_RE = re.compile(r"^test_\w+", re.IGNORECASE)


def _split_into_blocks(failures_text: str) -> tuple:
    """Split failures text into (blocks, names) aligned lists.

    Silently drops any block whose name does not look like a pytest test function
    (e.g. the 'coverage: platform …' line that pytest-cov injects).
    """
    separator_pattern = r"\n_{5,}\s*(.+?)\s*_{5,}\n"
    raw_names = re.findall(separator_pattern, failures_text)
    parts = re.split(separator_pattern, failures_text)
    raw_blocks = parts[2::2] if len(parts) > 2 else []

    names, blocks = [], []
    for raw_name, block in zip(raw_names, raw_blocks):
        test_name = raw_name.split("::")[-1].strip()
        if _TEST_NAME_RE.match(test_name):
            names.append(test_name)
            blocks.append(block)
    return blocks, names


def _classify_block(test_name: str, block: str) -> dict:
    assertion = _extract_assertion_line(block)
    actual, expected = _extract_actual_expected(block)
    base = {"test_name": test_name, "assertion": assertion,
            "actual": actual, "expected": expected}
    cat, detail = _categorize(test_name, block, assertion, actual, expected)
    return {**base, "category": cat, "detail": detail}


def _categorize(test_name: str, block: str, assertion: str,
                actual: str, expected: str) -> tuple:
    lower = block.lower()

    cat = _check_file_errors(lower)
    if cat[0]:
        return cat

    cat = _check_exception_failures(block, lower)
    if cat[0]:
        return cat

    if _is_type_assumption(test_name, block, assertion):
        return TYPE_ASSUMPTION_ERROR, "LLM assumed type constraint absent from spec"

    if actual and expected:
        return _classify_value_mismatch(test_name, assertion, actual, expected, block)

    if _is_boolean_mismatch(block):
        if _is_type_assumption(test_name, block, assertion):
            return TYPE_ASSUMPTION_ERROR, "LLM assumed type constraint absent from spec"
        return ORACLE_ERROR, f"Boolean assertion failed: {assertion[:100]}"

    if "assertionerror" in lower:
        return ORACLE_ERROR, f"Assertion failed: {assertion[:120]}"

    return FLAKY_GENERATION, "Unclassifiable failure — possibly non-deterministic"


def _check_file_errors(lower: str) -> tuple:
    if "syntaxerror" in lower:
        return SYNTAX_ERROR, "SyntaxError in generated test file"
    if "importerror" in lower or "modulenotfounderror" in lower or "has no attribute" in lower:
        return IMPORT_ERROR, "Import or attribute lookup failed"
    return "", ""


def _check_exception_failures(block: str, lower: str) -> tuple:
    if "did not raise" in lower:
        exc = _extract_expected_exception(block)
        return EXPECTED_EXCEPTION_MISSING, f"Expected {exc} was not raised"
    if _is_wrong_exception(block):
        return WRONG_EXCEPTION_TYPE, "Wrong exception type was raised"
    return "", ""


def _classify_value_mismatch(test_name: str, assertion: str,
                              actual: str, expected: str, block: str) -> tuple:
    if _is_hallucinated(expected, block):
        return HALLUCINATED_BEHAVIOR, f"Expected value '{expected}' not derivable from spec"
    if _is_unsupported_edge_case(test_name, assertion):
        return UNSUPPORTED_EDGE_CASE, "Edge case not specified in function docstring"
    return ORACLE_ERROR, f"Wrong expected value: got {actual!r}, asserted {expected!r}"


def _extract_assertion_line(block: str) -> str:
    """Find the `assert ...` line inside the block."""
    m = re.search(r"^\s{4}assert\s+.+", block, re.MULTILINE)
    return m.group(0).strip() if m else ""


def _extract_actual_expected(block: str) -> tuple:
    """
    Pull actual/expected from lines like:
      E   AssertionError: assert 'invalid' == 'scalene'
      E   assert 1 == 3
    """
    # Pattern A: AssertionError: assert <actual> == <expected>
    m = re.search(r"AssertionError: assert (.+?) ==\s*(.+)", block)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # Pattern B: E   assert <actual> == <expected>  (pytest expanded output)
    m = re.search(r"^E\s+assert (.+?) ==\s*(.+)", block, re.MULTILINE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", ""


def _extract_expected_exception(block: str) -> str:
    """Try to find which exception was expected in a pytest.raises block."""
    m = re.search(r"raises\((\w+Error|\w+Exception)\)", block)
    return m.group(1) if m else "exception"


def _is_wrong_exception(block: str) -> bool:
    """True if an exception was raised but it's the wrong type."""
    lower = block.lower()
    return (
        "error" in lower
        and "assertionerror" not in lower
        and "did not raise" not in lower
        and "typeerror" in lower or "valueerror" in lower
        and "raises" in lower
    )


def _is_boolean_mismatch(block: str) -> bool:
    return bool(re.search(r"assert\s+(True|False)\s+is\s+(True|False)", block)
                or re.search(r"E\s+assert (True|False) is (True|False)", block))


def _is_type_assumption(test_name: str, block: str, assertion: str) -> bool:
    """
    Heuristic: the LLM assumed a type restriction not guaranteed by the spec.
    Signals:
    - test name contains 'float', 'string', 'non_numeric', 'invalid_type', 'non_string'
    - OR: function returns True but the assertion says `is False` (e.g. is_prime(3.0))
    """
    type_signals = re.search(
        r"(float|non.numeric|invalid.type|non.string|non.int|type.error|wrong.type)",
        test_name, re.IGNORECASE
    )
    if type_signals:
        # Only flag if the test actually failed with a value mismatch
        if "assertionerror" in block.lower() or "true is false" in block.lower():
            return True
    # also catch `assert True is False` patterns in is_prime-like functions
    if re.search(r"assert True is False|assert False is True", block):
        return True
    return False


def _is_hallucinated(expected: str, block: str) -> bool:
    """
    Heuristic: the expected value looks made-up.
    Flags cases where the expected value is a non-trivial string that appears
    ONLY in the assertion, not in the error message context.
    """
    if not expected:
        return False
    # Numbers and common sentinels are not hallucinated
    if re.fullmatch(r"[-\d.]+|True|False|None|'invalid'|\"invalid\"", expected):
        return False
    # If expected is a specific number > 1 digit and actual is a small different number,
    # it may indicate a manual counting error (oracle hallucination)
    actual_m = re.search(r"AssertionError: assert (\d+) == (\d+)", block)
    if actual_m:
        actual_val = int(actual_m.group(1))
        exp_val = int(actual_m.group(2))
        # Big discrepancy in a count: likely hallucinated count
        if abs(actual_val - exp_val) >= 3:
            return True
    return False


def _is_unsupported_edge_case(test_name: str, assertion: str) -> bool:
    """Heuristic: test involves non-ASCII, unicode, or other unspecified behaviour."""
    signals = re.search(
        r"(unicode|non.ascii|non.english|accent|encoding|utf)",
        test_name + " " + assertion, re.IGNORECASE
    )
    return bool(signals)


def _parse_collection_errors(stdout: str, stderr: str) -> list:
    combined = stdout + stderr
    records = []
    if "SyntaxError" in combined:
        m = re.search(r"SyntaxError: (.+)", combined)
        records.append({
            "test_name": "COLLECTION",
            "assertion": "",
            "actual": "",
            "expected": "",
            "category": SYNTAX_ERROR,
            "detail": m.group(1).strip() if m else "SyntaxError during collection",
        })
    elif "ImportError" in combined or "ModuleNotFoundError" in combined:
        records.append({
            "test_name": "COLLECTION",
            "assertion": "",
            "actual": "",
            "expected": "",
            "category": IMPORT_ERROR,
            "detail": "Import failure during collection",
        })
    return records
