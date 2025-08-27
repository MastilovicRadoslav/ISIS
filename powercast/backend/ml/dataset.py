import numpy as np
from datetime import timedelta

# Kreira "sliding window" sekvence za trening/validaciju vremenskog niza.
# Ulazi (svi poravnati po istom indeksu i dužine N):
#   - times : 1D lista/array dužine N sa timestampovima (po satu)
#   - values: 1D lista/array dužine N sa target vrijednostima (npr. load_mw)
#   - feats : 2D array oblika (N, F) sa dodatnim osobinama po satu (npr. weather, kalendar)
# Parametri:
#   - input_window: koliko prošlih sati da gledamo (npr. 24)
#   - horizon     : koliko sati unaprijed predviđamo (npr. 6)
#
# Izlazi:
#   - X  : (num_samples, input_window)               → historija targeta
#   - Xf : (num_samples, input_window, F)            → historija feature-a
#   - Y  : (num_samples, horizon)                    → budući target koji se predviđa
#   - T  : lista dužine num_samples; svaka stavka je lista timestampova dužine horizon
#          (vremena koja odgovaraju svakom Y prozoru; ostavljeno kao lista zbog dtype-a)

def build_sequences(times, values, feats, input_window, horizon):
    X, Xf, Y, T = [], [], [], []
    n = len(values)  # ukupno dostupnih tačaka

    # i = kraj "input" prozora; budućnost ide od i do i+horizon (bez uključivog kraja)
    # poslednji validni i je n - horizon (range je ekskluzivan na kraju, pa +1)
    for i in range(input_window, n - horizon + 1):
        # Prošli input_window sati targeta → ulaz za model
        x = values[i - input_window:i]
        # Prošli input_window sati osobina (F kolona) → ulaz za model
        xf = feats[i - input_window:i]
        # Sljedećih horizon sati targeta → ono što model treba da nauči da pogodi
        y = values[i:i + horizon]

        X.append(x)
        Xf.append(xf)
        Y.append(y)
        # T su timestampovi za budućnost (isti prozor kao y)
        T.append(times[i:i + horizon])

    return np.array(X), np.array(Xf), np.array(Y), T
