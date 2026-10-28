"""ArchieCoins and Premium (D159)

Revision ID: c3f5a7b9d124
Revises: b2e4d6f8a013
Create Date: 2026-10-28 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3f5a7b9d124"
down_revision: str | None = "b2e4d6f8a013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("premium_paid_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "coin_redemptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("coins", sa.Integer(), nullable=False),
        sa.Column("what", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_coin_redemptions_user_id", "coin_redemptions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_coin_redemptions_user_id", table_name="coin_redemptions")
    op.drop_table("coin_redemptions")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("premium_paid_until")
