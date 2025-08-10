from flask import jsonify
from . import api_bp

@api_bp.get("/health")
def health():
    return jsonify({"status": "ok"})
