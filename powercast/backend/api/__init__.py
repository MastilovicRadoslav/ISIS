from flask import Blueprint
api_bp = Blueprint("api", __name__)

from . import health_routes  # noqa
