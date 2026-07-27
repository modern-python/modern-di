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
    # median of (1, 3, 2) is 2 µs, so both ratios are exactly 1.00
    assert _section(build_table(runs), "By-reference resolution") == [["C1 transient", "2.00 µs", "1.00", "1.00"]]
