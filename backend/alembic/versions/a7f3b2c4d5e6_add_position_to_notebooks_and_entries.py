"""add position to notebooks and entries

Revision ID: a7f3b2c4d5e6
Revises: 3c1a6f9b1d2e
Create Date: 2026-04-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7f3b2c4d5e6'
down_revision: Union[str, None] = '3c1a6f9b1d2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    notebook_columns = {c["name"] for c in inspector.get_columns("notebooks")}
    if "position" not in notebook_columns:
        with op.batch_alter_table("notebooks") as batch_op:
            batch_op.add_column(sa.Column("position", sa.Integer(), nullable=False, server_default="0"))
        # Initialise positions from creation order
        op.execute(
            sa.text(
                "UPDATE notebooks SET position = ("
                "  SELECT COUNT(*) FROM notebooks AS n2"
                "  WHERE n2.created_at < notebooks.created_at"
                "    AND n2.author_id = notebooks.author_id"
                ")"
            )
        )
        with op.batch_alter_table("notebooks") as batch_op:
            batch_op.alter_column("position", server_default=None)

    entry_columns = {c["name"] for c in inspector.get_columns("entries")}
    if "position" not in entry_columns:
        with op.batch_alter_table("entries") as batch_op:
            batch_op.add_column(sa.Column("position", sa.Integer(), nullable=False, server_default="0"))
        # Initialise positions from creation order
        op.execute(
            sa.text(
                "UPDATE entries SET position = ("
                "  SELECT COUNT(*) FROM entries AS e2"
                "  WHERE e2.created_at < entries.created_at"
                "    AND e2.notebook_id = entries.notebook_id"
                ")"
            )
        )
        with op.batch_alter_table("entries") as batch_op:
            batch_op.alter_column("position", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    entry_columns = {c["name"] for c in inspector.get_columns("entries")}
    if "position" in entry_columns:
        with op.batch_alter_table("entries") as batch_op:
            batch_op.drop_column("position")

    notebook_columns = {c["name"] for c in inspector.get_columns("notebooks")}
    if "position" in notebook_columns:
        with op.batch_alter_table("notebooks") as batch_op:
            batch_op.drop_column("position")
