# train.py
import io
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from pytz import UTC
from .utils import StandardScaler1D, mape
from .features import build_feature_frame
from .dataset import build_sequences
from .models import LSTMSeq2Seq

def prepare_region_dataframe(db, region, date_from, date_to, location_proxy="New York City, NY"):
    """
    Učitava satne load i weather podatke u opsegu [date_from, date_to],
    spaja po UTC satu i gradi feature frame u skladu sa NY lokalnim kalendarom/praznicima.
    """
    # Normalizuj ulazne stringove → NAIVE UTC (Mongo konvencija)
    dfrom = pd.to_datetime(date_from, utc=True).tz_convert(UTC).tz_localize(None)
    dto   = pd.to_datetime(date_to,   utc=True).tz_convert(UTC).tz_localize(None)

    # Load
    cur = db.series_load_hourly.find(
        {"region": region, "ts": {"$gte": dfrom.to_pydatetime(), "$lte": dto.to_pydatetime()}},
        {"_id": 0, "ts": 1, "load_mw": 1}
    ).sort("ts", 1)
    load_df = pd.DataFrame(list(cur))
    if load_df.empty:
        return None

    load_df["ts"] = pd.to_datetime(load_df["ts"])
    load_df = load_df.sort_values("ts").reset_index(drop=True)

    # Weather (proxy lokacija)
    curw = db.series_weather_hourly.find(
        {"location": location_proxy, "ts": {"$gte": dfrom.to_pydatetime(), "$lte": dto.to_pydatetime()}},
        {"_id": 0}
    ).sort("ts", 1)
    wdf = pd.DataFrame(list(curw))
    if not wdf.empty:
        wdf["ts"] = pd.to_datetime(wdf["ts"])

    # Merge po satu (UTC)
    df = load_df.copy()
    if not wdf.empty:
        df = df.merge(wdf, how="left", on="ts", suffixes=("", "_w"))

    # Feature frame (NY lokalni kalendar + praznici)
    feats = build_feature_frame(df.assign(ts=pd.to_datetime(df["ts"])), db=db, holiday_region="US")

    # Target i features
    y = pd.to_numeric(df["load_mw"], errors="coerce").values
    Xf = feats.values.astype(float)
    ts = pd.to_datetime(df["ts"]).tolist()

    # Ukloni slogove gdje je target NaN
    mask = ~np.isnan(y)
    y = y[mask]; Xf = Xf[mask]; ts = [t for m, t in zip(mask, ts) if m]

    return pd.DataFrame({"ts": ts, "y": y}).join(pd.DataFrame(Xf, index=range(len(Xf)))), feats.columns.tolist()


def train_lstm_on_regions(db, regions, date_from, date_to, hyper):
    # Hiperparametri
    input_window    = int(hyper.get("input_window", 168))
    horizon         = int(hyper.get("forecast_horizon", 168))
    hidden_size     = int(hyper.get("hidden_size", 128))
    num_layers      = int(hyper.get("layers", 2))
    dropout         = float(hyper.get("dropout", 0.2))
    epochs          = int(hyper.get("epochs", 25))
    batch_size      = int(hyper.get("batch_size", 64))
    lr              = float(hyper.get("learning_rate", 1e-3))
    teacher_forcing = float(hyper.get("teacher_forcing", 0.2))

    results = []

    # (opciono) reproducibilnost
    torch.manual_seed(42)
    np.random.seed(42)

    for region in regions:
        prep = prepare_region_dataframe(db, region, date_from, date_to)
        if prep is None:
            results.append({"region": region, "ok": False, "error": "No data in date range"})
            continue

        df, feat_names = prep
        ts = pd.to_datetime(df["ts"]).tolist()
        y  = df["y"].values.astype(float)
        Xf = df.drop(columns=["ts", "y"]).values.astype(float)

        # Skaliranje targeta
        scaler = StandardScaler1D().fit(y)
        y_s = scaler.transform(y)

        # Sekvence
        X, XF, Y, _ = build_sequences(ts, y_s, Xf, input_window, horizon)  # X:(N,T), XF:(N,T,F), Y:(N,H)
        if X.shape[0] < 10:
            results.append({"region": region, "ok": False, "error": "Not enough sequences (increase date range or reduce windows)."})
            continue

        # konkatenacija cilj+feature po času → (N,T,1+F)
        X_all = np.concatenate([X[..., None], XF], axis=2)

        # Split 70/15/15 po vremenu
        n = X_all.shape[0]
        n_train = int(n * 0.7)
        n_val   = int(n * 0.15)
        Xtr, Xva, Xte = X_all[:n_train], X_all[n_train:n_train+n_val], X_all[n_train+n_val:]
        Ytr, Yva, Yte = Y[:n_train],    Y[n_train:n_train+n_val],    Y[n_train+n_val:]

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = LSTMSeq2Seq(
            feat_dim=Xf.shape[1],
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout,
            horizon=horizon
        ).to(device)
        opt = torch.optim.Adam(model.parameters(), lr=lr)
        loss_fn = nn.MSELoss()

        def TT(a): return torch.tensor(a, dtype=torch.float32, device=device)

        tr_dl = DataLoader(TensorDataset(TT(Xtr), TT(Ytr)), batch_size=batch_size, shuffle=True, drop_last=False)
        va_dl = DataLoader(TensorDataset(TT(Xva), TT(Yva)), batch_size=batch_size, shuffle=False, drop_last=False)

        best_va = None
        best_state = None
        patience, patience_cnt = 6, 0

        for _ in range(1, epochs + 1):
            model.train()
            tr_loss = 0.0
            for xb, yb in tr_dl:
                opt.zero_grad()
                # teacher forcing: prosleđujemo y_hist kao (B,H,1)
                y_hist = yb.unsqueeze(-1)
                yhat = model(xb, y_hist=y_hist, teacher_forcing=teacher_forcing)
                loss = loss_fn(yhat, yb)
                loss.backward()
                opt.step()
                tr_loss += loss.item() * xb.size(0)
            tr_loss /= len(tr_dl.dataset)

            # validacija bez TF
            model.eval()
            va_loss = 0.0
            with torch.no_grad():
                for xb, yb in va_dl:
                    yhat = model(xb)  # bez y_hist
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

        # Test MAPE
        model.load_state_dict(best_state)
        model.eval()
        with torch.no_grad():
            yhat_te = model(TT(Xte)).cpu().numpy()  # (N,H)
        yh = scaler.inverse_transform(yhat_te.reshape(-1))
        yt = scaler.inverse_transform(Yte.reshape(-1))
        test_mape = mape(yt, yh)

        # Serijalizacija u bytes (state + scaler + meta)
        buffer = io.BytesIO()
        torch.save({
            "state_dict": best_state,
            "feat_dim": Xf.shape[1],
            "horizon": horizon,
            "hidden_size": hidden_size,
            "num_layers": num_layers,
            "dropout": dropout,
            "scaler": scaler.to_dict(),
            "feat_names": feat_names,
            "input_window": input_window,
        }, buffer)
        artifact_bytes = buffer.getvalue()

        results.append({
            "ok": True,
            "region": region,
            "artifact_bytes": artifact_bytes,
            "metrics": {"val_loss": float(best_va), "test_mape": float(test_mape)}
        })

    return results
