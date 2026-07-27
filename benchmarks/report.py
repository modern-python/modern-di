"""Generate the comparative ratio tables published in docs/introduction/performance.md.

The tables are generated, never hand-assembled: `main()` runs the comparative suite N times in
its isolated environment and `build_table()` reduces the runs to markdown. Split so the reduction
is unit-testable without running a benchmark (see tests/test_bench_report.py).

Three tables, because no single rival set fits every scenario: dishka and wireup expose only
by-type lookup, that-depends and dependency-injector only by-reference. Each C1-C3 table compares
one modern-di variant against the rivals whose API matches it, so no published cell is ever n/a.
C4 does not split this way: modern-di resolves by reference throughout its C4 body, so that table
compares it against all four rivals regardless of which lookup API they natively expose.
"""

import argparse
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


def _median_of_medians(runs: list[dict[tuple[str, str], float]], key: tuple[str, str]) -> float | None:
    values = [run[key] for run in runs if key in run]
    return statistics.median(values) if values else None


def _format_time(seconds: float) -> str:
    return f"{seconds * 1e6:.2f} µs" if seconds >= _MICROSECOND else f"{seconds * 1e9:.0f} ns"


def _render(table: Table, parsed: list[dict[tuple[str, str], float]]) -> str:
    header = "| Scenario | modern-di | " + " | ".join(f"vs {r.replace('_', '-')}" for r in table.rivals) + " |"
    lines = [f"### {table.title}", "", header, "|" + "---|" * (len(table.rivals) + 2)]
    for row in table.rows:
        ours = _median_of_medians(parsed, (row.modern_di_key, "modern_di"))
        if ours is None:
            continue
        # The divisor cancels in the ratio (both sides are batched alike); it only scales our cell.
        cells = [row.label, _format_time(ours / row.divisor)]
        for rival in table.rivals:
            theirs = _median_of_medians(parsed, (row.rival_key, rival))
            if theirs is None:
                cells.append("n/a")
                continue
            ratio = ours / theirs
            cells.append(f"**{ratio:.2f}**" if ratio < 1.0 else f"{ratio:.2f}")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_table(runs: list[dict]) -> str:
    """Render every published markdown table from N raw pytest-benchmark payloads."""
    parsed = [parse_run(run) for run in runs]
    return "\n\n".join(_render(table, parsed) for table in TABLES)


def main() -> None:
    """Run the comparative suite N times and print the published table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5, help="how many full suite runs to reduce")
    args = parser.parse_args()

    runs: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        for index in range(args.runs):
            out = pathlib.Path(tmp) / f"run-{index}.json"
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
