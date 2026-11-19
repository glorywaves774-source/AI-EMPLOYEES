from datetime import datetime, timezone
from flask import abort, flash, g, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app.extensions import db
from app.models import ApprovalRequest, AuditLog, Notification, TeamExecution, WorkforceTask
from app.security import roles_required, active_membership_required
from . import approvals_bp

@approvals_bp.get("/")
@login_required
@active_membership_required
def index():
    items = ApprovalRequest.query.filter_by(tenant_id=g.active_tenant_id).order_by(ApprovalRequest.created_at.desc()).all()
    team_reviews = (TeamExecution.query.join(WorkforceTask, TeamExecution.task_id == WorkforceTask.id)
        .filter(TeamExecution.tenant_id == g.active_tenant_id, TeamExecution.status == "needs_review")
        .order_by(TeamExecution.completed_at.desc()).all())
    return render_template("approvals/index.html", items=items, team_reviews=team_reviews)

@approvals_bp.post("/request")
@roles_required("owner", "admin", "manager")
def create_request():
    action_type = request.form.get("action_type", "").strip()
    description = request.form.get("description", "").strip()
    if not action_type or not description or len(action_type) > 80 or len(description) > 4000:
        flash("Provide a valid action type and description.", "error")
        return redirect(url_for("approvals.index"))
    item = ApprovalRequest(tenant_id=g.active_tenant_id, requested_by_user_id=current_user.id,
                           action_type=action_type, description=description)
    db.session.add(item)
    db.session.flush()
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
        action="approval.requested", target_type="approval_request", target_id=str(item.id)))
    db.session.commit()
    flash("Approval request recorded. No external action has been executed.", "success")
    return redirect(url_for("approvals.index"))

@approvals_bp.post("/<int:approval_id>/decision")
@roles_required("owner", "admin")
def decide(approval_id):
    item = ApprovalRequest.query.filter_by(id=approval_id, tenant_id=g.active_tenant_id).first_or_404()
    if item.status != "pending":
        abort(409)
    decision = request.form.get("decision")
    note = request.form.get("decision_note", "").strip()[:1000]
    if decision not in {"approved", "rejected"}:
        abort(400)
    item.status = decision
    item.decided_by_user_id = current_user.id
    item.decision_note = note
    item.decided_at = datetime.now(timezone.utc)
    db.session.add(AuditLog(tenant_id=g.active_tenant_id, actor_user_id=current_user.id,
        action=f"approval.{decision}", target_type="approval_request", target_id=str(item.id),
        details_json={"note": note}))
    if item.requested_by_user_id:
        db.session.add(Notification(tenant_id=g.active_tenant_id, user_id=item.requested_by_user_id,
            title=f"Approval {decision}", message=f"Your request for {item.action_type} was {decision}.", category="approval"))
    db.session.commit()
    flash(f"Request {decision}. This records authorisation only; it does not execute the action.", "success")
    return redirect(url_for("approvals.index"))
