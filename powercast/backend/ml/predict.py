# ml/predict.py
import io
import numpy as np
import pandas as pd
import torch
from pytz import UTC
from .features import build_feature_frame
from .utils import StandardScaler1D

def _to_naive_utc(ts_like):
    """Primljeni ISO/string/datetime -> aware UTC -> NAIVE UTC (bez tzinfo)."""
    t = pd.to_datetime(ts_like, utc=True)
    return t.tz_convert(UTC).tz_localize(None)

def load_artifact(fs, artifact_id):
    gridout = fs.get(artifact_id)
    by = gridout.read()
    data = torch.load(io.BytesIO(by), map_location="cpu")
    from .models import LSTMSeq2Seq
    model = LSTMSeq2Seq(
        feat_dim=int(data["feat_dim"]),
        hidden_size=int(data["hidden_size"]),
        num_layers=int(data["num_layers"]),
        dropout=float(data["dropout"]),
        horizon=int(data["horizon"]),
    )
    model.load_state_dict(data["state_dict"])
    model.eval()
    scaler = StandardScaler1D.from_dict(data["scaler"]) if isinstance(data.get("scaler"), dict) else None
    feat_names = data.get("feat_names", [])
    horizon = int(data["horizon"]) if "horizon" in data else 24
    saved_input_window = int(data.get("input_window", 168))
    return model, scaler, feat_names, horizon, saved_input_window

def prepare_inference_window(db, region, start_date, input_window, location_proxy="New York City, NY"):
    """
    Izvuci POSLJEDNJIH `input_window` SATI ispred start_date (ne uključujući start).
    - `ts` u bazi su NAIVE UTC -> radimo sve u NAIVE UTC.
    - Vraća striktno pun hourly grid; ako load nedostaje, prekidamo.
    """
    start = _to_naive_utc(start_date)
    hist_from = start - pd.Timedelta(hours=input_window)

    # Load (mora pokriti pun opseg)
    cur = db.series_load_hourly.find({
        "region": region,
        "ts": {"$gte": hist_from.to_pydatetime(), "$lt": start.to_pydatetime()}
    }, {"_id": 0, "ts": 1, "load_mw": 1}).sort("ts", 1)
    ldf = pd.DataFrame(list(cur))
    if ldf.empty:
        return None, "No load data in the requested window"

    ldf["ts"] = pd.to_datetime(ldf["ts"])
    ldf = ldf.drop_duplicates(subset=["ts"]).set_index("ts").sort_index()

    # Reindex na puni hourly grid
    idx = pd.date_range(hist_from, periods=input_window, freq="h")  # NAIVE UTC
    ldf = ldf.reindex(idx)

    # Ako ima rupa u load‑u → to je kritično
    if ldf["load_mw"].isna().any():
        missing = int(ldf["load_mw"].isna().sum())
        return None, f"Not enough history for input_window (missing {missing} hourly load points)."

    # Weather (dozvoljene rupe -> ffill/bfill)
    curw = db.series_weather_hourly.find({
        "location": location_proxy,
        "ts": {"$gte": hist_from.to_pydatetime(), "$lt": start.to_pydatetime()}
    }, {"_id": 0}).sort("ts", 1)
    wdf = pd.DataFrame(list(curw))
    if not wdf.empty:
        wdf["ts"] = pd.to_datetime(wdf["ts"])
        wdf = wdf.drop_duplicates(subset=["ts"]).set_index("ts").sort_index()
        wdf = wdf.reindex(idx)
        wdf = wdf.ffill().bfill()
        df = ldf.join(wdf, how="left")
    else:
        df = ldf.copy()

    df = df.reset_index().rename(columns={"index": "ts"})

    # Features (NY lokalni kalendar/praznici) — build_feature_frame očekuje NAIVE UTC `ts`
    feats = build_feature_frame(
        df.assign(ts=pd.to_datetime(df["ts"])),
        db=db,                    # usklađeno sa treningom
        holiday_region="US"
    )
    y = df["load_mw"].astype(float).values
    Xf = feats.values.astype(float)
    ts = pd.to_datetime(df["ts"]).tolist()

    out_df = pd.DataFrame({"ts": ts, "y": y}).join(pd.DataFrame(Xf, index=range(len(Xf))))
    return out_df, feats.columns.tolist()

def run_forecast(db, fs, model_doc, region, start_date, days):
    """
    Pokreće prognozu za [start_date, start_date + days*24h).
    Vraća (timestamps_naiveUTC, predictions, csv_id).
    """
    from bson import ObjectId
    import csv

    model, scaler, feat_names, horizon, saved_input_window = load_artifact(fs, ObjectId(model_doc["artifact_id"]))
    # Ako hyper ima input_window, to je prioritet; u suprotnom koristimo onaj iz artefakta
    input_window = int(model_doc.get("hyper", {}).get("input_window", saved_input_window or 168))

    # Pripremi istoriju
    prep = prepare_inference_window(db, region, start_date, input_window)
    if prep[0] is None:
        raise ValueError(prep[1])
    df, feat_cols = prep

    # Uskladi FEATURES sa onima iz treninga (iste kolone i isti redoslijed)
    y_hist = df["y"].values.astype(float)
    feats_df = df.drop(columns=["ts", "y"]).copy()
    # dodaj nule za kolone koje fale
    for c in feat_names:
        if c not in feats_df.columns:
            feats_df[c] = 0.0
    # reordnaj i odbaci viškove
    feats_df = feats_df[feat_names]
    Xf = feats_df.values.astype(float)

    # Skaliranje targeta kao na treningu
    y_s = scaler.transform(y_hist) if scaler else y_hist

    # (1, T, 1+F)
    X_all = np.concatenate([y_s[:, None], Xf], axis=1)[None, ...]
    X_all = torch.tensor(X_all, dtype=torch.float32)

    with torch.no_grad():
        yhat = model(X_all)  # (1, H)
    yhat = yhat.numpy().reshape(-1)
    if scaler:
        yhat = scaler.inverse_transform(yhat)

    # Timestamps (NAIVE UTC)
    start_naive = _to_naive_utc(start_date)
    H_req = int(days) * 24
    H = int(min(H_req, yhat.shape[0], horizon))
    ts_out = [(start_naive + pd.Timedelta(hours=i)).to_pydatetime() for i in range(H)]
    y_out = yhat[:H].astype(float).tolist()

    # CSV (UTC ISO format)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Datetime", "PredictedLoad"])
    for t, y in zip(ts_out, y_out):
        writer.writerow([pd.to_datetime(t).isoformat() + "Z", float(y)])
    data = buf.getvalue().encode("utf-8")

    csv_id = fs.put(data, filename=f"forecast_{region}_{start_naive.strftime('%Y%m%dT%H%M%S')}.csv")
    return ts_out, y_out, csv_id
