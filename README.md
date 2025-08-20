# PowerCast – Kratkoročna prognoza potrošnje električne energije

## 🎯 Opis projekta

Cilj projekta **PowerCast** je razvoj inteligentnog softverskog sistema za **kratkoročnu prognozu potrošnje električne energije** po regijama, na period do 7 dana unaprijed.  
Sistem koristi meteorološke podatke i istorijske serije opterećenja za treniranje neuronskih mreža, te omogućava:

- Uvoz i normalizaciju vremenskih serija (load, weather & holiday) u **MongoDB**  
- Treniranje neuronskih mreža (LSTM Seq2Seq, opcionalno GRU) sa izborom hiperparametara  
- Čuvanje modela u **GridFS** i metapodataka u kolekciji `models`  
- Generisanje prognoza i izračunavanje **MAPE** metrika  
- Vizualizaciju rezultata i interaktivnu evaluaciju prognoza  
- Intuitivan frontend interfejs za rad sa modelima i prognozama  

---

## 🏗️ Arhitektura sistema

Sistem je realizovan kao **višeslojna arhitektura**:

- **Frontend**: React (Vite) + Ant Design  
- **Backend**: Python (Flask + PyTorch)  
- **Baza podataka**: MongoDB (čuvanje serija, modela, fajlova)  

```
┌───────────┐     HTTP/JSON      ┌─────────────┐      PyTorch
│  Frontend │  ⇆  REST API  ⇆   │   Backend   │  ⇆   ML modeli
└───────────┘                   └─────────────┘
        │                             │
        ▼                             ▼
    React UI                   MongoDB + GridFS
```

---

## 🚀 Tehnologije

- **Frontend**:  
  - React (Vite)  
  - Ant Design (UI)  
  - Axios (API pozivi)  

- **Backend**:  
  - Flask (REST API)  
  - PyTorch (neuronske mreže – LSTM Seq2Seq, GRU)  
  - pandas, numpy (obrada podataka)  

- **Baza**:  
  - MongoDB + GridFS (čuvanje modela i serija)  

---

## 📂 Struktura projekta

```
powercast/
├── backend/
│   ├── api/            # Flask rute (train, forecast, evaluate, coverage, model)
│   ├── ml/             # ML moduli: dataset, features, modeli, trening
│   ├── db.py           # konekcija na MongoDB i GridFS
│   └── app.py          # entrypoint backend aplikacije
│
├── frontend/
│   ├── src/
│   │   ├── pages/      # stranice: Home, Coverage, Train, Models, Forecast, Evaluate
│   │   ├── components/ # React komponente
│   │   ├── services/   # API pozivi
│   │   └── App.jsx     # glavni layout
│   └── vite.config.js  # Vite konfiguracija
│
└── README.md           # ovaj dokument
```

---

## 📌 Sprintovi

### ✅ Sprint 0 – Skeleton i test konekcije
- Kreirani projekti: `backend/` (Flask) i `frontend/` (React + Vite + AntD)  
- Povezana aplikacija sa MongoDB i testirana ruta `/api/health`  
- Frontend prikazuje poruku “Backend OK”  

### ✅ Sprint 1 – Import podataka
- Uvoz CSV podataka (load, weather i holiday) u MongoDB kolekcije:  
  - `import_load_csv`  
  - `import_weather_csv`  
  - `import_holidays`  
- Normalizacija vremenskih serija na satni nivo  
- Validacija podataka (neispravne vrijednosti i prazni redovi se ignorišu)  

### ✅ Sprint 2 – Coverage i trening modela
- Ruta `/api/coverage` – pregled dostupnih vremenskih perioda po regionu  
- Implementiran **LSTM Seq2Seq** model u PyTorch-u  
- API ruta `/api/train/start` za treniranje po regionima  
- Čuvanje modela u `models` + GridFS artefakti  
- Frontend stranice: **Train** (izbor hiperparametara) i **Models** (pregled treniranih modela i metrika)  

### ✅ Sprint 3 – Prognoza
- API ruta `/api/forecast/run` – generisanje prognoze za region i period  
- Ekspozicija prognoze kao JSON + eksport u CSV  
- Frontend grafički prikaz prognoze (line chart)  
- Riješeni problemi sa vremenskim zonama (UTC vs lokalno, `Z` sufiks)  

### ✅ Sprint 4 – Evaluacija
- API ruta `/api/evaluate/run` – poređenje modela sa stvarnim podacima  
- Izračunavanje **MAPE** (Mean Absolute Percentage Error)  
- Frontend stranica **Evaluate** – interaktivni prikaz “Actual vs Forecast”  
- Dobijen primjer: trening za januar 2018 → predikcija prvih 7 dana februara (MAPE ≈ 11.5%)  

---

## ▶️ Pokretanje projekta

1. Kloniraj repo i otvori terminal:

```bash
git clone https://github.com/<tvoj-username>/powercast.git
cd powercast
```

2. Pokreni **MongoDB** lokalno.  

3. Backend:

```bash
cd backend
.\.venv\Scripts\Activate.ps1 
pip install -r requirements.txt
python app.py
```

4. Frontend:

```bash
cd frontend
npm install
npm run dev
```

5. Otvori u browseru:  
👉 `http://localhost:5173`

---

## 📊 Primer korišćenja

- `/train`: treniranje modela za `N.Y.C.` i `LONGIL` u periodu 2018–2021  
- `/models`: pregled sačuvanih modela i MAPE metrika  
- `/forecast`: prognoza na 7 dana unaprijed  
- `/evaluate`: poređenje prognoze i stvarnih podataka  

---

## 📈 Metodologija

- **Podaci**: satna potrošnja (MW) i meteorološki podaci (temperatura, vlažnost, padavine, solarno zračenje, vjetar).  
- **Model**: LSTM Seq2Seq sa teacher forcing strategijom; testirane i GRU varijante.  
- **Metod evaluacije**: MAPE kao osnovna metrika tačnosti.  
- **Frontend**: omogućava interaktivno biranje regije, perioda i pregled performansi modela.  

---

## ⚠️ Ograničenja i budući rad

- Trening na kratkom periodu (1 mjesec) dovodi do **zaglađenih prognoza** i slabijeg hvatanja pikova.  
- Trenutno se koristi samo LSTM/GRU; plan je testirati i **Transformer** modele.  
- Potrebno je dodati više ulaznih feature-a (radni dan vs vikend, praznici, vremenski uslovi).  
- U budućnosti: automatski izbor najboljeg modela po regiji + Docker orkestracija.  

---

## 📌 Autor i mentorstvo

📌 Projekat iz predmeta **Inteligentni softverski infrastrukturni sistemi**  
👩‍🏫 Mentor: **Sladjana Turudić**  
👨‍💻 Autor: **Radoslav Mastilović**  
