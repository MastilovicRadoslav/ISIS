import io, json
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from datetime import datetime
from .utils import StandardScaler1D, mape
from .features import build_feature_frame
from .dataset import build_sequences
from .models import LSTMSeq2Seq


def prepare_region_dataframe(db, region, date_from, date_to, location_proxy="New York City, NY"):
    # Učitaj satne load podatke
    cur = db.series_load_hourly.find({
        "region": region,
        "ts": {"$gte": pd.to_datetime(date_from), "$lte": pd.to_datetime(date_to)}
    }, {"_id":0, "ts":1, "load_mw":1}).sort("ts", 1)
    load_df = pd.DataFrame(list(cur))
    if load_df.empty:
        return None
    load_df = load_df.sort_values("ts").reset_index(drop=True)

    # Učitaj satne weather podatke (proxy lokacija)
    curw = db.series_weather_hourly.find({
        "location": location_proxy,
        "ts": {"$gte": pd.to_datetime(date_from), "$lte": pd.to_datetime(date_to)}
    }, {"_id":0}).sort("ts", 1)
    wdf = pd.DataFrame(list(curw))

    # Merge po satu
    df = load_df.copy()
    if not wdf.empty:
        df = df.merge(wdf, how="left", on="ts", suffixes=("", "_w"))

    # Feature frame
    feats = build_feature_frame(df.assign(ts=pd.to_datetime(df["ts"])) )

    # Target i matrica feature-a poravnati po indeksu
    y = df["load_mw"].astype(float).values
    Xf = feats.values.astype(float)
    ts = pd.to_datetime(df["ts"]).tolist()

    return pd.DataFrame({"ts": ts, "y": y}).join(pd.DataFrame(Xf, index=range(len(Xf)))), feats.columns.tolist()


def train_lstm_on_regions(db, regions, date_from, date_to, hyper):
    # Hiperparametri
    input_window = int(hyper.get("input_window", 168))
    horizon = int(hyper.get("forecast_horizon", 168))
    hidden_size = int(hyper.get("hidden_size", 128))
    num_layers = int(hyper.get("layers", 2))
    dropout = float(hyper.get("dropout", 0.2))
    epochs = int(hyper.get("epochs", 25))
    batch_size = int(hyper.get("batch_size", 64))
    lr = float(hyper.get("learning_rate", 1e-3))
    teacher_forcing = float(hyper.get("teacher_forcing", 0.2))

    results = []

    for region in regions:
        prep = prepare_region_dataframe(db, region, date_from, date_to)
        if prep is None:
            results.append({"region": region, "ok": False, "error": "No data in date range"})
            continue
        df, feat_names = prep
        ts = pd.to_datetime(df["ts"]).tolist()
        y = df["y"].values.astype(float)
        Xf = df.drop(columns=["ts","y"]).values.astype(float)

        # Skaliranje targeta (feature-e ne skaliramo minimalno za MVP)
        scaler = StandardScaler1D().fit(y)
        y_s = scaler.transform(y)

        # Spakuj 3D ulaz: (B, T, 1+F)
        X, XF, Y, _ = build_sequences(ts, y_s, Xf, input_window, horizon)
        # konkatenacija: cilj (1) + feature-i (F) po času → (B, T, 1+F)
        X_all = np.concatenate([X[..., None], XF], axis=2)

        # Split train/val/test po vremenu 70/15/15
        n = X_all.shape[0]
        n_train = int(n * 0.7)
        n_val = int(n * 0.15)
        Xtr, Xva, Xte = X_all[:n_train], X_all[n_train:n_train+n_val], X_all[n_train+n_val:]
        Ytr, Yva, Yte = Y[:n_train], Y[n_train:n_train+n_val], Y[n_train+n_val:]

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = LSTMSeq2Seq(feat_dim=Xf.shape[1], hidden_size=hidden_size, num_layers=num_layers, dropout=dropout, horizon=horizon).to(device)
        opt = torch.optim.Adam(model.parameters(), lr=lr)
        loss_fn = nn.MSELoss()

        def to_tensor(a):
            return torch.tensor(a, dtype=torch.float32, device=device)

        tr_dl = DataLoader(TensorDataset(to_tensor(Xtr), to_tensor(Ytr)), batch_size=batch_size, shuffle=True)
        va_dl = DataLoader(TensorDataset(to_tensor(Xva), to_tensor(Yva)), batch_size=batch_size, shuffle=False)

        best_va = None
        best_state = None
        patience, patience_cnt = 5, 0

        for ep in range(1, epochs+1):
            model.train()
            tr_loss = 0.0
            for xb, yb in tr_dl:
                opt.zero_grad()
                yhat = model(xb, None, teacher_forcing)
                loss = loss_fn(yhat, yb)
                loss.backward()
                opt.step()
                tr_loss += loss.item() * xb.size(0)
            tr_loss /= len(tr_dl.dataset)

            # val
            model.eval()
            va_loss = 0.0
            with torch.no_grad():
                for xb, yb in va_dl:
                    yhat = model(xb)
                    va_loss += loss_fn(yhat, yb).item() * xb.size(0)
            va_loss /= max(1, len(va_dl.dataset))

            if best_va is None or va_loss < best_va - 1e-6:
                best_va = va_loss
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
                patience_cnt = 0
            else:
                patience_cnt += 1
                if patience_cnt >= patience:
                    break

        # test MAPE
        model.load_state_dict(best_state)
        model.eval()
        with torch.no_grad():
            yhat_te = model(to_tensor(Xte)).cpu().numpy()
        # invert scaling
        # yhat_te shape (N, horizon); potrebno porediti na prvih horizon vrijednosti po slogovima
        # spoji sve u 1D radi MAPE procjene
        yh = scaler.inverse_transform(yhat_te.reshape(-1))
        yt = scaler.inverse_transform(Yte.reshape(-1))
        test_mape = mape(yt, yh)

        # serijalizacija modela i scaler‑a u bytes
        buffer = io.BytesIO()
        torch.save({"state_dict": best_state, "feat_dim": Xf.shape[1], "horizon": horizon,
                    "hidden_size": hidden_size, "num_layers": num_layers, "dropout": dropout,
                    "scaler": scaler.to_dict(), "feat_names": feat_names}, buffer)
        artifact_bytes = buffer.getvalue()

        results.append({
            "ok": True,
            "region": region,
            "artifact_bytes": artifact_bytes,
            "metrics": {"val_loss": float(best_va), "test_mape": float(test_mape)}
        })

    return results