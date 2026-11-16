"""Resume scoring: the hiring-agent rubric on top of jsearch's LLM layer.

One LLM call over the raw resume text (plus public GitHub signals when the
resume links a profile). hiring-agent's six-call section extraction is
skipped on purpose: the rubric reads plain text just as well.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re

import httpx
from pydantic import BaseModel, Field

from ..llm import LLM, generate_validated
from .scoring_prompts import LEVELS, MAX_BONUS, SYSTEM_PROMPT, criteria_prompt

logger = logging.getLogger(__name__)

LABELS = {
    "open_source": "Open Source",
    "self_projects": "Self Projects",
    "production": "Production Experience",
    "technical_skills": "Technical Skills",
}
# ponytail: one contributors call per repo; unauthenticated GitHub allows 60/h,
# so ~5 scorings an hour. Set GITHUB_TOKEN to lift that to 5000/h.
MAX_REPOS = 10
_GITHUB_USER = re.compile(r"github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?![A-Za-z0-9-])", re.I)
_NOT_USERS = {"orgs", "features", "topics", "about", "sponsors", "marketplace"}


# Lenient on numbers: the report clamps them, so a model that writes 40/35
# is corrected rather than retried.
class CategoryScore(BaseModel):
    score: float
    evidence: str = ""


class Scores(BaseModel):
    open_source: CategoryScore
    self_projects: CategoryScore
    production: CategoryScore
    technical_skills: CategoryScore


class BonusPoints(BaseModel):
    total: float = 0
    breakdown: str = ""


class Deductions(BaseModel):
    total: float = 0
    reasons: str = ""


class Evaluation(BaseModel):
    scores: Scores
    bonus_points: BonusPoints = Field(default_factory=BonusPoints)
    deductions: Deductions = Field(default_factory=Deductions)
    key_strengths: list[str] = Field(default_factory=list)
    areas_for_improvement: list[str] = Field(default_factory=list)


def github_username(text: str) -> str | None:
    for match in _GITHUB_USER.finditer(text):
        if match.group(1).lower() not in _NOT_USERS:
            return match.group(1)
    return None


async def fetch_github(username: str) -> dict | None:
    """Public profile + top repos, each tagged open_source / self_project.

    Best effort: any GitHub failure means "score without it", never an error.
    """
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(
            base_url="https://api.github.com", headers=headers, timeout=15
        ) as client:
            profile = await client.get(f"/users/{username}")
            if profile.status_code != 200:
                logger.info("github: no profile for %s (HTTP %d)", username, profile.status_code)
                return None
            listing = await client.get(
                f"/users/{username}/repos", params={"sort": "updated", "per_page": 100}
            )
            repos = listing.json() if listing.status_code == 200 else []
            # Same rule as hiring-agent: a fork only counts once others fork it.
            repos = [r for r in repos if not r.get("fork") or r.get("forks_count", 0) >= 5]
            repos.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
            repos = repos[:MAX_REPOS]
            contributors = await asyncio.gather(
                *(
                    client.get(f"/repos/{r['full_name']}/contributors", params={"per_page": 2})
                    for r in repos
                )
            )
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("github: fetch failed for %s: %s", username, exc)
        return None

    p = profile.json()
    return {
        "username": p.get("login"),
        "name": p.get("name"),
        "avatar_url": p.get("avatar_url"),
        "bio": p.get("bio"),
        "public_repos": p.get("public_repos"),
        "followers": p.get("followers"),
        "repos": [
            {
                "name": r.get("name"),
                "description": r.get("description"),
                "language": r.get("language"),
                "stars": r.get("stargazers_count", 0),
                "forks": r.get("forks_count", 0),
                "homepage": r.get("homepage") or None,
                # 204 (empty repo) or an error reads as a solo project.
                "project_type": "open_source"
                if c.status_code == 200 and len(c.json()) > 1
                else "self_project",
            }
            for r, c in zip(repos, contributors)
        ],
    }


def github_text(gh: dict) -> str:
    lines = [
        "\n\n=== GITHUB DATA ===",
        f"username: {gh['username']}  name: {gh['name']}  bio: {gh['bio']}",
        f"public_repos: {gh['public_repos']}  followers: {gh['followers']}",
    ]
    for r in gh["repos"]:
        lines.append(
            f"- {r['name']} [project_type: {r['project_type']}] "
            f"stars={r['stars']} forks={r['forks']} lang={r['language']} "
            f"live={r['homepage']} :: {r['description'] or ''}"
        )
    return "\n".join(lines)


def build_report(ev: Evaluation, level: str) -> dict:
    """Clamp the model's numbers to the level's limits and total them."""
    maxes = LEVELS[level].maxes
    categories = []
    for key, label in LABELS.items():
        cat, cap = getattr(ev.scores, key), maxes[key]
        score = max(0.0, min(cat.score, cap))
        categories.append(
            {"key": key, "label": label, "score": round(score, 1), "max": cap, "evidence": cat.evidence}
        )
    base_max = sum(maxes.values())
    bonus = max(0.0, min(ev.bonus_points.total, MAX_BONUS))
    deduction = max(0.0, ev.deductions.total)
    total = sum(c["score"] for c in categories) + bonus - deduction
    return {
        "level": level,
        "total": round(min(total, base_max + MAX_BONUS), 1),
        "base_max": base_max,
        "categories": categories,
        "bonus": {"total": round(bonus, 1), "breakdown": ev.bonus_points.breakdown},
        "deductions": {"total": round(deduction, 1), "reasons": ev.deductions.reasons},
        "key_strengths": ev.key_strengths[:5],
        "areas_for_improvement": ev.areas_for_improvement[:5],
    }


async def score_resume(llm: LLM, resume_text: str, level: str = "junior") -> dict:
    text = resume_text.strip()[:24000]
    username = github_username(text)
    gh = await fetch_github(username) if username else None
    if gh:
        text += github_text(gh)

    ev = await generate_validated(
        llm, SYSTEM_PROMPT, f"{criteria_prompt(LEVELS[level])}\n{text}", Evaluation
    )
    report = build_report(ev, level)
    report["github"] = {k: v for k, v in gh.items() if k != "repos"} if gh else None
    return report


if __name__ == "__main__":
    assert github_username("see https://github.com/orgs/x and github.com/Jane-Doe/repo") == "Jane-Doe"
    assert github_username("no links here") is None
    r = build_report(
        Evaluation(
            scores=Scores(
                open_source=CategoryScore(score=50, evidence="a"),  # over cap -> 35
                self_projects=CategoryScore(score=-3, evidence="b"),  # negative -> 0
                production=CategoryScore(score=20, evidence="c"),
                technical_skills=CategoryScore(score=10, evidence="d"),
            ),
            bonus_points=BonusPoints(total=30),  # over cap -> 20
            deductions=Deductions(total=5),
        ),
        "junior",
    )
    assert r["total"] == 35 + 0 + 20 + 10 + 20 - 5, r["total"]
    for name, lvl in LEVELS.items():
        assert sum(lvl.maxes.values()) == 100, name
        prompt = criteria_prompt(lvl)
        for key, cap in lvl.maxes.items():
            assert f'"{key}": {{"score": 0, "max": {cap}' in prompt, (name, key)
    print("ok")
