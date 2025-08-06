from flask import Flask
from flask_cors import CORS
from app.routes.upload_routes import upload_bp


app = Flask(__name__)
CORS(app, origins=["http://localhost:5173"])

app.register_blueprint(upload_bp, url_prefix='/api')


if __name__ == "__main__":
    app.run(debug=True)
