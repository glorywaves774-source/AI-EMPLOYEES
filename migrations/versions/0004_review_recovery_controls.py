"""Add human review decisions and bounded team recovery metadata.

Revision ID: 0004_review_recovery_controls
Revises: 0003_team_execution_steps
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_review_recovery_controls"
down_revision = "0003_team_execution_steps"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("team_executions") as batch_op:
        batch_op.add_column(sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("review_decision", sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column("review_note", sa.String(length=1000), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("recovery_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.create_foreign_key("fk_team_execution_reviewed_by", "users", ["reviewed_by_user_id"], ["id"], ondelete="SET NULL")


def downgrade():
    with op.batch_alter_table("team_executions") as batch_op:
        batch_op.drop_constraint("fk_team_execution_reviewed_by", type_="foreignkey")
        batch_op.drop_column("recovery_count")
        batch_op.drop_column("review_note")
        batch_op.drop_column("review_decision")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by_user_id")
