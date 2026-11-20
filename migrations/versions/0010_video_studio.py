"""Video studio: social media editor, AI video generation, add-on clip packs.

Revision ID: 0010_video_studio
Revises: 0009_chat_widgets
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_video_studio"
down_revision = "0009_chat_widgets"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "video_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("mode", sa.String(12), nullable=False),
        sa.Column("title", sa.String(180), nullable=False, server_default=""),
        sa.Column("brief", sa.String(2000), nullable=False, server_default=""),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("source_key", sa.String(64)),
        sa.Column("source_filename", sa.String(200), nullable=False, server_default=""),
        sa.Column("source_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("progress", sa.String(120), nullable=False, server_default=""),
        sa.Column("error_message", sa.String(500), nullable=False, server_default=""),
        sa.Column("uses_pack", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_video_projects_tenant_id", "video_projects", ["tenant_id"])
    op.create_index("ix_video_projects_status", "video_projects", ["status"])
    op.create_index("ix_video_projects_created_at", "video_projects", ["created_at"])
    op.create_table(
        "video_outputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("video_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False, server_default=""),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("post_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("start_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("storage_key", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_video_outputs_tenant_id", "video_outputs", ["tenant_id"])
    op.create_index("ix_video_outputs_project_id", "video_outputs", ["project_id"])
    op.create_table(
        "video_credits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clips", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_video_credits_tenant_id", "video_credits", ["tenant_id"])


def downgrade():
    op.drop_table("video_credits")
    op.drop_table("video_outputs")
    op.drop_table("video_projects")
