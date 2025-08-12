from flask import request, jsonify
from . import api_bp
from db import get_db
from bson import ObjectId
import pandas as pd
import numpy as np

def _to_naive_utc_series(s):
    # bilo koji ulaz -> aware UTC -> NAIVE UTC
    s = pd.to_datetime(s, errors="coerce", utc=True)
    s = s.dt.tz_convert("UTC").dt.tz_localize(None)
    return s

def _mape(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = np.maximum(np.abs(y_true), 1e-6)
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

    fdf = pd.DataFrame(vals)
    if fdf.empty or 'ts' not in fdf.columns:
        return jsonify({"ok": False, "error": "invalid forecast payload"}), 400

    # normalizuj forecast ts na NAIVE UTC (safety) i na pun sat
    fdf['ts'] = _to_naive_utc_series(fdf['ts']).dt.floor('h')
    fdf = fdf.dropna(subset=['ts']).drop_duplicates(subset=['ts']).sort_values('ts')

    ts_from = fdf['ts'].min()
    ts_to   = fdf['ts'].max()

    # učitaj actual u tom intervalu
    cur = db.series_load_hourly.find(
        {'region': region, 'ts': {'$gte': ts_from.to_pydatetime(), '$lte': ts_to.to_pydatetime()}},
        {'_id': 0, 'ts': 1, 'load_mw': 1}
    ).sort('ts', 1)
    adf = pd.DataFrame(list(cur))
    if adf.empty:
        return jsonify({"ok": True, "forecast_id": fid, "region": region, "points": 0, "mape": None})

    # normalizuj actual ts isto
    adf['ts'] = _to_naive_utc_series(adf['ts']).dt.floor('h')
    adf = adf.dropna(subset=['ts']).drop_duplicates(subset=['ts']).sort_values('ts')

    # inner join po satu
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
