import io
import numpy as np
import pandas as pd
import torch
from .features import build_feature_frame
from .utils import StandardScaler1D


def load_artifact(fs, artifact_id):
    gridout = fs.get(artifact_id)
    by = gridout.read()
    data = torch.load(io.BytesIO(by), map_location="cpu")
    # Konstruisi model
    from .models import LSTMSeq2Seq
    model = LSTMSeq2Seq(
        feat_dim=int(data["feat_dim"]),
        hidden_size=int(data["hidden_size"]),
        num_layers=int(data["num_layers"]),
        dropout=float(data["dropout"]),
        horizon=int(data["horizon"]),
    )
    model.load_state_dict(data["state_dict"])  # već CPU tensori
    model.eval()
    scaler = StandardScaler1D.from_dict(data["scaler"]) if isinstance(data.get("scaler"), dict) else None
    feat_names = data.get("feat_names", [])
    horizon = int(data["horizon"]) if "horizon" in data else 24
    return model, scaler, feat_names, horizon


def prepare_inference_window(db, region, start_date, input_window, location_proxy="New York City, NY"):
    """Izvuci poslednjih input_window sati pre start_date (ne uključujući start) i vrati dataframe
    sa kolonama: ts, y (load_mw), + weather/kalendarski kolone.
    """
    start = pd.to_datetime(start_date)
    hist_from = start - pd.Timedelta(hours=input_window)
    # Load
    cur = db.series_load_hourly.find({
        "region": region,
        "ts": {"$gte": hist_from, "$lt": start}
    }, {"_id":0, "ts":1, "load_mw":1}).sort("ts", 1)
    ldf = pd.DataFrame(list(cur))
    if ldf.shape[0] < input_window:
        return None, "Not enough history for input_window"

    # Weather (nije neophodno u dekoderu, ali u enkoderu jeste dio featura)
    curw = db.series_weather_hourly.find({
        "location": location_proxy,
        "ts": {"$gte": hist_from, "$lt": start}
    }, {"_id":0}).sort("ts", 1)
    wdf = pd.DataFrame(list(curw))

    df = ldf.copy()
    if not wdf.empty:
        df = df.merge(wdf, how="left", on="ts", suffixes=("", "_w"))

    feats = build_feature_frame(df.assign(ts=pd.to_datetime(df["ts"])) )
    y = df["load_mw"].astype(float).values
    Xf = feats.values.astype(float)
    ts = pd.to_datetime(df["ts"]).tolist()
    return pd.DataFrame({"ts": ts, "y": y}).join(pd.DataFrame(Xf, index=range(len(Xf)))), feats.columns.tolist()


def run_forecast(db, fs, model_doc, region, start_date, days):
    """Pokreni prognozu: koristi najnoviji model ili prosleđeni model_doc, generiši horizon=24..168h.
    Vraća (timestamps, predictions, artifact_id_csv).
    """
    from bson import ObjectId
    import csv

    # Ucitaj artefakt
    model, scaler, feat_names, horizon = load_artifact(fs, ObjectId(model_doc["artifact_id"]))

    # Izračunaj input_window iz modela? Nije snimljen – koristimo heuristiku: iz Train UI dolazi.
    # Pošto ga nismo sačuvali u artefaktu, za MVP uzimamo 168 (isti kao podrazumijevani).
    input_window = int(model_doc.get("hyper", {}).get("input_window", 168))

    # Pripremi prozor istorije
    prep = prepare_inference_window(db, region, start_date, input_window)
    if prep[0] is None:
        raise ValueError(prep[1])
    df, feat_cols = prep
    y_hist = df["y"].values.astype(float)
    Xf = df.drop(columns=["ts","y"]).values.astype(float)

    # Skaliraj target isto kao u treningu
    y_s = scaler.transform(y_hist) if scaler else y_hist

    # Sastavi (1, T, 1+F)
    X_all = np.concatenate([y_s[:, None], Xf], axis=1)[None, ...]
    X_all = torch.tensor(X_all, dtype=torch.float32)

    with torch.no_grad():
        yhat = model(X_all)  # (1, H)
    yhat = yhat.numpy().reshape(-1)
    if scaler:
        yhat = scaler.inverse_transform(yhat)

    # Konstrukcija timestamps za izlaz: od start_date, u satnim koracima, za days*24 sati
    H_req = int(days) * 24
    H = min(H_req, yhat.shape[0], horizon)
    start_ts = pd.to_datetime(start_date)
    ts_out = [ (start_ts + pd.Timedelta(hours=i)).to_pydatetime() for i in range(H) ]
    y_out = yhat[:H].tolist()

    # Napravi CSV u memoriji
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Datetime", "PredictedLoad"])
    for t, y in zip(ts_out, y_out):
        writer.writerow([pd.to_datetime(t).isoformat(), float(y)])
    data = buf.getvalue().encode("utf-8")
    csv_id = fs.put(data, filename=f"forecast_{region}_{start_ts.strftime('%Y%m%dT%H%M%S')}.csv")
    return ts_out, y_out, csv_id