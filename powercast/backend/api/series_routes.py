from flask import request, jsonify
from . import api_bp
from db import get_db
from pymongo import ASCENDING

# ako pokrenemo coverage pre importa, osigurajmo indekse
INDEXED = {
    "series_load_hourly": False,
    "series_weather_hourly": False,
    "holidays": False,
}

def ensure_indexes(db):
    global INDEXED
    if not INDEXED["series_load_hourly"] and "series_load_hourly" in db.list_collection_names():
        db.series_load_hourly.create_index([("region", ASCENDING), ("ts", ASCENDING)], unique=True)
        INDEXED["series_load_hourly"] = True
    if not INDEXED["series_weather_hourly"] and "series_weather_hourly" in db.list_collection_names():
        db.series_weather_hourly.create_index([("location", ASCENDING), ("ts", ASCENDING)], unique=True)
        INDEXED["series_weather_hourly"] = True
    if not INDEXED["holidays"] and "holidays" in db.list_collection_names():
        db.holidays.create_index([("Region", ASCENDING), ("Date", ASCENDING)], unique=True)
        INDEXED["holidays"] = True


@api_bp.get("/series/coverage")
def coverage():
    """
    Query params:
      type=load|weather|holidays   (obavezno)
      keys=comma,separated,list   (opciono)
        - za load: 'keys' su regioni (npr. N.Y.C., LONGIL)
        - za weather: 'keys' su locations (npr. New York City, NY)
        - za holidays: 'keys' su Region vrijednosti (npr. US)
    """
    db = get_db()
    ensure_indexes(db)

    t = request.args.get("type", "").lower()
    keys_param = request.args.get("keys", None)

    if t not in ("load", "weather", "holidays"):
        return jsonify({"ok": False, "error": "param 'type' mora biti 'load', 'weather' ili 'holidays'"}), 400

    match = {}
    pipeline = []

    if t == "load":
        coll = db.series_load_hourly
        group_key = "$region"
        out_key_name = "region"
        if keys_param:
            keys = [k.strip() for k in keys_param.split(",") if k.strip()]
            match = {"region": {"$in": keys}}
        time_field = "$ts"
        # hours = count dokumenata (satnih tačaka)
        project_extra = {"hours": 1}
        rename_count_field = ("hours", "hours")

    elif t == "weather":
        coll = db.series_weather_hourly
        group_key = "$location"
        out_key_name = "location"
        if keys_param:
            keys = [k.strip() for k in keys_param.split(",") if k.strip()]
            match = {"location": {"$in": keys}}
        time_field = "$ts"
        project_extra = {"hours": 1}
        rename_count_field = ("hours", "hours")

    else:  # holidays
        coll = db.holidays
        group_key = "$Region"
        out_key_name = "region"
        if keys_param:
            keys = [k.strip() for k in keys_param.split(",") if k.strip()]
            match = {"Region": {"$in": keys}}
        time_field = "$Date"
        # days = count dokumenata (dnevne tačke)
        project_extra = {"days": 1}
        rename_count_field = ("days", "days")

    if match:
        pipeline.append({"$match": match})

    pipeline += [
        {"$group": {
            "_id": group_key,
            "from": {"$min": time_field},
            "to": {"$max": time_field},
            rename_count_field[0]: {"$sum": 1}
        }},
        {"$project": {
            "_id": 0,
            out_key_name: "$_id",
            "from": {"$dateToString": {"format": "%Y-%m-%dT%H:%M:%SZ", "date": "$from"}},
            "to": {"$dateToString": {"format": "%Y-%m-%dT%H:%M:%SZ", "date": "$to"}},
            **project_extra
        }},
        {"$sort": {out_key_name: 1}}
    ]

    docs = list(coll.aggregate(pipeline))
    return jsonify({"ok": True, "type": t, "coverage": docs})


@api_bp.get("/series/coverage/summary")
def coverage_summary():
    """
    Vraća globalni min/max i count za load (hours), weather (hours) i holidays (days).
    """
    db = get_db()
    ensure_indexes(db)

    def summarize(coll_name, key_field, time_field, count_label):
        if coll_name not in db.list_collection_names():
            return {"exists": False, "from": None, "to": None, count_label: 0, "keys": 0}
        coll = db[coll_name]
        agg1 = list(coll.aggregate([
            {"$group": {"_id": None, "from": {"$min": f"${time_field}"}, "to": {"$max": f"${time_field}"}, count_label: {"$sum": 1}}},
            {"$project": {"_id": 0, "from": 1, "to": 1, count_label: 1}}
        ]))
        agg2 = list(coll.aggregate([
            {"$group": {"_id": f"${key_field}"}},
            {"$count": "keys"}
        ]))
        res = {"exists": True}
        if agg1:
            res.update({
                "from": agg1[0]["from"].isoformat() if agg1[0]["from"] else None,
                "to": agg1[0]["to"].isoformat() if agg1[0]["to"] else None,
                count_label: agg1[0][count_label]
            })
        else:
            res.update({"from": None, "to": None, count_label: 0})
        res["keys"] = (agg2[0]["keys"] if agg2 else 0)
        return res

    return jsonify({
        "ok": True,
        "load": summarize("series_load_hourly", "region", "ts", "hours"),
        "weather": summarize("series_weather_hourly", "location", "ts", "hours"),
        "holidays": summarize("holidays", "Region", "Date", "days"),
    })
