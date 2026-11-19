from functools import wraps
from flask import abort, g
from flask_login import current_user, login_required
from .models import TenantMembership, RolePermission, Permission

ALLOWED_ROLES = {"owner", "admin", "manager", "employee"}

def active_membership_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        tenant_id = g.get("active_tenant_id")
        if not tenant_id:
            abort(403)
        membership = TenantMembership.query.filter_by(tenant_id=tenant_id, user_id=current_user.id, status="active").first()
        if not membership:
            abort(403)
        g.membership = membership
        return view(*args, **kwargs)
    return wrapped

def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @active_membership_required
        def wrapped(*args, **kwargs):
            if g.membership.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator

def permission_required(code):
    def decorator(view):
        @wraps(view)
        @active_membership_required
        def wrapped(*args, **kwargs):
            if not has_permission(g.membership.role, code):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator

def has_permission(role, code):
    if role == "owner":
        return True
    return (RolePermission.query.join(Permission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role == role, Permission.code == code).first()) is not None
