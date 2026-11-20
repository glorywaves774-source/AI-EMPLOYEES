"""Recurring assignments.

Revision ID: 0007_recurring_assignments
Revises: 0006_generated_assets
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_recurring_assignments"
down_revision = "0006_generated_assets"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "recurring_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("frequency", sa.String(12), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("day_of_month", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("hour", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_task_id", sa.Integer()),
        sa.Column("last_error", sa.String(300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_recurring_assignments_tenant_id", "recurring_assignments", ["tenant_id"])
    op.create_index("ix_recurring_assignments_active", "recurring_assignments", ["active"])
    op.create_index("ix_recurring_assignments_next_run_at", "recurring_assignments", ["next_run_at"])


def downgrade():
    op.drop_table("recurring_assignments")
