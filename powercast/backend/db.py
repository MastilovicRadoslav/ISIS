from pymongo import MongoClient
from gridfs import GridFS
from config import Config

# Ovo su globalne varijable koje će čuvati konekciju na bazu, samu bazu i GridFS objekat
_client = None
_db = None
_fs = None

# Funkcija koja vraća bazu
def get_db():
    global _client, _db, _fs
    if _db is None:
        _client = MongoClient(Config.MONGO_URI)
        _db = _client[Config.MONGO_DB]
        _fs = GridFS(_db, collection="artifacts") # Posebna kolekcija za GridFS
    return _db

# Funkcija koja vraća GridFS objekat
def get_fs():
    global _fs
    if _fs is None:
        get_db()
    return _fs
