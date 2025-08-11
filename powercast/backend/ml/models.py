import torch
import torch.nn as nn

class LSTMSeq2Seq(nn.Module):
    def __init__(self, feat_dim, hidden_size=128, num_layers=2, dropout=0.2, horizon=24):
        super().__init__()
        self.horizon = horizon
        self.enc = nn.LSTM(input_size=feat_dim+1, hidden_size=hidden_size, num_layers=num_layers, batch_first=True, dropout=dropout)
        self.dec = nn.LSTM(input_size=1, hidden_size=hidden_size, num_layers=num_layers, batch_first=True, dropout=dropout)
        self.proj = nn.Linear(hidden_size, 1)

    def forward(self, x_hist, y_hist=None, teacher_forcing=0.0):
        # x_hist: (B, T, 1+F) -> 1: target (scaled load), F: features
        B, T, F = x_hist.shape
        _, (h, c) = self.enc(x_hist)
        # start token: poslednja poznata vrijednost targeta
        last_y = x_hist[:, -1:, :1]  # (B, 1, 1)
        dec_in = last_y
        outs = []
        h_dec, c_dec = h, c
        for _ in range(self.horizon):
            y_dec, (h_dec, c_dec) = self.dec(dec_in, (h_dec, c_dec))
            y_hat = self.proj(y_dec)
            outs.append(y_hat)
            if self.training and y_hist is not None and torch.rand(1).item() < teacher_forcing:
                dec_in = y_hist[:, :1, :]
                y_hist = y_hist[:, 1:, :]
            else:
                dec_in = y_hat
        y_out = torch.cat(outs, dim=1)  # (B, H, 1)
        return y_out.squeeze(-1)