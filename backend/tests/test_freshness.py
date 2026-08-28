"""Freshness filter tests: date parsing + stale-job dropping.

Jobs with unknown/missing dates must always be kept (never guessed).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas import DiscoveredJob
from app.services.freshness import (
    FRESHNESS_DAYS,
    filter_fresh_jobs,
    parse_posted_age_days,
)

NOW = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)


def job(posted_at: str | None = None, url: str | None = None) -> DiscoveredJob:
    path = url or f"jobs/{abs(hash(str(posted_at))) % 100000}"
    if not path.startswith("http"):
        path = f"https://x.example/{path}"
    return DiscoveredJob(title="Engineer", url=path, posted_at=posted_at)


class TestParsePostedAgeDays:
    def test_relative_days(self):
        assert parse_posted_age_days("2 days ago", NOW) == 2.0
        assert parse_posted_age_days("Posted 1 day ago", NOW) == 1.0

    def test_relative_hours_fraction(self):
        age = parse_posted_age_days("12 hours ago", NOW)
        assert age is not None
        assert abs(age - 0.5) < 0.01

    def test_relative_weeks_months_years(self):
        assert parse_posted_age_days("3 weeks ago", NOW) == 21.0
        assert abs(parse_posted_age_days("1 month ago", NOW) - 30.44) < 0.1
        assert parse_posted_age_days("1 year ago", NOW) == 365.0

    def test_today_yesterday_just_now(self):
        assert parse_posted_age_days("Today", NOW) == 0.0
        assert parse_posted_age_days("yesterday", NOW) == 1.0
        assert parse_posted_age_days("Just now", NOW) == 0.0

    def test_absolute_iso_date(self):
        age = parse_posted_age_days("2026-08-20", NOW)
        assert age == 6.0

    def test_absolute_us_style(self):
        assert parse_posted_age_days("08/20/2026", NOW) == 6.0

    def test_absolute_written_month(self):
        assert parse_posted_age_days("Aug 20, 2026", NOW) == 6.0
        assert parse_posted_age_days("20 August 2026", NOW) == 6.0

    def test_written_month_without_year_assumes_current_year(self):
        # Aug 25 with no year, "today" is Aug 26 -> one day old.
        assert parse_posted_age_days("Aug 25", NOW) == 1.0

    def test_written_month_without_year_rolls_back_when_future(self):
        # "Sep 1" with no year would be in the future for 2026 -> assume 2025.
        age = parse_posted_age_days("Sep 1", NOW)
        expected = (NOW - datetime(2025, 9, 1, tzinfo=timezone.utc)).days
        assert age is not None and abs(age - expected) < 1

    def test_ordinal_suffixes(self):
        assert parse_posted_age_days("August 20th", NOW) == 6.0

    def test_unknown_text_returns_none(self):
        assert parse_posted_age_days("requisition 48210", NOW) is None

    def test_empty_returns_none(self):
        assert parse_posted_age_days(None) is None
        assert parse_posted_age_days("") is None
        assert parse_posted_age_days("   ") is None


class TestFilterFreshJobs:
    def test_any_keeps_everything(self):
        jobs = [job("2020-01-01"), job(None), job("1 day ago")]
        fresh, stale = filter_fresh_jobs(jobs, "any", now=NOW)
        assert len(fresh) == 3 and stale == []

    def test_stale_dropped_fresh_and_unknown_kept(self):
        jobs = [
            job("2026-08-25", url="u-fresh"),     # 1 day old
            job("3 weeks ago", url="u-stale"),    # 21 days old
            job(None, url="u-unknown"),
        ]
        fresh, stale = filter_fresh_jobs(jobs, "1w", now=NOW)
        assert [j.url.rsplit("/", 1)[-1] for j in fresh] == ["u-fresh", "u-unknown"]
        assert [j.url.rsplit("/", 1)[-1] for j in stale] == ["u-stale"]

    def test_boundary_is_inclusive(self):
        edge = job("2026-08-19", url="u-edge")  # exactly 7.0 days old
        fresh, stale = filter_fresh_jobs([edge], "1w", now=NOW)
        assert len(fresh) == 1 and stale == []

    def test_all_windows_map_to_day_counts(self):
        assert FRESHNESS_DAYS["24h"] == 1
        assert FRESHNESS_DAYS["3d"] == 3
        assert FRESHNESS_DAYS["1w"] == 7
        assert FRESHNESS_DAYS["2w"] == 14
        assert FRESHNESS_DAYS["1m"] == 30
        assert FRESHNESS_DAYS["any"] is None

    def test_garbage_date_string_keeps_job(self):
        suspicious = job("posted soon-ish??", url="u-x")
        fresh, stale = filter_fresh_jobs([suspicious], "24h", now=NOW)
        assert fresh == [suspicious] and stale == []
