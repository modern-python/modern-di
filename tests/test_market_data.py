"""The adoption download table is generated, not hand-assembled — this guards the generator."""

import datetime

from planning.scripts import market_data


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
    stats = market_data.summarize("p", _flat(REFERENCE, 180, 1), REFERENCE)
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
