"""Literal keyword coverage - the thing the LLM matcher deliberately can't see.

The point of every test here is the same: semantic equivalence must NOT count.
A resume that says "K8s" and a posting that says "Kubernetes" is the exact
case an ATS keyword search misses, and this module has to notice it.
"""

from app.matching.keywords import coverage, requirement_terms, strip_latex

RESUME = r"""
\documentclass{article}
% a comment mentioning Rust, which must not count
\begin{document}
\section{Skills}
Languages: Python, Go, TypeScript.
Infrastructure: K8s, Terraform, Docker.
Databases: Postgres, Redis.
\section{Experience}
Built \textbf{REST} APIs handling 2M requests/day.
\end{document}
"""


class TestStripLatex:
    def test_command_arguments_survive_but_command_names_do_not(self):
        text = strip_latex(r"\textbf{Kubernetes} and \emph{Docker}")
        assert "Kubernetes" in text and "Docker" in text
        assert "textbf" not in text and "emph" not in text

    def test_comments_are_dropped(self):
        assert "Rust" not in strip_latex(RESUME)


class TestAliases:
    def test_abbreviation_on_the_resume_matches_the_full_name_in_the_posting(self):
        pct, missing = coverage(RESUME, ["Experience with Kubernetes required"])
        assert missing == []  # K8s on the resume covered it
        assert pct == 100

    def test_full_name_on_the_resume_matches_the_abbreviation_in_the_posting(self):
        pct, missing = coverage(RESUME, ["Strong PostgreSQL background"])
        assert missing == []  # resume says "Postgres"
        assert pct == 100

    def test_plurals_do_not_count_as_a_miss(self):
        _, missing = coverage(RESUME, ["Build REST APIs"])
        assert missing == []


class TestCoverage:
    def test_a_term_absent_from_the_resume_is_reported_missing(self):
        pct, missing = coverage(RESUME, ["Expert in Kubernetes, Rust and Kafka"])
        assert "rust" in missing and "kafka" in missing
        assert pct < 100

    def test_boilerplate_words_do_not_pad_the_score(self):
        # Nothing here is a real requirement, so nothing is checkable.
        pct, missing = coverage(
            RESUME, ["Excellent written and verbal communication skills required"]
        )
        assert (pct, missing) == (0, [])

    def test_no_requirements_means_unknown_not_zero_match(self):
        # 0 here means "nothing to check" - documented, and the UI must not
        # render it as "you match none of it".
        assert coverage(RESUME, []) == (0, [])

    def test_empty_resume_misses_everything(self):
        pct, missing = coverage("", ["Kubernetes and Terraform"])
        assert pct == 0 and set(missing) == {"kubernetes", "terraform"}

    def test_the_job_title_is_searched_too(self):
        _, missing = coverage(RESUME, ["5 years of relevant experience"], "Rust Engineer")
        assert "rust" in missing


class TestReportedSpelling:
    """Missing terms are shown to a person, so they carry the posting's own
    spelling - never the internal normalized stem."""

    def test_missing_terms_keep_the_postings_spelling(self):
        # A resume with none of these, so both terms come back missing.
        _, missing = coverage("Python and SQL only", ["Kubernetes and Kafka experience"])
        assert "kubernetes" in missing  # not the internal "kubernete" stem
        assert "kafka" in missing

    def test_plural_in_the_posting_is_reported_as_written(self):
        _, missing = coverage(RESUME, ["Experience with microservices"])
        assert missing == ["microservices"]

    def test_the_fuller_spelling_wins_over_an_abbreviation(self):
        _, missing = coverage("", ["Kubernetes (k8s) required"])
        assert missing == ["kubernetes"]


class TestRequirementTerms:
    def test_stopwords_and_bare_numbers_are_excluded(self):
        terms = requirement_terms(["5+ years of experience with Django"])
        assert terms == {"django"}
