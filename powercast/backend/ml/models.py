import torch
import torch.nn as nn

class LSTMSeq2Seq(nn.Module):
    """
    Jednostavan encoder–decoder (seq2seq) LSTM za višesatnu prognozu.
    - Encoder prima istoriju targeta zajedno sa feature-ima: dim ulaza = 1 (target) + F (features).
    - Decoder autoregresivno generiše narednih `horizon` vrijednosti targeta, hraneći svaki put
      prethodnu predikciju (ili, uz teacher forcing, sledeću "pravu" vrednost).
    - Linearna projekcija mapira LSTM skriveno stanje na skalarni izlaz po vremenskom koraku.
    """

    def __init__(self, feat_dim, hidden_size=128, num_layers=2, dropout=0.2, horizon=24):
        super().__init__()
        self.horizon = horizon  # koliko koraka unapred predviđamo (H)

        # Encoder: ulazna dimenzija = 1 (target) + feat_dim (broj dodatnih osobina po času)
        self.enc = nn.LSTM(
            input_size=feat_dim + 1,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout,  # primenjuje se između LSTM slojeva ako je num_layers > 1
        )

        # Decoder: u svakom koraku prima SAMO 1 kanal = prethodni target (skalar)
        self.dec = nn.LSTM(
            input_size=1,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout,
        )

        # Projekcija skrivenog stanja decoder-a na 1 izlaz (skalar po koraku)
        self.proj = nn.Linear(hidden_size, 1)

    def forward(self, x_hist, y_hist=None, teacher_forcing=0.0):
        """
        x_hist:  tenzor oblika (B, T, 1+F)  → istorija: [target || features] po času
                 - poslednja kolona targeta bi trebalo da je standardizovan (npr. z-score)
        y_hist:  opcioni tenzor (B, H, 1)   → budući "ground truth" target za teacher forcing
        teacher_forcing: verovatnoća (0..1) da u datom decoder koraku koristimo "pravi" y
                         umesto sopstvene prethodne predikcije (važi samo u treningu)

        Povratna vrednost: (B, H)  → H narednih predviđenih target vrednosti (na skali modela)
        """
        # x_hist: (B, T, 1+F)
        B, T, F = x_hist.shape

        # ENCODER: prolaz kroz istoriju, uzimamo završna (h, c) stanja kao inicijalna za decoder
        _, (h, c) = self.enc(x_hist)

        # START TOKEN za decoder:
        # koristimo poslednju poznatu vrednost targeta iz istorije kao prvi ulaz u decoder
        # x_hist[:, -1:, :1] → (B, 1, 1): uzimamo samo target kanal (prva kolona)
        last_y = x_hist[:, -1:, :1]
        dec_in = last_y

        outs = []        # sakupljamo izlaze po koraku: lista tenzora (B, 1, 1)
        h_dec, c_dec = h, c  # inicijalna stanja decoder-a su encoder-ova završna stanja

        # DECODER petlja: generišemo H narednih koraka
        for _ in range(self.horizon):
            # Jedan decoder korak
            y_dec, (h_dec, c_dec) = self.dec(dec_in, (h_dec, c_dec))  # y_dec: (B, 1, hidden)
            y_hat = self.proj(y_dec)                                  # (B, 1, 1)
            outs.append(y_hat)

            # Odaberi sledeći ulaz u decoder:
            # - u treningu, sa verovatnoćom 'teacher_forcing' koristimo naredni "pravi" y iz y_hist
            # - inače koristimo sopstvenu predikciju y_hat (autoregresivno)
            #
            # Napomena: torch.rand(1).item() generiše JEDAN slučajan broj po vremenskom koraku
            # (isti za celu batch instancu u tom koraku). Nije per-sample.
            if self.training and y_hist is not None and torch.rand(1).item() < teacher_forcing:
                # koristimo sledeći ground-truth korak kao ulaz i "odsečemo" ga iz y_hist
                dec_in = y_hist[:, :1, :]   # (B, 1, 1)
                y_hist = y_hist[:, 1:, :]   # shift za sledeći krug
            else:
                # koristimo vlastitu predikciju kao ulaz za naredni korak
                dec_in = y_hat              # (B, 1, 1)

        # Spajamo vremenske korake u sekvencu dužine H: (B, H, 1) → (B, H)
        y_out = torch.cat(outs, dim=1)
        return y_out.squeeze(-1)
