from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from app.services.upload_service import process_csv_files

upload_bp = Blueprint('upload', __name__)

@upload_bp.route('/upload', methods=['POST'])
def upload_files():
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400

    files = request.files.getlist('files')

    try:
        result = process_csv_files(files)
        return jsonify({'message': 'Files processed successfully', 'inserted': result}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
