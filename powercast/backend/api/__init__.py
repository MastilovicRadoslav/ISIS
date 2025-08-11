from flask import Blueprint
api_bp = Blueprint("api", __name__)

from . import health_routes  # noqa

#Sprint 1
from . import import_routes  # noqa: E402,F401
from . import series_routes  # noqa: E402,F401

#Sprint 2
from . import train_routes  # noqa: E402,F401
from . import model_routes  # noqa: E402,F401

#Sprint 3
from . import forecast_routes  

