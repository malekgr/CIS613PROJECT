def print_comparison(results: dict) -> None:
    """Print a side-by-side comparison table for all modes in results."""
    modes = list(results.keys())
    col = 24

    rows = [
        ("Tests Generated",        "total_count"),
        ("Tests Passed",           "passed_count"),
        ("Tests Failed",           "failed_count"),
        ("Execution Success Rate", "execution_success_rate"),
        ("Code Coverage (%)",      "coverage_pct"),
        ("Mutation Score",         "mutation_score"),
        ("Mutants Killed",         "killed"),
        ("Total Mutants",          "total"),
        ("Total Assertions",       "total_assertions"),
        ("Assertions / Test",      "assertions_per_test"),
        ("Value Assertion Ratio",  "value_assertion_ratio"),
    ]

    width = 32 + col * len(modes)
    print("\n" + "=" * width)
    print("  COMPARISON REPORT")
    print("=" * width)

    header = f"{'Metric':<32}" + "".join(f"{m:>{col}}" for m in modes)
    print(header)
    print("-" * width)

    for label, key in rows:
        row = f"{label:<32}"
        for mode in modes:
            val = results[mode].get(key)
            if val is None:
                cell = "N/A"
            elif isinstance(val, float):
                if key in ("coverage_pct",):
                    cell = f"{val:.1f}%"
                elif key in ("execution_success_rate", "mutation_score", "value_assertion_ratio"):
                    cell = f"{val:.4f}"
                else:
                    cell = f"{val:.2f}"
            else:
                cell = str(val)
            row += f"{cell:>{col}}"
        print(row)

    print("=" * width)
    _print_summary(results, modes)


def _print_summary(results: dict, modes: list) -> None:
    if len(modes) < 2:
        return

    print("\n  INSIGHTS")
    print("-" * 50)

    def cmp(key, higher_is_better=True):
        vals = {m: results[m].get(key) for m in modes if results[m].get(key) is not None}
        if len(vals) < 2:
            return
        best = max(vals, key=vals.__getitem__) if higher_is_better else min(vals, key=vals.__getitem__)
        worst = min(vals, key=vals.__getitem__) if higher_is_better else max(vals, key=vals.__getitem__)
        diff = abs(vals[best] - vals[worst])
        if diff > 0:
            print(f"  {key}: {best} leads by {diff:.4f}")

    cmp("execution_success_rate")
    cmp("coverage_pct")
    cmp("mutation_score")
    cmp("value_assertion_ratio")
    print()
