from flask import Blueprint
api_bp = Blueprint("api", __name__)

from . import health_routes  # noqa
from . import import_routes  # noqa: E402,F401
from . import series_routes  # noqa: E402,F401

