# ml/predict.py
import io
import numpy as np
import pandas as pd
import torch
from pytz import UTC
from .features import build_feature_frame
from .utils import StandardScaler1D

def _to_naive_utc(ts_like):
    """
    Bilo koji ulaz (ISO string / datetime) → parsiraj kao AWARE UTC → pretvori u NAIVE UTC.
    Razlog: u bazi 'ts' čuvamo kao NAIVE UTC (bez tzinfo), pa ovako usklađujemo ključeve.
    """
    t = pd.to_datetime(ts_like, utc=True)
    return t.tz_convert(UTC).tz_localize(None)

def load_artifact(fs, artifact_id):
    """
    Učitaj binarni artefakt modela iz GridFS-a i rekonstruiši sve što treba za inferenciju:
      - LSTMSeq2Seq instancu sa istom arhitekturom
      - state_dict (težine)
      - StandardScaler1D (mean/std)
      - imena feature kolona i ostale meta info (horizon, input_window)
    """
    gridout = fs.get(artifact_id)
    by = gridout.read()
    data = torch.load(io.BytesIO(by), map_location="cpu")

    # Rekonstrukcija modela identičnih dimenzija kao u treningu
    from .models import LSTMSeq2Seq
    model = LSTMSeq2Seq(
        feat_dim=int(data["feat_dim"]),
        hidden_size=int(data["hidden_size"]),
        num_layers=int(data["num_layers"]),
        dropout=float(data["dropout"]),
        horizon=int(data["horizon"]),
    )
    model.load_state_dict(data["state_dict"])
    model.eval()  # eval mod za inferenciju

    # Skaler i meta
    scaler = StandardScaler1D.from_dict(data["scaler"]) if isinstance(data.get("scaler"), dict) else None
    feat_names = data.get("feat_names", [])
    horizon = int(data["horizon"]) if "horizon" in data else 24
    saved_input_window = int(data.get("input_window", 168))
    return model, scaler, feat_names, horizon, saved_input_window

def prepare_inference_window(db, region, start_date, input_window, location_proxy="New York City, NY"):
    """
    Pripremi POSLEDNJIH `input_window` sati istorije prije 'start_date' (start nije uključen).
    - Radi isključivo u NAIVE UTC (kao i u bazi).
    - Load MORA biti potpun (bez rupa); weather može imati rupe (popunjava se ffill/bfill).
    - Vraća DataFrame sa kolonom ts, y (load_mw) i svim izgrađenim feature-ima + listu imena feature-a.
    """
    start = _to_naive_utc(start_date)
    hist_from = start - pd.Timedelta(hours=input_window)

    # ---- LOAD (kritično da bude kompletan) ----
    cur = db.series_load_hourly.find({
        "region": region,
        "ts": {"$gte": hist_from.to_pydatetime(), "$lt": start.to_pydatetime()}
    }, {"_id": 0, "ts": 1, "load_mw": 1}).sort("ts", 1)
    ldf = pd.DataFrame(list(cur))
    if ldf.empty:
        return None, "No load data in the requested window"

    ldf["ts"] = pd.to_datetime(ldf["ts"])
    ldf = ldf.drop_duplicates(subset=["ts"]).set_index("ts").sort_index()

    # Poravnaj na puni hourly grid (NAIVE UTC)
    idx = pd.date_range(hist_from, periods=input_window, freq="h")
    ldf = ldf.reindex(idx)

    # Ako fali ijedan sat loada → prekini (model nema punu istoriju)
    if ldf["load_mw"].isna().any():
        missing = int(ldf["load_mw"].isna().sum())
        return None, f"Not enough history for input_window (missing {missing} hourly load points)."

    # ---- WEATHER (dozvoljene rupe → ffill/bfill) ----
    curw = db.series_weather_hourly.find({
        "location": location_proxy,
        "ts": {"$gte": hist_from.to_pydatetime(), "$lt": start.to_pydatetime()}
    }, {"_id": 0}).sort("ts", 1)
    wdf = pd.DataFrame(list(curw))
    if not wdf.empty:
        wdf["ts"] = pd.to_datetime(wdf["ts"])
        wdf = wdf.drop_duplicates(subset=["ts"]).set_index("ts").sort_index()
        wdf = wdf.reindex(idx)
        wdf = wdf.ffill().bfill()  # popuni vremenske rupe
        df = ldf.join(wdf, how="left")
    else:
        df = ldf.copy()

    df = df.reset_index().rename(columns={"index": "ts"})

    # Izgradi feature-e (kalendar/praznici u NY lokalnom vremenu; ulazni 'ts' je NAIVE UTC)
    feats = build_feature_frame(
        df.assign(ts=pd.to_datetime(df["ts"])),
        db=db,
        holiday_region="US"
    )

    # Pripremi izlaz: ts, y (load), pa feature kolone
    y = df["load_mw"].astype(float).values
    Xf = feats.values.astype(float)
    ts = pd.to_datetime(df["ts"]).tolist()

    out_df = pd.DataFrame({"ts": ts, "y": y}).join(pd.DataFrame(Xf, index=range(len(Xf))))
    return out_df, feats.columns.tolist()

def run_forecast(db, fs, model_doc, region, start_date, days):
    """
    Glavna funkcija predikcije:
      - Učita model iz GridFS (po artifact_id iz model_doc)
      - Pripremi istoriju dužine input_window zaključno sa 'start_date' (exclusive)
      - Uskladi feature kolone (isti redoslijed/ime kao na treningu)
      - Izvrši inferenciju i vrati:
          * listu timestamps (NAIVE UTC) za H sati,
          * listu predikcija (float),
          * csv_id (GridFS) fajla sa prognozom (Datetime, PredictedLoad)
    Napomena: Maksimalni broj sati H = min(days*24, model_horizon).
    """
    from bson import ObjectId
    import csv

    # 1) Artefakt + meta
    model, scaler, feat_names, horizon, saved_input_window = load_artifact(fs, ObjectId(model_doc["artifact_id"]))
    # Ako hyper ima input_window → koristi njega, inače onaj zapisan u artefaktu
    input_window = int(model_doc.get("hyper", {}).get("input_window", saved_input_window or 168))

    # 2) Priprema pune istorije (load obavezno kompletan)
    prep = prepare_inference_window(db, region, start_date, input_window)
    if prep[0] is None:
        raise ValueError(prep[1])
    df, feat_cols = prep

    # 3) Uskladi FEATURE kolone s treningom:
    #    - dodaj 0.0 za kolone koje fale
    #    - reordnaj tačno po feat_names (višak kolona odbaci)
    y_hist = df["y"].values.astype(float)
    feats_df = df.drop(columns=["ts", "y"]).copy()
    for c in feat_names:
        if c not in feats_df.columns:
            feats_df[c] = 0.0
    feats_df = feats_df[feat_names]
    Xf = feats_df.values.astype(float)

    # 4) Skaliraj target istoriju istim skalerom kao na treningu
    y_s = scaler.transform(y_hist) if scaler else y_hist

    # 5) Složi ulaz za model: (1, T, 1+F)  → batch=1
    X_all = np.concatenate([y_s[:, None], Xf], axis=1)[None, ...]
    X_all = torch.tensor(X_all, dtype=torch.float32)

    # 6) Autoregresivna prognoza (decoder bez teacher forcing-a)
    with torch.no_grad():
        yhat = model(X_all)  # (1, H)
    yhat = yhat.numpy().reshape(-1)
    if scaler:
        yhat = scaler.inverse_transform(yhat)  # vrati u MW

    # 7) Izgradi timestamps i ispoštuj traženi broj dana, model_horizon i dužinu yhat
    start_naive = _to_naive_utc(start_date)
    H_req = int(days) * 24
    H = int(min(H_req, yhat.shape[0], horizon))
    ts_out = [(start_naive + pd.Timedelta(hours=i)).to_pydatetime() for i in range(H)]
    y_out = yhat[:H].astype(float).tolist()

    # 8) Snimi CSV (ISO UTC sa 'Z') u GridFS i vrati njegov ID
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Datetime", "PredictedLoad"])
    for t, y in zip(ts_out, y_out):
        writer.writerow([pd.to_datetime(t).isoformat() + "Z", float(y)])
    data = buf.getvalue().encode("utf-8")

    csv_id = fs.put(data, filename=f"forecast_{region}_{start_naive.strftime('%Y%m%dT%H%M%S')}.csv")
    return ts_out, y_out, csv_id
