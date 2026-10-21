"""radar signals: strategy found by Archie (D118)

Revision ID: 5c1f0a9d7e21
Revises: 28d81e7b3dac
Create Date: 2026-10-21 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5c1f0a9d7e21"
down_revision: str | None = "28d81e7b3dac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("radar_signals") as batch_op:
        batch_op.add_column(sa.Column("strategy", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("radar_signals") as batch_op:
        batch_op.drop_column("strategy")
