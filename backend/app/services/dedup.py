"""Job deduplication by normalized canonical URL.

No embeddings, no vector database: straightforward URL normalization.
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..schemas import DiscoveredJob

logger = logging.getLogger(__name__)

# Common tracking/analytics query parameters that never identify a job.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_DROP_EXACT = {"gclid", "fbclid", "mc_cid", "mc_eid", "ref", "referrer", "ref_src",
               "src", "source", "gh_src", "_ga", "trk"}


def normalize_job_url(url: str) -> str:
    """Canonical form used as deduplication key."""
    if not url:
        return ""
    parsed = urlparse(url.strip())

    scheme = parsed.scheme.lower()
    host = (parsed.netloc or "").lower()
    # Strip default ports and a leading www. for canonical comparison.
    if host.endswith(":80") and scheme == "http":
        host = host[:-3]
    if host.endswith(":443") and scheme == "https":
        host = host[:-4]
    if host.startswith("www."):
        host = host[4:]

    path = parsed.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")

    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in _DROP_EXACT or any(
            key.lower().startswith(prefix) for prefix in _TRACKING_PARAM_PREFIXES
        ):
            continue
        kept.append((key, value))
    query = urlencode(kept)

    return urlunparse((scheme, host, path, "", query, ""))  # fragment dropped


def deduplicate_jobs(jobs: list[DiscoveredJob]) -> list[DiscoveredJob]:
    """Collapse jobs discovered multiple times, keeping the first occurrence.

    Primary key is the normalized job URL. Jobs without a usable URL are
    already rejected at validation time; they are skipped defensively here.
    """
    seen: set[str] = set()
    unique: list[DiscoveredJob] = []
    for job in jobs:
        key = normalize_job_url(job.url)
        if not key or key in seen:
            logger.debug("Dropping duplicate/URL-less job %r (%s)", job.title, job.url)
            continue
        seen.add(key)
        unique.append(job)
    return unique
