from flask import Flask, render_template, request, send_file, jsonify
import fitz  # PyMuPDF para manejar PDFs
import qrcode
import os
from io import BytesIO
from PIL import Image  # Importar la biblioteca Pillow
from datetime import datetime  # Para manejar fechas y horas
import pytz  # Para manejar zonas horarias
from flask import Blueprint, render_template, request, redirect, session, send_file
import random  # Para generar el número aleatorio
from barcode import Code128
from barcode.writer import ImageWriter

app = Flask(__name__)
# Crear el Blueprint para las funcionalidades de enmarcado
enmarcado_bp = Blueprint('enmarcado', __name__, url_prefix='/')

# Configuración para el tamaño máximo de archivos (16 MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

# Ruta al archivo de fondo
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

def is_within_working_hours():
    # Obtener la hora actual en UTC y convertirla a la zona horaria de México
    now = datetime.now(pytz.utc).astimezone(mexico_timezone)
    
    # Imprimir la hora actual del servidor en la zona horaria de México
    print(f"Hora actual del servidor (Hora México): {now.strftime('%Y-%m-%d %H:%M:%S')}")

    # Definir el horario de trabajo (9 AM a 5 PM)
    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = now.replace(hour=23, minute=59, second=59, microsecond=0)

    # Verificar si la hora actual está dentro del horario permitido
    return start_time <= now <= end_time

# Función para generar el código QR en memoria (BytesIO)
def generate_qr_code(text):
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

# Función para generar código de barras
def generate_barcode(text):
    try:
        # Crear un objeto BytesIO para guardar la imagen
        output = BytesIO()
        
        # Configurar el escritor para no mostrar texto y reducir la zona de silencio
        writer = ImageWriter()
        writer.set_options({
            'write_text': False,  # Esto desactiva el texto debajo del código
            'quiet_zone': 1       # Reducir la zona de silencio alrededor del código
        })
        
        # Generar código de barras Code128 sin texto
        code128 = Code128(text, writer=writer)
        code128.write(output)
        
        # Mover el puntero al inicio del stream
        output.seek(0)

        # Guardar la imagen temporalmente para usarla con fitz
        with open("temp_barcode.png", "wb") as f:
            f.write(output.getvalue())

        # Crear un Pixmap de PyMuPDF a partir de la imagen generada
        barcode_img = fitz.open("temp_barcode.png")

        return barcode_img
    except Exception as e:
        print(f"Error generando código de barras: {e}")
        return None

# Función modificada para superponer PDFs según las opciones seleccionadas
def overlay_pdf_on_background(pdf_file, output_stream, apply_front, apply_rear, apply_folio):
    try:
        # Leer el PDF subido en memoria
        try:
            selected_pdf = fitz.open(stream=pdf_file.read(), filetype="pdf")
        except Exception as e:
            return False, f"Error al cargar el archivo PDF: {e}"

        if len(selected_pdf) == 0:
            return False, "Error: El PDF cargado está vacío."

        output_pdf = fitz.open()

        # Si se selecciona el enmarcado delantero, se usa el PDF de fondo (marcoparaactas.pdf)
        if apply_front:
            background_pdf = fitz.open(BACKGROUND_PDF_PATH)
            for page_num in range(len(background_pdf)):
                background_page = background_pdf.load_page(page_num)
                new_page = output_pdf.new_page(width=background_page.rect.width, height=background_page.rect.height)
                new_page.show_pdf_page(new_page.rect, background_pdf, page_num)
                if page_num < len(selected_pdf):
                    selected_page = selected_pdf.load_page(page_num)
                    new_page.show_pdf_page(new_page.rect, selected_pdf, page_num)
            background_pdf.close()
        else:
            # Si NO se selecciona el delantero, se agregan las páginas del PDF subido directamente
            for page_num in range(len(selected_pdf)):
                selected_page = selected_pdf.load_page(page_num)
                new_page = output_pdf.new_page(width=selected_page.rect.width, height=selected_page.rect.height)
                new_page.show_pdf_page(new_page.rect, selected_pdf, page_num)

        # Si se selecciona el enmarcado trasero, se agregan los marcos (segunda parte)
        if apply_rear:
            filename = os.path.basename(pdf_file.filename)
            state_abbr = filename[11:13].upper()
            if state_abbr in ESTADOS:
                state_pdf_path = os.path.join(MARCOS_FOLDER, f"{state_abbr}.pdf")
                if os.path.exists(state_pdf_path):
                    state_pdf = fitz.open(state_pdf_path)
                    for state_page_num in range(len(state_pdf)):
                        new_page = output_pdf.new_page(width=state_pdf[state_page_num].rect.width, height=state_pdf[state_page_num].rect.height)
                        new_page.show_pdf_page(new_page.rect, state_pdf, state_page_num)
                    state_pdf.close()

        # Insertar códigos QR en la segunda página (parte inferior izquierda) se mantiene sin cambios
        if len(output_pdf) > 1:
            filename = os.path.basename(pdf_file.filename)
            qr_img = generate_qr_code(filename)
            second_page = output_pdf.load_page(1)
            # Primer QR (parte superior)
            qr_rect = fitz.Rect(34, 24, 95, 88)
            second_page.insert_image(qr_rect, pixmap=qr_img)
            # Segundo QR (parte inferior izquierda)
            page_height = second_page.rect.height
            qr_size_small = 17 * 2.83465  # Tamaño del segundo QR en puntos
            move_up = 5.33 * 2.83465  # Ajuste para mover el QR hacia arriba
            move_right = 4.26 * 2.83465  # Ajuste para mover el QR hacia la derecha
            qr_rect_bottom_left = fitz.Rect(
                20 + move_right,
                (page_height - qr_size_small - 10) - move_up,
                (20 + qr_size_small + move_right),
                (page_height - 10) - move_up
            )
            second_page.insert_image(qr_rect_bottom_left, pixmap=qr_img)

        # Insertar folio (si se selecciona) en la primera página con código de barras real
        if apply_folio:
            folio_random = random.randint(100000, 999999)
            barcode_text = "A30" + str(folio_random)  # Sin espacio para el código de barras

            first_page = output_pdf.load_page(0)
            first_page.insert_text((68, 45), "FOLIO", fontsize=14, fontname="times-bold", color=(0, 0, 0))
            first_page.insert_text((55, 65), "A30-" + str(folio_random), fontsize=12, fontname="times-bold", color=(0, 0, 0))
            
           # Generar imagen del código de barras sin texto (solo el código visual)
            output = BytesIO()
            writer = ImageWriter()
            # Configurar el writer para no mostrar texto
            writer.text_options = {"write_text": False}
            Code128(barcode_text, writer=writer).write(output)
            output.seek(0)
            
            # Insertar imagen del código de barras entre el folio y el texto "CODIGO DE BARRA"
            barcode_img = fitz.Pixmap(output.getvalue())
            if barcode_img:
                first_page.insert_image(fitz.Rect(55, 75, 200, 125), pixmap=barcode_img)

        output_pdf.save(output_stream)
        output_pdf.close()
        selected_pdf.close()
        return True, "PDF generado correctamente."

    except Exception as e:
        print(f"Error overlaying PDFs: {e}")
        return False, f"Error al generar el PDF: {e}"


# Modificar la ruta para leer los checkboxes y pasarlos a la función
@enmarcado_bp.route('/process_pdf', methods=['POST'])
def process_pdf():
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

# Configuración del servidor para producción o local
if __name__ == '__main__':
    app.run(debug=os.getenv("FLASK_DEBUG", False), host='0.0.0.0', port=os.getenv("PORT", 5001))

