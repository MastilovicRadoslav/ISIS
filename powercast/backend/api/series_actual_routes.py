from flask import request, jsonify
from . import api_bp
from db import get_db
from datetime import datetime

@api_bp.get('/series/actual')
def series_actual():
    region = request.args.get('region')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    if not region or not date_from or not date_to:
        return jsonify({"ok": False, "error": "region, from, to are required"}), 400

    db = get_db()
    df = datetime.fromisoformat(date_from.replace('Z','+00:00').split('+')[0])
    dt = datetime.fromisoformat(date_to.replace('Z','+00:00').split('+')[0])

    cur = db.series_load_hourly.find({
        'region': region,
        'ts': { '$gte': df, '$lte': dt }
    }, { '_id': 0, 'ts': 1, 'load_mw': 1 }).sort('ts', 1)

    items = list(cur)
    return jsonify({"ok": True, "region": region, "items": items})