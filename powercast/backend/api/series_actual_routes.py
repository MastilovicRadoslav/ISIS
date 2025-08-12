from flask import request, jsonify
from . import api_bp
from db import get_db
import pandas as pd

def _to_naive_utc(ts_like):
    t = pd.to_datetime(ts_like, utc=True)
    return t.tz_convert("UTC").tz_localize(None)

@api_bp.get('/series/actual')
def series_actual():
    region = request.args.get('region')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    if not region or not date_from or not date_to:
        return jsonify({"ok": False, "error": "region, from, to are required"}), 400

    df = _to_naive_utc(date_from)
    dt = _to_naive_utc(date_to)

    db = get_db()
    cur = db.series_load_hourly.find({
        'region': region,
        'ts': { '$gte': df.to_pydatetime(), '$lte': dt.to_pydatetime() }
    }, { '_id': 0, 'ts': 1, 'load_mw': 1 }).sort('ts', 1)

    items = list(cur)
    return jsonify({"ok": True, "region": region, "items": items})
