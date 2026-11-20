"""Charts, presentations and graphics generated from assignments.

Revision ID: 0006_generated_assets
Revises: 0005_starter_employee_profiles
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_generated_assets"
down_revision = "0005_starter_employee_profiles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "generated_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("workforce_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("style", sa.String(20), nullable=False, server_default=""),
        sa.Column("brief", sa.String(1000), nullable=False, server_default=""),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("error_message", sa.String(500), nullable=False, server_default=""),
        sa.Column("storage_key", sa.String(64)),
        sa.Column("mime_type", sa.String(120), nullable=False, server_default=""),
        sa.Column("filename", sa.String(200), nullable=False, server_default=""),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_generated_assets_tenant_id", "generated_assets", ["tenant_id"])
    op.create_index("ix_generated_assets_task_id", "generated_assets", ["task_id"])
    op.create_index("ix_generated_assets_status", "generated_assets", ["status"])
    op.create_index("ix_generated_assets_created_at", "generated_assets", ["created_at"])


def downgrade():
    op.drop_table("generated_assets")
