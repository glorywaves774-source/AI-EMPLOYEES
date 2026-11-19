from flask import request, g
from .extensions import db
from .models import SecurityEvent


def record_security_event(event_type, severity="info", *, user_id=None, tenant_id=None, platform_admin_id=None, details=None):
    event = SecurityEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        platform_admin_id=platform_admin_id,
        event_type=event_type,
        severity=severity,
        ip_address=request.remote_addr,
        user_agent=(request.user_agent.string or "")[:500],
        request_id=g.get("request_id"),
        details_json=details or {},
    )
    db.session.add(event)
    return event
