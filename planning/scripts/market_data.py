"""Size the Python DI field by PyPI downloads: the rival set, and our own integration split.

Run it before spending maintainer time on adoption or outreach — it answers which framework, if
any, that time should target. `collect()` pulls each package's daily series from pypistats and
`build_table()` reduces it to markdown. Split so the reduction is unit-testable without network
(see tests/test_market_data.py).

Mirrors are excluded: mirror traffic is not installs, and this table exists to carry a number
worth betting maintainer time on.
"""

import argparse
import collections.abc
import dataclasses
import datetime
import json
import time
import typing
import urllib.error
import urllib.request


WINDOW = 30
_QUARTER = 90
_HALF_YEAR = 180

RIVALS = (
    "modern-di",
    "dishka",
    "dependency-injector",
    "wireup",
    "svcs",
    "that-depends",
    "injector",
    "punq",
)

# Hardcoded, not configurable: the sets are the design. A --packages flag would let a later run
# quietly redefine "the field" and make two snapshots incomparable.
OURS = (
    "modern-di",
    "modern-di-fastapi",
    "modern-di-litestar",
    "modern-di-faststream",
    "modern-di-typer",
    "modern-di-aiohttp",
    "modern-di-starlette",
    "modern-di-flask",
    "modern-di-grpc",
    "modern-di-celery",
    "modern-di-arq",
    "modern-di-taskiq",
    "modern-di-aiogram",
    "modern-di-pytest",
)

API = "https://pypistats.org/api/packages/{package}/overall?mirrors=false"

_ATTEMPTS = 4
_DELAY = 2.0
_PAUSE = 1.0

Opener = collections.abc.Callable[[str], typing.ContextManager]
Sleeper = collections.abc.Callable[[float], None]
Fetcher = collections.abc.Callable[[str], list[dict]]


class MarketDataError(RuntimeError):
    """A package's series could not be retrieved; the table must not be published with a hole."""


@dataclasses.dataclass(frozen=True, slots=True)
class Stats:
    """One package reduced: window totals with mirrors excluded, plus the 30-day trend."""

    package: str
    d30: int
    d90: int
    d180: int
    trend_pct: float | None


def _daily(rows: list[dict]) -> dict[datetime.date, int]:
    """Index a pypistats `data` list by date."""
    return {datetime.date.fromisoformat(row["date"]): row["downloads"] for row in rows}


def _total(daily: dict[datetime.date, int], reference: datetime.date, start: int, days: int) -> int:
    """Sum `days` days, ending `start` days back from `reference`; a missing day counts as zero."""
    return sum(daily.get(reference - datetime.timedelta(days=offset), 0) for offset in range(start, start + days))


def newest_date(rows: list[dict]) -> datetime.date:
    """Return the latest day present in one series."""
    return max(datetime.date.fromisoformat(row["date"]) for row in rows)


def summarize(package: str, rows: list[dict], reference: datetime.date) -> Stats:
    """Reduce one package's daily series to its window totals and trend.

    `reference` is the newest day across the whole run, not this package's own newest, so a
    package that went quiet for a few days is not silently given a shifted window.
    """
    daily = _daily(rows)
    recent = _total(daily, reference, 0, WINDOW)
    prior = _total(daily, reference, WINDOW, WINDOW)
    return Stats(
        package=package,
        d30=recent,
        d90=_total(daily, reference, 0, _QUARTER),
        d180=_total(daily, reference, 0, _HALF_YEAR),
        trend_pct=None if prior == 0 else (recent - prior) / prior * 100,
    )


def _format_trend(pct: float | None) -> str:
    return "n/a" if pct is None else f"{pct:+.1f}%"


def render_table(title: str, stats: list[Stats]) -> str:
    """Render one package set, ordered by 30-day downloads descending."""
    lines = [
        f"### {title}",
        "",
        "| Package | 30d | 90d | 180d | Trend (30d vs prior 30d) |",
        "|---|---:|---:|---:|---:|",
    ]
    lines += [
        f"| `{row.package}` | {row.d30:,} | {row.d90:,} | {row.d180:,} | {_format_trend(row.trend_pct)} |"
        for row in sorted(stats, key=lambda row: row.d30, reverse=True)
    ]
    return "\n".join(lines)


def build_table(rivals: list[Stats], ours: list[Stats], reference: datetime.date) -> str:
    """Render the published table: the rival field, then our own integration split."""
    stamp = f"_PyPI downloads, mirrors excluded, windows ending {reference.isoformat()}._"
    return "\n\n".join([stamp, render_table("The field", rivals), render_table("modern-di integrations", ours)])


def fetch_series(
    package: str,
    *,
    opener: Opener = urllib.request.urlopen,
    attempts: int = _ATTEMPTS,
    delay: float = _DELAY,
    sleep: Sleeper = time.sleep,
) -> list[dict]:
    """Fetch one package's daily series, retrying with exponential backoff.

    Throttling is indistinguishable from a missing package at the call site, so every failure is
    retried and an exhausted budget raises instead of returning an empty series.
    """
    for attempt in range(attempts):
        try:
            with opener(API.format(package=package)) as response:
                rows = json.loads(response.read())["data"]
        except (OSError, ValueError, KeyError, TypeError):
            rows = []
        if rows:
            return rows
        if attempt < attempts - 1:
            sleep(delay * 2**attempt)
    msg = f"{package}: no data after {attempts} attempts (throttled, or the package does not exist)"
    raise MarketDataError(msg)


def collect(
    packages: tuple[str, ...],
    *,
    fetch: Fetcher = fetch_series,
    pause: float = _PAUSE,
    sleep: Sleeper = time.sleep,
) -> dict[str, list[dict]]:
    """Fetch every package's series sequentially, pausing between calls to stay under the rate limit."""
    series: dict[str, list[dict]] = {}
    for index, package in enumerate(packages):
        if index:
            sleep(pause)
        series[package] = fetch(package)
    return series


def main() -> None:
    """Pull both package sets and print the published markdown table."""
    parser = argparse.ArgumentParser(description="Pull the PyPI download table for the adoption gate.")
    parser.add_argument("--pause", type=float, default=_PAUSE, help="seconds between requests (rate-limit guard)")
    args = parser.parse_args()

    # dict.fromkeys dedupes modern-di, which belongs to both sets, so it is fetched once.
    series = collect(tuple(dict.fromkeys(RIVALS + OURS)), pause=args.pause)
    reference = max(newest_date(rows) for rows in series.values())
    rivals = [summarize(package, series[package], reference) for package in RIVALS]
    ours = [summarize(package, series[package], reference) for package in OURS]
    print(build_table(rivals, ours, reference))  # noqa: T201


if __name__ == "__main__":
    main()
