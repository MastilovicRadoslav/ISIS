# utils.py
# Pomoćne util funkcije/klase za Sprint 2:
# - StandardScaler1D: standardizacija jedne numeričke serije (npr. target y = load_mw)
# - mape: metrika Mean Absolute Percentage Error (%)
#
# Napomena:
#   - Skaler FIT-ovati isključivo na TRAIN segmentu (bez “curenja” informacija u val/test).
#   - Skaler serijalizovati kroz to_dict() i čuvati u models metapodacima;
#     model_state ide u GridFS, a scaler parametri (mean/std) u kolekciju `models`.

import json, io
import numpy as np


class StandardScaler1D:
    """
    Jednostavan skaler za 1D niz: čuva mean i std, i radi:
      z = (x - mean) / std
    Inverse transform vraća nazad:
      x = z * std + mean
    """
    def __init__(self):
        # Parametri fit-ovanog skalera
        self.mean_ = None
        self.std_ = None

    def fit(self, x):
        """
        Računa mean i std preko ulaznog niza x.
        - np.nanmean / np.nanstd ignorišu NaN vrijednosti.
        - dodajemo mali epsilon (1e-8) na std da izbjegnemo dijeljenje nulom
          u slučajevima konstante serije.
        """
        x = np.asarray(x, dtype=float)
        self.mean_ = float(np.nanmean(x))
        self.std_ = float(np.nanstd(x) + 1e-8)
        return self  # omogući chaining

    def transform(self, x):
        """
        Standardizacija:
          z = (x - mean_) / std_
        Radi za skalar, vektor ili 1D/ND strukture (NumPy broadcasting).
        Pretpostavlja da je fit() već pozvan.
        """
        x = np.asarray(x, dtype=float)
        return (x - self.mean_) / self.std_

    def inverse_transform(self, x):
        """
        Inverzna transformacija (vrati originalnu skalu):
          x = z * std_ + mean_
        Koristi se prije računanja metrika/serviranja (npr. predikcije u MW).
        """
        x = np.asarray(x, dtype=float)
        return x * self.std_ + self.mean_

    def to_dict(self):
        """
        Serijalizacija parametara skalera (JSON-friendly).
        Ovo se može snimiti u metapodatke modela (kolekcija `models`).
        """
        return {"mean": self.mean_, "std": self.std_}

    @staticmethod
    def from_dict(d):
        """
        Rekonstrukcija skalera iz dict-a (npr. poslije učitavanja metapodataka).
        """
        sc = StandardScaler1D()
        sc.mean_ = float(d["mean"]); sc.std_ = float(d["std"])
        return sc


def mape(y_true, y_pred, eps=1e-6):
    """
    Mean Absolute Percentage Error (MAPE) u procentima.
      MAPE = mean( |(y_true - y_pred) / max(|y_true|, eps)| ) * 100
    - eps štiti od dijeljenja nulom kada je y_true≈0.
    - Preporuka: računati na originalnoj skali (poslije inverse_transform).
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = np.maximum(np.abs(y_true), eps)
    return float(np.mean(np.abs((y_true - y_pred) / denom)) * 100.0)
