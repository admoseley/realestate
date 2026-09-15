"""Add jobs.kind, so one type of job (shares) can be counted for rate limiting.

Revision ID: 0002_job_kind
Revises: 0001_baseline
Create Date: 2026-09-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_job_kind"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows stay NULL: they predate kinds and no limit counts them.
    # No index: the table grows by a few dozen rows a day, so counting a
    # rolling hour stays cheap without one.
    op.add_column("jobs", sa.Column("kind", sa.String(length=30), nullable=True))


def downgrade() -> None:
    # Batch mode, because SQLite can't drop columns with a plain ALTER TABLE.
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_column("kind")
