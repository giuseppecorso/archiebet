"""account fields (D162): display name and email

Revision ID: d4a6c8e0f235
Revises: c3f5a7b9d124
Create Date: 2026-10-29 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4a6c8e0f235"
down_revision: str | None = "c3f5a7b9d124"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("display_name", sa.String(length=60), nullable=True))
        batch.add_column(sa.Column("email", sa.String(length=120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email")
        batch.drop_column("display_name")
