from flask import request, jsonify
from . import api_bp
from db import get_db, get_fs
from datetime import datetime, timezone
from ml.train import train_lstm_on_regions
from bson import ObjectId

@api_bp.post("/train/start")
def train_start():
    data = request.get_json(force=True)
    regions = data.get("regions") or []
    date_from = data.get("date_from")
    date_to = data.get("date_to")
    hyper = data.get("hyper", {})

    if not regions or len(regions) < 1:
        return jsonify({"ok": False, "error": "regions is required"}), 400
    if not date_from or not date_to:
        return jsonify({"ok": False, "error": "date_from/date_to required"}), 400

    db = get_db()
    fs = get_fs()

    # treniraj (vrati artifact_bytes po regionu)
    results = train_lstm_on_regions(db, regions, date_from, date_to, hyper)
    out = []

    now_tag = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    now_utc = datetime.now(timezone.utc)  # aware UTC

    for r in results:
        if not r.get("ok"):
            out.append(r)
            continue

        # 1) Snimi u GridFS
        filename = f"model_{r['region']}_{now_tag}.pt"
        artifact_id = fs.put(r["artifact_bytes"], filename=filename)

        # 2) Upis u kolekciju models (metapodaci)
        doc = {
            "region": r["region"],
            "algo": "LSTMSeq2Seq",
            "hyper": hyper,
            "train_range": {"from": date_from, "to": date_to},
            "metrics": r["metrics"],
            "created_at": now_utc,                       # aware UTC zapis u Mongo
            "created_at_ms": int(now_utc.timestamp()*1000),  # zgodno i za FE
            "artifact_id": artifact_id
        }
        ins = db.models.insert_one(doc)

        out.append({
            "ok": True,
            "region": r["region"],
            "model_id": str(ins.inserted_id),
            "artifact_id": str(artifact_id),
            "metrics": r["metrics"],
            "created_at_ms": doc["created_at_ms"],      # odmah vrati ms

        })

    return jsonify({"ok": True, "results": out})
