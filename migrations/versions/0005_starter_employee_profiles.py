"""Give existing starter AI employees a full job profile.

Workspaces created before this release received the ten starter employees
with an empty description, responsibilities and skills, which left the AI
with almost nothing to work from. Only rows that are still blank are filled;
anything an owner has written is left untouched. Status is not changed.

Revision ID: 0005_starter_employee_profiles
Revises: 0004_review_recovery_controls
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_starter_employee_profiles"
down_revision = "0004_review_recovery_controls"
branch_labels = None
depends_on = None


def upgrade():
    from app.workforce.profiles import STARTER_PROFILES

    employees = sa.table(
        "ai_employees",
        sa.column("job_title", sa.String),
        sa.column("description", sa.String),
        sa.column("responsibilities_json", sa.JSON),
        sa.column("skills_json", sa.JSON),
        sa.column("is_system_template", sa.Boolean),
    )
    for title, (description, responsibilities, skills) in STARTER_PROFILES.items():
        op.execute(
            employees.update()
            .where(employees.c.is_system_template.is_(True))
            .where(employees.c.job_title == title)
            .where(sa.func.coalesce(employees.c.description, "") == "")
            .values(description=description, responsibilities_json=responsibilities, skills_json=skills)
        )


def downgrade():
    # Profile text is harmless to keep; nothing to undo.
    pass
