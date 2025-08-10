from pymongo import MongoClient
from gridfs import GridFS
from config import Config

_client = None
_db = None
_fs = None

def get_db():
    global _client, _db, _fs
    if _db is None:
        _client = MongoClient(Config.MONGO_URI)
        _db = _client[Config.MONGO_DB]
        _fs = GridFS(_db, collection="artifacts")
    return _db

def get_fs():
    global _fs
    if _fs is None:
        get_db()
    return _fs
