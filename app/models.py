from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, ForeignKeyConstraint
from flask_login import UserMixin
from .extensions import db, login_manager

def utcnow():
    return datetime.now(timezone.utc)

class Tenant(db.Model):
    __tablename__ = "tenants"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)
    status = db.Column(db.String(24), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    memberships = db.relationship("TenantMembership", back_populates="tenant", cascade="all, delete-orphan")

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(160), nullable=False)
    is_active_account = db.Column(db.Boolean, nullable=False, default=True)
    email_verified_at = db.Column(db.DateTime(timezone=True))
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
    mfa_enabled = db.Column(db.Boolean, nullable=False, default=False)
    mfa_secret = db.Column(db.String(64))
    mfa_recovery_codes_json = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    memberships = db.relationship("TenantMembership", back_populates="user", cascade="all, delete-orphan")

    @property
    def is_active(self):
        return self.is_active_account


class SecurityToken(db.Model):
    __tablename__ = "security_tokens"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = db.Column(db.String(128), unique=True, nullable=False, index=True)
    token_type = db.Column(db.String(32), nullable=False, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class Permission(db.Model):
    __tablename__ = "permissions"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=False, default="")


class RolePermission(db.Model):
    __tablename__ = "role_permissions"
    __table_args__ = (db.UniqueConstraint("role", "permission_id", name="uq_role_permission"),)
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(32), nullable=False, index=True)
    permission_id = db.Column(db.Integer, db.ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True)


class TenantMembership(db.Model):
    __tablename__ = "tenant_memberships"
    __table_args__ = (db.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user"),)
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = db.Column(db.String(32), nullable=False, default="owner")
    status = db.Column(db.String(24), nullable=False, default="active")
    tenant = db.relationship("Tenant", back_populates="memberships")
    user = db.relationship("User", back_populates="memberships")

class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(80))
    target_id = db.Column(db.String(80))
    details_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


class Department(db.Model):
    __tablename__ = "departments"
    __table_args__ = (db.UniqueConstraint("tenant_id", "name", name="uq_department_tenant_name"),)
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    employees = db.relationship("AIEmployee", back_populates="department")

class AIEmployee(db.Model):
    __tablename__ = "ai_employees"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    job_title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(1000), nullable=False, default="")
    responsibilities_json = db.Column(db.JSON, nullable=False, default=list)
    skills_json = db.Column(db.JSON, nullable=False, default=list)
    instructions = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(24), nullable=False, default="draft")
    is_system_template = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    department = db.relationship("Department", back_populates="employees")

class GeneratedAsset(db.Model):
    """A chart, presentation or graphic made from a finished assignment. Stored encrypted; draft until reviewed."""
    __tablename__ = "generated_assets"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("workforce_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)          # chart | presentation | graphic
    style = db.Column(db.String(20), nullable=False, default="")  # graphic: design | photo
    brief = db.Column(db.String(1000), nullable=False, default="")
    title = db.Column(db.String(200), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="queued", index=True)  # queued|running|ready|failed
    error_message = db.Column(db.String(500), nullable=False, default="")
    storage_key = db.Column(db.String(64))
    mime_type = db.Column(db.String(120), nullable=False, default="")
    filename = db.Column(db.String(200), nullable=False, default="")
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    review_status = db.Column(db.String(20), nullable=False, default="pending")  # pending|approved|rejected
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = db.Column(db.DateTime(timezone=True))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    completed_at = db.Column(db.DateTime(timezone=True))


class WorkforceTask(db.Model):
    __tablename__ = "workforce_tasks"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "id", name="uq_workforce_task_tenant_id"),
    )
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = db.Column(db.String(180), nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(24), nullable=False, default="queued", index=True)
    final_output = db.Column(db.Text, nullable=False, default="")
    error_message = db.Column(db.String(500), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True))
    runs = db.relationship("AgentRun", back_populates="task", cascade="all, delete-orphan", order_by="AgentRun.created_at")

class TeamExecution(db.Model):
    """Durable coordinator-level execution record for one parent assignment."""
    __tablename__ = "team_executions"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "task_id", name="uq_team_execution_tenant_task"),
        db.UniqueConstraint("tenant_id", "id", name="uq_team_execution_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["workforce_tasks.tenant_id", "workforce_tasks.id"],
            ondelete="CASCADE", name="fk_team_execution_tenant_task",
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, nullable=False, index=True)
    task_id = db.Column(db.Integer, nullable=False, index=True)
    status = db.Column(db.String(24), nullable=False, default="planned", index=True)
    plan_json = db.Column(db.JSON, nullable=False, default=dict)
    max_parallelism = db.Column(db.Integer, nullable=False, default=3)
    token_budget = db.Column(db.Integer, nullable=False, default=12000)
    tokens_used = db.Column(db.Integer, nullable=False, default=0)
    cost_budget_usd = db.Column(db.Numeric(12, 4), nullable=True)
    cost_used_usd = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    error_message = db.Column(db.String(500), nullable=False, default="")
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True))
    review_decision = db.Column(db.String(24))
    review_note = db.Column(db.String(1000), nullable=False, default="")
    recovery_count = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    task = db.relationship("WorkforceTask", primaryjoin="and_(TeamExecution.tenant_id == WorkforceTask.tenant_id, TeamExecution.task_id == WorkforceTask.id)", foreign_keys=[tenant_id, task_id], viewonly=True)


class TeamExecutionStep(db.Model):
    """Durable specialist work unit within a coordinator-managed execution."""
    __tablename__ = "team_execution_steps"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "team_execution_id", "step_key", name="uq_team_step_key"),
        db.ForeignKeyConstraint(
            ["tenant_id", "team_execution_id"],
            ["team_executions.tenant_id", "team_executions.id"],
            ondelete="CASCADE", name="fk_team_step_execution_tenant",
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, nullable=False, index=True)
    team_execution_id = db.Column(db.Integer, nullable=False, index=True)
    step_key = db.Column(db.String(40), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True)
    employee_name = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    depends_on_json = db.Column(db.JSON, nullable=False, default=list)
    status = db.Column(db.String(24), nullable=False, default="queued", index=True)
    result_text = db.Column(db.Text, nullable=False, default="")
    error_message = db.Column(db.String(500), nullable=False, default="")
    input_tokens = db.Column(db.Integer, nullable=False, default=0)
    output_tokens = db.Column(db.Integer, nullable=False, default=0)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class WorkforceTaskDependency(db.Model):
    """Tenant-safe directed dependency edge between workforce assignments."""
    __tablename__ = "workforce_task_dependencies"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "task_id", "depends_on_task_id", name="uq_task_dependency_edge"),
        CheckConstraint("task_id <> depends_on_task_id", name="ck_task_dependency_not_self"),
        ForeignKeyConstraint(
            ["tenant_id", "task_id"],
            ["workforce_tasks.tenant_id", "workforce_tasks.id"],
            ondelete="CASCADE", name="fk_task_dependency_task_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "depends_on_task_id"],
            ["workforce_tasks.tenant_id", "workforce_tasks.id"],
            ondelete="CASCADE", name="fk_task_dependency_parent_tenant",
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, nullable=False, index=True)
    task_id = db.Column(db.Integer, nullable=False, index=True)
    depends_on_task_id = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class AgentRun(db.Model):
    __tablename__ = "agent_runs"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("workforce_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True)
    employee_name = db.Column(db.String(120), nullable=False)
    model_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="running")
    input_text = db.Column(db.Text, nullable=False)
    output_text = db.Column(db.Text, nullable=False, default="")
    error_message = db.Column(db.String(500), nullable=False, default="")
    input_tokens = db.Column(db.Integer, nullable=False, default=0)
    output_tokens = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True))
    task = db.relationship("WorkforceTask", back_populates="runs")

class AgentMessage(db.Model):
    __tablename__ = "agent_messages"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("workforce_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_employee_id = db.Column(db.Integer, db.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True)
    recipient_employee_id = db.Column(db.Integer, db.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True)
    message_type = db.Column(db.String(32), nullable=False, default="contribution")
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class ApprovalRequest(db.Model):
    __tablename__ = "approval_requests"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey("workforce_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    action_type = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(24), nullable=False, default="pending", index=True)
    decision_note = db.Column(db.String(1000), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    decided_at = db.Column(db.DateTime(timezone=True))

class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    message = db.Column(db.String(1000), nullable=False)
    category = db.Column(db.String(40), nullable=False, default="general")
    read_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class KnowledgeRepository(db.Model):
    __tablename__ = "knowledge_repositories"
    __table_args__ = (db.UniqueConstraint("tenant_id", "name", name="uq_knowledge_repo_tenant_name"),)
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(600), nullable=False, default="")
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    documents = db.relationship("KnowledgeDocument", back_populates="repository", cascade="all, delete-orphan")


class KnowledgeDocument(db.Model):
    __tablename__ = "knowledge_documents"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    repository_id = db.Column(db.Integer, db.ForeignKey("knowledge_repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(64), unique=True, nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(24), nullable=False, default="ready", index=True)
    extracted_chars = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    repository = db.relationship("KnowledgeRepository", back_populates="documents")
    chunks = db.relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan", order_by="KnowledgeChunk.chunk_index")


class KnowledgeChunk(db.Model):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (db.UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_document_index"),)
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = db.Column(db.Integer, db.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    document = db.relationship("KnowledgeDocument", back_populates="chunks")


class AIEmployeeKnowledgePermission(db.Model):
    __tablename__ = "ai_employee_knowledge_permissions"
    __table_args__ = (db.UniqueConstraint("tenant_id", "employee_id", "repository_id", name="uq_employee_knowledge_repository"),)
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("ai_employees.id", ondelete="CASCADE"), nullable=False, index=True)
    repository_id = db.Column(db.Integer, db.ForeignKey("knowledge_repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    granted_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class IntegrationConnection(db.Model):
    """Encrypted credential envelope; provider OAuth/API execution is a later integration phase."""
    __tablename__ = "integration_connections"
    __table_args__ = (db.UniqueConstraint("tenant_id", "provider", "display_name", name="uq_integration_tenant_provider_name"),)
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = db.Column(db.String(40), nullable=False, index=True)
    display_name = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="not_connected")
    scopes_json = db.Column(db.JSON, nullable=False, default=list)
    credential_ciphertext = db.Column(db.Text, nullable=False, default="")
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SubscriptionPlan(db.Model):
    __tablename__ = "subscription_plans"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(500), nullable=False, default="")
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    currency = db.Column(db.String(8), nullable=False, default="GHS")
    billing_interval = db.Column(db.String(20), nullable=False, default="monthly")
    trial_days = db.Column(db.Integer, nullable=False, default=14)
    max_ai_employees = db.Column(db.Integer, nullable=False, default=3)
    monthly_task_limit = db.Column(db.Integer, nullable=False, default=100)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class TenantSubscription(db.Model):
    __tablename__ = "tenant_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="trialing", index=True)
    trial_ends_at = db.Column(db.DateTime(timezone=True))
    current_period_start = db.Column(db.DateTime(timezone=True))
    current_period_end = db.Column(db.DateTime(timezone=True))
    cancel_at_period_end = db.Column(db.Boolean, nullable=False, default=False)
    canceled_at = db.Column(db.DateTime(timezone=True))
    provider = db.Column(db.String(20), nullable=False, default="manual")
    provider_customer_id = db.Column(db.String(180))
    provider_subscription_id = db.Column(db.String(180))
    provider_metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    tenant = db.relationship("Tenant", backref=db.backref("subscription", uselist=False))
    plan = db.relationship("SubscriptionPlan")


class SubscriptionChangeRequest(db.Model):
    __tablename__ = "subscription_change_requests"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    current_plan_id = db.Column(db.Integer, db.ForeignKey("subscription_plans.id", ondelete="SET NULL"), nullable=True)
    requested_plan_id = db.Column(db.Integer, db.ForeignKey("subscription_plans.id", ondelete="SET NULL"), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="pending", index=True)
    notes = db.Column(db.String(1000), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    decided_at = db.Column(db.DateTime(timezone=True))


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("tenant_subscriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = db.Column(db.String(20), nullable=False)
    provider_reference = db.Column(db.String(180), nullable=False, unique=True, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(8), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="pending", index=True)
    invoice_number = db.Column(db.String(80), unique=True)
    receipt_url = db.Column(db.String(500))
    paid_at = db.Column(db.DateTime(timezone=True))
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    refunded_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    refunded_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class BillingWebhookEvent(db.Model):
    __tablename__ = "billing_webhook_events"
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(20), nullable=False)
    event_id = db.Column(db.String(255), nullable=False)
    event_type = db.Column(db.String(120), nullable=False, default="")
    status = db.Column(db.String(24), nullable=False, default="received")
    payload_hash = db.Column(db.String(128), nullable=False, default="")
    processed_at = db.Column(db.DateTime(timezone=True))
    error_message = db.Column(db.String(500))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (db.UniqueConstraint("provider", "event_id", name="uq_billing_webhook_provider_event"),)


class Invoice(db.Model):
    __tablename__ = "invoices"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("tenant_subscriptions.id", ondelete="SET NULL"), nullable=True)
    invoice_number = db.Column(db.String(80), unique=True, nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(8), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="issued")
    period_start = db.Column(db.DateTime(timezone=True))
    period_end = db.Column(db.DateTime(timezone=True))
    issued_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    due_at = db.Column(db.DateTime(timezone=True))
    paid_at = db.Column(db.DateTime(timezone=True))
    pdf_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class PlatformAdmin(db.Model):
    __tablename__ = "platform_admins"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(160), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime(timezone=True))
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
    mfa_enabled = db.Column(db.Boolean, nullable=False, default=False)
    mfa_secret = db.Column(db.String(64))
    mfa_recovery_codes_json = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class PlatformAuditLog(db.Model):
    __tablename__ = "platform_audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    platform_admin_id = db.Column(db.Integer, db.ForeignKey("platform_admins.id", ondelete="SET NULL"), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(80))
    target_id = db.Column(db.String(80))
    details_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class SecurityEvent(db.Model):
    __tablename__ = "security_events"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    platform_admin_id = db.Column(db.Integer, db.ForeignKey("platform_admins.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    severity = db.Column(db.String(16), nullable=False, default="info", index=True)
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(500))
    request_id = db.Column(db.String(64), index=True)
    details_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)
