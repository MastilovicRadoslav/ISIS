import numpy as np
from datetime import timedelta

# Kreira sliding window sekvence X (input_window) i Y (forecast_horizon)
# times: 1D lista timestampova (posle spajanja i resampla)
# values: 1D lista target vrijednosti (load_mw)
# feats: 2D (N, F) dodatne osobine po satu (npr. weather, kalendar)

def build_sequences(times, values, feats, input_window, horizon):
    X, Xf, Y, T = [], [], [], []
    n = len(values)
    for i in range(input_window, n - horizon + 1):
        x = values[i - input_window:i]
        xf = feats[i - input_window:i]
        y = values[i:i + horizon]
        X.append(x)
        Xf.append(xf)
        Y.append(y)
        T.append(times[i:i + horizon])
    return np.array(X), np.array(Xf), np.array(Y), T