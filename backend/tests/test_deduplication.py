"""Deduplication tests: URL normalization and cross-company collapsing."""

from __future__ import annotations

from app.schemas import DiscoveredJob
from app.services.dedup import deduplicate_jobs, normalize_job_url


def job(url: str, title: str = "Backend Engineer") -> DiscoveredJob:
    return DiscoveredJob(title=title, url=url)


class TestNormalizeJobUrl:
    def test_trailing_slash_removed(self):
        assert (
            normalize_job_url("https://stripe.com/jobs/123/")
            == normalize_job_url("https://stripe.com/jobs/123")
        )

    def test_fragment_dropped(self):
        assert normalize_job_url("https://x.com/j#section") == "https://x.com/j"

    def test_tracking_params_removed(self):
        base = "https://boards.greenhouse.io/stripe/jobs/4001"
        dirty = base + "?utm_source=linkedin&gclid=abc&gh_src=xyz"
        assert normalize_job_url(dirty) == base

    def test_meaningful_params_kept(self):
        a = normalize_job_url("https://x.com/jobs?id=7")
        b = normalize_job_url("https://x.com/jobs?id=8")
        assert a != b

    def test_host_case_and_www_insensitive(self):
        assert normalize_job_url("https://WWW.Stripe.com/Jobs/1") == normalize_job_url(
            "https://stripe.com/Jobs/1"
        )

    def test_default_ports_dropped(self):
        assert normalize_job_url("http://x.com:80/a") == normalize_job_url("http://x.com/a")
        assert normalize_job_url("https://x.com:443/a") == normalize_job_url("https://x.com/a")


class TestDeduplicateJobs:
    def test_same_job_from_multiple_pages_collapses(self):
        jobs = [
            job("https://careers.google.com/jobs/results/12345"),
            job("https://www.careers.google.com/jobs/results/12345/?utm_source=agent"),
            job("https://careers.google.com/jobs/results/99999", title="Other role"),
        ]
        unique = deduplicate_jobs(jobs)
        assert len(unique) == 2
        assert {j.url.split("/")[-1].rstrip("/") for j in unique} == {"12345", "99999"}

    def test_first_occurrence_wins(self):
        first = job("https://x.com/j/1", "First Title")
        second = job("https://x.com/j/1/", "Second Title")
        unique = deduplicate_jobs([first, second])
        assert len(unique) == 1
        assert unique[0].title == "First Title"

    def test_distinct_jobs_all_kept(self):
        jobs = [job(f"https://x.com/j/{i}") for i in range(5)]
        assert len(deduplicate_jobs(jobs)) == 5

    def test_empty_input(self):
        assert deduplicate_jobs([]) == []
