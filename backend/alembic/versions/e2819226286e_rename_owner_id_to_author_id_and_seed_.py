"""rename_owner_id_to_author_id_and_seed_owner_permissions

Revision ID: e2819226286e
Revises: cd74e2f1f38c
Create Date: 2026-03-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2819226286e'
down_revision: Union[str, None] = 'cd74e2f1f38c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename owner_id → author_id on notebooks table
    # SQLite doesn't support ALTER COLUMN RENAME natively before 3.25,
    # but Alembic's batch mode handles it.
    with op.batch_alter_table("notebooks") as batch_op:
        batch_op.alter_column("owner_id", new_column_name="author_id")

    # Update any existing 'admin' access_level values to 'owner'
    # (SQLite stores enums as text, so this is a simple UPDATE)
    op.execute("UPDATE permissions SET access_level = 'owner' WHERE access_level = 'admin'")

    # Seed owner permissions for existing notebooks that don't have one
    op.execute("""
        INSERT INTO permissions (subject_id, resource_type, resource_id, access_level, created_at)
        SELECT n.author_id, 'notebook', n.id, 'owner', n.created_at
        FROM notebooks n
        WHERE NOT EXISTS (
            SELECT 1 FROM permissions p
            WHERE p.resource_type = 'notebook'
              AND p.resource_id = n.id
              AND p.subject_id = n.author_id
              AND p.access_level = 'owner'
        )
    """)


def downgrade() -> None:
    with op.batch_alter_table("notebooks") as batch_op:
        batch_op.alter_column("author_id", new_column_name="owner_id")

    op.execute("UPDATE permissions SET access_level = 'admin' WHERE access_level = 'owner'")
