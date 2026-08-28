"""Literal keyword coverage: what a recruiter's search box would see.

The LLM matcher scores *meaning* - it happily calls "K8s" on the resume a
match for "Kubernetes" in the posting. Applicant tracking systems and the
recruiters driving them do not: they run literal boolean searches over the
resume text. A job can be a perfect semantic fit and still never surface.

So this module answers a deliberately dumber question than the matcher:
which of the posting's own words appear, verbatim, in the resume?

No LLM. The resume text used here is the RAW LaTeX source, not the
extracted profile - the profile is the model's paraphrase, which is exactly
the layer that hides this problem.
"""

from __future__ import annotations

import re

# Requirement boilerplate. These words appear in every posting and matching
# them proves nothing, so they must not pad the denominator.
_STOPWORDS = frozenset(
    """
    a an and or the of to in on at for with without from by as is are be been
    you your our we us they their this that these those it its will would can
    could should must have has had not no any all both each other more most
    such than then there here about into over under across within
    year years experience experienced work working works worked strong solid
    excellent good great proven demonstrated ability able skills skill
    knowledge understanding familiarity familiar background hands
    plus bonus preferred required requirement requirements qualifications
    minimum least equivalent related relevant similar including include
    includes etc using use used usage new latest modern
    team teams teamwork collaborate collaboration collaborative communication
    written verbal interpersonal problem solving solve solutions
    degree bachelor bachelors master masters phd field study
    role position job candidate candidates applicant company business
    development developing developer engineer engineering software technical
    technology technologies environment environments systems system
    build building design designing designs implement implementing
    maintain maintaining support supporting deliver delivering
    high quality best practices practice standards
    comfortable expert expertise proficient proficiency passionate eager
    motivated driven curious paced fast deep deeply well
    ship own drive lead leading manage managing write writing written ensure
    ensuring help helping contribute partner scale scaling improve improving
    optimize optimizing create creating develop end across multiple various
    """.split()
)

# Written the way postings write them -> the way resumes tend to write them.
# Applied to BOTH sides, so direction does not matter.
_ALIASES = {
    "k8s": "kubernetes",
    "k8": "kubernetes",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "golang": "go",
    "postgres": "postgresql",
    "psql": "postgresql",
    "pg": "postgresql",
    "node": "nodejs",
    "node.js": "nodejs",
    "react.js": "react",
    "reactjs": "react",
    "vue.js": "vue",
    "vuejs": "vue",
    "gcp": "googlecloud",
    "ml": "machinelearning",
    "ci": "cicd",
    "cd": "cicd",
    "ci/cd": "cicd",
    "tf": "terraform",
    "iac": "infrastructureascode",
    "restful": "rest",
    "apis": "api",
    "db": "database",
    "dbs": "database",
    "rdbms": "database",
    "oop": "objectoriented",
    "tdd": "testdriven",
    "k8s/kubernetes": "kubernetes",
}

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#./-]*")


def _normalize(token: str) -> str:
    """Alias first, then naive de-pluralisation.

    Order matters: "postgres" must become "postgresql" before any 's' is
    stripped, or it would collapse to "postgre" and stop matching a resume
    that spells it out in full.
    """
    token = _ALIASES.get(token, token)
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        token = token[:-1]
    return token


def _tokens(text: str) -> set[str]:
    """Normalized token set - used for the resume side, where only presence
    matters and the original spelling is never shown back to anyone."""
    return {_normalize(m.group()) for m in _TOKEN_RE.finditer(text.lower())}


def strip_latex(latex: str) -> str:
    """LaTeX source -> rough plain text, keeping every word a human would read.

    ponytail: regex, not a parser. Command *arguments* survive (that is where
    the words are); command names and markup do not. URLs inside \\href leak
    through, which can only make the resume look slightly wordier - it never
    invents a skill.
    """
    text = re.sub(r"(?m)(?<!\\)%.*$", " ", latex)  # comments
    text = re.sub(r"\\[a-zA-Z@]+\*?", " ", text)  # command names, args kept
    text = re.sub(r"[{}$&~^_\\]", " ", text)  # markup punctuation
    return text


def _term_map(requirements: list[str], title: str = "") -> dict[str, str]:
    """Normalized term -> the way the posting actually spelled it.

    Matching has to happen on the normalized form ("k8s" and "kubernetes"
    are the same term), but anything shown to a person must use the posting's
    own spelling. Reporting the internal stem - "kubernete" - reads like a
    typo and tells the user nothing about what to put on their resume.
    """
    terms: dict[str, str] = {}
    for line in [*requirements, title]:
        for match in _TOKEN_RE.finditer(line.lower()):
            surface = match.group()
            token = _normalize(surface)
            if surface in _STOPWORDS or token in _STOPWORDS:
                continue
            # A term worth searching a resume for contains a letter: this
            # drops "5+", "10", "2024" and other requirement scaffolding.
            if len(surface) < 2 or not any(c.isalpha() for c in surface):
                continue
            # First spelling wins, and a longer one beats an abbreviation:
            # "Kubernetes (k8s)" should report as "kubernetes".
            if token not in terms or len(surface) > len(terms[token]):
                terms[token] = surface
    return terms


def requirement_terms(requirements: list[str], title: str = "") -> set[str]:
    """The normalized words in a posting worth searching a resume for."""
    return set(_term_map(requirements, title))


def coverage(resume_latex: str, requirements: list[str], title: str = "") -> tuple[int, list[str]]:
    """(percentage 0-100, the terms that are missing).

    Empty requirements return 0 with no missing terms - "we could not tell",
    not "you match nothing". Callers must not treat 0 as a signal on its own.

    ponytail: single words only. A recruiter searching the exact phrase
    "machine learning" is not modelled; add bigrams if the missing lists
    start looking obviously wrong.
    """
    terms = _term_map(requirements, title)
    if not terms:
        return 0, []

    present = _tokens(strip_latex(resume_latex))
    # Report the posting's spelling, not the internal stem.
    missing = sorted(surface for token, surface in terms.items() if token not in present)
    covered = len(terms) - len(missing)
    return round(covered * 100 / len(terms)), missing
