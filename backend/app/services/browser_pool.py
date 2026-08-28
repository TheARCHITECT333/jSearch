"""Global browser-context gate.

Chromium contexts are the RAM-heavy unit (~50-100 MB each). The scheduler
bounds companies per search; this gate bounds contexts across ALL searches
combined, so worst-case memory stays predictable no matter how many
searches run concurrently.

Worst case = SEARCH_WORKERS x COMPANY_CONCURRENCY, hard-capped here.
"""

from __future__ import annotations

import asyncio
import os

MAX_BROWSER_CONTEXTS = max(1, int(os.getenv("MAX_BROWSER_CONTEXTS", "8")))


def make_context_gate(limit: int | None = None) -> asyncio.Semaphore:
    return asyncio.Semaphore(max(1, limit or MAX_BROWSER_CONTEXTS))


# Shared gate for production (tests may build their own).
global_context_gate = make_context_gate()
