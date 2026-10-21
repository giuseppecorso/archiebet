"""match events (D133): live score commentary with scorers, cards and substitutions

Revision ID: 7b3e9d2c4a10
Revises: 5c1f0a9d7e21
Create Date: 2026-10-21 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b3e9d2c4a10"
down_revision: str | None = "5c1f0a9d7e21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "match_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=True),
        sa.Column("extra", sa.Integer(), nullable=True),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("player", sa.String(length=80), nullable=True),
        sa.Column("other", sa.String(length=80), nullable=True),
        sa.Column("detail", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], name=op.f("fk_match_events_match_id_matches"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_events")),
    )
    op.create_index("ix_match_events_match", "match_events", ["match_id", "seq"])
    with op.batch_alter_table("matches") as batch_op:
        batch_op.add_column(sa.Column("events_synced_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("matches") as batch_op:
        batch_op.drop_column("events_synced_at")
    op.drop_index("ix_match_events_match", table_name="match_events")
    op.drop_table("match_events")
