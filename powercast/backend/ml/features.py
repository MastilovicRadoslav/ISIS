# features.py
# Skup helpera za građenje feature-a za vremenske nizove (NYISO use-case).
# - _utc_to_ny_local: konverzija UTC timestampa u lokalno NY vrijeme (aware)
# - join_holidays: spajanje dnevnih praznika (iz Mongo kolekcije `holidays`) na satne zapise
# - build_feature_frame: kreiranje vremenskih, cikličnih, meteo, lag/rolling i holiday feature-a

import numpy as np
import pandas as pd
from pytz import timezone, UTC

NY_TZ = timezone("America/New_York")

def _utc_to_ny_local(ts_series: pd.Series) -> pd.Series:
    """
    Ulaz: serija 'ts' koja može biti naive ili aware.
    Korak 1: parsiraj u aware UTC (utc=True garantuje tzinfo=UTC)
    Korak 2: konvertuj u lokalnu NY zonu (aware NY)
    Rezultat: pd.Series sa NY lokalnim aware timestampovima.
    """
    # Bez obzira da li dolazi naive ili aware, forsiraj na aware UTC pa u NY
    s = pd.to_datetime(ts_series, utc=True, errors="coerce")
    return s.dt.tz_convert(NY_TZ)


def join_holidays(df, db, holiday_region="US"):
    """
    Za dati satni DataFrame 'df' i Mongo konekciju 'db':
      - izračunaj koji NY lokalni dan (00:00) pripada svakom 'ts'
      - spoji sa kolekcijom 'holidays' po NAIVE UTC datumu (ključ 'Date')
      - vrati DataFrame sa kolonama:
          is_holiday  ∈ {0,1}
          pre_holiday ∈ {0,1}  (dan prije praznika, po NY lokalnom datumu)
          post_holiday∈ {0,1}  (dan poslije praznika, po NY lokalnom datumu)
    Ako nema podataka, vraća kolone pune nula (poravnate po df.index).
    """
    if df.empty:
        return pd.DataFrame({"is_holiday": 0, "pre_holiday": 0, "post_holiday": 0}, index=df.index)

    # 1) ts → aware UTC
    ts_utc = pd.to_datetime(df["ts"], utc=True, errors="coerce")

    # 2) NY lokalni dan (ponoć) — AWARE NY; koristi floor("D") da dobijemo 00:00 lokalno
    local_midnight = ts_utc.dt.tz_convert(NY_TZ).dt.floor("D")

    # 3) Taj lokalni dan mapiraj na NAIVE UTC 00:00 (ključ za join sa Mongo 'holidays.Date')
    date_utc_for_join = local_midnight.dt.tz_convert(UTC).dt.tz_localize(None)
    dd = pd.DataFrame({"Date": date_utc_for_join}, index=df.index)

    # Učitaj praznike iz baze (holidays) za dati region; 'Date' je NAIVE UTC u kolekciji
    cur = db.holidays.find({"Region": holiday_region}, {"_id": 0, "Date": 1})
    hdf = pd.DataFrame(list(cur))
    if hdf.empty:
        return pd.DataFrame({"is_holiday": 0, "pre_holiday": 0, "post_holiday": 0}, index=df.index)

    # Očisti i označi praznike
    hdf["Date"] = pd.to_datetime(hdf["Date"])
    hdf = hdf.drop_duplicates(subset=["Date"])
    hdf["is_holiday"] = 1

    # Join po NAIVE UTC datumu (dd: naš dnevni ključ, hdf: praznici)
    dd2 = dd.merge(hdf, how="left", on="Date").fillna({"is_holiday": 0})
    dd2.index = df.index  # zadrži izvorni index

    # Izvedi skup lokalnih NY "dnevnih" prazničnih datuma (aware NY na ponoć)
    hol_local_days = (
        hdf["Date"]
        .dt.tz_localize(UTC)   # 'Date' iz baze je naive UTC → učini ga aware UTC
        .dt.tz_convert(NY_TZ)  # prebaci u NY lokalno
        .dt.floor("D")         # uzmi lokalni dan (00:00)
        .drop_duplicates()
    )

    # pre_holiday: ako je naš lokalni dan == (praznik + 1 dan)
    # post_holiday: ako je naš lokalni dan == (praznik - 1 dan)
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
    Glavni feature builder.
    Očekuje da 'df' sadrži:
      - ts: NAIVE UTC (Mongo konvencija), po satu
      - load_mw: target (opciono za lag/rolling)
      - opcione meteo kolone: temp, humidity, windspeed, precip, ...
    Generiše:
      - vremenske komponente (hour, dow, month, is_weekend) po NY lokalnom vremenu
      - ciklične enkodere (sin/cos za hour i dow)
      - meteo kolone (ako postoje u df)
      - lagovi i rolajući prosjeci nad load_mw (ako su uključeni)
      - indikator praznika (is/pre/post) spojen iz Mongo 'holidays' (po NY lokalnom danu)
      - popunjavanje rupa (ffill/bfill) i NaN → 0.0
    Vraća DataFrame poravnat na df.index.
    """
    out = pd.DataFrame(index=df.index)

    # NY lokalne komponente vremena (iz 'ts' koji je u NAIVE UTC)
    ts_local = _utc_to_ny_local(df["ts"])
    out["hour"] = ts_local.dt.hour
    out["dow"] = ts_local.dt.dayofweek
    out["month"] = ts_local.dt.month
    out["is_weekend"] = (out["dow"] >= 5).astype(int)

    # Ciklični (sin/cos) enkodinzi za sat u danu i dan u sedmici
    out["sin_hour"] = np.sin(2 * np.pi * out["hour"] / 24)
    out["cos_hour"] = np.cos(2 * np.pi * out["hour"] / 24)
    out["sin_dow"]  = np.sin(2 * np.pi * out["dow"] / 7)
    out["cos_dow"]  = np.cos(2 * np.pi * out["dow"] / 7)

    # Meteo kolone (kopiraj samo ako postoje; coerceanje u broj)
    for c in ["temp", "dew", "humidity", "windspeed", "precip", "solarradiation", "uvindex", "sealevelpressure", "cloudcover"]:
        if c in df.columns:
            out[c] = pd.to_numeric(df[c], errors="coerce")

    # Lagovi targeta (load_mw) — npr. 1h, 24h, 48h, 168h (sedmica)
    if add_lags and "load_mw" in df.columns:
        s = pd.to_numeric(df["load_mw"], errors="coerce")
        for L in lags:
            out[f"lag_{L}"] = s.shift(L)

    # Rolajući prosjeci targeta
    if add_roll and "load_mw" in df.columns:
        s = pd.to_numeric(df["load_mw"], errors="coerce")
        for W in roll_windows:
            # min_periods je ~ trećina prozora, da se dobije vrijednost i na početku serije
            out[f"rollmean_{W}"] = s.rolling(W, min_periods=max(1, W//3)).mean()

    # Praznici (spoji is/pre/post za region; koristi NY lokalni kalendar)
    if db is not None:
        h = join_holidays(df, db, holiday_region)
        out = pd.concat([out, h], axis=1)

    # Popuni nedostajuće kroz forward/backward fill (npr. rupe u meteo ili praznicima)
    out = out.ffill().bfill()

    # Sve preostale NaN (npr. početni lagovi) na 0.0 — stabilno za modele
    out = out.fillna(0.0)
    return out
