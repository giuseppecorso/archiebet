"""system bets (D157): "k su n" on a bet

Revision ID: a1f3c5e7b902
Revises: 9d5e2c7f1a66
Create Date: 2026-10-28 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1f3c5e7b902"
down_revision: str | None = "9d5e2c7f1a66"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("bets") as batch:
        batch.add_column(sa.Column("system", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bets") as batch:
        batch.drop_column("system")
