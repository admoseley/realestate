"""Baseline schema: reports, property_deals, and jobs.

Recreates the tables previously built by ``Base.metadata.create_all`` and adds
``jobs`` (job progress used to be held in memory). There was no production data
to carry over: the previous host kept SQLite on ephemeral disk.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("property_count", sa.Integer(), nullable=True),
        sa.Column("buy_count", sa.Integer(), nullable=True),
        sa.Column("consider_count", sa.Integer(), nullable=True),
        sa.Column("no_buy_count", sa.Integer(), nullable=True),
        sa.Column("watch_count", sa.Integer(), nullable=True),
        sa.Column("perfect_count", sa.Integer(), nullable=True),
        sa.Column("avoid_count", sa.Integer(), nullable=True),
        sa.Column("pdf_path", sa.String(length=500), nullable=True),
        sa.Column("deals_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reports_id"), "reports", ["id"], unique=False)

    op.create_table(
        "property_deals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("municipality", sa.String(length=200), nullable=True),
        sa.Column("deal_json", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
        sa.Column("pdf_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_property_deals_id"), "property_deals", ["id"], unique=False)
    op.create_index(op.f("ix_property_deals_sale_id"), "property_deals", ["sale_id"], unique=True)

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_index(op.f("ix_property_deals_sale_id"), table_name="property_deals")
    op.drop_index(op.f("ix_property_deals_id"), table_name="property_deals")
    op.drop_table("property_deals")
    op.drop_index(op.f("ix_reports_id"), table_name="reports")
    op.drop_table("reports")
