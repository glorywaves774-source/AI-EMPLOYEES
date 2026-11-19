"""Persist specialist steps for asynchronous team orchestration.

Revision ID: 0003_team_execution_steps
Revises: 0002_team_orchestration
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_team_execution_steps"
down_revision = "0002_team_orchestration"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("team_executions", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_team_execution_tenant_id", ["tenant_id", "id"])
    op.create_table(
        "team_execution_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("team_execution_id", sa.Integer(), nullable=False),
        sa.Column("step_key", sa.String(length=40), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("employee_name", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("depends_on_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("result_text", sa.Text(), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["ai_employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id", "team_execution_id"], ["team_executions.tenant_id", "team_executions.id"], ondelete="CASCADE", name="fk_team_step_execution_tenant"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "team_execution_id", "step_key", name="uq_team_step_key"),
    )
    op.create_index("ix_team_execution_steps_tenant_id", "team_execution_steps", ["tenant_id"])
    op.create_index("ix_team_execution_steps_team_execution_id", "team_execution_steps", ["team_execution_id"])
    op.create_index("ix_team_execution_steps_status", "team_execution_steps", ["status"])


def downgrade():
    op.drop_index("ix_team_execution_steps_status", table_name="team_execution_steps")
    op.drop_index("ix_team_execution_steps_team_execution_id", table_name="team_execution_steps")
    op.drop_index("ix_team_execution_steps_tenant_id", table_name="team_execution_steps")
    op.drop_table("team_execution_steps")
    with op.batch_alter_table("team_executions", schema=None) as batch_op:
        batch_op.drop_constraint("uq_team_execution_tenant_id", type_="unique")
