"""add scoped_tokens table

Revision ID: b03d8c407546
Revises: e2819226286e
Create Date: 2026-03-12 15:00:27.709820
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b03d8c407546'
down_revision: Union[str, None] = 'e2819226286e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scoped_tokens",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("token_prefix", sa.String(12), nullable=False),
        sa.Column("label", sa.String(255), nullable=False, server_default=""),
        sa.Column(
            "resource_type",
            sa.Enum("notebook", "entry", name="scoped_token_resource_type"),
            nullable=False,
        ),
        sa.Column("resource_id", sa.String(32), nullable=False, index=True),
        sa.Column(
            "access_level",
            sa.Enum("read", "readwrite", name="scoped_token_access"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("scoped_tokens")
