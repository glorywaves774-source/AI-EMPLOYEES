from flask import Blueprint
workspace_bp = Blueprint("workspace", __name__)
from . import routes
