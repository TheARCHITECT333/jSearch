"""Job location matching.

The user chooses target locations for a search. Jobs whose page-stated
location clearly falls OUTSIDE that list are dropped before matching.
Consistent with the freshness rules: jobs with NO visible location are
always kept (never guessed), and Remote postings fit every selection.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

from ..schemas import DiscoveredJob

logger = logging.getLogger(__name__)

# Common city-name variants so "Bengaluru" matches a wanted "Bangalore".
_ALIASES: dict[str, str] = {
    "bengaluru": "bangalore",
    "gurgaon": "gurugram",
    "nyc": "new york",
    "sf bay area": "san francisco bay area",
    "wfh": "remote",
}

# Job boards print the country as an ISO code at least as often as they spell
# it out - Amazon renders "Bengaluru, KA, IND", so a search for "India" found
# no whole word "india" and discarded every result on the page.
#
# Alpha-3 only, and only codes that are not also ordinary English words:
# "PER", "NOR" and "ARE" would match prose, and matching the wrong country is
# worse than missing an abbreviation. "CAN" is kept because Canada matters
# more than the risk - location strings do not contain the verb "can".
_COUNTRY_CODES: dict[str, str] = {
    "ind": "india",
    "usa": "united states",
    "gbr": "united kingdom",
    "deu": "germany",
    "fra": "france",
    "can": "canada",
    "aus": "australia",
    "nzl": "new zealand",
    "sgp": "singapore",
    "jpn": "japan",
    "chn": "china",
    "kor": "south korea",
    "twn": "taiwan",
    "hkg": "hong kong",
    "idn": "indonesia",
    "mys": "malaysia",
    "phl": "philippines",
    "vnm": "vietnam",
    "tha": "thailand",
    "nld": "netherlands",
    "irl": "ireland",
    "esp": "spain",
    "ita": "italy",
    "prt": "portugal",
    "che": "switzerland",
    "aut": "austria",
    "bel": "belgium",
    "swe": "sweden",
    "dnk": "denmark",
    "fin": "finland",
    "pol": "poland",
    "cze": "czechia",
    "rou": "romania",
    "isr": "israel",
    "tur": "turkey",
    "bra": "brazil",
    "mex": "mexico",
    "arg": "argentina",
    "zaf": "south africa",
    "egy": "egypt",
}

_ALIASES.update(_COUNTRY_CODES)

_REMOTE_RE = re.compile(r"\b(remote|anywhere|work from home)\b")


def _normalize(text: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _apply_aliases(text: str) -> str:
    words_fixed = f" {text} "
    for alias, canonical in _ALIASES.items():
        if alias in _ALIASES and len(alias.split()) > 1:
            # multi-word aliases replace in place
            words_fixed = words_fixed.replace(f" {alias} ", f" {canonical} ")
        else:
            words_fixed = re.sub(
                rf"\b{re.escape(alias)}\b", canonical, words_fixed
            )
    return words_fixed.strip()


def _contains_word(haystack: str, needle: str) -> bool:
    if not needle:
        return False
    return re.search(rf"\b{re.escape(needle)}\b", haystack) is not None


def location_matches(job_location: str | None, wanted_locations: Iterable[str]) -> bool:
    """True when the job's location plausibly fits the wanted list."""
    wanted = [w for w in (_normalize(w) for w in wanted_locations) if w]
    if not wanted:
        return True  # no restriction requested

    if not job_location or not job_location.strip():
        return True  # unknown location is never dropped

    job_norm = _apply_aliases(_normalize(job_location))

    # Remote jobs are location-flexible: they fit every selection.
    if _REMOTE_RE.search(job_norm):
        return True

    wanted_remote_only = all(w in ("remote", "anywhere") for w in wanted)
    if wanted_remote_only:
        return False  # non-remote, city-anchored posting can't be remote-only

    for w in wanted:
        w_alias = _apply_aliases(w)
        if w_alias in ("remote", "anywhere"):
            continue
        if _contains_word(job_norm, w_alias) or _contains_word(w_alias, job_norm):
            return True
    return False


def filter_jobs_by_location(
    jobs: Iterable[DiscoveredJob],
    wanted_locations: Iterable[str],
) -> tuple[list[DiscoveredJob], list[DiscoveredJob]]:
    """Split jobs into (in-location-or-unknown, clearly-elsewhere)."""
    kept: list[DiscoveredJob] = []
    dropped: list[DiscoveredJob] = []
    for job in jobs:
        if location_matches(job.location, wanted_locations):
            kept.append(job)
        else:
            dropped.append(job)
    return kept, dropped
