from flask import request, jsonify
from . import api_bp
from db import get_db
from pymongo import ASCENDING

INDEXED = {
    "series_load_hourly": False,
    "series_weather_hourly": False,
    "holidays": False,
}

def ensure_indexes(db):
    global INDEXED
    try:
        if not INDEXED["series_load_hourly"] and "series_load_hourly" in db.list_collection_names():
            db.series_load_hourly.create_index([("region", ASCENDING), ("ts", ASCENDING)], unique=True)
            INDEXED["series_load_hourly"] = True
    except Exception:
        INDEXED["series_load_hourly"] = True

    try:
        if not INDEXED["series_weather_hourly"] and "series_weather_hourly" in db.list_collection_names():
            db.series_weather_hourly.create_index([("location", ASCENDING), ("ts", ASCENDING)], unique=True)
            INDEXED["series_weather_hourly"] = True
    except Exception:
        INDEXED["series_weather_hourly"] = True

    try:
        if not INDEXED["holidays"] and "holidays" in db.list_collection_names():
            db.holidays.create_index([("Region", ASCENDING), ("Date", ASCENDING)], unique=True)
            INDEXED["holidays"] = True
    except Exception:
        INDEXED["holidays"] = True


@api_bp.get("/series/coverage")
def coverage():
    """
    Query params:
      type=load|weather|holidays
      keys=comma,separated (opciono)
    """
    db = get_db()
    ensure_indexes(db)

    t = request.args.get("type", "").lower()
    keys_param = request.args.get("keys", None)

    if t not in ("load", "weather", "holidays"):
        return jsonify({"ok": False, "error": "param 'type' mora biti 'load', 'weather' ili 'holidays'"}), 400

    if t == "load":
        coll = db.series_load_hourly
        group_key = "$region"
        out_key_name = "region"
        time_field = "$ts"
        count_field_name = "hours"
        match = {"region": {"$in": [k.strip() for k in keys_param.split(",")]}} if keys_param else {}
    elif t == "weather":
        coll = db.series_weather_hourly
        group_key = "$location"
        out_key_name = "location"
        time_field = "$ts"
        count_field_name = "hours"
        match = {"location": {"$in": [k.strip() for k in keys_param.split(",")]}} if keys_param else {}
    else:
        coll = db.holidays
        group_key = "$Region"
        out_key_name = "region"
        time_field = "$Date"
        count_field_name = "days"
        match = {"Region": {"$in": [k.strip() for k in keys_param.split(",")]}} if keys_param else {}

    pipeline = []
    if match:
        pipeline.append({"$match": match})

    pipeline += [
        {"$group": {
            "_id": group_key,
            "from": {"$min": time_field},
            "to": {"$max": time_field},
            count_field_name: {"$sum": 1}
        }},
        {"$project": {
            "_id": 0,
            out_key_name: "$_id",
            # zaštita ako from/to fali (teoretski)
            "from": {
                "$cond": [
                    {"$ifNull": ["$from", False]},
                    {"$dateToString": {"format": "%Y-%m-%dT%H:%M:%SZ", "date": "$from"}},
                    None
                ]
            },
            "to": {
                "$cond": [
                    {"$ifNull": ["$to", False]},
                    {"$dateToString": {"format": "%Y-%m-%dT%H:%M:%SZ", "date": "$to"}},
                    None
                ]
            },
            count_field_name: 1
        }},
        {"$sort": {out_key_name: 1}}
    ]

    docs = list(coll.aggregate(pipeline, allowDiskUse=True))
    return jsonify({"ok": True, "type": t, "coverage": docs})


@api_bp.get("/series/coverage/summary")
def coverage_summary():
    db = get_db()
    ensure_indexes(db)

    def summarize(coll_name, key_field, time_field, count_label):
        if coll_name not in db.list_collection_names():
            return {"exists": False, "from": None, "to": None, count_label: 0, "keys": 0}
        coll = db[coll_name]

        agg_range = list(coll.aggregate([
            {"$group": {"_id": None, "from": {"$min": f"${time_field}"}, "to": {"$max": f"${time_field}"}, count_label: {"$sum": 1}}},
            {"$project": {"_id": 0, "from": 1, "to": 1, count_label: 1}}
        ], allowDiskUse=True))

        agg_keys = list(coll.aggregate([
            {"$group": {"_id": f"${key_field}"}},
            {"$count": "keys"}
        ], allowDiskUse=True))

        res = {"exists": True}
        if agg_range:
            res.update({
                "from": agg_range[0]["from"].isoformat() if agg_range[0]["from"] else None,
                "to": agg_range[0]["to"].isoformat() if agg_range[0]["to"] else None,
                count_label: agg_range[0][count_label]
            })
        else:
            res.update({"from": None, "to": None, count_label: 0})
        res["keys"] = (agg_keys[0]["keys"] if agg_keys else 0)
        return res

    return jsonify({
        "ok": True,
        "load": summarize("series_load_hourly", "region", "ts", "hours"),
        "weather": summarize("series_weather_hourly", "location", "ts", "hours"),
        "holidays": summarize("holidays", "Region", "Date", "days"),
    })
