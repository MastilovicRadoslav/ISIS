from flask import request, jsonify
from . import api_bp
from db import get_db
from pymongo import ASCENDING

# Cache-flagovi kako se ne bi kreirali indeksi više puta tokom istog procesa
INDEXED = {
    "series_load_hourly": False,
    "series_weather_hourly": False,
    "holidays": False,
}

def ensure_indexes(db):
    """
    Idempotentno kreiranje unikantnih indeksa po kolekcijama,
    ali samo ako kolekcija postoji i indeks još nije kreiran u ovom procesu.
    """
    global INDEXED
    try:
        # LOAD kolekcija: jedinstven par (region, ts)
        if not INDEXED["series_load_hourly"] and "series_load_hourly" in db.list_collection_names():
            db.series_load_hourly.create_index([("region", ASCENDING), ("ts", ASCENDING)], unique=True)
            INDEXED["series_load_hourly"] = True
    except Exception:
        # Ako dođe do greške (npr. indeks već postoji), pretpostavi da je sve ok
        INDEXED["series_load_hourly"] = True

    try:
        # WEATHER kolekcija: jedinstven par (location, ts)
        if not INDEXED["series_weather_hourly"] and "series_weather_hourly" in db.list_collection_names():
            db.series_weather_hourly.create_index([("location", ASCENDING), ("ts", ASCENDING)], unique=True)
            INDEXED["series_weather_hourly"] = True
    except Exception:
        INDEXED["series_weather_hourly"] = True

    try:
        # HOLIDAYS kolekcija: jedinstven par (Region, Date)
        if not INDEXED["holidays"] and "holidays" in db.list_collection_names():
            db.holidays.create_index([("Region", ASCENDING), ("Date", ASCENDING)], unique=True)
            INDEXED["holidays"] = True
    except Exception:
        INDEXED["holidays"] = True


@api_bp.get("/series/coverage")
def coverage():
    """
    API: GET /series/coverage
    Query parametri:
      - type=load|weather|holidays  (obavezno: koju seriju pokrivenosti želiš)
      - keys=comma,separated        (opciono: filtriraj samo za dati skup ključeva)
    Vraća po ključu (region/location/Region) minimalni i maksimalni datum i broj zapisa.
    """
    db = get_db()
    ensure_indexes(db)  # osiguraj da postoje indeksi

    # Validacija tipa serije
    t = request.args.get("type", "").lower()
    keys_param = request.args.get("keys", None)

    if t not in ("load", "weather", "holidays"):
        return jsonify({"ok": False, "error": "param 'type' mora biti 'load', 'weather' ili 'holidays'"}), 400

    # Odabir kolekcije i polja po tipu serije
    if t == "load":
        coll = db.series_load_hourly
        group_key = "$region"          # grupišemo po regionu
        out_key_name = "region"        # naziv izlaznog polja
        time_field = "$ts"             # vremensko polje
        count_field_name = "hours"     # naziv brojčanog polja u izlazu
        # Opcioni $match filter po listi regiona
        match = {"region": {"$in": [k.strip() for k in keys_param.split(",")]}} if keys_param else {}
    elif t == "weather":
        coll = db.series_weather_hourly
        group_key = "$location"
        out_key_name = "location"
        time_field = "$ts"
        count_field_name = "hours"
        match = {"location": {"$in": [k.strip() for k in keys_param.split(",")]}} if keys_param else {}
    else:
        # holidays (dnevna serija)
        coll = db.holidays
        group_key = "$Region"
        out_key_name = "region"
        time_field = "$Date"
        count_field_name = "days"
        match = {"Region": {"$in": [k.strip() for k in keys_param.split(",")]}} if keys_param else {}

    # Sastavi agregacioni pipeline:
    pipeline = []
    if match:
        pipeline.append({"$match": match})  # filtriraj po ključevima ako su dati

    pipeline += [
        # Grupisanje po ključu uz minimalni i maksimalni datum i brojanje dokumenata
        {"$group": {
            "_id": group_key,
            "from": {"$min": time_field},
            "to": {"$max": time_field},
            count_field_name: {"$sum": 1}
        }},
        # Project: preimenuj polja i formatiraj datume u ISO string (ako postoje)
        {"$project": {
            "_id": 0,
            out_key_name: "$_id",
            # Zaštita: ako from/to ne postoje, stavi None
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
        # Sortiraj po ključu radi urednog ispisa
        {"$sort": {out_key_name: 1}}
    ]

    # Izvrši agregaciju i vrati rezultat
    docs = list(coll.aggregate(pipeline, allowDiskUse=True))
    return jsonify({"ok": True, "type": t, "coverage": docs})


@api_bp.get("/series/coverage/summary")
def coverage_summary():
    """
    API: GET /series/coverage/summary
    Sažetak po svakoj kolekciji:
      - da li kolekcija postoji
      - globalni 'from' i 'to'
      - ukupan broj zapisa (hours/days)
      - broj jedinstvenih ključeva (region/location/Region)
    """
    db = get_db()
    ensure_indexes(db)

    def summarize(coll_name, key_field, time_field, count_label):
        """
        Helper: za zadatu kolekciju vrati info:
          exists, from, to, total_count (count_label), keys (broj jedinstvenih ključeva)
        """
        # Ako kolekcija ne postoji u bazi, vrati "prazan" sažetak
        if coll_name not in db.list_collection_names():
            return {"exists": False, "from": None, "to": None, count_label: 0, "keys": 0}

        coll = db[coll_name]

        # 1) Globalni raspon datuma i ukupan broj dokumenata
        agg_range = list(coll.aggregate([
            {"$group": {
                "_id": None,
                "from": {"$min": f"${time_field}"},
                "to": {"$max": f"${time_field}"},
                count_label: {"$sum": 1}
            }},
            {"$project": {"_id": 0, "from": 1, "to": 1, count_label: 1}}
        ], allowDiskUse=True))

        # 2) Broj jedinstvenih ključeva (npr. regiona/locations)
        agg_keys = list(coll.aggregate([
            {"$group": {"_id": f"${key_field}"}},
            {"$count": "keys"}
        ], allowDiskUse=True))

        # Sastavi odgovor
        res = {"exists": True}
        if agg_range:
            res.update({
                # isoformat() pretvara Python datetime u ISO 8601 string; ako je None, vrati None
                "from": agg_range[0]["from"].isoformat() if agg_range[0]["from"] else None,
                "to": agg_range[0]["to"].isoformat() if agg_range[0]["to"] else None,
                count_label: agg_range[0][count_label]
            })
        else:
            # Ako agregacija ne vrati ništa (prazna kolekcija)
            res.update({"from": None, "to": None, count_label: 0})

        # Koliko ima jedinstvenih vrijednosti ključa
        res["keys"] = (agg_keys[0]["keys"] if agg_keys else 0)
        return res

    # Sažetak za sve tri serije (load/weather satni, holidays dnevni)
    return jsonify({
        "ok": True,
        "load": summarize("series_load_hourly", "region", "ts", "hours"),
        "weather": summarize("series_weather_hourly", "location", "ts", "hours"),
        "holidays": summarize("holidays", "Region", "Date", "days"),
    })
