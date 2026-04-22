import json
import re
import subprocess
import sys
from pathlib import Path


def run_tests(test_file: str, project_root: str, coverage_output: str = None,
              cov_target: str = "dataset") -> dict:
    """Run pytest on test_file, optionally collecting coverage into coverage_output (JSON path)."""
    cmd = [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short", "--no-header"]

    if coverage_output:
        Path(coverage_output).parent.mkdir(parents=True, exist_ok=True)
        cmd += [
            f"--cov={cov_target}",
            "--cov-branch",
            f"--cov-report=json:{coverage_output}",
            "--cov-report=term-missing",
        ]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_root)

    passed, failed, total = _parse_counts(result.stdout)
    coverage_pct = _parse_coverage(coverage_output) if coverage_output else None

    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "passed": result.returncode == 0,
        "passed_count": passed,
        "failed_count": failed,
        "total_count": total,
        "execution_success_rate": passed / total if total > 0 else 0.0,
        "coverage_pct": coverage_pct,
    }


def _parse_counts(output: str):
    passed = failed = 0
    m = re.search(r"(\d+) passed", output)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+) failed", output)
    if m:
        failed = int(m.group(1))
    return passed, failed, passed + failed


def _parse_coverage(coverage_json: str):
    try:
        data = json.loads(Path(coverage_json).read_text())
        return round(data["totals"]["percent_covered"], 2)
    except Exception:
        return None
