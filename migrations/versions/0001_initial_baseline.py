"""Frozen initial schema for AI Workforce Milestone 12.

This migration is intentionally a fixed snapshot. Do not import application
models or use metadata.create_all() here: later model changes belong in a new
revision and must never alter the behavior of this historical migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
        op.create_table('billing_webhook_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('event_id', sa.String(length=255), nullable=False),
        sa.Column('event_type', sa.String(length=120), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('payload_hash', sa.String(length=128), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'event_id', name='uq_billing_webhook_provider_event')
        )
        op.create_table('permissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_permissions_code'), 'permissions', ['code'], unique=True)
        op.create_table('platform_admins',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=160), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed_login_attempts', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('mfa_enabled', sa.Boolean(), nullable=False),
        sa.Column('mfa_secret', sa.String(length=64), nullable=True),
        sa.Column('mfa_recovery_codes_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_platform_admins_email'), 'platform_admins', ['email'], unique=True)
        op.create_table('subscription_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False),
        sa.Column('billing_interval', sa.String(length=20), nullable=False),
        sa.Column('trial_days', sa.Integer(), nullable=False),
        sa.Column('max_ai_employees', sa.Integer(), nullable=False),
        sa.Column('monthly_task_limit', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_subscription_plans_code'), 'subscription_plans', ['code'], unique=True)
        op.create_table('tenants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('slug', sa.String(length=180), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_tenants_slug'), 'tenants', ['slug'], unique=True)
        op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=160), nullable=False),
        sa.Column('is_active_account', sa.Boolean(), nullable=False),
        sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed_login_attempts', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('mfa_enabled', sa.Boolean(), nullable=False),
        sa.Column('mfa_secret', sa.String(length=64), nullable=True),
        sa.Column('mfa_recovery_codes_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
        op.create_table('audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('target_type', sa.String(length=80), nullable=True),
        sa.Column('target_id', sa.String(length=80), nullable=True),
        sa.Column('details_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_audit_logs_tenant_id'), 'audit_logs', ['tenant_id'], unique=False)
        op.create_table('departments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_department_tenant_name')
        )
        op.create_index(op.f('ix_departments_tenant_id'), 'departments', ['tenant_id'], unique=False)
        op.create_table('integration_connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=40), nullable=False),
        sa.Column('display_name', sa.String(length=120), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('scopes_json', sa.JSON(), nullable=False),
        sa.Column('credential_ciphertext', sa.Text(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'provider', 'display_name', name='uq_integration_tenant_provider_name')
        )
        op.create_index(op.f('ix_integration_connections_provider'), 'integration_connections', ['provider'], unique=False)
        op.create_index(op.f('ix_integration_connections_tenant_id'), 'integration_connections', ['tenant_id'], unique=False)
        op.create_table('knowledge_repositories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.String(length=600), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_knowledge_repo_tenant_name')
        )
        op.create_index(op.f('ix_knowledge_repositories_tenant_id'), 'knowledge_repositories', ['tenant_id'], unique=False)
        op.create_table('notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=180), nullable=False),
        sa.Column('message', sa.String(length=1000), nullable=False),
        sa.Column('category', sa.String(length=40), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_notifications_tenant_id'), 'notifications', ['tenant_id'], unique=False)
        op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
        op.create_table('platform_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('platform_admin_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('target_type', sa.String(length=80), nullable=True),
        sa.Column('target_id', sa.String(length=80), nullable=True),
        sa.Column('details_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['platform_admin_id'], ['platform_admins.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_table('role_permissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('permission_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('role', 'permission_id', name='uq_role_permission')
        )
        op.create_index(op.f('ix_role_permissions_permission_id'), 'role_permissions', ['permission_id'], unique=False)
        op.create_index(op.f('ix_role_permissions_role'), 'role_permissions', ['role'], unique=False)
        op.create_table('security_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('platform_admin_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(length=80), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('details_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['platform_admin_id'], ['platform_admins.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_security_events_created_at'), 'security_events', ['created_at'], unique=False)
        op.create_index(op.f('ix_security_events_event_type'), 'security_events', ['event_type'], unique=False)
        op.create_index(op.f('ix_security_events_platform_admin_id'), 'security_events', ['platform_admin_id'], unique=False)
        op.create_index(op.f('ix_security_events_request_id'), 'security_events', ['request_id'], unique=False)
        op.create_index(op.f('ix_security_events_severity'), 'security_events', ['severity'], unique=False)
        op.create_index(op.f('ix_security_events_tenant_id'), 'security_events', ['tenant_id'], unique=False)
        op.create_index(op.f('ix_security_events_user_id'), 'security_events', ['user_id'], unique=False)
        op.create_table('security_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=128), nullable=False),
        sa.Column('token_type', sa.String(length=32), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_security_tokens_token_hash'), 'security_tokens', ['token_hash'], unique=True)
        op.create_index(op.f('ix_security_tokens_token_type'), 'security_tokens', ['token_type'], unique=False)
        op.create_index(op.f('ix_security_tokens_user_id'), 'security_tokens', ['user_id'], unique=False)
        op.create_table('subscription_change_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('requested_by_user_id', sa.Integer(), nullable=True),
        sa.Column('current_plan_id', sa.Integer(), nullable=True),
        sa.Column('requested_plan_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('notes', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['current_plan_id'], ['subscription_plans.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['requested_plan_id'], ['subscription_plans.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_subscription_change_requests_status'), 'subscription_change_requests', ['status'], unique=False)
        op.create_index(op.f('ix_subscription_change_requests_tenant_id'), 'subscription_change_requests', ['tenant_id'], unique=False)
        op.create_table('tenant_memberships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'user_id', name='uq_tenant_user')
        )
        op.create_index(op.f('ix_tenant_memberships_tenant_id'), 'tenant_memberships', ['tenant_id'], unique=False)
        op.create_index(op.f('ix_tenant_memberships_user_id'), 'tenant_memberships', ['user_id'], unique=False)
        op.create_table('tenant_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False),
        sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('provider_customer_id', sa.String(length=180), nullable=True),
        sa.Column('provider_subscription_id', sa.String(length=180), nullable=True),
        sa.Column('provider_metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['subscription_plans.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_tenant_subscriptions_status'), 'tenant_subscriptions', ['status'], unique=False)
        op.create_index(op.f('ix_tenant_subscriptions_tenant_id'), 'tenant_subscriptions', ['tenant_id'], unique=True)
        op.create_table('workforce_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=180), nullable=False),
        sa.Column('instructions', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('final_output', sa.Text(), nullable=False),
        sa.Column('error_message', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_workforce_tasks_status'), 'workforce_tasks', ['status'], unique=False)
        op.create_index(op.f('ix_workforce_tasks_tenant_id'), 'workforce_tasks', ['tenant_id'], unique=False)
        op.create_table('ai_employees',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('job_title', sa.String(length=120), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=False),
        sa.Column('responsibilities_json', sa.JSON(), nullable=False),
        sa.Column('skills_json', sa.JSON(), nullable=False),
        sa.Column('instructions', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('is_system_template', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_ai_employees_department_id'), 'ai_employees', ['department_id'], unique=False)
        op.create_index(op.f('ix_ai_employees_tenant_id'), 'ai_employees', ['tenant_id'], unique=False)
        op.create_table('approval_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('requested_by_user_id', sa.Integer(), nullable=True),
        sa.Column('decided_by_user_id', sa.Integer(), nullable=True),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('action_type', sa.String(length=80), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('decision_note', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['decided_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['task_id'], ['workforce_tasks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_approval_requests_status'), 'approval_requests', ['status'], unique=False)
        op.create_index(op.f('ix_approval_requests_task_id'), 'approval_requests', ['task_id'], unique=False)
        op.create_index(op.f('ix_approval_requests_tenant_id'), 'approval_requests', ['tenant_id'], unique=False)
        op.create_table('invoices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=True),
        sa.Column('invoice_number', sa.String(length=80), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pdf_url', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['subscription_id'], ['tenant_subscriptions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_invoices_invoice_number'), 'invoices', ['invoice_number'], unique=True)
        op.create_index(op.f('ix_invoices_tenant_id'), 'invoices', ['tenant_id'], unique=False)
        op.create_table('knowledge_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('storage_key', sa.String(length=64), nullable=False),
        sa.Column('mime_type', sa.String(length=120), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('extracted_chars', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['repository_id'], ['knowledge_repositories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('storage_key')
        )
        op.create_index(op.f('ix_knowledge_documents_repository_id'), 'knowledge_documents', ['repository_id'], unique=False)
        op.create_index(op.f('ix_knowledge_documents_sha256'), 'knowledge_documents', ['sha256'], unique=False)
        op.create_index(op.f('ix_knowledge_documents_status'), 'knowledge_documents', ['status'], unique=False)
        op.create_index(op.f('ix_knowledge_documents_tenant_id'), 'knowledge_documents', ['tenant_id'], unique=False)
        op.create_table('payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=True),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('provider_reference', sa.String(length=180), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('invoice_number', sa.String(length=80), nullable=True),
        sa.Column('receipt_url', sa.String(length=500), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('refunded_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('refunded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['subscription_id'], ['tenant_subscriptions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('invoice_number')
        )
        op.create_index(op.f('ix_payments_provider_reference'), 'payments', ['provider_reference'], unique=True)
        op.create_index(op.f('ix_payments_status'), 'payments', ['status'], unique=False)
        op.create_index(op.f('ix_payments_subscription_id'), 'payments', ['subscription_id'], unique=False)
        op.create_index(op.f('ix_payments_tenant_id'), 'payments', ['tenant_id'], unique=False)
        op.create_table('agent_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('sender_employee_id', sa.Integer(), nullable=True),
        sa.Column('recipient_employee_id', sa.Integer(), nullable=True),
        sa.Column('message_type', sa.String(length=32), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['recipient_employee_id'], ['ai_employees.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sender_employee_id'], ['ai_employees.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['task_id'], ['workforce_tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_agent_messages_task_id'), 'agent_messages', ['task_id'], unique=False)
        op.create_index(op.f('ix_agent_messages_tenant_id'), 'agent_messages', ['tenant_id'], unique=False)
        op.create_table('agent_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=True),
        sa.Column('employee_name', sa.String(length=120), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('input_text', sa.Text(), nullable=False),
        sa.Column('output_text', sa.Text(), nullable=False),
        sa.Column('error_message', sa.String(length=500), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['employee_id'], ['ai_employees.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['task_id'], ['workforce_tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_agent_runs_task_id'), 'agent_runs', ['task_id'], unique=False)
        op.create_index(op.f('ix_agent_runs_tenant_id'), 'agent_runs', ['tenant_id'], unique=False)
        op.create_table('ai_employee_knowledge_permissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('granted_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['ai_employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['granted_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['repository_id'], ['knowledge_repositories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'employee_id', 'repository_id', name='uq_employee_knowledge_repository')
        )
        op.create_index(op.f('ix_ai_employee_knowledge_permissions_employee_id'), 'ai_employee_knowledge_permissions', ['employee_id'], unique=False)
        op.create_index(op.f('ix_ai_employee_knowledge_permissions_repository_id'), 'ai_employee_knowledge_permissions', ['repository_id'], unique=False)
        op.create_index(op.f('ix_ai_employee_knowledge_permissions_tenant_id'), 'ai_employee_knowledge_permissions', ['tenant_id'], unique=False)
        op.create_table('knowledge_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['knowledge_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id', 'chunk_index', name='uq_knowledge_chunk_document_index')
        )
        op.create_index(op.f('ix_knowledge_chunks_document_id'), 'knowledge_chunks', ['document_id'], unique=False)
        op.create_index(op.f('ix_knowledge_chunks_tenant_id'), 'knowledge_chunks', ['tenant_id'], unique=False)
        # ### end Alembic commands ###


def downgrade():
    # This is the historical foundation migration. A blanket downgrade could
    # destroy tenant data; restore a verified backup or use a reviewed forward
    # migration instead.
    raise RuntimeError(
        "The initial AI Workforce baseline is intentionally non-reversible. "
        "Restore a verified backup or use a reviewed forward migration."
    )
