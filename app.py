import os
import uuid
import logging
import base64
from flask import Flask, request, send_file, jsonify, render_template
from werkzeug.utils import secure_filename
from PIL import Image
from io import BytesIO
import traceback
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.update(
    MAX_CONTENT_LENGTH=100 * 1024 * 1024,  # 100MB limit
    ALLOWED_EXTENSIONS={'png', 'jpg', 'jpeg', 'webp'},
    UPLOAD_FOLDER='uploads',
    OUTPUT_FOLDER='output',
    SECRET_KEY=str(uuid.uuid4())
)

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

class ImageProcessor:
    @staticmethod
    def allowed_file(filename):
        """Check if file has allowed extension"""
        if not filename or not isinstance(filename, str):
            return False
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

    @staticmethod
    def convert_to_jpeg(file_stream, filename):
        """Convert image to JPEG format for consistent PDF generation"""
        try:
            img_bytes = file_stream.read()
            if not img_bytes:
                raise ValueError("Empty file content")
                
            with Image.open(BytesIO(img_bytes)) as img:
                # Convert to RGB if needed (especially for PNGs)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                output = BytesIO()
                img.save(output, format='JPEG', quality=90)
                return output.getvalue()
                
        except Exception as e:
            logger.error(f"Error converting {filename}: {str(e)}")
            return None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload-images', methods=['POST'])
def upload_images():
    """Handle image uploads and conversion"""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files uploaded'}), 400
            
        files = request.files.getlist('files')
        if not files or all(file.filename == '' for file in files):
            return jsonify({'error': 'No files selected'}), 400

        processed_images = []
        for file in files:
            if not file or not hasattr(file, 'filename'):
                continue
                
            filename = secure_filename(file.filename)
            if not ImageProcessor.allowed_file(filename):
                continue

            try:
                converted_data = ImageProcessor.convert_to_jpeg(file.stream, filename)
                if converted_data:
                    processed_images.append({
                        'id': str(uuid.uuid4()),
                        'data': base64.b64encode(converted_data).decode('utf-8'),
                        'name': filename
                    })
            except Exception as e:
                logger.error(f"Error processing {filename}: {str(e)}")
            finally:
                if hasattr(file, 'close'):
                    file.close()

        if not processed_images:
            return jsonify({'error': 'No valid images processed'}), 400

        return jsonify({'images': processed_images})
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/generate-pdf', methods=['POST'])
def generate_pdf():
    """Generate PDF from images"""
    try:
        data = request.get_json()
        if not data or not isinstance(data, dict) or 'images' not in data:
            return jsonify({'error': 'Invalid request data'}), 400

        images = data['images']
        if not isinstance(images, list) or not images:
            return jsonify({'error': 'No images provided'}), 400

        pdf_buffer = BytesIO()
        image_objects = []
        
        for img_data in images:
            try:
                if not img_data or not isinstance(img_data, dict) or not img_data.get('data'):
                    continue
                    
                img_bytes = base64.b64decode(img_data['data'])
                img = Image.open(BytesIO(img_bytes))
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                image_objects.append(img)
            except Exception as e:
                logger.error(f"Error loading image: {str(e)}")
                continue

        if not image_objects:
            return jsonify({'error': 'No valid images to convert'}), 400

        # Save as PDF
        image_objects[0].save(
            pdf_buffer,
            format='PDF',
            save_all=True,
            append_images=image_objects[1:] if len(image_objects) > 1 else None,
            quality=90
        )
        
        pdf_buffer.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'document_{timestamp}.pdf'
        )
        
    except Exception as e:
        logger.error(f"PDF generation failed: {str(e)}")
        return jsonify({'error': 'Failed to generate PDF'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)