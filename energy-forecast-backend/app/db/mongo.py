from pymongo import MongoClient

# Konekcija ka lokalnoj MongoDB instanci
client = MongoClient("mongodb://localhost:27017/")

# Baza podataka
db = client["energy_forecast_db"]

# Kolekcije (kao tabele)
energy_data_collection = db["energy_data"]
