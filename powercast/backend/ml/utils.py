# utils.py
import json, io
import numpy as np

class StandardScaler1D:
    def __init__(self):
        self.mean_ = None
        self.std_ = None
    def fit(self, x):
        x = np.asarray(x, dtype=float)
        self.mean_ = float(np.nanmean(x))
        self.std_ = float(np.nanstd(x) + 1e-8)
        return self
    def transform(self, x):
        x = np.asarray(x, dtype=float)
        return (x - self.mean_) / self.std_
    def inverse_transform(self, x):
        x = np.asarray(x, dtype=float)
        return x * self.std_ + self.mean_
    def to_dict(self):
        return {"mean": self.mean_, "std": self.std_}
    @staticmethod
    def from_dict(d):
        sc = StandardScaler1D()
        sc.mean_ = float(d["mean"]); sc.std_ = float(d["std"])
        return sc


def mape(y_true, y_pred, eps=1e-6):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = np.maximum(np.abs(y_true), eps)
    return float(np.mean(np.abs((y_true - y_pred) / denom)) * 100.0)
