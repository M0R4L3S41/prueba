from flask import Flask, render_template, request, send_file, jsonify, Blueprint, redirect, session
import fitz  # PyMuPDF para manejar PDFs
import qrcode
import os
from io import BytesIO
from PIL import Image  # Importar la biblioteca Pillow
from datetime import datetime  # Para manejar fechas y horas
import pytz  # Para manejar zonas horarias
import random  # Para generar el número aleatorio
from barcode import Code128
from barcode.writer import ImageWriter

# Inicialización de la aplicación
app = Flask(_name_)

# Configuración para el tamaño máximo de archivos (16 MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

# Crear el Blueprint para las funcionalidades de enmarcado
enmarcado_bp = Blueprint('enmarcado', _name_, url_prefix='/')

# Constantes
BACKGROUND_PDF_PATH = "static/marcoparaactas.pdf"
MARCOS_FOLDER = "static/marcostraceros"

# Diccionario de abreviaturas y estados
ESTADOS = {
    "AS": "AGUASCALIENTES", "BC": "BAJA CALIFORNIA", "BS": "BAJA CALIFORNIA SUR", "CC": "CAMPECHE",
    "CL": "COAHUILA", "CM": "COLIMA", "CS": "CHIAPAS", "CH": "CHIHUAHUA", "DF": "DISTRITO FEDERAL",
    "DG": "DURANGO", "GT": "GUANAJUATO", "GR": "GUERRERO", "HG": "HIDALGO", "JC": "JALISCO",
    "MC": "MÉXICO", "MN": "MICHOACÁN", "MS": "MORELOS", "NT": "NAYARIT", "NL": "NUEVO LEÓN",
    "OC": "OAXACA", "PL": "PUEBLA", "QT": "QUERÉTARO", "QR": "QUINTANA ROO", "SP": "SAN LUIS POTOSÍ",
    "SL": "SINALOA", "SR": "SONORA", "TC": "TABASCO", "TS": "TAMAULIPAS", "TL": "TLAXCALA",
    "VZ": "VERACRUZ", "YN": "YUCATÁN", "ZS": "ZACATECAS", "NE": "NACIDO EN EL EXTRANJERO"
}

# Definir la zona horaria de México
mexico_timezone = pytz.timezone('America/Mexico_City')

# Funciones auxiliares
def is_within_working_hours():
    """Verifica si la hora actual está dentro del horario de trabajo."""
    # Obtener la hora actual en UTC y convertirla a la zona horaria de México
    now = datetime.now(pytz.utc).astimezone(mexico_timezone)
    
    # Imprimir la hora actual del servidor en la zona horaria de México
    print(f"Hora actual del servidor (Hora México): {now.strftime('%Y-%m-%d %H:%M:%S')}")

    # Definir el horario de trabajo (9 AM a 5 PM)
    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = now.replace(hour=23, minute=59, second=59, microsecond=0)

    # Verificar si la hora actual está dentro del horario permitido
    return start_time <= now <= end_time

def generate_qr_code(text):
    """Genera un código QR en memoria y devuelve un objeto Pixmap de PyMuPDF."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=0,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')

    # Convertir la imagen de QR a formato PNG utilizando Pillow
    img_byte_array = BytesIO()
    img.save(img_byte_array, format="PNG")  # Guardar en BytesIO como PNG
    img_byte_array.seek(0)  # Mover el puntero al inicio

    # Crear un Pixmap de PyMuPDF desde el stream de bytes PNG
    qr_img_fitz = fitz.Pixmap(img_byte_array)  # Cargar imagen PNG directamente en Pixmap
    
    return qr_img_fitz

def generate_barcode(text):
    """Genera un código de barras en SVG y lo convierte en un Pixmap de alta calidad para PDF."""
    try:
        # Crear un objeto StringIO para capturar el SVG
        svg_io = StringIO()
        options = {
            'write_text': False,
            'module_height': 15,  # Altura en píxeles
            'module_width': 0.3,  # Ancho mínimo de cada barra
            'quiet_zone': 1
        }

        # Generar código de barras en SVG
        Code128(text, writer=SVGWriter()).write(svg_io, options=options)
        svg_content = svg_io.getvalue()

        # Ajustar dimensiones en SVG
        width_match = re.search(r'width="(\d+(\.\d+)?)"', svg_content)
        height_match = re.search(r'height="(\d+(\.\d+)?)"', svg_content)

        if width_match and height_match:
            svg_content = svg_content.replace(width_match.group(0), 'width="120"')
            svg_content = svg_content.replace(height_match.group(0), 'height="15"')

        # Convertir el SVG a PNG
        png_data = BytesIO()
        svg2png(bytestring=svg_content.encode('utf-8'), write_to=png_data, dpi=300)
        png_data.seek(0)

        # Crear un Pixmap de fitz
        barcode_img = fitz.open("png", png_data.read())

        return barcode_img
    except Exception as e:
        print(f"Error generando código de barras SVG: {e}")
        return None

def overlay_pdf_on_background(pdf_file, output_stream, apply_front, apply_rear, apply_folio):
    """Superpone PDFs según las opciones seleccionadas."""
    try:
        # Leer el PDF en memoria
        try:
            selected_pdf = fitz.open(stream=pdf_file.read(), filetype="pdf")
        except Exception as e:
            return False, f"Error al cargar el archivo PDF: {e}"

        if len(selected_pdf) == 0:
            return False, "Error: El PDF cargado está vacío."

        output_pdf = fitz.open()

        # 🟢 Aplicar fondo delantero (marco)
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

        # 🟢 Aplicar fondo trasero (según estado)
        if apply_rear:
            try:
                filename = getattr(pdf_file, 'filename', "unknown.pdf")
                state_abbr = filename[11:13].upper()
                if state_abbr in ESTADOS:
                    state_pdf_path = os.path.join(MARCOS_FOLDER, f"{state_abbr}.pdf")
                    if os.path.exists(state_pdf_path):
                        state_pdf = fitz.open(state_pdf_path)
                        for state_page_num in range(len(state_pdf)):
                            new_page = output_pdf.new_page(width=state_pdf[state_page_num].rect.width, height=state_pdf[state_page_num].rect.height)
                            new_page.show_pdf_page(new_page.rect, state_pdf, state_page_num)
                        state_pdf.close()
            except Exception as e:
                print(f"Error al cargar fondo trasero: {e}")

        # 🟢 Insertar QR en la segunda página
        if len(output_pdf) > 1:
            qr_img = generate_qr_code("QR_Data")  # Modifica aquí si necesitas datos dinámicos
            second_page = output_pdf.load_page(1)
            second_page.insert_image(fitz.Rect(34, 24, 95, 88), pixmap=qr_img)
            second_page.insert_image(fitz.Rect(20, second_page.rect.height - 45, 55, second_page.rect.height - 10), pixmap=qr_img)

        # 🟢 Insertar Folio y Código de Barras
        if apply_folio:
            try:
                folio_random = random.randint(100000, 999999)
                barcode_text = "A30" + str(folio_random)

                first_page = output_pdf.load_page(0)
                first_page.insert_text((85, 48), "FOLIO", fontsize=14, fontname="times-bold", color=(0, 0, 0))
                first_page.insert_text((75, 65), "A30-" + str(folio_random), fontsize=12, fontname="times-bold", color=(0, 0, 0))

                # Generar código de barras
                barcode_img = generate_barcode(barcode_text)
                
                if barcode_img:
                    first_page.insert_image(fitz.Rect(45, 72, 175, 87), pixmap=barcode_img)
                else:
                    print("❌ Error: No se pudo generar el código de barras.")
            except Exception as e:
                print(f"❌ Error al insertar el folio: {e}")

        output_pdf.save(output_stream)
        return True, None
    except Exception as e:
        return False, f"❌ Error general: {e}"
# Rutas del Blueprint
@enmarcado_bp.route('/process_pdf', methods=['POST'])
def process_pdf():
    """Procesa el PDF según las opciones seleccionadas."""
    if not is_within_working_hours():
        return "El servicio no está disponible fuera del horario de 9 AM a 5 PM.", 403
    
    try:
        if 'pdf_file' not in request.files:
            print("No file in request.files")
            return 'No file uploaded', 400

        pdf_file = request.files['pdf_file']
        print(f"Archivo recibido: {pdf_file.filename}")
        
        if pdf_file.filename == '':
            print("No file selected")
            return 'No selected file', 400
        
        # Leer las opciones de enmarcado del formulario
        apply_front = True if request.form.get('front_frame') == 'on' else False
        apply_rear  = True if request.form.get('rear_frame')  == 'on' else False
        apply_folio = True if request.form.get('folio')       == 'on' else False

        output_stream = BytesIO()
        success, message = overlay_pdf_on_background(pdf_file, output_stream, apply_front, apply_rear, apply_folio)
        if not success:
            print(f"Error generando el PDF: {message}")
            return message, 500

        output_stream.seek(0)
        return send_file(output_stream, as_attachment=True, download_name=f"_{pdf_file.filename}", mimetype='application/pdf')

    except Exception as e:
        print(f"Error procesando PDF: {e}")
        return 'Error procesando archivo PDF', 500

# Registrar el Blueprint con la aplicación
app.register_blueprint(enmarcado_bp)

# Configuración del servidor para producción o local
if _name_ == '_main_':
    app.run(debug=os.getenv("FLASK_DEBUG", False), host='0.0.0.0', port=os.getenv("PORT", 5001))
