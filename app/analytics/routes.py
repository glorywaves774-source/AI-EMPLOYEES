import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from sqlalchemy import case
from flask import render_template, g, request, Response, current_app, abort
from flask_login import login_required
from app.extensions import db
from app.models import WorkforceTask, AgentRun, ApprovalRequest, KnowledgeDocument, AIEmployee
from app.security import roles_required
from . import analytics_bp

def _period_days():
    try: days = int(request.args.get("days", "30"))
    except (TypeError, ValueError): abort(400)
    if days not in (7, 30, 90, 365): abort(400)
    return days

def _report_data(days):
    tenant_id = g.active_tenant_id
    since = datetime.now(timezone.utc) - timedelta(days=days)
    task_base = WorkforceTask.query.filter(WorkforceTask.tenant_id == tenant_id, WorkforceTask.created_at >= since)
    total_tasks = task_base.count()
    completed = task_base.filter(WorkforceTask.status == "completed").count()
    failed = task_base.filter(WorkforceTask.status == "failed").count()
    queued = task_base.filter(WorkforceTask.status.in_(["queued", "running"])).count()
    run_filter = (AgentRun.tenant_id == tenant_id, AgentRun.created_at >= since)
    run_count = AgentRun.query.filter(*run_filter).count()
    totals = db.session.query(
        db.func.coalesce(db.func.sum(AgentRun.input_tokens), 0),
        db.func.coalesce(db.func.sum(AgentRun.output_tokens), 0)
    ).filter(*run_filter).one()
    input_tokens, output_tokens = int(totals[0]), int(totals[1])
    employee_rows = db.session.query(
        AgentRun.employee_name,
        db.func.count(AgentRun.id),
        db.func.sum(case((AgentRun.status == "completed", 1), else_=0)),
        db.func.coalesce(db.func.sum(AgentRun.input_tokens), 0),
        db.func.coalesce(db.func.sum(AgentRun.output_tokens), 0)
    ).filter(*run_filter).group_by(AgentRun.employee_name).order_by(db.func.count(AgentRun.id).desc()).all()
    pending = ApprovalRequest.query.filter_by(tenant_id=tenant_id, status="pending").count()
    documents = KnowledgeDocument.query.filter_by(tenant_id=tenant_id).count()
    active = AIEmployee.query.filter_by(tenant_id=tenant_id, status="active").count()
    input_rate = float(current_app.config.get("ESTIMATED_INPUT_USD_PER_MILLION", 0) or 0)
    output_rate = float(current_app.config.get("ESTIMATED_OUTPUT_USD_PER_MILLION", 0) or 0)
    estimated_cost = input_tokens / 1_000_000 * input_rate + output_tokens / 1_000_000 * output_rate
    return dict(days=days,total_tasks=total_tasks,completed=completed,failed=failed,queued=queued,
        run_count=run_count,input_tokens=input_tokens,output_tokens=output_tokens,total_tokens=input_tokens+output_tokens,
        pending_approvals=pending,documents=documents,active_employees=active,employee_rows=employee_rows,
        completion_rate=round(completed/total_tasks*100,1) if total_tasks else 0,
        estimated_cost=estimated_cost,cost_configured=bool(input_rate or output_rate))

@analytics_bp.get("/")
@login_required
@roles_required("owner", "admin", "manager")
def index():
    return render_template("analytics/index.html", report=_report_data(_period_days()))

@analytics_bp.get("/export.csv")
@login_required
@roles_required("owner", "admin", "manager")
def export_csv():
    report = _report_data(_period_days())
    output = StringIO(); writer = csv.writer(output)
    writer.writerow(["AI Workforce usage report"])
    for label, key in [("Period (days)","days"),("Tasks","total_tasks"),("Completed tasks","completed"),
        ("Failed tasks","failed"),("Queued or running tasks","queued"),("Completion rate (%)","completion_rate"),
        ("Agent runs","run_count"),("Input tokens","input_tokens"),("Output tokens","output_tokens"),
        ("Pending approvals","pending_approvals"),("Knowledge documents","documents"),("Active AI employees","active_employees")]:
        writer.writerow([label,report[key]])
    writer.writerow([]); writer.writerow(["AI employee","Runs","Completed runs","Input tokens","Output tokens"])
    for row in report["employee_rows"]: writer.writerow(list(row))
    filename=f"ai-workforce-usage-{report['days']}-days.csv"
    return Response(output.getvalue(),mimetype="text/csv",headers={"Content-Disposition":f'attachment; filename="{filename}"'})
