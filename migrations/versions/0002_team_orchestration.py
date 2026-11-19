"""Add durable team execution and tenant-safe task dependencies.

Revision ID: 0002_team_orchestration
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_team_orchestration"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    # The composite unique key must exist before tables add composite tenant/task
    # foreign keys. Batch mode works on SQLite and PostgreSQL.
    with op.batch_alter_table("workforce_tasks", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_workforce_task_tenant_id", ["tenant_id", "id"]
        )

    op.create_table(
        "team_executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("plan_json", sa.JSON(), nullable=False),
        sa.Column("max_parallelism", sa.Integer(), nullable=False),
        sa.Column("token_budget", sa.Integer(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("cost_budget_usd", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("cost_used_usd", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["workforce_tasks.tenant_id", "workforce_tasks.id"],
            name="fk_team_execution_tenant_task", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "task_id", name="uq_team_execution_tenant_task"),
    )
    op.create_index("ix_team_executions_status", "team_executions", ["status"])
    op.create_index("ix_team_executions_task_id", "team_executions", ["task_id"])
    op.create_index("ix_team_executions_tenant_id", "team_executions", ["tenant_id"])

    op.create_table(
        "workforce_task_dependencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("depends_on_task_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("task_id <> depends_on_task_id", name="ck_task_dependency_not_self"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "depends_on_task_id"],
            ["workforce_tasks.tenant_id", "workforce_tasks.id"],
            name="fk_task_dependency_parent_tenant", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["workforce_tasks.tenant_id", "workforce_tasks.id"],
            name="fk_task_dependency_task_tenant", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "task_id", "depends_on_task_id", name="uq_task_dependency_edge"),
    )
    op.create_index("ix_workforce_task_dependencies_depends_on_task_id", "workforce_task_dependencies", ["depends_on_task_id"])
    op.create_index("ix_workforce_task_dependencies_task_id", "workforce_task_dependencies", ["task_id"])
    op.create_index("ix_workforce_task_dependencies_tenant_id", "workforce_task_dependencies", ["tenant_id"])


def downgrade():
    op.drop_index("ix_workforce_task_dependencies_tenant_id", table_name="workforce_task_dependencies")
    op.drop_index("ix_workforce_task_dependencies_task_id", table_name="workforce_task_dependencies")
    op.drop_index("ix_workforce_task_dependencies_depends_on_task_id", table_name="workforce_task_dependencies")
    op.drop_table("workforce_task_dependencies")
    op.drop_index("ix_team_executions_tenant_id", table_name="team_executions")
    op.drop_index("ix_team_executions_task_id", table_name="team_executions")
    op.drop_index("ix_team_executions_status", table_name="team_executions")
    op.drop_table("team_executions")
    with op.batch_alter_table("workforce_tasks", schema=None) as batch_op:
        batch_op.drop_constraint("uq_workforce_task_tenant_id", type_="unique")
