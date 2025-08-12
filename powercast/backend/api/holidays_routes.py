import re
import pandas as pd
from flask import request, jsonify
from . import api_bp
from db import get_db
from pymongo import UpdateOne, ASCENDING
from pytz import timezone, UTC

NY_TZ = timezone("America/New_York")
YEAR_RE = re.compile(r"^\s*(19|20)\d{2}\s*$")
MDY_RE  = re.compile(r"^\s*(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\s*$")  # MM/DD ili MM-DD (+ opcionalna godina)

@api_bp.post("/import/holidays")
def import_holidays():
    db = get_db()
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Missing 'file' in form-data"}), 400

    f = request.files["file"]
    try:
        if f.filename.lower().endswith((".xlsx", ".xls")):
            df_raw = pd.read_excel(f, header=None, dtype=str)
        else:
            df_raw = pd.read_csv(f, header=None, dtype=str)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Parse error: {e}"}), 400

    if df_raw.shape[1] < 3:
        return jsonify({"ok": False, "error": "Unexpected file format (min 3 kolone)"}), 400

    df_raw = df_raw.fillna("").applymap(lambda x: x.strip() if isinstance(x, str) else x)

    curr_year = None
    rows = []

    for _, row in df_raw.iterrows():
        c0 = row[0] if len(row) > 0 else ""
        c1 = row[1] if len(row) > 1 else ""
        c2 = row[2] if len(row) > 2 else ""   # kolona sa datumom
        c3 = row[3] if len(row) > 3 else ""   # kolona sa imenom praznika

        # 1) Header red: samo godina u prvoj koloni, ostalo prazno
        if c0 and YEAR_RE.match(c0) and (c1 == "" and c2 == "" and c3 == ""):
            curr_year = int(c0)
            continue

        # Bez aktivne godine ne radimo ništa (dok ne naiđe prvi header)
        if curr_year is None:
            continue

        if not c2:
            continue  # nema datuma

        date_txt = c2

        # 2) Eksplicitno IGNORIŠI godinu u datumu i koristi curr_year
        #    Prihvatamo MM/DD, MM-DD, MM/DD/YYYY, itd. — u svakom slučaju uzimamo MM i DD,
        #    a godinu postavljamo na curr_year.
        m = MDY_RE.match(c2)
        if m:
            mm = m.group(1).zfill(2)
            dd = m.group(2).zfill(2)
            date_txt = f"{curr_year}-{mm}-{dd}"
        else:
            # Ako format nije MM/DD ili MM-DD, pokušaj parsirati pa zamijeni godinu na curr_year
            dt_try = pd.to_datetime(c2, errors="coerce")
            if pd.isna(dt_try):
                continue
            # Zamijeni godinu
            try:
                dt_try = dt_try.replace(year=curr_year)
            except ValueError:
                # npr. 29. februar kad curr_year nije prestupna — preskoči
                continue
            date_txt = dt_try.strftime("%Y-%m-%d")

        # Konačni parse
        dt = pd.to_datetime(date_txt, errors="coerce")
        if pd.isna(dt):
            continue

        rows.append({
            "DateLocal": dt,                     # naive lokalni kalendarski datum (bez tz)
            "Name": (c3 or str(dt.date())).strip(),
            "Region": "US",
            "is_holiday": True
        })

    if not rows:
        return jsonify({"ok": False, "error": "Nema validnih redova"}), 400

    df = pd.DataFrame(rows)

    # Lokalno NY -> UTC -> 00:00 UTC (dnevni ključ)
    dates_local = pd.to_datetime(df["DateLocal"]).dt.tz_localize(
        NY_TZ, ambiguous="infer", nonexistent="shift_forward"
    )
    dates_utc_midnight = dates_local.dt.tz_convert(UTC).dt.normalize()

    out = pd.DataFrame({
        "DateUTC": dates_utc_midnight,
        "Name": df["Name"].astype(str),
        "Region": df["Region"],
        "is_holiday": True
    })

    # Naive UTC za Mongo ključ (stabilno, bez tz)
    out["Date"] = out["DateUTC"].dt.tz_localize(None)
    out = out.drop(columns=["DateUTC"])

    # Unique index (Region, Date)
    try:
        db.holidays.create_index([("Region", ASCENDING), ("Date", ASCENDING)], unique=True)
    except Exception:
        pass

    ops = [
        UpdateOne(
            {"Region": r["Region"], "Date": pd.to_datetime(r["Date"]).to_pydatetime()},
            {"$set": {
                "Region": r["Region"],
                "Date": pd.to_datetime(r["Date"]).to_pydatetime(),
                "Name": r["Name"],
                "is_holiday": True
            }},
            upsert=True
        )
        for _, r in out.iterrows()
    ]

    res = None
    if ops:
        try:
            res = db.holidays.bulk_write(ops, ordered=False, bypass_document_validation=True)
        except Exception as e:
            return jsonify({"ok": False, "error": f"Mongo bulk_write error: {e}"}), 400

    # Tiho, kratak sažetak
    date_min = out["Date"].min()
    date_max = out["Date"].max()
    return jsonify({
        "ok": True,
        "file": f.filename,
        "rows": int(out.shape[0]),
        "regions": sorted(out["Region"].unique().tolist()),
        "range": {
            "from_utc": date_min.isoformat() + "Z",
            "to_utc": date_max.isoformat() + "Z"
        },
        "upserts": getattr(res, "upserted_count", 0) if res else 0,
        "modified": getattr(res, "modified_count", 0) if res else 0
    })
