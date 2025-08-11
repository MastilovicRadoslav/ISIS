from flask import request, jsonify
from . import api_bp
from db import get_db
from bson import ObjectId
import pandas as pd
import numpy as np


def _mape(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = np.where(np.abs(y_true) < 1e-6, 1.0, np.abs(y_true))
    return float(np.mean(np.abs((y_true - y_pred) / denom)) * 100.0)

@api_bp.get('/metrics/mape/for-forecast')
def mape_for_forecast():
    """
    Params:
      forecast_id: ID prognoze
    Vraća MAPE za dio perioda gdje postoje ostvarenja (series_load_hourly).
    """
    fid = request.args.get('forecast_id')
    if not fid:
        return jsonify({"ok": False, "error": "forecast_id required"}), 400

    db = get_db()
    f = db.forecasts.find_one({"_id": ObjectId(fid)})
    if not f:
        return jsonify({"ok": False, "error": "forecast not found"}), 404

    region = f['region']
    vals = f.get('values', [])
    if not vals:
        return jsonify({"ok": False, "error": "empty forecast"}), 400

    # Raspon prognoze
    ts_from = min(v['ts'] for v in vals)
    ts_to = max(v['ts'] for v in vals)

    # Učitaj actual za region u tom intervalu
    cur = db.series_load_hourly.find({
        'region': region,
        'ts': { '$gte': ts_from, '$lte': ts_to }
    }, { '_id': 0, 'ts': 1, 'load_mw': 1 }).sort('ts', 1)
    adf = pd.DataFrame(list(cur))

    if adf.empty:
        return jsonify({"ok": True, "forecast_id": fid, "region": region, "points": 0, "mape": None})

    fdf = pd.DataFrame(vals)
    # Join po satu (pretpostavljamo da su timestamps već na satnom nivou)
    j = fdf.merge(adf, how='inner', on='ts')
    if j.empty:
        return jsonify({"ok": True, "forecast_id": fid, "region": region, "points": 0, "mape": None})

    mape = _mape(j['load_mw'].values, j['yhat'].values)

    return jsonify({
        "ok": True,
        "forecast_id": fid,
        "region": region,
        "points": int(j.shape[0]),
        "from": j['ts'].min().isoformat(),
        "to": j['ts'].max().isoformat(),
        "mape": mape
    })