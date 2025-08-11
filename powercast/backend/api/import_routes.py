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
    df["hour"] = df["Time Stamp"].dt.floor("h")
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
        # stabilnije čitanje CSV-a
        df = pd.read_csv(f, low_memory=False)
    except Exception as e:
        return _response_error(f"CSV parse error: {e}")

    if df.empty or df.shape[1] == 0:
        return _response_error("Empty CSV or no columns")

    # --- Header normalizacija ---
    # trim + lower, pa poslije napravimo alias mape
    original_cols = df.columns.tolist()
    norm_cols = [c.strip() for c in original_cols]
    lower_map = {c: c.strip().lower() for c in original_cols}
    df.columns = [lower_map[c] for c in original_cols]

    # aliasi za tipične varijante
    rename_map = {
        "date time": "datetime",
        "timestamp": "datetime",
        "time": "datetime",
        "city": "name",
        "location": "name",
    }
    for src, dst in rename_map.items():
        if src in df.columns and dst not in df.columns:
            df = df.rename(columns={src: dst})

    # Provjera obaveznih kolona
    required = ["datetime", "name"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return _response_error(f"Missing columns: {missing}. Seen columns={list(df.columns)}")

    # --- Čišćenje i priprema ---
    df = df.dropna(subset=["datetime", "name"]).copy()
    # parsiraj vrijeme (dozvoli razne formate)
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
    df = df.dropna(subset=["datetime"])
    if df.empty:
        return _response_error("No valid datetimes after parsing")

    # normalizuj na pun sat
    df["hour"] = df["datetime"].dt.floor("h")

    # identifikuj kandidat kolone za numeriku: sve osim meta kolona
    meta_cols = {"datetime", "name", "hour"}
    candidate_cols = [c for c in df.columns if c not in meta_cols]

    # coerci u numeričko gdje moguće (prazne kolone ostaju NaN)
    numeric_cols = []
    for c in candidate_cols:
        # probaj pretvoriti u broj; ako ništa ne uspije, kolona će biti all-NaN
        coerced = pd.to_numeric(df[c], errors="coerce")
        # zadrži ako ima bar jedan broj
        if coerced.notna().any():
            df[c] = coerced
            numeric_cols.append(c)

    if not numeric_cols:
        return _response_error("No numeric columns detected (after coercion)")

    # agregacija na sat (mean)
    agg = {c: "mean" for c in numeric_cols}
    g = df.groupby(["name", "hour"]).agg(agg).reset_index().rename(
        columns={"name": "location", "hour": "ts"}
    )

    if g.empty:
        return _response_error("No usable rows after cleaning/grouping")

    # --- Bulk upsert ---
    ops = []
    for _, row in g.iterrows():
        doc = {
            "location": row["location"],
            "ts": pd.to_datetime(row["ts"]).to_pydatetime(),  # timezone-aware → naive UTC dt ok
        }
        for c in numeric_cols:
            v = row[c]
            if pd.notna(v):
                doc[c] = float(v)
        ops.append(
            UpdateOne(
                {"location": doc["location"], "ts": doc["ts"]},
                {"$set": doc},
                upsert=True,
            )
        )

    res = None
    if ops:
        try:
            res = db.series_weather_hourly.bulk_write(ops, ordered=False)
        except Exception as e:
            # Ako već ima duplikata i tek sada pravimo unique index, ovo može dići grešku
            return _response_error(f"Mongo bulk_write error: {e}")

    locations = sorted(g["location"].unique().tolist())
    ts_min, ts_max = g["ts"].min(), g["ts"].max()

    return jsonify({
        "ok": True,
        "file": f.filename,
        "locations": locations,
        "rows_hourly": int(g.shape[0]),
        "ts_range": {"from": pd.to_datetime(ts_min).isoformat(), "to": pd.to_datetime(ts_max).isoformat()},
        "upserts": getattr(res, "upserted_count", 0) if res else 0,
        "modified": getattr(res, "modified_count", 0) if res else 0,
        # korisno za debug u UI:
        "detected_numeric_columns": numeric_cols,
        "all_columns_seen": list(df.columns),
    })
