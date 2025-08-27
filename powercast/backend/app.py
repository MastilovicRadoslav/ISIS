from flask import Flask
from flask_cors import CORS
from config import Config
from db import get_db
from api import api_bp

def create_app():
    app = Flask(__name__)
    
    CORS(app, resources={r"/*": {"origins": Config.CORS_ORIGINS.split(",")}}) #CORS standardno ali za sve rtue

    _ = get_db()  # inicijalizacija konekcije ka Mongo
    app.register_blueprint(api_bp, url_prefix="/api") # registrovanje Blueprint za aktiviranje importa ruta, sve imaju prefiks /api

    @app.get("/") # healt-check
    def root():
        return {"service": "powercast-backend", "ok": True}

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.FLASK_ENV == "development")
