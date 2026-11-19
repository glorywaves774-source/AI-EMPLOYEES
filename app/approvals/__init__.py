from flask import Blueprint
approvals_bp = Blueprint("approvals", __name__, url_prefix="/approvals")
from . import routes
