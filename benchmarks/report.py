"""Generate the comparative ratio tables published in docs/introduction/performance.md.

The tables are generated, never hand-assembled: `main()` runs the comparative suite N times in
its isolated environment and `build_table()` reduces the runs to markdown. Split so the reduction
is unit-testable without running a benchmark (see tests/test_bench_report.py).

Four tables, because no single rival set fits every scenario: dishka and wireup expose only
by-type lookup, that-depends and dependency-injector only by-reference. Each C1-C3 table compares
one modern-di variant against the rivals whose API matches it, so no published cell is ever n/a.
C4 and C6 do not split this way: modern-di resolves by reference throughout both bodies, so those
tables compare it against all four rivals regardless of which lookup API they natively expose.
C6 is one table for C4's reason alone: modern-di has no by-type C6 variant, so a split would leave
that half mixed-basis. The rivals do line up with the C1-C3 grouping here — that-depends resolves
its C6 handler by reference, as it does on C1-C3.

Ratios are **paired per run**: one run measures both sides under the same machine state, so the
published statistic is the median of the per-run ratios, not a ratio of two independently-reduced
medians. Pairing also gives each ratio a well-defined across-run IQR, published as `±X.X%` on the
cell -- a ratio of two medians has none, which is why these columns used to be bare.

Two different across-run IQRs therefore appear per table and are named apart: the `±` on a cell is
the spread of that cell's own reduced values (paired ratios for a ratio cell, medians for the
modern-di column), while the footnote bounds each *side's own median*. They do not agree, and
must not be presented as if they did.
"""

import argparse
import contextlib
import dataclasses
import json
import pathlib
import statistics
import subprocess
import tempfile


BATCH = 100
_MICROSECOND = 1e-6  # named so ruff's PLR2004 (magic value in comparison) stays clean

BY_REFERENCE = ("dependency_injector", "that_depends")
BY_TYPE = ("dishka", "wireup")
FRAMEWORKS = ("modern_di", *BY_REFERENCE, *BY_TYPE)

# Longest first: "dependency_injector" must win over any shorter suffix that could also match.
_SUFFIXES = tuple(sorted(FRAMEWORKS, key=len, reverse=True))


@dataclasses.dataclass(frozen=True, slots=True)
class Row:
    """One published row: a modern-di scenario key and the rival key it is measured against."""

    label: str
    modern_di_key: str
    rival_key: str
    divisor: int = 1


@dataclasses.dataclass(frozen=True, slots=True)
class Table:
    """One published table: a rival set and the rows compared against it."""

    title: str
    rivals: tuple[str, ...]
    rows: tuple[Row, ...]


TABLES = (
    Table(
        "By-reference resolution",
        BY_REFERENCE,
        (
            Row("C1 transient", "c1_transient_by_ref", "c1_transient"),
            Row("C2 warm singleton", "c2_singleton_by_ref", "c2_singleton"),
            Row("C3 deep chain (6)", "c3_deep_chain_by_ref", "c3_deep_chain"),
        ),
    ),
    Table(
        "By-type resolution",
        BY_TYPE,
        (
            Row("C1 transient", "c1_transient_by_type", "c1_transient"),
            Row("C2 warm singleton", "c2_singleton_by_type", "c2_singleton"),
            Row("C3 deep chain (6)", "c3_deep_chain_by_type", "c3_deep_chain"),
        ),
    ),
    Table(
        "Request lifecycle (batched, published per request)",
        BY_REFERENCE + BY_TYPE,
        (Row("C4 request lifecycle", "c4_request_lifecycle", "c4_request_lifecycle", divisor=BATCH),),
    ),
    Table(
        "Per-request context",
        BY_REFERENCE + BY_TYPE,
        (Row("C6 context", "c6_context", "c6_context"),),
    ),
)


def _split_name(name: str) -> tuple[str, str] | None:
    """Split `test_<scenario>_<framework>` into (scenario, framework); None if no framework matches."""
    stem = name.removeprefix("test_")
    for framework in _SUFFIXES:
        if stem.endswith(f"_{framework}"):
            return stem.removesuffix(f"_{framework}"), framework
    return None


def parse_run(payload: dict) -> dict[tuple[str, str], float]:
    """Reduce one pytest-benchmark JSON payload to {(scenario, framework): median seconds}."""
    parsed: dict[tuple[str, str], float] = {}
    for entry in payload["benchmarks"]:
        key = _split_name(entry["name"])
        if key is not None:
            parsed[key] = entry["stats"]["median"]
    return parsed


@dataclasses.dataclass(frozen=True, slots=True)
class _Cell:
    """One published cell reduced across runs: the median, plus its spread.

    `iqr_pct` is the interquartile range of the per-run values, as a percentage of `median` --
    None when fewer than 2 runs contribute, since IQR is undefined for a single value.
    """

    median: float
    iqr_pct: float | None


def _reduce(values: list[float]) -> _Cell | None:
    """Reduce per-run values to a median and its across-run IQR%; None if no run contributed."""
    if not values:
        return None
    median = statistics.median(values)
    if len(values) < 2:  # noqa: PLR2004
        return _Cell(median, None)
    q1, _q2, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return _Cell(median, (q3 - q1) / median * 100)


def _reduce_cell(runs: list[dict[tuple[str, str], float]], key: tuple[str, str]) -> _Cell | None:
    """Reduce one (scenario, framework) cell across runs; None if no run reports this key."""
    return _reduce([run[key] for run in runs if key in run])


def _reduce_ratio(
    runs: list[dict[tuple[str, str], float]], ours: tuple[str, str], theirs: tuple[str, str]
) -> _Cell | None:
    """Reduce the ours/theirs ratio, paired within each run; None if no run reports both keys.

    Pairing is what makes the ratio's IQR meaningful: a run measures both sides under the same
    machine state, so dividing within the run cancels that state instead of carrying it into
    two separately-reduced medians.
    """
    return _reduce([run[ours] / run[theirs] for run in runs if ours in run and theirs in run])


def _format_time(seconds: float) -> str:
    return f"{seconds * 1e6:.2f} µs" if seconds >= _MICROSECOND else f"{seconds * 1e9:.0f} ns"


def _render(table: Table, parsed: list[dict[tuple[str, str], float]]) -> str:
    header = "| Scenario | modern-di | " + " | ".join(f"vs {r.replace('_', '-')}" for r in table.rivals) + " |"
    lines = [f"### {table.title}", "", header, "|" + "---|" * (len(table.rivals) + 2)]
    modern_di_pcts: list[float] = []
    rival_pcts: list[float] = []
    for row in table.rows:
        ours = _reduce_cell(parsed, (row.modern_di_key, "modern_di"))
        if ours is None:
            continue
        # The divisor cancels in the ratio (both sides are batched alike); it only scales our cell.
        # It also cancels in iqr_pct, a ratio of the (equally-scaled) IQR to the (equally-scaled)
        # median, so the annotation needs no separate adjustment.
        cell = _format_time(ours.median / row.divisor)
        if ours.iqr_pct is not None:
            cell += f" ±{ours.iqr_pct:.1f}%"
            modern_di_pcts.append(ours.iqr_pct)
        cells = [row.label, cell]
        for rival in table.rivals:
            # The divisor cancels inside the paired ratio too -- both sides are batched alike.
            ratio = _reduce_ratio(parsed, (row.modern_di_key, "modern_di"), (row.rival_key, rival))
            if ratio is None:
                cells.append("n/a")
                continue
            text = f"**{ratio.median:.2f}**" if ratio.median < 1.0 else f"{ratio.median:.2f}"
            if ratio.iqr_pct is not None:
                text += f" ±{ratio.iqr_pct:.1f}%"
            cells.append(text)
            theirs = _reduce_cell(parsed, (row.rival_key, rival))
            if theirs is not None and theirs.iqr_pct is not None:
                rival_pcts.append(theirs.iqr_pct)
        lines.append("| " + " | ".join(cells) + " |")
    if modern_di_pcts and rival_pcts:
        lines.append("")
        # Named explicitly: this bounds each side's OWN median, which is not the quantity the
        # ± on a ratio cell reports. Both are across-run IQRs; leaving them unlabelled let the
        # footnote read as contradicting cells above it whose paired spread is larger.
        lines.append(
            f"_Across-run IQR of each side's own median ({len(parsed)} runs): "
            f"modern-di ≤{max(modern_di_pcts):.1f}%, rivals ≤{max(rival_pcts):.1f}%. "
            f"The ± on each ratio cell is a different quantity: the spread of the paired per-run ratios._"
        )
    return "\n".join(lines)


def build_table(runs: list[dict]) -> str:
    """Render every published markdown table from N raw pytest-benchmark payloads."""
    parsed = [parse_run(run) for run in runs]
    return "\n\n".join(_render(table, parsed) for table in TABLES)


def main() -> None:
    """Run the comparative suite N times and print the published table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5, help="how many full suite runs to reduce")
    parser.add_argument(
        "--json-dir",
        type=pathlib.Path,
        default=None,
        help="keep the raw per-run pytest-benchmark JSON here (default: a temp dir, discarded)",
    )
    args = parser.parse_args()

    runs: list[dict] = []
    with contextlib.ExitStack() as stack:
        tmp = args.json_dir or pathlib.Path(stack.enter_context(tempfile.TemporaryDirectory()))
        tmp.mkdir(parents=True, exist_ok=True)
        for index in range(args.runs):
            out = tmp / f"run-{index}.json"
            subprocess.run(  # noqa: S603
                [  # noqa: S607
                    "uv",
                    "run",
                    "--project",
                    "benchmarks/comparative",
                    "pytest",
                    "benchmarks/comparative/",
                    "--benchmark-only",
                    f"--benchmark-json={out}",
                    "-q",
                ],
                check=True,
            )
            runs.append(json.loads(out.read_text()))
    print(build_table(runs))  # noqa: T201


if __name__ == "__main__":
    main()
