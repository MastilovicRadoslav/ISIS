import numpy as np
import pandas as pd

# pomoćna funkcija za join s praznicima
def join_holidays(df, db, holiday_region="US"):
    # df mora imati kolonu ts (datetime)
    # spajamo po datumu (normalize)
    dd = pd.DataFrame({"Date": pd.to_datetime(df["ts"]).dt.normalize()})
    cur = db.holidays.find({
        "Region": holiday_region,
        "Date": {"$in": dd["Date"].unique().tolist()}
    })
    hdf = pd.DataFrame(list(cur))
    if hdf.empty:
        out = pd.Series(False, index=df.index)
        return pd.DataFrame({
            "is_holiday": out.astype(int),
            "pre_holiday": 0,
            "post_holiday": 0
        })
    hdf = hdf[["Date"]].drop_duplicates()
    hdf["is_holiday"] = 1
    dd2 = dd.join(hdf.set_index("Date"), on="Date").fillna({"is_holiday": 0})
    # pre/post holiday flagovi (dan prije/poslije)
    dd2["pre_holiday"] = dd2["Date"].isin(hdf["Date"] + pd.Timedelta(days=1)).astype(int)
    dd2["post_holiday"] = dd2["Date"].isin(hdf["Date"] - pd.Timedelta(days=1)).astype(int)
    return dd2[["is_holiday", "pre_holiday", "post_holiday"]].set_index(df.index)


# glavna funkcija za kreiranje feature matrice
def build_feature_frame(
    df,
    add_lags=True,
    lags=(1, 24, 48),
    add_roll=True,
    roll_windows=(24, 168),
    db=None,
    holiday_region="US"
):
    # df: ts (datetime), load_mw, opcionalno weather kolone
    out = pd.DataFrame(index=df.index)
    out["hour"] = df["ts"].dt.hour
    out["dow"] = df["ts"].dt.dayofweek
    out["month"] = df["ts"].dt.month
    out["is_weekend"] = (out["dow"] >= 5).astype(int)

    # ciklični
    out["sin_hour"] = np.sin(2 * np.pi * out["hour"] / 24)
    out["cos_hour"] = np.cos(2 * np.pi * out["hour"] / 24)
    out["sin_dow"] = np.sin(2 * np.pi * out["dow"] / 7)
    out["cos_dow"] = np.cos(2 * np.pi * out["dow"] / 7)

    # weather kolone ako postoje
    for c in ["temp", "dew", "humidity", "windspeed", "precip", "solarradiation", "uvindex"]:
        if c in df.columns:
            out[c] = df[c].astype(float)

    # lagovi targeta (na osnovu df['load_mw'])
    if add_lags and "load_mw" in df.columns:
        s = df["load_mw"].astype(float)
        for L in lags:
            out[f"lag_{L}"] = s.shift(L)

    # klizni prosjeci
    if add_roll and "load_mw" in df.columns:
        s = df["load_mw"].astype(float)
        for W in roll_windows:
            out[f"rollmean_{W}"] = s.rolling(W, min_periods=max(1, W // 3)).mean()

    # praznici (ako je dostupan db)
    if db is not None:
        h = join_holidays(df, db, holiday_region)
        out = pd.concat([out, h], axis=1)

    # ffill/bfill
    out = out.ffill().bfill().fillna(0)
    return out
