"""Team invitations.

Revision ID: 0008_team_invitations
Revises: 0007_recurring_assignments
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_team_invitations"
down_revision = "0007_recurring_assignments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "team_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_team_invitations_tenant_id", "team_invitations", ["tenant_id"])
    op.create_index("ix_team_invitations_email", "team_invitations", ["email"])


def downgrade():
    op.drop_table("team_invitations")
