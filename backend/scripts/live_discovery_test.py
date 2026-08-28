"""Manual live-discovery test against real career sites.

Usage (from backend/, with the venv active and Chromium installed):

    python scripts/live_discovery_test.py --companies Google,Amazon --steps 14

Point LLM_BASE_URL/LLM_MODEL at your hosted server. Results print per
company and are saved to /tmp/opencode/live_discovery_results.json.
This hits REAL career sites - use sparingly.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.career_agent import CareerAgent  # noqa: E402
from app.llm import OllamaLLM  # noqa: E402
from app.services.search import chromium_browser  # noqa: E402
from app.services.browser_pool import global_context_gate  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


async def run_company(llm, name: str, url: str, steps: int) -> dict:
    started = time.monotonic()
    try:
        async with chromium_browser() as browser:
            agent = CareerAgent(
                llm=llm,
                company_name=name,
                careers_url=url,
                freshness=os.getenv("FRESHNESS", "any"),
                max_steps=steps,
                max_job_visits=int(os.getenv("MAX_JOB_VISITS", "8")),
            )
            jobs = await agent.run(browser, context_gate=global_context_gate)
        return {
            "company": name,
            "status": "completed",
            "elapsed_s": round(time.monotonic() - started, 1),
            "examined": agent.jobs_examined,
            "jobs": [j.model_dump(mode="json") for j in jobs],
        }
    except Exception as exc:  # noqa: BLE001 - report, keep going
        return {
            "company": name,
            "status": "failed",
            "elapsed_s": round(time.monotonic() - started, 1),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def main() -> None:
    _setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--companies", required=True, help="Comma-separated names")
    parser.add_argument("--steps", type=int, default=14)
    args = parser.parse_args()

    wanted = [c.strip().lower() for c in args.companies.split(",") if c.strip()]
    catalog = {
        c["name"]: c["careers_url"]
        for c in json.loads((ROOT / "companies.example.json").read_text())
    }

    llm = OllamaLLM(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434"),
        model=os.getenv("LLM_MODEL", "qwen3:32b"),
        api_key=os.getenv("LLM_API_KEY") or None,
        timeout=240,
    )

    results = []
    for name in catalog:
        if name.lower() not in wanted:
            continue
        print(f"\n=== {name} -> {catalog[name]} ===", flush=True)
        result = await run_company(llm, name, catalog[name], args.steps)
        results.append(result)
        print(
            f"--- {name}: {result['status']} in {result['elapsed_s']}s "
            f"({result.get('examined', 0)} examined)",
            flush=True,
        )
        for job in result.get("jobs", []):
            print(f"    {job['overall_score'] if 'match' in job else ''}"
                  f"{job['title']}\n      {job['url']}", flush=True)

    out = Path("/tmp/opencode/live_discovery_results.json")
    out.write_text(json.dumps(results, indent=2))
    print(f"\nsaved -> {out}", flush=True)
    await llm.close()


if __name__ == "__main__":
    asyncio.run(main())
