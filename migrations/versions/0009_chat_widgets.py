"""Customer chatbot for business websites.

Revision ID: 0009_chat_widgets
Revises: 0008_team_invitations
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_chat_widgets"
down_revision = "0008_team_invitations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_widgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("public_key", sa.String(40), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("bot_name", sa.String(60), nullable=False, server_default="Assistant"),
        sa.Column("greeting", sa.String(300), nullable=False, server_default="Hello! How can I help you today?"),
        sa.Column("contact_note", sa.String(300), nullable=False, server_default=""),
        sa.Column("brand_color", sa.String(7), nullable=False, server_default="#1a5fc2"),
        sa.Column("allowed_origins", sa.Text(), nullable=False, server_default=""),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_widgets_public_key", "chat_widgets", ["public_key"])
    op.create_table(
        "widget_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("widget_id", sa.Integer(), sa.ForeignKey("chat_widgets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(40), nullable=False),
        sa.Column("question", sa.String(1000), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("origin", sa.String(200), nullable=False, server_default=""),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_widget_messages_tenant_id", "widget_messages", ["tenant_id"])
    op.create_index("ix_widget_messages_widget_id", "widget_messages", ["widget_id"])
    op.create_index("ix_widget_messages_session_id", "widget_messages", ["session_id"])
    op.create_index("ix_widget_messages_created_at", "widget_messages", ["created_at"])


def downgrade():
    op.drop_table("widget_messages")
    op.drop_table("chat_widgets")
