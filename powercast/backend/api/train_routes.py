import os
from flask import request, jsonify
from . import api_bp
from db import get_db, get_fs
from datetime import datetime, timezone
from ml.train import train_lstm_on_regions
from bson import ObjectId

# Lokalni folder za modele (može i iz ENV varijable)
MODEL_DIR = os.environ.get(
    "MODEL_DIR",
    r"C:\Users\Lenovo\Documents\GitHub\ISIS\powercast\models"
)
os.makedirs(MODEL_DIR, exist_ok=True)

@api_bp.post("/train/start")
def train_start():
    """
    Endpoint koji startuje trening za jedan ili više regiona.
    Očekuje JSON tijelo:
      {
        "regions": ["CAPITL", "N.Y.C", ...],   # obavezno: lista regiona
        "date_from": "2019-01-01T00:00:00Z",   # obavezno: ISO8601 (UTC)
        "date_to":   "2021-12-31T23:00:00Z",   # obavezno: ISO8601 (UTC)
        "hyper": {                             # opcionalno: hiperparametri
          "input_window": 168,
          "forecast_horizon": 168,
          "hidden_size": 128,
          "layers": 2,
          "dropout": 0.2,
          "epochs": 25,
          "batch_size": 64,
          "learning_rate": 1e-3,
          "teacher_forcing": 0.2
        }
      }

    Vraća listu rezultata po regionu sa ID-jevima modela/artifakta i metrikama.
    """
    data = request.get_json(force=True)
    regions = data.get("regions") or []
    date_from = data.get("date_from")
    date_to = data.get("date_to")
    hyper = data.get("hyper", {})

    # Osnovne validacije ulaza
    if not regions or len(regions) < 1:
        return jsonify({"ok": False, "error": "regions is required"}), 400
    if not date_from or not date_to:
        return jsonify({"ok": False, "error": "date_from/date_to required"}), 400

    # Konekcije na bazu i GridFS
    db = get_db()
    fs = get_fs()

    # Pokreni trening; dobijamo listu rezultata po regionu.
    # Svaki rezultat (za ok=True) sadrži:
    #   - artifact_bytes: bajtovi torch.save paketa (state_dict + meta + scaler)
    #   - metrics: npr. {"val_loss": ..., "test_mape": ...}
    results = train_lstm_on_regions(db, regions, date_from, date_to, hyper)
    out = []

    # Tag za filename u GridFS (naivni UTC string, dovoljan za naziv)
    now_tag = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    # Aware UTC timestamp za Mongo polje created_at (preporučeno)
    now_utc = datetime.now(timezone.utc)  # aware UTC

    for r in results:
        if not r.get("ok"):
            out.append(r)
            continue

        # Ime fajla (isti tag kao za GridFS)
        filename = f"model_{r['region']}_{now_tag}.pt"

        # (A) Snimi lokalno (ne ruši ako fail-uje)
        local_path = None
        try:
            local_path = os.path.join(MODEL_DIR, filename)
            with open(local_path, "wb") as fh:
                fh.write(r["artifact_bytes"])
        except Exception:
            local_path = None  # nastavi dalje, GridFS je i dalje primarni storage

        # (B) Snimi u GridFS (kao i ranije)
        artifact_id = fs.put(r["artifact_bytes"], filename=filename)

        # (C) Upis meta u 'models' (dodaj i local_path da se vidi u UI/inspekciji)
        doc = {
            "region": r["region"],
            "algo": "LSTMSeq2Seq",
            "hyper": hyper,
            "train_range": {"from": date_from, "to": date_to},
            "metrics": r["metrics"],
            "created_at": now_utc,                       # aware UTC
            "created_at_ms": int(now_utc.timestamp() * 1000),
            "artifact_id": artifact_id,
            "local_path": local_path                     # <— NOVO: putanja na disku
        }
        ins = db.models.insert_one(doc)

        out.append({
            "ok": True,
            "region": r["region"],
            "model_id": str(ins.inserted_id),
            "artifact_id": str(artifact_id),
            "metrics": r["metrics"],
            "created_at_ms": doc["created_at_ms"],
            "local_path": local_path                     # <— po želji vrati i klijentu
        })

    # Finalni odgovor za sve regione
    return jsonify({"ok": True, "results": out})
