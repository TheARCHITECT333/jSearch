"""Match eligibility: disqualifiers, seniority, literal keyword coverage.

Splits "would this candidate do well here" (the existing *_fit scores) from
"could this application survive the filter at all" (disqualifiers). All
columns are additive with safe defaults, so rows written before this
revision simply read back as "nothing ruled out, coverage unknown".

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Plain ADD COLUMN, not batch_alter_table: SQLite supports adding a
    # column in place, and batch mode (which rebuilds the table) trips over
    # column ordering when several are added at once.
    op.add_column(
        "matches",
        sa.Column(
            "disqualifiers_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column("matches", sa.Column("seniority_band", sa.String(16), nullable=True))
    op.add_column("matches", sa.Column("required_years", sa.Integer(), nullable=True))
    op.add_column(
        "matches",
        sa.Column(
            "keyword_coverage", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "matches",
        sa.Column(
            "missing_keywords_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("matches") as batch:
        batch.drop_column("missing_keywords_json")
        batch.drop_column("keyword_coverage")
        batch.drop_column("required_years")
        batch.drop_column("seniority_band")
        batch.drop_column("disqualifiers_json")
