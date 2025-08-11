from flask import request, jsonify
from . import api_bp
from db import get_db, get_fs
from datetime import datetime
from ml.train import train_lstm_on_regions
from bson import ObjectId
import os

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

    # pripremi lokalni folder models/
    models_dir = os.path.join(os.getcwd(), "models")
    os.makedirs(models_dir, exist_ok=True)

    now_tag = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    for r in results:
        if not r.get("ok"):
            out.append(r)
            continue

        # 1) Snimi u GridFS
        filename = f"model_{r['region']}_{now_tag}.pt"
        artifact_id = fs.put(r["artifact_bytes"], filename=filename)

        # 2) Snimi lokalno u models/
        local_path = os.path.join(models_dir, filename)
        try:
            with open(local_path, "wb") as f:
                f.write(r["artifact_bytes"])
        except Exception as e:
            # Ako lokalni zapis ne uspije, i dalje vraćamo GridFS artefakt
            local_path = None

        # 3) Upis u kolekciju models (metapodaci)
        doc = {
            "region": r["region"],
            "algo": "LSTMSeq2Seq",
            "hyper": hyper,
            "train_range": {"from": date_from, "to": date_to},
            "metrics": r["metrics"],
            "created_at": datetime.utcnow(),
            "artifact_id": artifact_id,
            "local_path": local_path,  # <- NOVO: putanja lokalnog fajla (ako je uspjelo)
        }
        ins = db.models.insert_one(doc)

        out.append({
            "ok": True,
            "region": r["region"],
            "model_id": str(ins.inserted_id),
            "artifact_id": str(artifact_id),
            "local_path": local_path,
            "metrics": r["metrics"],
        })

    return jsonify({"ok": True, "results": out})
