from flask import Blueprint
workforce_bp = Blueprint("workforce", __name__, url_prefix="/workforce")
from . import routes
