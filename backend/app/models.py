"""SQLAlchemy models: job history, search history, matches, cached profiles.

Column types are deliberately generic (String/Text/JSON/Integer) so the same
models run on SQLite today and Postgres later without changes.

Changing anything here requires a matching Alembic revision in
`migrations/versions/` - the schema is never created from these models
directly. See `AGENTS.md`.
"""

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Search(Base):
    """One FIND JOBS run (history survives restarts)."""

    __tablename__ = "searches"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    freshness: Mapped[str] = mapped_column(String(8), default="any")
    locations_json: Mapped[list] = mapped_column(JSON, default=list)
    companies_json: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    final_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Job(Base):
    """A job posting, deduplicated by normalized-URL hash across all searches."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    careers_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    posted_at_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    requirements_json: Mapped[list] = mapped_column(JSON, default=list)
    preferred_qualifications_json: Mapped[list] = mapped_column(JSON, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class Match(Base):
    """A candidate-vs-job evaluation produced for a specific search."""

    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("search_id", "job_id", name="uq_matches_search_job"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("searches.id"), index=True
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)

    overall_score: Mapped[int] = mapped_column(Integer)
    role_fit: Mapped[int] = mapped_column(Integer)
    skill_fit: Mapped[int] = mapped_column(Integer)
    experience_fit: Mapped[int] = mapped_column(Integer)
    location_fit: Mapped[int] = mapped_column(Integer)
    matching_skills_json: Mapped[list] = mapped_column(JSON, default=list)
    missing_skills_json: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(Text, default="")

    # Eligibility, kept apart from the fit scores above (see MatchResult).
    disqualifiers_json: Mapped[list] = mapped_column(JSON, default=list)
    seniority_band: Mapped[str | None] = mapped_column(String(16), nullable=True)
    required_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keyword_coverage: Mapped[int] = mapped_column(Integer, default=0)
    missing_keywords_json: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class Profile(Base):
    """Cached candidate profile keyed by resume-content hash."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    profile_json: Mapped[dict] = mapped_column(JSON)
    model_used: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
