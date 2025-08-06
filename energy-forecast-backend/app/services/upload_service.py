import pandas as pd
from app.db.mongo import energy_data_collection
from datetime import datetime

def clean_column_name(col):
    return col.strip().lower().replace(" ", "_")

def process_csv_files(files):
    total_inserted = 0

    for file in files:
        filename = file.filename
        df = pd.read_csv(file)

        # Očisti nazive kolona
        df.columns = [clean_column_name(c) for c in df.columns]

        # Pretvaranje kolone sa vremenom ako postoji
        if 'datetime' in df.columns:
            df['datetime'] = pd.to_datetime(df['datetime'])
        elif 'date' in df.columns:
            df['datetime'] = pd.to_datetime(df['date'])
            df.drop(columns=['date'], inplace=True)

        # Pretvori u listu dict-ova
        records = df.to_dict(orient='records')

        # Dodaj naziv fajla za identifikaciju
        for r in records:
            r['source_file'] = filename

        # Upis u Mongo
        if records:
            result = energy_data_collection.insert_many(records)
            total_inserted += len(result.inserted_ids)

    return total_inserted
