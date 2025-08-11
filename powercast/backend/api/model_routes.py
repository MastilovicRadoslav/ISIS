from flask import jsonify, request, send_file
from . import api_bp
from db import get_db, get_fs
from bson import ObjectId
import io

@api_bp.get("/model/list")
def model_list():
    db = get_db()
    region = request.args.get("region")
    q = {"region": region} if region else {}
    docs = list(db.models.find(q).sort("created_at", -1))
    for d in docs:
        d["_id"] = str(d["_id"])
        d["artifact_id"] = str(d["artifact_id"]) if d.get("artifact_id") else None
        # stringify datetime da AntD lijepo prikaže
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        # uklonjeno: d["local_path"]
    return jsonify({"ok": True, "models": docs})

@api_bp.get("/model/latest")
def model_latest():
    db = get_db()
    region = request.args.get("region")
    if not region:
        return jsonify({"ok": False, "error": "region required"}), 400
    d = db.models.find_one({"region": region}, sort=[("created_at", -1)])
    if not d:
        return jsonify({"ok": False, "error": "no model for region"}), 404
    d["_id"] = str(d["_id"])
    d["artifact_id"] = str(d["artifact_id"]) if d.get("artifact_id") else None
    if d.get("created_at"):
        d["created_at"] = d["created_at"].isoformat()
    # uklonjeno: d["local_path"]
    return jsonify({"ok": True, "model": d})

@api_bp.get("/model/artifact/<artifact_id>")
def model_artifact(artifact_id):
    fs = get_fs()
    gridout = fs.get(ObjectId(artifact_id))
    return send_file(
        io.BytesIO(gridout.read()),
        as_attachment=True,
        download_name=f"{artifact_id}.pt",
        mimetype="application/octet-stream"
    )
