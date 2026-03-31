"""add entry version for optimistic concurrency

Revision ID: 3c1a6f9b1d2e
Revises: b03d8c407546
Create Date: 2026-03-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c1a6f9b1d2e'
down_revision: Union[str, None] = 'b03d8c407546'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    entry_columns = {c["name"] for c in inspector.get_columns("entries")}
    if "version" not in entry_columns:
        with op.batch_alter_table("entries") as batch_op:
            batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    # Keep default handling in the ORM model; no DB-level server default needed.
    with op.batch_alter_table("entries") as batch_op:
        batch_op.alter_column("version", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    entry_columns = {c["name"] for c in inspector.get_columns("entries")}
    if "version" in entry_columns:
        with op.batch_alter_table("entries") as batch_op:
            batch_op.drop_column("version")
