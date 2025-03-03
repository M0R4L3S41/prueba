from flask import Flask, render_template, request, send_file, jsonify, Blueprint, redirect, session
import fitz  # PyMuPDF para manejar PDFs
import qrcode
import os
import re
from io import BytesIO, StringIO
from PIL import Image  # Importar la biblioteca Pillow
from datetime import datetime  # Para manejar fechas y horas
import pytz  # Para manejar zonas horarias
import random  # Para generar el número aleatorio
from barcode import Code128
from barcode.writer import ImageWriter, SVGWriter
from cairosvg import svg2png  # Para convertir SVG a PNG

# Inicialización de la aplicación
app = Flask(__name__)

# Configuración para el tamaño máximo de archivos (16 MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

# Crear el Blueprint para las funcionalidades de enmarcado
enmarcado_bp = Blueprint('enmarcado', __name__, url_prefix='/')

# Constantes
BACKGROUND_PDF_PATH = "static/marcoparaactas.pdf"
MARCOS_FOLDER = "static/marcostraceros"

# Diccionario de abreviaturas y estados
ESTADOS = {
    "AS": "AGUASCALIENTES", "BC": "BAJA CALIFORNIA", "BS": "BAJA CALIFORNIA SUR", "CM": "CAMPECHE",
    "CL": "COAHUILA", "CM": "COLIMA", "CS": "CHIAPAS", "CH": "CHIHUAHUA", "DF": "DISTRITO FEDERAL",
    "DG": "DURANGO", "GT": "GUANAJUATO", "GR": "GUERRERO", "HG": "HIDALGO", "JC": "JALISCO",
    "MC": "MÉXICO", "MN": "MICHOACÁN", "MS": "MORELOS", "NT": "NAYARIT", "NL": "NUEVO LEÓN",
    "OC": "OAXACA", "PL": "PUEBLA", "QT": "QUERÉTARO", "QR": "QUINTANA ROO", "SP": "SAN LUIS POTOSÍ",
    "SL": "SINALOA", "SR": "SONORA", "TC": "TABASCO", "TS": "TAMAULIPAS", "TL": "TLAXCALA",
    "VZ": "VERACRUZ", "YN": "YUCATÁN", "ZS": "ZACATECAS", "NE": "NACIDO EN EL EXTRANJERO"
}

# Definir la zona horaria de México
mexico_timezone = pytz.timezone('America/Mexico_City')

def is_within_working_hours():
    """Verifica si la hora actual está dentro del horario de trabajo."""
    now = datetime.now(pytz.utc).astimezone(mexico_timezone)
    print(f"Hora actual del servidor (Hora México): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    start_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
    end_time = now.replace(hour=17, minute=0, second=0, microsecond=0)
    return start_time <= now <= end_time

def generate_qr_code(text):
    """Genera un código QR en memoria y devuelve un objeto Pixmap de PyMuPDF."""
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=0)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    
    img_byte_array = BytesIO()
    img.save(img_byte_array, format="PNG")
    img_byte_array.seek(0)

    return fitz.Pixmap(img_byte_array)

def generate_barcode(text):
    """Genera un código de barras en SVG y lo convierte en Pixmap."""
    try:
        svg_io = StringIO()
        options = {'write_text': False, 'module_height': 15, 'module_width': 0.3, 'quiet_zone': 1}
        Code128(text, writer=SVGWriter()).write(svg_io, options=options)
        svg_content = svg_io.getvalue()

        width_match = re.search(r'width="(\d+(\.\d+)?)"', svg_content)
        height_match = re.search(r'height="(\d+(\.\d+)?)"', svg_content)

        if width_match and height_match:
            svg_content = svg_content.replace(width_match.group(0), 'width="120"')
            svg_content = svg_content.replace(height_match.group(0), 'height="15"')

        png_data = BytesIO()
        svg2png(bytestring=svg_content.encode('utf-8'), write_to=png_data, dpi=300)
        png_data.seek(0)

        return fitz.open("png", png_data.read())
    except Exception as e:
        print(f"Error generando código de barras SVG: {e}")
        return None

def overlay_pdf_on_background(pdf_file, output_stream, apply_front, apply_rear, apply_folio):
    """Superpone PDFs según las opciones seleccionadas."""
    try:
        selected_pdf = fitz.open(stream=pdf_file.read(), filetype="pdf")
        if len(selected_pdf) == 0:
            return False, "Error: El PDF cargado está vacío."

        output_pdf = fitz.open()
        if apply_front:
            background_pdf = fitz.open(BACKGROUND_PDF_PATH)
            for page_num in range(len(background_pdf)):
                background_page = background_pdf.load_page(page_num)
                new_page = output_pdf.new_page(width=background_page.rect.width, height=background_page.rect.height)
                new_page.show_pdf_page(new_page.rect, background_pdf, page_num)
                if page_num < len(selected_pdf):
                    new_page.show_pdf_page(new_page.rect, selected_pdf, page_num)
            background_pdf.close()
        else:
            for page_num in range(len(selected_pdf)):
                selected_page = selected_pdf.load_page(page_num)
                new_page = output_pdf.new_page(width=selected_page.rect.width, height=selected_page.rect.height)
                new_page.show_pdf_page(new_page.rect, selected_pdf, page_num)

        if apply_folio:
            folio_random = random.randint(100000, 999999)
            barcode_text = f"A30{folio_random}"
            first_page = output_pdf.load_page(0)
            first_page.insert_text((85, 48), "FOLIO", fontsize=14, fontname="times-bold", color=(0, 0, 0))
            first_page.insert_text((75, 65), f"A30-{folio_random}", fontsize=12, fontname="times-bold", color=(0, 0, 0))
            barcode_img = generate_barcode(barcode_text)
            if barcode_img:
                first_page.insert_image(fitz.Rect(45, 72, 175, 87), pixmap=barcode_img)

        output_pdf.save(output_stream)
        return True, None
    except Exception as e:
        return False, f"Error: {e}"

app.register_blueprint(enmarcado_bp)

if _name_ == "_main_":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5001)))
