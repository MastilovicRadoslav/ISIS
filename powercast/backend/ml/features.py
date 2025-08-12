# features.py
import numpy as np
import pandas as pd
from pytz import timezone, UTC

NY_TZ = timezone("America/New_York")

def _utc_to_ny_local(ts_series: pd.Series) -> pd.Series:
    # Bez obzira da li dolazi naive ili aware, forsiraj na aware UTC pa u NY
    s = pd.to_datetime(ts_series, utc=True, errors="coerce")
    return s.dt.tz_convert(NY_TZ)


def join_holidays(df, db, holiday_region="US"):
    if df.empty:
        return pd.DataFrame({"is_holiday": 0, "pre_holiday": 0, "post_holiday": 0}, index=df.index)

    # 1) ts → aware UTC
    ts_utc = pd.to_datetime(df["ts"], utc=True, errors="coerce")

    # 2) NY lokalni dan (ponać) — AWARE NY; koristi floor("D")
    local_midnight = ts_utc.dt.tz_convert(NY_TZ).dt.floor("D")

    # 3) Taj lokalni dan mapiraj na NAIVE UTC 00:00 (ključ za join)
    date_utc_for_join = local_midnight.dt.tz_convert(UTC).dt.tz_localize(None)
    dd = pd.DataFrame({"Date": date_utc_for_join}, index=df.index)

    # Praznici iz baze (naive UTC Date)
    cur = db.holidays.find({"Region": holiday_region}, {"_id": 0, "Date": 1})
    hdf = pd.DataFrame(list(cur))
    if hdf.empty:
        return pd.DataFrame({"is_holiday": 0, "pre_holiday": 0, "post_holiday": 0}, index=df.index)

    hdf["Date"] = pd.to_datetime(hdf["Date"])
    hdf = hdf.drop_duplicates(subset=["Date"])
    hdf["is_holiday"] = 1

    # Join po NAIVE UTC datumu
    dd2 = dd.merge(hdf, how="left", on="Date").fillna({"is_holiday": 0})
    dd2.index = df.index  # zadrži izvorni index

    # pre/post po NY lokalnom datumu
    hol_local_days = (
        hdf["Date"]
        .dt.tz_localize(UTC)           # Date iz baze je naive UTC → učini aware UTC
        .dt.tz_convert(NY_TZ)          # u NY
        .dt.floor("D")                 # lokalni dan
        .drop_duplicates()
    )

    pre_mask  = local_midnight.isin(hol_local_days + pd.Timedelta(days=1))
    post_mask = local_midnight.isin(hol_local_days - pd.Timedelta(days=1))

    dd2["pre_holiday"]  = pre_mask.astype(int).values
    dd2["post_holiday"] = post_mask.astype(int).values

    return dd2[["is_holiday", "pre_holiday", "post_holiday"]]

def build_feature_frame(
    df,
    add_lags=True,
    lags=(1, 24, 48, 168),
    add_roll=True,
    roll_windows=(24, 168),
    db=None,
    holiday_region="US"
):
    """
    df: mora imati kolone:
      - ts: NAIVE UTC (Mongo konvencija)
      - load_mw
      - opcionalne meteo kolone (npr. temp, humidity, ...)
    Kalendar računamo u NY lokalnom vremenu.
    """
    out = pd.DataFrame(index=df.index)

    # NY lokalne komponente vremena
    ts_local = _utc_to_ny_local(df["ts"])
    out["hour"] = ts_local.dt.hour
    out["dow"] = ts_local.dt.dayofweek
    out["month"] = ts_local.dt.month
    out["is_weekend"] = (out["dow"] >= 5).astype(int)

    # ciklični
    out["sin_hour"] = np.sin(2 * np.pi * out["hour"] / 24)
    out["cos_hour"] = np.cos(2 * np.pi * out["hour"] / 24)
    out["sin_dow"]  = np.sin(2 * np.pi * out["dow"] / 7)
    out["cos_dow"]  = np.cos(2 * np.pi * out["dow"] / 7)

    # meteo (ako postoje u df)
    for c in ["temp", "dew", "humidity", "windspeed", "precip", "solarradiation", "uvindex", "sealevelpressure", "cloudcover"]:
        if c in df.columns:
            out[c] = pd.to_numeric(df[c], errors="coerce")

    # lagovi/rolovi nad targetom
    if add_lags and "load_mw" in df.columns:
        s = pd.to_numeric(df["load_mw"], errors="coerce")
        for L in lags:
            out[f"lag_{L}"] = s.shift(L)

    if add_roll and "load_mw" in df.columns:
        s = pd.to_numeric(df["load_mw"], errors="coerce")
        for W in roll_windows:
            out[f"rollmean_{W}"] = s.rolling(W, min_periods=max(1, W//3)).mean()

    # praznici (po NY lokalnom danu)
    if db is not None:
        h = join_holidays(df, db, holiday_region)
        out = pd.concat([out, h], axis=1)

    # popuni rupe
    out = out.ffill().bfill()

    # sve ostalo preostalo NaN -> 0 (npr. početni lagovi)
    out = out.fillna(0.0)
    return out
