from flask import request, jsonify
from . import api_bp
from db import get_db
import pandas as pd
from datetime import datetime
from pymongo import UpdateOne, ASCENDING

# — Helpers —
REQUIRED_LOAD_COLS = ["Time Stamp", "Name", "Load"]
REQUIRED_WEATHER_COLS = ["datetime", "name"]  # ostale numeric kolone uzimamo kada postoje

INDEXED = {"series_load_hourly": False, "series_weather_hourly": False}

def ensure_indexes(db):
    global INDEXED
    if not INDEXED["series_load_hourly"]:
        db.series_load_hourly.create_index([("region", ASCENDING), ("ts", ASCENDING)], unique=True)
        INDEXED["series_load_hourly"] = True
    if not INDEXED["series_weather_hourly"]:
        db.series_weather_hourly.create_index([("location", ASCENDING), ("ts", ASCENDING)], unique=True)
        INDEXED["series_weather_hourly"] = True


def _response_error(msg, status=400):
    return jsonify({"ok": False, "error": msg}), status


@api_bp.post("/import/load")
def import_load_csv():
    db = get_db()
    ensure_indexes(db)

    if "file" not in request.files:
        return _response_error("Missing 'file' in form-data")

    f = request.files["file"]
    try:
        df = pd.read_csv(f)
    except Exception as e:
        return _response_error(f"CSV parse error: {e}")

    missing = [c for c in REQUIRED_LOAD_COLS if c not in df.columns]
    if missing:
        return _response_error(f"Missing columns: {missing}")

    # Drop NA & to datetime
    df = df.dropna(subset=["Time Stamp", "Name", "Load"]).copy()
    df["Time Stamp"] = pd.to_datetime(df["Time Stamp"], errors="coerce")
    df = df.dropna(subset=["Time Stamp"])  # ukloni neparsirane datume

    # Normališe na sat: NYISO 'Load' je MW snapshot -> uzmimo prosjek u satu
    df["hour"] = df["Time Stamp"].dt.floor("H")
    g = df.groupby(["Name", "hour"])['Load'].mean().reset_index().rename(columns={"Name": "region", "hour": "ts", "Load": "load_mw"})

    if g.empty:
        return _response_error("No usable rows after cleaning")

    # Bulk upsert po (region, ts)
    ops = []
    for _, row in g.iterrows():
        ops.append(
            UpdateOne(
                {"region": row["region"], "ts": pd.to_datetime(row["ts"]).to_pydatetime()},
                {"$set": {"region": row["region"], "ts": pd.to_datetime(row["ts"]).to_pydatetime(), "load_mw": float(row["load_mw"]) }},
                upsert=True
            )
        )
    if ops:
        res = db.series_load_hourly.bulk_write(ops, ordered=False)
    else:
        res = None

    regions = sorted(g["region"].unique().tolist())
    ts_min, ts_max = g["ts"].min(), g["ts"].max()

    return jsonify({
        "ok": True,
        "file": f.filename,
        "regions": regions,
        "rows_hourly": int(g.shape[0]),
        "ts_range": {"from": ts_min.isoformat(), "to": ts_max.isoformat()},
        "upserts": getattr(res, 'upserted_count', 0),
        "modified": getattr(res, 'modified_count', 0)
    })


@api_bp.post("/import/weather")
def import_weather_csv():
    db = get_db()
    ensure_indexes(db)

    if "file" not in request.files:
        return _response_error("Missing 'file' in form-data")

    f = request.files["file"]
    try:
        df = pd.read_csv(f)
    except Exception as e:
        return _response_error(f"CSV parse error: {e}")

    missing = [c for c in REQUIRED_WEATHER_COLS if c not in df.columns]
    if missing:
        return _response_error(f"Missing columns: {missing}")

    df = df.dropna(subset=["datetime", "name"]).copy()
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"])  # validni datumi

    # Ako rezolucija nije točno 1h, normalizuj na 1h (mean)
    df["hour"] = df["datetime"].dt.floor("H")

    # Uzmi relevantne numeric kolone (temp, dew, humidity, windspeed, precip, solar)
    keep_numeric = [c for c in df.columns if c not in ("datetime", "name", "hour")]
    num_cols = df[keep_numeric].select_dtypes(include=['number']).columns.tolist()

    agg = {c: 'mean' for c in num_cols}
    g = df.groupby(["name", "hour"]).agg(agg).reset_index().rename(columns={"name": "location", "hour": "ts"})

    if g.empty:
        return _response_error("No usable rows after cleaning")

    # Bulk upsert
    ops = []
    for _, row in g.iterrows():
        doc = {"location": row["location"], "ts": pd.to_datetime(row["ts"]).to_pydatetime()}
        for c in num_cols:
            v = row.get(c)
            if pd.notna(v):
                doc[c] = float(v)
        ops.append(
            UpdateOne(
                {"location": doc["location"], "ts": doc["ts"]},
                {"$set": doc},
                upsert=True
            )
        )
    if ops:
        res = db.series_weather_hourly.bulk_write(ops, ordered=False)
    else:
        res = None

    locations = sorted(g["location"].unique().tolist())
    ts_min, ts_max = g["ts"].min(), g["ts"].max()

    return jsonify({
        "ok": True,
        "file": f.filename,
        "locations": locations,
        "rows_hourly": int(g.shape[0]),
        "ts_range": {"from": ts_min.isoformat(), "to": ts_max.isoformat()},
        "upserts": getattr(res, 'upserted_count', 0),
        "modified": getattr(res, 'modified_count', 0)
    })