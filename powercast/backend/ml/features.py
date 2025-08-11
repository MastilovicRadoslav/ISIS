import numpy as np
import pandas as pd

# Izgradi feature matrice po satu: weather + kalendarski + ciklični

def build_feature_frame(df):
    # df mora imati kolone: ts (datetime), load_mw, i po želji weather kolone
    out = pd.DataFrame(index=df.index)
    out["hour"] = df["ts"].dt.hour
    out["dow"] = df["ts"].dt.dayofweek
    out["month"] = df["ts"].dt.month
    out["is_weekend"] = (out["dow"] >= 5).astype(int)

    # ciklični
    out["sin_hour"] = np.sin(2*np.pi*out["hour"]/24)
    out["cos_hour"] = np.cos(2*np.pi*out["hour"]/24)
    out["sin_dow"] = np.sin(2*np.pi*out["dow"]/7)
    out["cos_dow"] = np.cos(2*np.pi*out["dow"]/7)

    # weather kolone ako postoje
    for c in ["temp","dew","humidity","windspeed","precip","solarradiation","uvindex"]:
        if c in df.columns:
            out[c] = df[c].astype(float)
    # forward/backward fill za rijetke rupe
    out = out.ffill().bfill()
    return out