"""daily bets (D192): every Daily slip is played automatically for every user

Revision ID: e5b7d9f1a346
Revises: d4a6c8e0f235
Create Date: 2026-11-10 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5b7d9f1a346"
down_revision: str | None = "d4a6c8e0f235"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("bets") as batch:
        batch.add_column(sa.Column("daily_slip_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_bets_daily_slip_id", "daily_slips", ["daily_slip_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_bets_daily_slip_id", ["daily_slip_id"])


def downgrade() -> None:
    with op.batch_alter_table("bets") as batch:
        batch.drop_index("ix_bets_daily_slip_id")
        batch.drop_constraint("fk_bets_daily_slip_id", type_="foreignkey")
        batch.drop_column("daily_slip_id")
