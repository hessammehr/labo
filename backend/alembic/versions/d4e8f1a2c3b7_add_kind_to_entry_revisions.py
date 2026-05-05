"""add kind to entry_revisions and clear change_summary

Introduces a first-class ``kind`` column on ``entry_revisions`` so that
behaviour can branch on a typed enum rather than the free-form
``change_summary`` string. The closed historical vocabulary maps cleanly:

    "Auto checkpoint"   -> "auto"
    "Before restore"    -> "before_restore"
    anything else       -> "manual"

After backfilling ``kind``, ``change_summary`` is reset to "" everywhere.
From this point on it is reserved for free-form user notes; system code
must not put sentinel strings into it.

Revision ID: d4e8f1a2c3b7
Revises: a7f3b2c4d5e6
Create Date: 2026-05-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e8f1a2c3b7"
down_revision: Union[str, None] = "a7f3b2c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REVISION_KIND = sa.Enum("manual", "auto", "before_restore", name="revision_kind")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("entry_revisions")}

    # On Postgres the named ENUM type must exist before columns reference it.
    # On SQLite this is a no-op.
    REVISION_KIND.create(bind, checkfirst=True)

    if "kind" not in columns:
        with op.batch_alter_table("entry_revisions") as batch_op:
            # Add as nullable first so the ALTER succeeds on a non-empty table,
            # then backfill, then tighten to NOT NULL.
            batch_op.add_column(sa.Column("kind", REVISION_KIND, nullable=True))

    # Backfill kind from the historical change_summary vocabulary.
    op.execute(
        "UPDATE entry_revisions SET kind = 'auto' "
        "WHERE kind IS NULL AND change_summary = 'Auto checkpoint'"
    )
    op.execute(
        "UPDATE entry_revisions SET kind = 'before_restore' "
        "WHERE kind IS NULL AND change_summary = 'Before restore'"
    )
    op.execute(
        "UPDATE entry_revisions SET kind = 'manual' WHERE kind IS NULL"
    )

    with op.batch_alter_table("entry_revisions") as batch_op:
        batch_op.alter_column("kind", existing_type=REVISION_KIND, nullable=False)

    # Reset change_summary now that kind carries the type information.
    # change_summary is from this point on a free-form user-note field.
    op.execute("UPDATE entry_revisions SET change_summary = ''")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("entry_revisions")}
    if "kind" in columns:
        with op.batch_alter_table("entry_revisions") as batch_op:
            batch_op.drop_column("kind")
    REVISION_KIND.drop(bind, checkfirst=True)
