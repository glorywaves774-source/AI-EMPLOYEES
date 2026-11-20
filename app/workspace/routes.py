from flask import render_template, session, g, redirect, url_for, abort, request, flash
from flask_login import login_required, current_user
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import TenantMembership, Department, AIEmployee, AuditLog, WorkforceTask
from app.security import active_membership_required, roles_required
from . import workspace_bp
from app.models import RecurringAssignment
from app.workforce.assignment_templates import TEMPLATES, BY_KEY as TEMPLATE_BY_KEY
from app.billing.services import trial_summary, can_activate_employee

@workspace_bp.before_request
def load_tenant_context():
    if not current_user.is_authenticated:
        return
    tenant_id = session.get("active_tenant_id")
    membership = TenantMembership.query.filter_by(
        tenant_id=tenant_id, user_id=current_user.id, status="active"
    ).first() if tenant_id else None
    if not membership:
        membership = TenantMembership.query.filter_by(
            user_id=current_user.id, status="active"
        ).first()
        if membership:
            session["active_tenant_id"] = membership.tenant_id
    if membership:
        g.active_tenant_id = membership.tenant_id
        g.active_tenant = membership.tenant
        g.membership = membership

def tenant_employees():
    return AIEmployee.query.filter_by(tenant_id=g.active_tenant_id).order_by(AIEmployee.created_at.asc())

@workspace_bp.get("/dashboard")
@login_required
@active_membership_required
def dashboard():
    departments = Department.query.filter_by(tenant_id=g.active_tenant_id).order_by(Department.name).all()
    employees = tenant_employees().all()
    recent_tasks = WorkforceTask.query.filter_by(tenant_id=g.active_tenant_id).order_by(WorkforceTask.created_at.desc()).limit(8).all()
    return render_template("workspace/dashboard.html", tenant=g.active_tenant,
        departments=departments, employees=employees, recent_tasks=recent_tasks,
        active_count=sum(1 for e in employees if e.status == "active"),
        trial=trial_summary(g.active_tenant_id), templates=TEMPLATES,
        chosen_template=TEMPLATE_BY_KEY.get(request.args.get("template", "")),
        recurring_count=RecurringAssignment.query.filter_by(tenant_id=g.active_tenant_id).count())

@workspace_bp.post("/departments")
@roles_required("owner", "admin", "manager")
def create_department():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    if not name or len(name) > 100:
        flash("Enter a department name of 1–100 characters.", "error")
        return redirect(url_for("workspace.dashboard"))
    department = Department(tenant_id=g.active_tenant_id, name=name, description=description[:500])
    db.session.add(department)
    try:
        db.session.flush()
        db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
            action="department.created", target_type="department", target_id=str(department.id)))
        db.session.commit()
        flash("Department created.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("A department with that name already exists.", "error")
    return redirect(url_for("workspace.dashboard"))

@workspace_bp.post("/employees")
@roles_required("owner", "admin", "manager")
def create_employee():
    name = request.form.get("name", "").strip()
    title = request.form.get("job_title", "").strip()
    description = request.form.get("description", "").strip()
    department_id = request.form.get("department_id", type=int)
    department = Department.query.filter_by(id=department_id, tenant_id=g.active_tenant_id).first() if department_id else None
    if not name or not title or len(name) > 120 or len(title) > 120:
        flash("Enter a valid employee name and job title.", "error")
        return redirect(url_for("workspace.dashboard"))
    if department_id and not department:
        abort(400)
    employee = AIEmployee(tenant_id=g.active_tenant_id, department_id=department.id if department else None,
        name=name, job_title=title, description=description[:1000], status="draft", is_system_template=False)
    db.session.add(employee)
    db.session.flush()
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
        action="ai_employee.created", target_type="ai_employee", target_id=str(employee.id)))
    db.session.commit()
    flash("AI employee created as a draft. Configure and test it before activation.", "success")
    return redirect(url_for("workspace.dashboard"))

@workspace_bp.post("/employees/<int:employee_id>/edit")
@roles_required("owner", "admin", "manager")
def edit_employee(employee_id):
    employee = AIEmployee.query.filter_by(id=employee_id, tenant_id=g.active_tenant_id).first_or_404()
    name = request.form.get("name", "").strip()
    title = request.form.get("job_title", "").strip()
    description = request.form.get("description", "").strip()
    department_id = request.form.get("department_id", type=int)
    department = Department.query.filter_by(id=department_id, tenant_id=g.active_tenant_id).first() if department_id else None
    if not name or not title or len(name) > 120 or len(title) > 120 or len(description) > 1000:
        flash("Enter a valid employee name and job title.", "error")
        return redirect(url_for("workspace.dashboard"))
    if department_id and not department:
        abort(400)
    changes = {}
    for field, value in (("name", name), ("job_title", title), ("description", description),
                         ("department_id", department.id if department else None)):
        if getattr(employee, field) != value:
            changes[field] = {"from": getattr(employee, field), "to": value}
            setattr(employee, field, value)
    if changes:
        db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
            action="ai_employee.updated", target_type="ai_employee", target_id=str(employee.id),
            details_json=changes))
        db.session.commit()
        flash(f"{employee.name} has been updated.", "success")
    return redirect(url_for("workspace.dashboard"))

@workspace_bp.post("/employees/<int:employee_id>/status")
@roles_required("owner", "admin", "manager")
def update_employee_status(employee_id):
    employee = AIEmployee.query.filter_by(id=employee_id, tenant_id=g.active_tenant_id).first_or_404()
    requested = request.form.get("status")
    if requested not in {"active", "paused", "draft"}:
        abort(400)
    if requested == "active" and employee.status != "active":
        allowed, message = can_activate_employee(g.active_tenant_id)
        if not allowed:
            flash(message, "error")
            return redirect(url_for("workspace.dashboard"))
    employee.status = requested
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
        action="ai_employee.status_changed", target_type="ai_employee", target_id=str(employee.id),
        details_json={"status": requested}))
    db.session.commit()
    flash(f"{employee.name} is now {requested}.", "success")
    return redirect(url_for("workspace.dashboard"))

@workspace_bp.get("/settings/data-export")
@login_required
@roles_required("owner")
def export_tenant_data():
    """Export tenant-owned operational data for privacy/compliance workflows."""
    from flask import jsonify
    tenant_id = g.active_tenant_id
    employees = AIEmployee.query.filter_by(tenant_id=tenant_id).all()
    departments = Department.query.filter_by(tenant_id=tenant_id).all()
    tasks = WorkforceTask.query.filter_by(tenant_id=tenant_id).all()
    memberships = TenantMembership.query.filter_by(tenant_id=tenant_id).all()
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tenant": {"id": g.active_tenant.id, "name": g.active_tenant.name, "slug": g.active_tenant.slug},
        "members": [{"user_id": m.user_id, "role": m.role, "status": m.status} for m in memberships],
        "departments": [{"id": d.id, "name": d.name, "description": d.description} for d in departments],
        "ai_employees": [{"id": e.id, "name": e.name, "job_title": e.job_title, "status": e.status, "department_id": e.department_id} for e in employees],
        "tasks": [{"id": t.id, "title": t.title, "status": t.status, "created_at": t.created_at.isoformat() if t.created_at else None} for t in tasks],
    }
    db.session.add(AuditLog(tenant_id=tenant_id, actor_user_id=current_user.id, action="tenant.data_exported", target_type="tenant", target_id=str(tenant_id)))
    db.session.commit()
    return jsonify(payload)
