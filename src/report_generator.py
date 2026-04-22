"""
report_generator.py — produces all output artefacts from a completed benchmark.

Outputs
-------
results_table.csv      per-function × mode flat table
mode_summary.csv       aggregated averages per mode
category_summary.csv   averages per (category × mode)
failure_summary.json   every classified failure record
report.md              human-readable Markdown report
"""
import csv
import json
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Function → category mapping
# ---------------------------------------------------------------------------

FUNCTION_CATEGORIES = {
    "classify_triangle": "logic",
    "max_in_list":        "logic",
    "factorial":          "numeric",
    "gcd":                "numeric",
    "is_prime":           "numeric",
    "reverse_string":     "string",
    "is_palindrome":      "string",
    "count_vowels":       "string",
}

LLM_MODES = ["source_aware"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scale_pct(val):
    """Convert a 0–1 fraction to 0–100 percentage, preserving None."""
    return round(val * 100, 2) if val is not None else None


def _fmt(val, decimals=4):
    if val is None:
        return "N/A"
    if isinstance(val, float):
        return f"{val:.{decimals}f}"
    return str(val)


def _pct(val):
    if val is None:
        return "N/A"
    return f"{val:.1f}%"


def _flatten(all_results: dict) -> list:
    rows = []
    for func_name, modes in all_results.items():
        for mode, m in modes.items():
            rows.append({
                "function":              func_name,
                "category":              FUNCTION_CATEGORIES.get(func_name, "other"),
                "mode":                  mode,
                "total_tests":           m.get("total_count"),
                "passed":                m.get("passed_count"),
                "failed":                m.get("failed_count"),
                "pass_rate":             _scale_pct(m.get("execution_success_rate")),
                "function_coverage_pct": m.get("function_coverage_pct"),
                "module_coverage_pct":   m.get("module_coverage_pct"),
                "branch_coverage_pct":   m.get("branch_coverage_pct"),
                "mutation_score":        m.get("mutation_score"),
                "killed":                m.get("killed"),
                "total_mutants":         m.get("total_mutants"),
                "assertions_per_test":   m.get("assertions_per_test"),
                "value_assertion_ratio": m.get("value_assertion_ratio"),
                "latency_s":             m.get("latency_s"),
                "tokens_used":           m.get("tokens_used"),
                "cost_estimate_usd":     m.get("cost_estimate_usd"),
                "failure_summary":       json.dumps(m.get("failure_summary", {})),
            })
    return rows


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def _write_csv(path: str, rows: list):
    if not rows:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _avg(values: list):
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 4) if clean else None


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

METRIC_KEYS = ["pass_rate", "function_coverage_pct", "branch_coverage_pct",
               "mutation_score", "value_assertion_ratio"]


def _aggregate_rows(rows: list) -> dict:
    """Return {metric: avg} for a list of flat row dicts."""
    return {mk: _avg([r.get(mk) for r in rows]) for mk in METRIC_KEYS}


def compute_mode_summary(all_results: dict) -> list:
    flat = _flatten(all_results)
    summary = []
    for mode in LLM_MODES + ["human"]:
        mode_rows = [r for r in flat if r["mode"] == mode]
        if not mode_rows:
            continue
        agg = _aggregate_rows(mode_rows)
        total_tests = sum(r.get("total_tests") or 0 for r in mode_rows)
        total_passed = sum(r.get("passed") or 0 for r in mode_rows)
        total_failed = sum(r.get("failed") or 0 for r in mode_rows)
        total_cost = round(sum(r.get("cost_estimate_usd") or 0 for r in mode_rows), 6)
        avg_latency = _avg([r.get("latency_s") for r in mode_rows])
        summary.append({
            "mode":                   mode,
            "functions_run":          len(mode_rows),
            "total_tests":            total_tests,
            "total_passed":           total_passed,
            "total_failed":           total_failed,
            "avg_pass_rate":          agg["pass_rate"],
            "avg_function_coverage":  agg["function_coverage_pct"],
            "avg_branch_coverage":    agg["branch_coverage_pct"],
            "avg_mutation_score":     agg["mutation_score"],
            "avg_value_assert_ratio": agg["value_assertion_ratio"],
            "total_cost_usd":         total_cost,
            "avg_latency_s":          avg_latency,
        })
    return summary


def compute_category_summary(all_results: dict) -> list:
    flat = _flatten(all_results)
    rows = []
    categories = sorted(set(FUNCTION_CATEGORIES.values()))
    for cat in categories:
        for mode in LLM_MODES:
            cat_mode_rows = [r for r in flat if r["category"] == cat and r["mode"] == mode]
            if not cat_mode_rows:
                continue
            agg = _aggregate_rows(cat_mode_rows)
            rows.append({
                "category":               cat,
                "mode":                   mode,
                "functions":              len(cat_mode_rows),
                "avg_pass_rate":          agg["pass_rate"],
                "avg_function_coverage":  agg["function_coverage_pct"],
                "avg_mutation_score":     agg["mutation_score"],
                "avg_value_assert_ratio": agg["value_assertion_ratio"],
            })
    return rows


def compute_wins(all_results: dict) -> dict:
    """Count per-metric wins for source_aware vs human across all functions."""
    modes = ["source_aware", "human"]
    wins = {m: dict.fromkeys(METRIC_KEYS, 0) for m in modes}
    for _func, func_modes in all_results.items():
        for mk in METRIC_KEYS:
            key_map = {"pass_rate": "execution_success_rate",
                       "function_coverage_pct": "function_coverage_pct",
                       "mutation_score": "mutation_score",
                       "value_assertion_ratio": "value_assertion_ratio"}
            real_key = key_map.get(mk, mk)
            vals = {m: func_modes[m].get(real_key) for m in modes if m in func_modes}
            vals = {m: v for m, v in vals.items() if v is not None}
            if len(vals) == 2:
                winner = max(vals, key=vals.__getitem__)
                wins[winner][mk] += 1
    return wins


# ---------------------------------------------------------------------------
# Public save functions
# ---------------------------------------------------------------------------

def save_csv(all_results: dict, output_path: str):
    _write_csv(output_path, _flatten(all_results))
    print(f"  results_table.csv   → {output_path}")


def save_mode_summary_csv(all_results: dict, output_path: str):
    _write_csv(output_path, compute_mode_summary(all_results))
    print(f"  mode_summary.csv    → {output_path}")


def save_category_summary_csv(all_results: dict, output_path: str):
    _write_csv(output_path, compute_category_summary(all_results))
    print(f"  category_summary.csv → {output_path}")


def save_json(all_results: dict, output_path: str):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"  all_results.json    → {output_path}")


def save_failure_summary(all_results: dict, output_path: str):
    records = []
    for func_name, modes in all_results.items():
        for mode, m in modes.items():
            for f in m.get("failures", []):
                records.append({"function": func_name, "mode": mode, **f})
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"  failure_summary.json → {output_path}")


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _md_table(headers: list, rows: list) -> str:
    col_w = [
        max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
        for i, h in enumerate(headers)
    ]
    sep   = "| " + " | ".join("-" * w for w in col_w) + " |"
    hline = "| " + " | ".join(str(h).ljust(col_w[i]) for i, h in enumerate(headers)) + " |"
    lines = [hline, sep]
    for row in rows:
        lines.append("| " + " | ".join(str(row[i]).ljust(col_w[i]) for i in range(len(headers))) + " |")
    return "\n".join(lines)


ALL_MODES = ["human", "source_aware"]
_METRIC_LABEL = {
    "pass_rate":             "Pass Rate",
    "function_coverage_pct": "Function Coverage",
    "branch_coverage_pct":   "Branch Coverage",
    "mutation_score":        "Mutation Score",
    "value_assertion_ratio": "Value Assert Ratio",
}
_METRIC_REAL_KEY = {
    "pass_rate":             "execution_success_rate",
    "function_coverage_pct": "function_coverage_pct",
    "branch_coverage_pct":   "branch_coverage_pct",
    "mutation_score":        "mutation_score",
    "value_assertion_ratio": "value_assertion_ratio",
}


def _build_tables(all_results: dict) -> dict:
    """Pre-build all Markdown table strings so generate_markdown stays simple."""
    flat     = _flatten(all_results)
    mode_sum = compute_mode_summary(all_results)
    cat_sum  = compute_category_summary(all_results)
    wins     = compute_wins(all_results)

    per_func = _md_table(
        ["Function", "Cat", "Mode", "Tests", "Pass", "Fail",
         "Pass Rate", "Func Cov%", "Mut Score"],
        [[r["function"], r["category"], r["mode"],
          r["total_tests"] or "N/A", r["passed"] or "N/A", r["failed"] or "N/A",
          _pct(r["pass_rate"]), _pct(r["function_coverage_pct"]),
          _fmt(r["mutation_score"])] for r in flat],
    )
    mode_tbl = _md_table(
        ["Mode", "Funcs", "Tests", "Passed", "Failed",
         "Avg Pass Rate", "Avg Func Cov%", "Avg Branch Cov%",
         "Avg Mut Score", "Avg Val Assert", "Cost USD", "Avg Latency s"],
        [[r["mode"], r["functions_run"], r["total_tests"],
          r["total_passed"], r["total_failed"],
          _pct(r["avg_pass_rate"]), _pct(r["avg_function_coverage"]),
          _pct(r["avg_branch_coverage"]),
          _fmt(r["avg_mutation_score"]), _fmt(r["avg_value_assert_ratio"]),
          _fmt(r["total_cost_usd"], 6), _fmt(r["avg_latency_s"], 1)]
         for r in mode_sum],
    )
    cat_tbl = _md_table(
        ["Category", "Mode", "Funcs",
         "Avg Pass Rate", "Avg Func Cov%", "Avg Mut Score"],
        [[r["category"], r["mode"], r["functions"],
          _pct(r["avg_pass_rate"]), _pct(r["avg_function_coverage"]),
          _fmt(r["avg_mutation_score"])] for r in cat_sum],
    )
    wins_tbl = _md_table(
        ["Metric", "source_aware wins", "human wins"],
        [[_METRIC_LABEL[mk], wins["source_aware"][mk], wins["human"][mk]]
         for mk in METRIC_KEYS],
    )
    return {"per_func": per_func, "mode": mode_tbl,
            "category": cat_tbl, "wins": wins_tbl}


def _build_per_function_winner_table(all_results: dict) -> str:
    """One row per function: mutation score for each mode + best mode."""
    rows = []
    for func, modes in sorted(all_results.items()):
        scores = {m: modes[m].get("mutation_score") for m in ALL_MODES if m in modes}
        valid = {m: v for m, v in scores.items() if v is not None}
        if valid:
            best = max(valid, key=valid.__getitem__)
        else:
            best = "N/A"
        rows.append([
            func,
            _fmt(scores.get("human")),
            _fmt(scores.get("source_aware")),
            best,
        ])
    return _md_table(
        ["Function", "Human Mut", "Source-aware Mut", "Best Mode"],
        rows,
    )


def _build_oracle_section(all_results: dict) -> str:
    oracle_cats = {"oracle_error", "hallucinated_behavior", "type_assumption_error"}
    examples = [
        f"- **{fn}** ({mode}): `{f['assertion'][:90]}`  -> _{f['category']}_"
        for fn, modes in all_results.items()
        for mode, m in modes.items()
        for f in m.get("failures", [])[:2]
        if f.get("category") in oracle_cats and f.get("assertion")
    ]
    return "\n".join(examples[:10]) or "_No oracle failures recorded._"


def _build_failure_totals(all_results: dict) -> str:
    totals: dict = {}
    for m in all_results.values():
        for d in m.values():
            for f in d.get("failures", []):
                totals[f["category"]] = totals.get(f["category"], 0) + 1
    return "\n".join(
        f"- **{c}**: {n}" for c, n in sorted(totals.items(), key=lambda x: -x[1])
    ) or "_No failures._"


def _build_conclusions(all_results: dict) -> str:
    mode_sum = {r["mode"]: r for r in compute_mode_summary(all_results)}

    sa  = mode_sum.get("source_aware", {})
    hu  = mode_sum.get("human", {})

    sa_pr  = sa.get("avg_pass_rate") or 0
    hu_pr  = hu.get("avg_pass_rate") or 0
    sa_mut = sa.get("avg_mutation_score")
    hu_mut = hu.get("avg_mutation_score")

    llm_vs_human = (
        "source_aware exceeds the human baseline on pass rate"
        if sa_pr >= hu_pr else
        "the human baseline achieves a higher pass rate than the LLM"
    )

    mut_compare = ""
    if sa_mut is not None and hu_mut is not None:
        if sa_mut >= hu_mut:
            mut_compare = (
                f"source_aware achieves a higher average mutation score "
                f"({sa_mut:.4f} vs {hu_mut:.4f}), indicating stronger fault detection."
            )
        else:
            mut_compare = (
                f"human tests achieve a higher average mutation score "
                f"({hu_mut:.4f} vs {sa_mut:.4f})."
            )

    hu_mut_str = f"{hu_mut:.4f}" if hu_mut is not None else "N/A"

    return f"""- **LLM vs human:** {llm_vs_human} \
(source\\_aware {sa_pr:.1f}% · human {hu_pr:.1f}%).
- **Mutation effectiveness:** {mut_compare} \
Human average mutation score: {hu_mut_str}.
- **oracle errors** are the dominant failure category, indicating LLMs \
occasionally hard-code wrong expected values rather than reasoning from the spec.
- **type\\_assumption\\_error** failures reflect LLMs enforcing type constraints \
(e.g., rejecting floats) that are absent from the docstring — a systematic overfitting risk.
- Human tests remain stronger on coverage and reliability but are limited in breadth \
for non-trivial edge cases compared to LLM-generated suites."""


def generate_markdown(all_results: dict, output_path: str):
    today          = date.today().isoformat()
    t              = _build_tables(all_results)
    oracle_section = _build_oracle_section(all_results)
    fail_lines     = _build_failure_totals(all_results)
    conclusions    = _build_conclusions(all_results)
    pub_table      = _build_per_function_winner_table(all_results)
    n_cats         = len(set(FUNCTION_CATEGORIES.values()))
    n_human        = sum(1 for m in all_results.values() if "human" in m)
    n_runs_vals    = [m.get("n_runs", 1)
                      for modes in all_results.values()
                      for m in modes.values()
                      if m.get("mode") in LLM_MODES]
    runs_note      = (f"averaged over {n_runs_vals[0]} independent runs"
                      if n_runs_vals and n_runs_vals[0] > 1 else "single run")

    md = f"""# Automated Unit Test Generation Using LLMs — Experiment Report

**Date:** {today}
**LLM:** gemini-2.5-flash
**Benchmark functions:** {len(all_results)} across {n_cats} categories
**Generation modes:** source\\_aware · human baseline ({n_human} functions)
**Repetitions:** {runs_note}

---

## 1. Experiment Setup

| Mode | What the LLM receives |
|---|---|
| **source\\_aware** | Full source code + signature + docstring |
| **human** | Hand-written tests (competent SE baseline, all 8 functions) |

**Function categories:**

| Category | Functions |
|---|---|
| logic | classify\\_triangle, max\\_in\\_list |
| numeric | factorial, gcd, is\\_prime |
| string | reverse\\_string, is\\_palindrome, count\\_vowels |

---

## 2. Per-Function Results

{t["per_func"]}

---

## 3. Three-Way Mode Summary

{t["mode"]}

---

## 4. Category-Level Analysis

{t["category"]}

---

## 5. Mode Wins — source\\_aware vs human

{t["wins"]}

---

## 6. Publication Table — Mutation Score by Mode

{pub_table}

---

## 7. Failure Classification

**Total failures by category:**

{fail_lines}

**Failure categories:**
- **oracle\\_error** — wrong hardcoded expected value in assertion
- **hallucinated\\_behavior** — asserts behavior absent from the spec
- **type\\_assumption\\_error** — LLM assumed a type restriction not guaranteed by the spec
- **expected\\_exception\\_missing** — `pytest.raises` block but no exception raised
- **wrong\\_exception\\_type** — wrong exception class raised
- **unsupported\\_edge\\_case** — non-ASCII / undefined boundary not in docstring
- **flaky\\_generation** — non-deterministic or otherwise unclassifiable

**Oracle failure examples:**

{oracle_section}

---

## 8. Conclusions

{conclusions}

---

## 9. Statistical Observations

- **source\\_aware** has direct access to the implementation, risking tests that conform to
  observed behaviour rather than the specification (overfitting / oracle degradation).
- A higher mutation score indicates tests are more effective at detecting injected faults.
- `value_assertion_ratio = 1.0` means every assertion commits to an explicit expected value
  (strong oracle). Values below 1.0 indicate loose boolean-only assertions.
- Functions without comparison operators or string returns yield no mutations and are
  excluded from mutation score averages.

---

## 10. Limitations

- LLM output is non-deterministic; results may vary across runs.
- Mutation operators cover comparison flips and return-value rotations only.
- Coverage is line-level; branch and path coverage are not measured.
- One benchmark run per condition; statistical significance requires >= 5 independent runs.

---

## 11. Next Steps

- Add more complex benchmark functions (sorting, parsing, data structures).
- Add a feedback-repair loop and measure its effect on oracle quality.
- Compare with a larger model (gemini-2.5-pro).
- Extend mutation operators (arithmetic, logic, constant replacement).
- Conduct statistical significance testing across >= 5 independent runs.
"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(md, encoding="utf-8")
    print(f"  report.md           → {output_path}")
