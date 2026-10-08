import os
import re
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\etiop\AppData\Local\Tesseract-OCR\tesseract.exe'
from pypdf import PdfReader
from docx import Document
from PIL import ImageGrab
def identificar_archivo(ruta):
    extension = os.path.splitext(ruta)[1].lower()
    if extension == ".pdf":
        return "pdf"
    elif extension == ".docx":
        return "docx"
    elif extension in [".jpg", ".jpeg", ".png", ".bmp"]:
        return "imagen"
    else:
        return "desconocido"
def leer_archivos(ruta):
    tipo = identificar_archivo(ruta)
    if tipo == "pdf":
        reader = PdfReader(ruta)
        texto = ""
        for page in reader.pages:
            texto += page.extract_text() + "\n"
        return texto
    elif tipo == "docx":
        doc = Document(ruta)
        texto = ""
        for para in doc.paragraphs:
            texto += para.text + "\n"
        return texto
    elif tipo == "imagen":
        imagen = ImageGrab.grabclipboard()
        if imagen is not None:
            texto = pytesseract.image_to_string(imagen, lang='spa')  # Cambia 'spa' a 'eng' si quieres inglés
            return texto
        else:
            return "No se pudo leer la imagen."
    else:
        return "Tipo de archivo no soportado."
def encontrar_rutas_existentes(texto):
    # Patrón para rutas de Windows y Linux/Mac
    patron = r'([A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*|\/(?:[^\/\r\n]+\/)*[^\/\r\n]*)'
    rutas = re.findall(patron, texto)
    # Validar si las rutas existen en el sistema
    rutas_existentes = [ruta for ruta in rutas if os.path.exists(ruta)]
    return rutas, rutas_existentes
prompt = input("Ingrese el prompt: ")
rutas_existentes = encontrar_rutas_existentes(prompt)
archi = leer_archivos(rutas_existentes)
print(archi)