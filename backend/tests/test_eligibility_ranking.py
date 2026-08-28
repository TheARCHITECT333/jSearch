"""Disqualifiers are a gate, not a penalty.

The whole point of the eligibility split: a job you are barred from must
LEAVE the ranking, not lose a few points and still sit near the top. A 95%
fit you cannot legally apply for is worth less than a 60% fit you can.
"""

from app.schemas import JobResult, MatchResult


def _result(title: str, score: int, disqualifiers: list[str] | None = None) -> JobResult:
    return JobResult(
        company="Acme",
        job_title=title,
        job_url=f"https://acme.example/{title}",
        match=MatchResult(
            overall_score=score,
            role_fit=score,
            skill_fit=score,
            experience_fit=score,
            location_fit=score,
            disqualifiers=disqualifiers or [],
        ),
    )


def _ranked(results):
    from app.services.search import _rank_key

    return [r.job_title for r in sorted(results, key=_rank_key, reverse=True)]


class TestRanking:
    def test_a_disqualified_job_sinks_below_every_eligible_one(self):
        order = _ranked(
            [
                _result("perfect-but-barred", 98, ["Requires active security clearance"]),
                _result("mediocre-but-open", 55),
            ]
        )
        assert order == ["mediocre-but-open", "perfect-but-barred"]

    def test_eligible_jobs_still_rank_by_fit(self):
        order = _ranked([_result("weak", 40), _result("strong", 90), _result("mid", 65)])
        assert order == ["strong", "mid", "weak"]

    def test_disqualified_jobs_rank_among_themselves_by_fit(self):
        # They are still shown - the user gets to disagree with the filter -
        # so their internal order should stay useful.
        order = _ranked(
            [
                _result("barred-weak", 30, ["10+ years required"]),
                _result("barred-strong", 88, ["On-site in Zurich"]),
            ]
        )
        assert order == ["barred-strong", "barred-weak"]


class TestMatchResult:
    def test_empty_disqualifiers_means_eligible(self):
        assert not _result("x", 50).match.disqualified

    def test_any_disqualifier_marks_the_job(self):
        assert _result("x", 50, ["No visa sponsorship"]).match.disqualified

    def test_scores_are_untouched_by_a_disqualifier(self):
        # Fit and eligibility are separate answers; the gate must not quietly
        # rewrite the fit score, or the "why" shown to the user becomes a lie.
        match = _result("x", 92, ["Requires US citizenship"]).match
        assert match.overall_score == 92
