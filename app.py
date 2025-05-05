import os
import uuid
import logging
import base64
from flask import Flask, request, send_file, jsonify, render_template
from werkzeug.utils import secure_filename
from PIL import Image, UnidentifiedImageError
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
    MAX_CONTENT_LENGTH=1000 * 1024 * 1024,  # 1GB limit
    ALLOWED_EXTENSIONS={'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff'},
    SECRET_KEY=str(uuid.uuid4())
)

class ImageProcessor:
    @staticmethod
    def allowed_file(filename):
        """Check if the file has an allowed extension"""
        if not filename or filename.strip() == '':
            return False
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

    @staticmethod
    def process_image(file_stream, filename, edits=None):
        """Process image with optional edits"""
        try:
            if edits is None:
                edits = []
                
            # Read image data
            img_bytes = file_stream.read()
            img_buffer = BytesIO(img_bytes)
            
            with Image.open(img_buffer) as img:
                # Apply edits
                for edit in edits:
                    if edit == 'rotate_90':
                        img = img.rotate(-90, expand=True)
                    elif edit == 'rotate_270':
                        img = img.rotate(90, expand=True)
                    elif edit == 'flip_horizontal':
                        img = img.transpose(Image.FLIP_LEFT_RIGHT)
                    elif edit == 'flip_vertical':
                        img = img.transpose(Image.FLIP_TOP_BOTTOM)
                
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Save to buffer
                output = BytesIO()
                img.save(output, format='JPEG', quality=90)
                return output.getvalue()
                
        except Exception as e:
            logger.error(f"Error processing {filename}: {str(e)}")
            return None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/process-images', methods=['POST'])
def process_images():
    """Handle image processing with edits"""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files uploaded'}), 400
            
        files = request.files.getlist('files')
        if not files:
            return jsonify({'error': 'No files selected'}), 400

        # Get edit instructions from form data
        edits = request.form.getlist('edits[]')
        
        processed_images = []
        for file in files:
            if file and ImageProcessor.allowed_file(file.filename):
                try:
                    processed_data = ImageProcessor.process_image(
                        file.stream,
                        secure_filename(file.filename),
                        edits
                    )
                    if processed_data:
                        processed_images.append({
                            'id': str(uuid.uuid4()),
                            'data': base64.b64encode(processed_data).decode('utf-8'),
                            'name': secure_filename(file.filename)
                        })
                except Exception as e:
                    logger.error(f"Error processing {file.filename}: {str(e)}")
                finally:
                    file.close()

        return jsonify({'images': processed_images})
        
    except Exception as e:
        logger.error(f"Processing error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/generate-pdf', methods=['POST'])
def generate_pdf():
    """Generate PDF from processed images"""
    try:
        data = request.get_json()
        if not data or 'images' not in data:
            return jsonify({'error': 'No images provided'}), 400

        images = data['images']
        if not images:
            return jsonify({'error': 'No valid images'}), 400

        pdf_buffer = BytesIO()
        image_objects = []
        
        # Process all images first
        for img_data in images:
            try:
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
            resolution=100.0
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
        logger.error(f"PDF generation failed: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)