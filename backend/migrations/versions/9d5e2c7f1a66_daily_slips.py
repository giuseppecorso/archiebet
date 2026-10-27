"""daily slips (D153): the board of slips published by Archie

Revision ID: 9d5e2c7f1a66
Revises: 8c4f1a2b3d55
Create Date: 2026-10-28 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d5e2c7f1a66"
down_revision: str | None = "8c4f1a2b3d55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_slips",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("legs", sa.JSON(), nullable=False),
        sa.Column("total_odds", sa.Float(), nullable=False),
        sa.Column("win_probability", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_slips")),
        sa.UniqueConstraint("kind", "period", name="uq_daily_slips_kind_period"),
    )


def downgrade() -> None:
    op.drop_table("daily_slips")
