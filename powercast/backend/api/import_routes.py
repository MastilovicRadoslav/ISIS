# import_routes.py
from flask import request, jsonify
from . import api_bp
from db import get_db
from pymongo import UpdateOne, ASCENDING
import pandas as pd
import numpy as np
from pytz import timezone, UTC

# ---------- Global / helpers ----------

NY_TZ = timezone("America/New_York")

REQUIRED_LOAD_COLS = ["Time Stamp", "Name", "Load"]

# koristimo memorijski flag da indexe ne kreiramo stalno
INDEXED = {"series_load_hourly": False, "series_weather_hourly": False}

#Uniformno vraća grešku: {"ok": False, "error": msg}, sa HTTP status kodom.
def _response_error(msg, status=400):
    return jsonify({"ok": False, "error": msg}), status

#Idempotentno kreira unique indekse:
def ensure_indexes(db):
    """Kreira unique indexe (idempotentno)."""
    global INDEXED
    try:
        if not INDEXED["series_load_hourly"]:
            db.series_load_hourly.create_index(
                [("region", ASCENDING), ("ts", ASCENDING)], unique=True
            )
            INDEXED["series_load_hourly"] = True
    except Exception:
        INDEXED["series_load_hourly"] = True  # pretpostavi da već postoji

    try:
        if not INDEXED["series_weather_hourly"]:
            db.series_weather_hourly.create_index(
                [("location", ASCENDING), ("ts", ASCENDING)], unique=True
            )
            INDEXED["series_weather_hourly"] = True
    except Exception:
        INDEXED["series_weather_hourly"] = True

def to_utc_series_localized(s: pd.Series) -> pd.Series:
    # 1) Pretvori ulaznu seriju (stringovi ili datumi) u pandas datetime.
    #    - errors="coerce" → sve nevažeće vrijednosti postaju NaT (Not a Time).
    s = pd.to_datetime(s, errors="coerce")

    # 2) Izbaci sve NaT vrijednosti (neispravne ili prazne datume).
    s = s.dropna()

    s = s.sort_values()

    # 3) Lokalizuj datume u vremensku zonu "America/New_York".
    #    Ovdje nastaju DST rubni slučajevi:
    #    - ambiguous='infer'  → u jesen (fall back) sat od 1:00–2:00 se ponavlja 2 puta;
    #                           Pandas pokušava pogoditi koji je ispravan.
    #    - nonexistent='shift_forward' → u proljeće (spring forward) sat od 2:00–3:00 ne postoji;
    #                                    vrijeme se pomjera unaprijed na prvi validan sat (npr. 03:00).
    s_local = s.dt.tz_localize(
        NY_TZ, 
        ambiguous="infer", 
        nonexistent="shift_forward"
    )

    # 4) Konvertuj iz lokalnog vremena (NY) u univerzalno UTC vrijeme.
    #    Na ovaj način dobijamo jednoznačne, stabilne UTC datetime vrijednosti.
    return s_local.dt.tz_convert(UTC)

def utc_floor_hour(s_utc: pd.Series) -> pd.Series:
    """Floor na puni sat u UTC zoni (aware Timestamp)."""
    return s_utc.dt.floor("h")


def aware_to_naive_utc(ts: pd.Timestamp) -> pd.Timestamp:
    """
    Pretvara aware UTC Timestamp u naive UTC (bez tzinfo),
    što je poželjno za Mongo index stabilnost.
    """
    if ts.tzinfo is None:
        # pretpostavi da je već UTC-naive
        return ts
    return ts.tz_convert(UTC).tz_localize(None)


# ---------- LOAD IMPORT (5-min → hourly mean) ----------

@api_bp.post("/import/load")
def import_load_csv():
    db = get_db()  # 1) Dobavi Mongo konekciju (pymongo database objekat)
    ensure_indexes(db)  # 2) Idempotentno kreiraj unikatne indekse (region+ts)

    # 3) Validacija da je fajl prisutan u multipart form-data pod ključem "file"
    if "file" not in request.files:
        return _response_error("Missing 'file' in form-data")

    f = request.files["file"]

    # 4) Učitaj CSV u pandas DataFrame (bez nepotrebnog tip-guessanja)
    try:
        df = pd.read_csv(f, low_memory=False)
    except Exception as e:
        return _response_error(f"CSV parse error: {e}")

    # 5) Provjeri da su obavezne kolone prisutne (Time Stamp, Name, Load)
    missing = [c for c in REQUIRED_LOAD_COLS if c not in df.columns]
    if missing:
        return _response_error(f"Missing columns: {missing}")

    # 6) Osnovno čišćenje:
    #    - zapamti ulazni broj redova (za povratnu informaciju)
    #    - odbaci redove bez bilo koje od ključnih kolona
    before_rows = len(df)
    df = df.dropna(subset=["Time Stamp", "Name", "Load"]).copy()

    # 7) Parsiraj Load u numerički tip; sve nevažeće vrijednosti postaju NaN
    df["Load"] = pd.to_numeric(df["Load"], errors="coerce")
    #    - odbaci redove gdje je Load NaN
    df = df.dropna(subset=["Load"])

    # 8) Pretvori "Time Stamp" (naivni lokalni NY) u AWARE UTC,
    #    uz rješavanje DST rubnih slučajeva (spring forward / fall back)
    try:
        ts_utc = to_utc_series_localized(df["Time Stamp"])
    except Exception as e:
        return _response_error(f"Timezone localization error: {e}")

    #    - poravnaj DF na validne indekse (gdje je parsiranje uspjelo),
    #      i sačuvaj kolonu sa UTC aware timestampom
    df = df.loc[ts_utc.index].copy()
    df["ts_utc"] = ts_utc

    # 9) Floor na puni sat u UTC (npr. 12:34 → 12:00); priprema za satnu agregaciju
    df["ts_hour_utc"] = utc_floor_hour(df["ts_utc"])

    # 10) Grupacija i satna agregacija:
    #     - po regionu ("Name") i satu (UTC) uzmi prosjek od 5-min vrijednosti
    g = (
        df.groupby(["Name", "ts_hour_utc"])["Load"]
          .mean()
          .reset_index()
          .rename(columns={"Name": "region", "Load": "load_mw", "ts_hour_utc": "ts"})
    )

    # 11) Ako je sve odbačeno tokom čišćenja – javi korisniku
    if g.empty:
        return _response_error("No usable rows after cleaning")

    # 12) Ukloni eventualne duplikate (region, ts)
    g = g.drop_duplicates(subset=["region", "ts"])

    # 13) Pretvori AWARE UTC → NAIVE UTC (bez tzinfo) radi stabilnih Mongo indeksa
    g["ts"] = g["ts"].apply(aware_to_naive_utc)

    # 14) Bulk upsert priprema – za svaki red napravi UpdateOne sa upsert=True
    ops = []
    for _, row in g.iterrows():
        ops.append(
            UpdateOne(
                {"region": row["region"], "ts": pd.to_datetime(row["ts"]).to_pydatetime()},
                {"$set": {
                    "region": row["region"],
                    "ts": pd.to_datetime(row["ts"]).to_pydatetime(),
                    "load_mw": float(row["load_mw"])
                }},
                upsert=True
            )
        )

    # 15) Izvrši bulk_write ne-ordered (brže; preskače konflikte gdje može)
    res = None
    if ops:
        try:
            res = db.series_load_hourly.bulk_write(
                ops, ordered=False, bypass_document_validation=True
            )
        except Exception as e:
            return _response_error(f"Mongo bulk_write error: {e}")

    # 16) Pripremi povratnu informaciju o importu (opseg vremena, broj regiona, itd.)
    regions = sorted(g["region"].unique().tolist())
    ts_min, ts_max = pd.to_datetime(g["ts"]).min(), pd.to_datetime(g["ts"]).max()

    # 17) JSON odgovor sa metrikama i statistikama upisa
    return jsonify({
        "ok": True,
        "file": f.filename,
        "regions": regions,
        "rows_input": int(before_rows),        # koliko je došlo
        "rows_hourly": int(g.shape[0]),        # koliko satnih zapisa je nastalo
        "ts_range": {"from": ts_min.isoformat(), "to": ts_max.isoformat()},
        "upserts": getattr(res, 'upserted_count', 0) if res else 0,
        "modified": getattr(res, 'modified_count', 0) if res else 0
    })

# ---------- WEATHER IMPORT (hourly → hourly mean by hour) ----------

@api_bp.post("/import/weather")
def import_weather_csv():
    db = get_db()
    ensure_indexes(db)

    if "file" not in request.files:
        return _response_error("Missing 'file' in form-data")

    f = request.files["file"]

    try:
        df = pd.read_csv(f, low_memory=False)
    except Exception as e:
        return _response_error(f"CSV parse error: {e}")

    if df.empty or df.shape[1] == 0:
        return _response_error("Empty CSV or no columns")

    # Header normalizacija (trim, lower)
    original_cols = df.columns.tolist()
    df.columns = [c.strip() for c in df.columns]
    lower_map = {c: c.lower() for c in df.columns}
    df.rename(columns=lower_map, inplace=True)

    # aliasi
    rename_map = {
        "date time": "datetime",
        "timestamp": "datetime",
        "time": "datetime",
        "city": "name",
        "location": "name",
    }
    for src, dst in rename_map.items():
        if src in df.columns and dst not in df.columns:
            df.rename(columns={src: dst}, inplace=True)

    # validacija obaveznih
    required = ["datetime", "name"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return _response_error(f"Missing columns: {missing}. Seen columns={list(df.columns)}")

    # čišćenje
    before_rows = len(df)
    df = df.dropna(subset=["datetime", "name"]).copy()
    df["name"] = df["name"].astype(str).str.strip()

    # u lokalno NY pa u UTC (aware)
    try:
        dt_utc = to_utc_series_localized(df["datetime"])
    except Exception as e:
        return _response_error(f"Timezone localization error: {e}")
    df = df.loc[dt_utc.index].copy()
    df["ts_utc"] = dt_utc
    df["ts_hour_utc"] = utc_floor_hour(df["ts_utc"])

    # kolone koje NE tretiramo kao numeriku
    exclude_cols = {"datetime", "name", "ts_utc", "ts_hour_utc", "preciptype", "conditions"}
    candidate_cols = [c for c in df.columns if c not in exclude_cols]

    # numeričke kolone kroz coercion
    numeric_cols = []
    for c in candidate_cols:
        coerced = pd.to_numeric(df[c], errors="coerce")
        if coerced.notna().any():
            df[c] = coerced
            numeric_cols.append(c)

    if not numeric_cols:
        return _response_error("No numeric columns detected (after coercion)")

    # agregacija mean po satu i lokaciji
    agg = {c: "mean" for c in numeric_cols}
    g = (
        df.groupby(["name", "ts_hour_utc"])
          .agg(agg)
          .reset_index()
          .rename(columns={"name": "location", "ts_hour_utc": "ts"})
    )

    if g.empty:
        return _response_error("No usable rows after cleaning/grouping")

    # deduplikacija
    g = g.drop_duplicates(subset=["location", "ts"])

    # NAIVE UTC za Mongo
    g["ts"] = g["ts"].apply(aware_to_naive_utc)

    # bulk upsert
    ops = []
    for _, row in g.iterrows():
        doc = {
            "location": row["location"],
            "ts": pd.to_datetime(row["ts"]).to_pydatetime(),  # naive UTC
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
            res = db.series_weather_hourly.bulk_write(
                ops, ordered=False, bypass_document_validation=True
            )
        except Exception as e:
            return _response_error(f"Mongo bulk_write error: {e}")

    locations = sorted(g["location"].unique().tolist())
    ts_min, ts_max = pd.to_datetime(g["ts"]).min(), pd.to_datetime(g["ts"]).max()

    return jsonify({
        "ok": True,
        "file": f.filename,
        "locations": locations,
        "rows_input": int(before_rows),
        "rows_hourly": int(g.shape[0]),
        "ts_range": {"from": ts_min.isoformat(), "to": ts_max.isoformat()},
        "upserts": getattr(res, "upserted_count", 0) if res else 0,
        "modified": getattr(res, "modified_count", 0) if res else 0,
        "detected_numeric_columns": numeric_cols,
        "all_columns_seen": list(df.columns),
    })
