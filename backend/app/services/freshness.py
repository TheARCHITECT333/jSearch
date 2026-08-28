"""Job freshness: parse posting dates shown on pages and drop stale jobs.

The agent records `posted_at` verbatim from the page (an absolute date or a
relative phrase like "2 weeks ago"). Jobs with NO visible date are always
kept - we never guess a job's age.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Iterable

from ..schemas import DiscoveredJob

logger = logging.getLogger(__name__)

FRESHNESS_DAYS: dict[str, float | None] = {
    "any": None,
    "24h": 1,
    "3d": 3,
    "1w": 7,
    "2w": 14,
    "1m": 30,
}

FRESHNESS_LABELS: dict[str, str] = {
    "any": "any age",
    "24h": "the last 24 hours",
    "3d": "the last 3 days",
    "1w": "the last week",
    "2w": "the last two weeks",
    "1m": "the last month",
}

_UNIT_DAYS = {
    "hour": 1 / 24,
    "hr": 1 / 24,
    "h": 1 / 24,
    "day": 1,
    "d": 1,
    "week": 7,
    "wk": 7,
    "month": 30.44,
    "year": 365,
}

_RELATIVE_RE = re.compile(
    r"(\d+)\s*(hour|hr|h|day|d|week|wk|month|year)s?\s*ago", re.IGNORECASE
)
_MONTH_DAY_RE = re.compile(r"\b([a-z]{3,9})\s+(\d{1,2})\b", re.IGNORECASE)
_ORDINAL_RE = re.compile(r"(\d)(st|nd|rd|th)\b", re.IGNORECASE)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d.%m.%Y",
)


def parse_posted_age_days(text: str | None, now: datetime | None = None) -> float | None:
    """Best-effort conversion of a page's posting date text to an age in days.

    Absolute dates are compared in CALENDAR days (e.g. "Aug 20" seen on
    Aug 26 -> 6.0). Returns None when the text is empty or cannot be
    confidently parsed - callers must treat None as "unknown" (keep the job).
    """
    if not text or not text.strip():
        return None

    now = now or datetime.now(timezone.utc)
    raw = text.strip()
    t = _ORDINAL_RE.sub(r"\1", raw.lower())
    today = now.date()

    # Relative phrases ------------------------------------------------------
    if "just now" in t or "posted today" in t or t in ("today", "new"):
        return 0.0
    if "yesterday" in t:
        return 1.0

    match = _RELATIVE_RE.search(t)
    if match:
        count = int(match.group(1))
        unit = match.group(2).lower()
        return count * _UNIT_DAYS[unit]

    # Absolute dates --------------------------------------------------------
    cleaned = re.sub(r"\b(posted|date|on)\b", " ", t)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-")

    def calendar_age(day: object) -> float | None:
        # day is a datetime.date-like via .date() if datetime
        d = day.date() if hasattr(day, "date") else day
        ahead = (d - today).days
        if ahead > 1:  # future date beyond clock skew -> bad data
            return None
        return float(max(0, (today - d).days))

    for fmt in _DATE_FORMATS:
        try:
            return calendar_age(datetime.strptime(cleaned, fmt))
        except ValueError:
            continue

    # ISO datetimes like 2026-08-20T14:30:00
    iso_match = re.match(r"(\d{4}-\d{2}-\d{2})", cleaned)
    if iso_match:
        try:
            return calendar_age(datetime.fromisoformat(iso_match.group(1)))
        except ValueError:
            pass

    # "Aug 20" / "August 20" without a year -> assume current year,
    # previous year if that would land noticeably in the future.
    month_day = _MONTH_DAY_RE.search(cleaned)
    if month_day:
        month_name = month_day.group(1)[:3]
        day = int(month_day.group(2))
        month = _MONTHS.get(month_name)
        if month is not None and 1 <= day <= 31:
            try:
                candidate = datetime(now.year, month, day)
            except ValueError:
                return None
            age = calendar_age(candidate)
            if age is None:  # future this year -> it must mean last year
                try:
                    age = calendar_age(datetime(now.year - 1, month, day))
                except ValueError:
                    return None
            return age

    logger.debug("Could not parse posting date text: %r", text)
    return None


def filter_fresh_jobs(
    jobs: Iterable[DiscoveredJob],
    freshness: str,
    *,
    now: datetime | None = None,
) -> tuple[list[DiscoveredJob], list[DiscoveredJob]]:
    """Split jobs into (fresh/unknown, provably-stale) for the given window."""
    max_age = FRESHNESS_DAYS.get(freshness)
    if max_age is None:
        return list(jobs), []

    fresh: list[DiscoveredJob] = []
    stale: list[DiscoveredJob] = []
    for job in jobs:
        age = parse_posted_age_days(job.posted_at, now=now)
        if age is not None and age > max_age:
            stale.append(job)
        else:
            fresh.append(job)
    return fresh, stale
