from flask import Flask
from flask_cors import CORS

# Kreiranje Flask aplikacije
app = Flask(__name__)

# Omogućavanje CORS (za komunikaciju između frontend-a i backend-a)
cors = CORS(app, resources={r"/*": {"origins": "*"}})

# Konfiguracija foldera za upload fajlova
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Importovanje ruta iz views.py (implementiraćemo kasnije)
from views import *

# Pokretanje aplikacije
if __name__ == '__main__':
    app.run(port=5000, debug=True)
