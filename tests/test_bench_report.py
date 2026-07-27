"""The published comparative tables are generated, not hand-assembled — this guards the generator."""

from benchmarks.report import build_table, parse_run


def _run(**medians: float) -> dict:
    """Build a minimal pytest-benchmark JSON payload from name -> median (seconds)."""
    return {"benchmarks": [{"name": name, "stats": {"median": median}} for name, median in medians.items()]}


def _section(table: str, title: str) -> list[list[str]]:
    """Return the data rows of the named `### ` section as lists of stripped cells."""
    block = next(part for part in table.split("### ") if part.startswith(title))
    return [
        [cell.strip() for cell in line.strip("|").split("|")]
        for line in block.splitlines()
        if line.startswith("| ") and "---" not in line and not line.startswith("| Scenario")
    ]


def _footnote(table: str, title: str) -> str | None:
    """Return the named section's across-run IQR footnote line, or None if it has none."""
    block = next(part for part in table.split("### ") if part.startswith(title))
    lines = [line for line in block.splitlines() if line.startswith("_Across-run IQR")]
    return lines[0] if lines else None


def test_parse_run_splits_scenario_from_framework() -> None:
    parsed = parse_run(_run(test_c1_transient_by_ref_modern_di=1e-6, test_c1_transient_dishka=2e-6))
    assert parsed[("c1_transient_by_ref", "modern_di")] == 1e-6  # noqa: PLR2004
    assert parsed[("c1_transient", "dishka")] == 2e-6  # noqa: PLR2004


def test_parse_run_handles_underscored_framework_names() -> None:
    parsed = parse_run(_run(test_c3_deep_chain_that_depends=3e-6, test_c3_deep_chain_dependency_injector=4e-6))
    assert parsed[("c3_deep_chain", "that_depends")] == 3e-6  # noqa: PLR2004
    assert parsed[("c3_deep_chain", "dependency_injector")] == 4e-6  # noqa: PLR2004


def test_build_table_compares_each_variant_against_its_matching_rivals() -> None:
    run = _run(
        test_c1_transient_by_ref_modern_di=1e-6,
        test_c1_transient_by_type_modern_di=2e-6,
        test_c1_transient_dependency_injector=5e-7,
        test_c1_transient_that_depends=2e-6,
        test_c1_transient_dishka=4e-6,
        test_c1_transient_wireup=1e-6,
    )
    table = build_table([run])
    # by-reference: 1.0/0.5 = 2.00 vs dependency-injector, 1.0/2.0 = 0.50 vs that-depends
    assert _section(table, "By-reference resolution") == [["C1 transient", "1.00 µs", "2.00", "**0.50**"]]
    # by-type: 2.0/4.0 = 0.50 vs dishka, 2.0/1.0 = 2.00 vs wireup
    assert _section(table, "By-type resolution") == [["C1 transient", "2.00 µs", "**0.50**", "2.00"]]


def test_build_table_publishes_c4_per_request_not_per_batch() -> None:
    # C4 is timed as a batch of 100 cycles; the published cell is per request. Ratios are unaffected
    # by the division (both sides share the divisor) — only the modern-di column changes.
    run = _run(
        test_c4_request_lifecycle_modern_di=200e-6,
        test_c4_request_lifecycle_dependency_injector=400e-6,
        test_c4_request_lifecycle_that_depends=400e-6,
        test_c4_request_lifecycle_dishka=400e-6,
        test_c4_request_lifecycle_wireup=400e-6,
    )
    assert _section(build_table([run]), "Request lifecycle") == [
        ["C4 request lifecycle", "2.00 µs", "**0.50**", "**0.50**", "**0.50**", "**0.50**"]
    ]


def test_build_table_takes_the_median_across_runs() -> None:
    runs = [
        _run(
            test_c1_transient_by_ref_modern_di=median,
            test_c1_transient_dependency_injector=2e-6,
            test_c1_transient_that_depends=2e-6,
        )
        for median in (1e-6, 3e-6, 2e-6)
    ]
    # median of (1, 3, 2) is 2 µs, so both ratios are exactly 1.00. modern-di now spans 3 runs
    # with real spread (1, 3, 2 µs), so Fix 6 forces an IQR% onto the modern-di cell: quantiles
    # of [1, 2, 3] (inclusive) are Q1=1.5, Q3=2.5 -> IQR 1.0 / median 2.0 * 100 = 50.0%.
    assert _section(build_table(runs), "By-reference resolution") == [
        ["C1 transient", "2.00 µs ±50.0%", "1.00", "1.00"]
    ]


def test_build_table_shows_across_run_iqr_percent_on_modern_di_cell() -> None:
    # modern-di values (ns): 300, 305, 310, 320, 340 -> median 310, quantiles (inclusive) give
    # Q1=305, Q3=320 -> IQR 15 / median 310 * 100 = 4.8387...% -> "4.8" to one decimal.
    runs = [
        _run(test_c1_transient_by_ref_modern_di=modern_di, test_c1_transient_dependency_injector=6.2e-7)
        for modern_di in (3.00e-7, 3.05e-7, 3.10e-7, 3.20e-7, 3.40e-7)
    ]
    row = _section(build_table(runs), "By-reference resolution")[0]
    assert row[:2] == ["C1 transient", "310 ns ±4.8%"]
    # the ratio column stays bare -- no spread is fabricated for a ratio of two medians
    assert "±" not in row[2]


def test_build_table_footnote_reports_worst_spread_in_that_table() -> None:
    # Per-cell IQR% (hand-computed the same way as above):
    #   c1 modern-di:              310 ns,  ±4.8387...%  (max modern-di contender)
    #   c1 vs dependency-injector: 620 ns,  ±0.0%
    #   c1 vs that-depends:        620 ns,  ±3.2258...%
    #   c2 modern-di:              1.10 us, ±13.6363...% (max modern-di -- this one wins)
    #   c2 vs dependency-injector: 2.10 us, ±7.1428...%  (max rival -- this one wins)
    #   c2 vs that-depends:        2.00 us, ±0.0%
    runs = [
        _run(
            test_c1_transient_by_ref_modern_di=c1_modern_di,
            test_c1_transient_dependency_injector=6.2e-7,
            test_c1_transient_that_depends=c1_that_depends,
            test_c2_singleton_by_ref_modern_di=c2_modern_di,
            test_c2_singleton_dependency_injector=c2_dependency_injector,
            test_c2_singleton_that_depends=2e-6,
        )
        for c1_modern_di, c1_that_depends, c2_modern_di, c2_dependency_injector in zip(
            (3.00e-7, 3.05e-7, 3.10e-7, 3.20e-7, 3.40e-7),
            (6.0e-7, 6.1e-7, 6.2e-7, 6.3e-7, 6.4e-7),
            (1.0e-6, 1.05e-6, 1.10e-6, 1.20e-6, 1.6e-6),
            (2.0e-6, 2.05e-6, 2.10e-6, 2.20e-6, 2.50e-6),
            strict=True,
        )
    ]
    footnote = _footnote(build_table(runs), "By-reference resolution")
    assert footnote == "_Across-run IQR (5 runs): modern-di ≤13.6%, rivals ≤7.1%._"


def test_build_table_single_run_has_no_iqr_annotation_or_footnote() -> None:
    run = _run(test_c1_transient_by_ref_modern_di=3.1e-7, test_c1_transient_dependency_injector=6.2e-7)
    table = build_table([run])
    # IQR is undefined for a single run: no ± on the cell, and no footnote -- never crash, never fake 0.0%.
    assert _section(table, "By-reference resolution") == [["C1 transient", "310 ns", "**0.50**", "n/a"]]
    assert _footnote(table, "By-reference resolution") is None
