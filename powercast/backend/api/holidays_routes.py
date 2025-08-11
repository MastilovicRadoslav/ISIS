import pandas as pd
from flask import request, jsonify
from . import api_bp
from db import get_db
from pymongo import UpdateOne, ASCENDING

@api_bp.post("/import/holidays")
def import_holidays():
    db = get_db()
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Missing 'file' in form-data"}), 400
    f = request.files["file"]

    try:
        if f.filename.lower().endswith((".xlsx", ".xls")):
            df_raw = pd.read_excel(f, header=None)
        else:
            df_raw = pd.read_csv(f, header=None)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Parse error: {e}"}), 400

    # Očekujemo format: Godina | DayName | Date | HolidayName
    if df_raw.shape[1] < 4:
        return jsonify({"ok": False, "error": "Unexpected file format"}), 400

    df = pd.DataFrame({
        "Date": pd.to_datetime(df_raw[2], errors="coerce").dt.normalize(),
        "Name": df_raw[3].astype(str).str.strip(),
        "Region": "US"
    })

    df = df.dropna(subset=["Date"]).copy()

    # Upsert po (Region, Date)
    ops = []
    db.holidays.create_index([("Region", ASCENDING), ("Date", ASCENDING)], unique=True)
    for _, r in df.iterrows():
        ops.append(UpdateOne(
            {"Region": r["Region"], "Date": r["Date"].to_pydatetime()},
            {"$set": {
                "Region": r["Region"],
                "Date": r["Date"].to_pydatetime(),
                "Name": str(r["Name"])
            }},
            upsert=True
        ))
    if ops:
        db.holidays.bulk_write(ops, ordered=False)

    return jsonify({
        "ok": True,
        "rows": int(df.shape[0]),
        "regions": sorted(df["Region"].unique().tolist())
    })
