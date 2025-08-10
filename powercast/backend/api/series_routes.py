from flask import request, jsonify
from . import api_bp
from db import get_db
from pymongo import ASCENDING

# ako pokrenemo coverage pre importa, osigurajmo indekse
INDEXED = {"series_load_hourly": False, "series_weather_hourly": False}

def ensure_indexes(db):
    global INDEXED
    if not INDEXED["series_load_hourly"] and "series_load_hourly" in db.list_collection_names():
        db.series_load_hourly.create_index([("region", ASCENDING), ("ts", ASCENDING)], unique=True)
        INDEXED["series_load_hourly"] = True
    if not INDEXED["series_weather_hourly"] and "series_weather_hourly" in db.list_collection_names():
        db.series_weather_hourly.create_index([("location", ASCENDING), ("ts", ASCENDING)], unique=True)
        INDEXED["series_weather_hourly"] = True


@api_bp.get("/series/coverage")
def coverage():
    """
    Query params:
      type=load|weather   (obavezno)
      keys=comma,separated,list   (opciono)
        - za load: 'keys' su regioni (npr. N.Y.C., LONGIL)
        - za weather: 'keys' su locations (npr. New York City, NY)
    """
    db = get_db()
    ensure_indexes(db)

    t = request.args.get("type", "").lower()
    keys_param = request.args.get("keys", None)

    if t not in ("load", "weather"):
        return jsonify({"ok": False, "error": "param 'type' mora biti 'load' ili 'weather'"}), 400

    if t == "load":
        coll = db.series_load_hourly
        group_key = "$region"
        out_key_name = "region"
        match = {}
        if keys_param:
            keys = [k.strip() for k in keys_param.split(",") if k.strip()]
            match = {"region": {"$in": keys}}
    else:
        coll = db.series_weather_hourly
        group_key = "$location"
        out_key_name = "location"
        match = {}
        if keys_param:
            keys = [k.strip() for k in keys_param.split(",") if k.strip()]
            match = {"location": {"$in": keys}}

    pipeline = []
    if match:
        pipeline.append({"$match": match})
    pipeline += [
        {"$group": {
            "_id": group_key,
            "from": {"$min": "$ts"},
            "to": {"$max": "$ts"},
            "hours": {"$sum": 1}
        }},
        {"$project": {
            "_id": 0,
            out_key_name: "$_id",
            "from": {"$dateToString": {"format": "%Y-%m-%dT%H:%M:%SZ", "date": "$from"}},
            "to": {"$dateToString": {"format": "%Y-%m-%dT%H:%M:%SZ", "date": "$to"}},
            "hours": 1
        }},
        {"$sort": {out_key_name: 1}}
    ]

    docs = list(coll.aggregate(pipeline))
    return jsonify({"ok": True, "type": t, "coverage": docs})


@api_bp.get("/series/coverage/summary")
def coverage_summary():
    """
    Vraća globalni min/max i broj sati za load i weather odvojeno.
    """
    db = get_db()
    ensure_indexes(db)

    def summarize(coll_name, key_field):
        if coll_name not in db.list_collection_names():
            return {"exists": False, "from": None, "to": None, "hours": 0, "keys": 0}
        coll = db[coll_name]
        # global min/max + count
        agg1 = list(coll.aggregate([
            {"$group": {"_id": None, "from": {"$min": "$ts"}, "to": {"$max": "$ts"}, "hours": {"$sum": 1}}},
            {"$project": {"_id": 0, "from": 1, "to": 1, "hours": 1}}
        ]))
        # broj različitih ključeva (region/location)
        agg2 = list(coll.aggregate([
            {"$group": {"_id": f"${key_field}"}},
            {"$count": "keys"}
        ]))
        res = {"exists": True}
        if agg1:
            res.update({
                "from": agg1[0]["from"].isoformat() if agg1[0]["from"] else None,
                "to": agg1[0]["to"].isoformat() if agg1[0]["to"] else None,
                "hours": agg1[0]["hours"]
            })
        else:
            res.update({"from": None, "to": None, "hours": 0})
        res["keys"] = (agg2[0]["keys"] if agg2 else 0)
        return res

    return jsonify({
        "ok": True,
        "load": summarize("series_load_hourly", "region"),
        "weather": summarize("series_weather_hourly", "location")
    })
