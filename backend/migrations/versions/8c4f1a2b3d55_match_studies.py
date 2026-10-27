"""match studies (D137): Archie's study of each upcoming match

Revision ID: 8c4f1a2b3d55
Revises: 7b3e9d2c4a10
Create Date: 2026-10-27 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c4f1a2b3d55"
down_revision: str | None = "7b3e9d2c4a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "match_studies",
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], name=op.f("fk_match_studies_match_id_matches"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("match_id", name=op.f("pk_match_studies")),
    )


def downgrade() -> None:
    op.drop_table("match_studies")
