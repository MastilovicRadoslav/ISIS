from flask import request, jsonify, send_file
from . import api_bp
from db import get_db, get_fs
from bson import ObjectId
from datetime import datetime
from ml.predict import run_forecast
import io
import pandas as pd


@api_bp.post("/forecast/run")
def forecast_run():
    data = request.get_json(force=True)
    region = data.get("region")
    start_date = data.get("start_date")
    days = int(data.get("days", 1))
    if not region or not start_date:
        return jsonify({"ok": False, "error": "region and start_date required"}), 400
    if days < 1 or days > 7:
        return jsonify({"ok": False, "error": "days must be 1..7"}), 400

    db = get_db(); fs = get_fs()
    # nadji najnoviji model za region
    model_doc = db.models.find_one({"region": region}, sort=[("created_at", -1)])
    if not model_doc:
        return jsonify({"ok": False, "error": "No model for region. Train first."}), 400

    try:
        ts_out, y_out, csv_id = run_forecast(db, fs, model_doc, region, start_date, days)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    # upis u forecasts kolekciju, i markiranje poslednje kao relevantne

    doc = {
        "region": region,
        # dosljedno parsiranje ulaza iz fronta (ISO/UTC) u Python datetime
        "start_date": pd.to_datetime(start_date).to_pydatetime(),
        "horizon_h": len(y_out),
        "created_at": datetime.utcnow(),
        "values": [{"ts": t, "yhat": float(v)} for t, v in zip(ts_out, y_out)],
        "export_id": csv_id,
        "is_latest": True
    }

    # set is_latest=false za starije sa istim start_date
    db.forecasts.update_many({"region": region, "start_date": doc["start_date"], "_id": {"$exists": True}}, {"$set": {"is_latest": False}})
    ins = db.forecasts.insert_one(doc)

    return jsonify({"ok": True, "forecast_id": str(ins.inserted_id), "export_id": str(csv_id), "count": len(y_out)})


@api_bp.get("/forecast/<fid>")
def forecast_get(fid):
    db = get_db()
    from bson import ObjectId
    d = db.forecasts.find_one({"_id": ObjectId(fid)})
    if not d:
        return jsonify({"ok": False, "error": "not found"}), 404
    d["_id"] = str(d["_id"])
    d["export_id"] = str(d["export_id"]) if d.get("export_id") else None
    return jsonify({"ok": True, "forecast": d})


@api_bp.get("/forecast/search")
def forecast_search():
    db = get_db()
    region = request.args.get("region")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    q = {}
    if region:
        q["region"] = region
    if date_from or date_to:
        q["start_date"] = {}
        if date_from:
            q["start_date"]["$gte"] = datetime.fromisoformat(date_from.replace('Z','+00:00').split('+')[0])
        if date_to:
            q["start_date"]["$lte"] = datetime.fromisoformat(date_to.replace('Z','+00:00').split('+')[0])
    docs = list(db.forecasts.find(q).sort("created_at", -1))
    for d in docs:
        d["_id"] = str(d["_id"])
        d["export_id"] = str(d["export_id"]) if d.get("export_id") else None
    return jsonify({"ok": True, "items": docs})


@api_bp.get("/forecast/export/<export_id>")
def forecast_export(export_id):
    fs = get_fs()
    gridout = fs.get(ObjectId(export_id))
    return send_file(io.BytesIO(gridout.read()), as_attachment=True, download_name=f"forecast_{export_id}.csv", mimetype="text/csv")