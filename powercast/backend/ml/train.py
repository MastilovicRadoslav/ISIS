# train.py
import io
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from pytz import UTC

# Naši helperi iz prethodnih fajlova
from .utils import StandardScaler1D, mape
from .features import build_feature_frame
from .dataset import build_sequences
from .models import LSTMSeq2Seq


def prepare_region_dataframe(db, region, date_from, date_to, location_proxy="New York City, NY"):
    """
    Učitava satne load i weather podatke iz Mongo u opsegu [date_from, date_to] (UTC),
    spaja po UTC satu i gradi feature frame (NY lokalni kalendar/praznici).
    Vraća:
      - DataFrame: kolone ts (UTC), y (target), zatim sve feature kolone
      - lista imena feature kolona (redosled kao u DataFrame-u posle ts,y)
    """
    # 1) Normalizuj granice opsega u NAIVE UTC (Mongo konvencija)
    dfrom = pd.to_datetime(date_from, utc=True).tz_convert(UTC).tz_localize(None)
    dto   = pd.to_datetime(date_to,   utc=True).tz_convert(UTC).tz_localize(None)

    # 2) Učitaj LOAD (satno) za region i opseg
    cur = db.series_load_hourly.find(
        {"region": region, "ts": {"$gte": dfrom.to_pydatetime(), "$lte": dto.to_pydatetime()}},
        {"_id": 0, "ts": 1, "load_mw": 1}
    ).sort("ts", 1)
    load_df = pd.DataFrame(list(cur))
    if load_df.empty:
        return None  # nema podataka u opsegu

    load_df["ts"] = pd.to_datetime(load_df["ts"])
    load_df = load_df.sort_values("ts").reset_index(drop=True)

    # 3) Učitaj WEATHER (satno) za proxy lokaciju i opseg
    curw = db.series_weather_hourly.find(
        {"location": location_proxy, "ts": {"$gte": dfrom.to_pydatetime(), "$lte": dto.to_pydatetime()}},
        {"_id": 0}
    ).sort("ts", 1)
    wdf = pd.DataFrame(list(curw))
    if not wdf.empty:
        wdf["ts"] = pd.to_datetime(wdf["ts"])

    # 4) Merge po satu (UTC). Ako nema meteo – ostaje samo load_df.
    df = load_df.copy()
    if not wdf.empty:
        df = df.merge(wdf, how="left", on="ts", suffixes=("", "_w"))

    # 5) Izgradi feature frame (NY lokalno: hour/dow/month, sin/cos, meteo, lag/roll, praznici)
    feats = build_feature_frame(df.assign(ts=pd.to_datetime(df["ts"])), db=db, holiday_region="US")

    # 6) Target (y), feature matrica (Xf) i vremenska osa (ts)
    y = pd.to_numeric(df["load_mw"], errors="coerce").values
    Xf = feats.values.astype(float)
    ts = pd.to_datetime(df["ts"]).tolist()

    # 7) Ukloni slogove sa NaN targetom (poravnaj Xf i ts na istu masku)
    mask = ~np.isnan(y)
    y = y[mask]; Xf = Xf[mask]; ts = [t for m, t in zip(mask, ts) if m]

    # 8) Vrati DataFrame sa (ts, y, feature_i...) i listu imena feature kolona
    return pd.DataFrame({"ts": ts, "y": y}).join(pd.DataFrame(Xf, index=range(len(Xf)))), feats.columns.tolist()


def train_lstm_on_regions(db, regions, date_from, date_to, hyper):
    """
    Trening LSTMSeq2Seq po regionima.
    - Učita podatke (prepare_region_dataframe)
    - Skalira target (StandardScaler1D) — fit na SVIM dostupnim tačkama u opsegu
    - Kreira sekvence (build_sequences): X (target istorija), XF (feature istorija), Y (budućnost)
    - Napravi train/val/test split (70/15/15) po vremenu
    - Trenira LSTM sa teacher forcing-om i early stopping-om (po val loss)
    - Testira (MAPE na originalnoj skali)
    - Pakuje artefakt modela (state_dict + meta + scaler) u bytes
    Vraća listu rezultata po regionu.
    """
    # --- Hiperparametri (sa podrazumijevanim vrijednostima) ---
    input_window    = int(hyper.get("input_window", 168))          # broj prošlih sati koji ulaze u model (T) – npr. 168 = 7 dana istorije
    horizon         = int(hyper.get("forecast_horizon", 168))      # broj sati unaprijed koje model predviđa (H) – npr. 168 = prognoza za 7 dana
    hidden_size     = int(hyper.get("hidden_size", 128))           # dimenzija skrivenog sloja u RNN/LSTM – koliko neurona po sloju
    num_layers      = int(hyper.get("layers", 2))                  # broj slojeva u RNN/LSTM mreži – dublje mreže = veća sposobnost učenja
    dropout         = float(hyper.get("dropout", 0.2))             # dropout stopa – vjerovatnoća “gašenja” neurona radi regularizacije
    epochs          = int(hyper.get("epochs", 25))                 # broj epoha – koliko puta model vidi cijeli trening set
    batch_size      = int(hyper.get("batch_size", 64))             # veličina batch-a – koliko primjera se obrađuje prije update-a težina
    lr              = float(hyper.get("learning_rate", 1e-3))      # learning rate – brzina učenja optimizatora
    teacher_forcing = float(hyper.get("teacher_forcing", 0.2))     # vjerovatnoća teacher forcing-a – koliko često koristimo stvarni izlaz umjesto predikcije tokom treninga

    results = []

    # (opciono) reproducibilnost
    torch.manual_seed(42)
    np.random.seed(42)

    for region in regions:
        # 1) Priprema podataka za region (load+weather→features; ts,y,Xf)
        prep = prepare_region_dataframe(db, region, date_from, date_to)
        if prep is None:
            results.append({"region": region, "ok": False, "error": "No data in date range"})
            continue

        df, feat_names = prep
        ts = pd.to_datetime(df["ts"]).tolist()
        y  = df["y"].values.astype(float)
        Xf = df.drop(columns=["ts", "y"]).values.astype(float)

        # 2) Skaliranje targeta (z-score). VAŽNO: ovdje se fit radi na svim dostupnim tačkama.
        #    Ako želiš striktan train-only fit (bez lekkage), promijeni logiku: fit na train segmentu nakon split-a.
        scaler = StandardScaler1D().fit(y)
        y_s = scaler.transform(y) # normalizovan cilj, pomaže treniranju

        # 3) Sliding window sekvence: X:(N,T), XF:(N,T,F), Y:(N,H)
        X, XF, Y, _ = build_sequences(ts, y_s, Xf, input_window, horizon)
        if X.shape[0] < 10:
            results.append({"region": region, "ok": False, "error": "Not enough sequences (increase date range or reduce windows)."})
            continue

        # 4) Spoji target istoriju i feature-e po vremenskom koraku: (N,T,1+F)
        X_all = np.concatenate([X[..., None], XF], axis=2)

        # 5) Vremenski split: 70% train, 15% val, 15% test
        n = X_all.shape[0]
        n_train = int(n * 0.7)
        n_val   = int(n * 0.15)
        Xtr, Xva, Xte = X_all[:n_train], X_all[n_train:n_train+n_val], X_all[n_train+n_val:]
        Ytr, Yva, Yte = Y[:n_train],    Y[n_train:n_train+n_val],    Y[n_train+n_val:]

        # 6) Model + optimizator + loss
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

        # Helper za konverziju numpy→torch na ispravan device/dtype
        def TT(a): return torch.tensor(a, dtype=torch.float32, device=device)

        # 7) DataLoader-i (batching)
        tr_dl = DataLoader(TensorDataset(TT(Xtr), TT(Ytr)), batch_size=batch_size, shuffle=True,  drop_last=False)
        va_dl = DataLoader(TensorDataset(TT(Xva), TT(Yva)), batch_size=batch_size, shuffle=False, drop_last=False)

        # 8) Early stopping po najboljem val loss-u
        best_va = None
        best_state = None
        patience, patience_cnt = 6, 0

        for _ in range(1, epochs + 1):
            # --- Trening petlja (sa teacher forcing-om) ---
            model.train()
            tr_loss = 0.0
            for xb, yb in tr_dl:
                opt.zero_grad()
                # Teacher forcing: prosljeđujemo ground-truth y za decoder (kao (B,H,1))
                y_hist = yb.unsqueeze(-1)          # (B,H,1)
                yhat = model(xb, y_hist=y_hist, teacher_forcing=teacher_forcing)  # izlaz: (B,H)
                loss = loss_fn(yhat, yb)           # MSE na skali modela (standardizovanoj)
                loss.backward()
                opt.step()
                tr_loss += loss.item() * xb.size(0)
            tr_loss /= len(tr_dl.dataset)

            # --- Validacija (bez teacher forcing-a) ---
            model.eval()
            va_loss = 0.0
            with torch.no_grad():
                for xb, yb in va_dl:
                    yhat = model(xb)               # autoregresivno (bez y_hist)
                    va_loss += loss_fn(yhat, yb).item() * xb.size(0)
            va_loss /= max(1, len(va_dl.dataset))

            # --- Early stopping logika ---
            if best_va is None or va_loss < best_va - 1e-6:
                best_va = va_loss
                # Sačuvaj najbolja stanja (cpu kopija tensor-a)
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
                patience_cnt = 0
            else:
                patience_cnt += 1
                if patience_cnt >= patience:
                    break  # zaustavi ako nema poboljšanja

        # 9) Test: učitaj najbolja stanja i izračunaj MAPE na originalnoj skali (MW)
        model.load_state_dict(best_state)
        model.eval()
        with torch.no_grad():
            yhat_te = model(TT(Xte)).cpu().numpy()   # (N,H) na standardizovanoj skali
        yh = scaler.inverse_transform(yhat_te.reshape(-1))  # vrati u MW
        yt = scaler.inverse_transform(Yte.reshape(-1))      # vrati GT u MW
        test_mape = mape(yt, yh)                            # % greške

        # 10) Serijalizuj artefakt modela (state_dict + meta + scaler) u bytes (za GridFS)
        buffer = io.BytesIO()
        torch.save({
            "state_dict": best_state,        # težine modela
            "feat_dim": Xf.shape[1],         # broj feature-a po času
            "horizon": horizon,
            "hidden_size": hidden_size,
            "num_layers": num_layers,
            "dropout": dropout,
            "scaler": scaler.to_dict(),      # mean/std za inverse_transform u serviranju
            "feat_names": feat_names,        # imena kolona feature-a
            "input_window": input_window,    # veličina istorijskog prozora
        }, buffer)
        artifact_bytes = buffer.getvalue()

        # 11) Rezultat za region
        results.append({
            "ok": True,
            "region": region,
            "artifact_bytes": artifact_bytes,                 # spremno za upload u GridFS
            "metrics": {"val_loss": float(best_va), "test_mape": float(test_mape)}
        })

    return results
