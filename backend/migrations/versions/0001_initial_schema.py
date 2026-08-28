"""Initial schema: searches, jobs, matches, profiles.

Revision ID: 0001
Revises:
Create Date: 2026-08-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "searches",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("freshness", sa.String(length=8), nullable=False),
        sa.Column("locations_json", sa.JSON(), nullable=False),
        sa.Column("companies_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("final_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_searches_status", "searches", ["status"])
    op.create_index("ix_searches_created_at", "searches", ["created_at"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("careers_url", sa.String(length=1000), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("employment_type", sa.String(length=100), nullable=True),
        sa.Column("posted_at_text", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("requirements_json", sa.JSON(), nullable=False),
        sa.Column("preferred_qualifications_json", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_jobs_url_hash", "jobs", ["url_hash"], unique=True)
    op.create_index("ix_jobs_company", "jobs", ["company"])
    op.create_index("ix_jobs_last_seen_at", "jobs", ["last_seen_at"])

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("search_id", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("role_fit", sa.Integer(), nullable=False),
        sa.Column("skill_fit", sa.Integer(), nullable=False),
        sa.Column("experience_fit", sa.Integer(), nullable=False),
        sa.Column("location_fit", sa.Integer(), nullable=False),
        sa.Column("matching_skills_json", sa.JSON(), nullable=False),
        sa.Column("missing_skills_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["search_id"], ["searches.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.UniqueConstraint("search_id", "job_id", name="uq_matches_search_job"),
    )
    op.create_index("ix_matches_search_id", "matches", ["search_id"])
    op.create_index("ix_matches_job_id", "matches", ["job_id"])
    op.create_index("ix_matches_created_at", "matches", ["created_at"])

    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("resume_hash", sa.String(length=64), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("model_used", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_profiles_resume_hash", "profiles", ["resume_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("profiles")
    op.drop_table("matches")
    op.drop_table("jobs")
    op.drop_table("searches")
