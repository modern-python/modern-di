"""The adoption download table is generated, not hand-assembled — this guards the generator."""

import datetime
import json
import typing
import urllib.error

import pytest

from planning.scripts import market_data


if typing.TYPE_CHECKING:
    import typing_extensions


REFERENCE = datetime.date(2026, 7, 29)


def _flat(end: datetime.date, days: int, per_day: int) -> list[dict]:
    """Build a pypistats `data` list: `days` consecutive days ending `end`, `per_day` downloads each."""
    return [
        {
            "category": "without_mirrors",
            "date": (end - datetime.timedelta(days=offset)).isoformat(),
            "downloads": per_day,
        }
        for offset in range(days)
    ]


def test_summarize_sums_each_window() -> None:
    # 200 days, wider than any window, so a window-boundary regression (e.g. _HALF_YEAR growing
    # past 180) is caught rather than silently contributing zero from outside a 180-day fixture.
    stats = market_data.summarize("p", _flat(REFERENCE, 200, 1), REFERENCE)
    assert (stats.d30, stats.d90, stats.d180) == (30, 90, 180)


def test_summarize_trend_compares_the_last_30_days_to_the_previous_30() -> None:
    rows = _flat(REFERENCE, 30, 2) + _flat(REFERENCE - datetime.timedelta(days=30), 30, 1)
    stats = market_data.summarize("p", rows, REFERENCE)
    assert stats.d30 == 60  # noqa: PLR2004
    assert stats.trend_pct == 100.0  # noqa: PLR2004


def test_summarize_counts_missing_days_as_zero() -> None:
    stats = market_data.summarize("p", _flat(REFERENCE, 10, 5), REFERENCE)
    assert stats.d30 == 50  # noqa: PLR2004
    assert stats.d180 == 50  # noqa: PLR2004


def test_summarize_uses_the_run_reference_not_the_package_newest_day() -> None:
    # Newest row is 25 days stale, so only 5 of its days fall inside the run's 30-day window.
    stale = _flat(REFERENCE - datetime.timedelta(days=25), 30, 1)
    assert market_data.summarize("p", stale, REFERENCE).d30 == 5  # noqa: PLR2004


def test_summarize_reports_no_trend_when_the_previous_window_is_empty() -> None:
    assert market_data.summarize("p", _flat(REFERENCE, 30, 3), REFERENCE).trend_pct is None


def test_newest_date_reads_the_latest_day_in_the_series() -> None:
    assert market_data.newest_date(_flat(REFERENCE, 5, 1)) == REFERENCE


def test_summarize_rejects_a_row_not_in_the_without_mirrors_category() -> None:
    rows = _flat(REFERENCE, 3, 1)
    rows[0]["category"] = "with_mirrors"
    with pytest.raises(market_data.MarketDataError, match="mirrors=false was not honored"):
        market_data.summarize("p", rows, REFERENCE)


def test_summarize_rejects_a_duplicate_date() -> None:
    rows = _flat(REFERENCE, 3, 1) + _flat(REFERENCE, 1, 1)
    with pytest.raises(market_data.MarketDataError, match="duplicate date"):
        market_data.summarize("p", rows, REFERENCE)


def test_render_table_orders_by_thirty_day_downloads() -> None:
    rows = [market_data.Stats("small", 1, 1, 1, None), market_data.Stats("big", 9, 9, 9, 50.0)]
    table = market_data.render_table("Field", rows)
    assert table.index("`big`") < table.index("`small`")
    assert "+50.0%" in table
    assert "n/a" in table


def test_build_table_stamps_the_reference_date_and_both_sections() -> None:
    table = market_data.build_table([], [], REFERENCE)
    assert "2026-07-29" in table
    assert "The field" in table
    assert "modern-di integrations" in table


def test_package_sets_are_deduped_and_both_anchor_on_modern_di() -> None:
    assert len(set(market_data.RIVALS)) == len(market_data.RIVALS)
    assert len(set(market_data.OURS)) == len(market_data.OURS)
    assert "modern-di" in market_data.RIVALS
    assert "modern-di" in market_data.OURS


class _Response:
    """A minimal stand-in for the context manager `urllib.request.urlopen` returns."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "typing_extensions.Self":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_fetch_series_retries_until_the_throttling_clears() -> None:
    payload = json.dumps({"data": _flat(REFERENCE, 3, 1)}).encode()
    calls: list[str] = []

    def opener(url: str) -> _Response:
        calls.append(url)
        if len(calls) < 3:  # noqa: PLR2004
            msg = "throttled"
            raise urllib.error.URLError(msg)
        return _Response(payload)

    rows = market_data.fetch_series("dishka", opener=opener, sleep=lambda _: None)
    assert len(rows) == 3  # noqa: PLR2004
    assert len(calls) == 3  # noqa: PLR2004
    assert "mirrors=false" in calls[0]
    assert "dishka" in calls[0]


def test_fetch_series_raises_rather_than_returning_a_hole() -> None:
    def opener(_: str) -> _Response:
        return _Response(b'{"data": []}')

    with pytest.raises(market_data.MarketDataError, match="after 4 attempts"):
        market_data.fetch_series("nope", opener=opener, sleep=lambda _: None)


def test_fetch_series_treats_malformed_payloads_as_retryable() -> None:
    def opener(_: str) -> _Response:
        return _Response(b"<html>rate limited</html>")

    with pytest.raises(market_data.MarketDataError):
        market_data.fetch_series("nope", opener=opener, attempts=2, sleep=lambda _: None)


def test_fetch_series_retries_a_hanging_opener_rather_than_blocking() -> None:
    # TimeoutError is an OSError, so a stalled connection (a WAF, or a rate limiter that accepts
    # the TCP connection and never responds) must be retried like any other OSError, not hang.
    def opener(_: str) -> _Response:
        raise TimeoutError

    with pytest.raises(market_data.MarketDataError, match="after 2 attempts"):
        market_data.fetch_series("nope", opener=opener, attempts=2, sleep=lambda _: None)


def test_fetch_series_backs_off_between_attempts() -> None:
    waits: list[float] = []

    def opener(_: str) -> _Response:
        msg = "throttled"
        raise urllib.error.URLError(msg)

    with pytest.raises(market_data.MarketDataError):
        market_data.fetch_series("nope", opener=opener, attempts=3, delay=2.0, sleep=waits.append)
    assert waits == [2.0, 4.0]


def test_collect_pauses_between_packages() -> None:
    waits: list[float] = []
    series = market_data.collect(
        ("a", "b", "c"),
        fetch=lambda _: _flat(REFERENCE, 1, 1),
        pause=0.5,
        sleep=waits.append,
    )
    assert list(series) == ["a", "b", "c"]
    assert waits == [0.5, 0.5]


def test_collect_propagates_a_failure_instead_of_skipping_the_package() -> None:
    def fetch(package: str) -> list[dict]:
        raise market_data.MarketDataError(package)

    with pytest.raises(market_data.MarketDataError):
        market_data.collect(("a",), fetch=fetch, sleep=lambda _: None)
