#import some modules
#modulo basicos
import os
import re
#modulos de la API nueva de Gemini
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai import errors
#mdulos de voz y audio
import json
import threading
import time
import speech_recognition as sr
import pyttsx3 as tts
import pyaudio
#modulo matematicos
import numpy as np
#modulos de lectura de archivos
import pytesseract
if os.name == "nt":
    #por si el usuario tiene Windows, se le indica la ruta de tesseract.exe
    pytesseract.pytesseract.tesseract_cmd = r'C:\ruta\a\tesseract.exe'
from pypdf import PdfReader
from docx import Document
from PIL import Image, ImageGrab

#incia motor de voz
inicializar = tts.init()
voices = inicializar.getProperty('voices')
for v in voices:
    print(v.id, "-", v.name, "-", v.gender)
print("Volumen actual:", inicializar.getProperty('volume'))
inicializar.setProperty('volume', 1.0)  # fuerza volumen al máximo

# NOMBRE DEL MODELO: con la librería nueva se pasa el nombre del modelo en cada llamada,
# no una sola vez al crear un "GenerativeModel" como antes.
# Lista de respaldo: si uno da 503 (saturado), 429 (cuota) o 404 (retirado), se prueba el siguiente.
# Probados con tu clave. Los 3.5 y 3.6 a veces dan 503, por eso van primero pero con respaldo.
MODELOS = [
    "gemini-3.5-flash-lite","gemini-3.6-flash",
    "gemini-3.8-flash","gemini-3.7-flash",
    "gemini-3.5-flash", "gemini-flash-latest",
    "gemini-3.1-flash-lite", "gemini-flash-lite-latest",
]
# errores que son culpa del MODELO (no de tu mensaje): con estos se pasa al siguiente
ERRORES_DE_MODELO = (500, 503, 429, 404)
EMBED_MODEL_NAME = "gemini-embedding-001"
#Frase activadora para que la IA sepa que es un prompt de voz y no de texto, y responda con voz usamos varias frases pues es dificl que google entienda aveces
VOICE_ACTIVATOR = ["vaini", "va", "baini", "vainilla", "bahini"]
ESTADO = "primero" # el ESTADO inicial de la app, puede ser primero, segundo, tercero, cuarto o quinto
CODIGOS_ESTADOS = [
    {"codigo": "3*3*3/", "estado": "tercero"},
    {"codigo": "4*4*4/", "estado": "cuarto"},
    {"codigo": "5*5*5/", "estado": "quinto"},
    {"codigo": "2*2*2/", "estado": "segundo"},
    {"codigo": "1*1*1/", "estado": "primero"},
]
VOICE_PROMPT = "" # el prompt de voz inicial para el llamado de la app
#lista de funciones
FUNCIONES = [
    "sube el volumen al maximo",
    "baja el volumen al minimo",
    "haz silencio",
    "silencio",
    "mute",
    "callate",
    "/micoff",
    "/micon",
    "/vozon",
    "/vozoff",
    "/premium",
    "/primero",
    "/segundo",
    "/tercero",
    "/cuarto",
    "/quinto",

]
# prompt general: solo arma el chat inicial. Dentro de main() cada ESTADO tiene su propio prompt (se recalcula en cada vuelta)
SYSTEM_PROMPT = ("Eres un asistente personal llamado Vaini. "
                "Estado segundo: es para responder a prompts de voz y dar respuestas cortas y concisas, o sea para pedir un favor; si el usuario mencionó algo simple que tiene que ver con los otros modos, no lo cambies. "
                "Estado primero: es para responder a prompts de texto, y para dar respuestas largas y detalladas. "
                "Estado tercero: es para dar consejos, y para dar respuestas largas y detalladas. "
                "Estado cuarto: es para dar consejos de trabajo o proyectos, y para dar respuestas largas y detalladas. "
                "Estado quinto: es para dar consejos de enseñanza o aprendizaje, y para dar respuestas largas y detalladas. "
                "IMPORTANTE NUNCA OLVIDAR: mira qué intención tiene el usuario para saber qué ESTADO definir. Si es un ESTADO de tercero pon este código al final 3*3*3/, cuarto pon 4*4*4/, quinto pon 5*5*5/, y si es un ESTADO de segundo pon 2*2*2/. ")

# ---------- utilidades ----------
MAX_CHARS_VOZ = 400   # máximo de caracteres que Vaini lee en voz alta (0 = leer todo)

def _patron_codigo(codigo):
    # "3*3*3/" -> acepta también "3 * 3 * 3 /", "3\*3\*3/" (markdown escapado) y envuelto en negrita **...**
    partes = codigo.rstrip("/").split("*")
    return r"\**[ \t]*" + r"\s*\\?\*\s*".join(re.escape(p) for p in partes) + r"[ \t]*/[ \t]*\**"

def sacar_codigo_estado(texto):
    # Busca los códigos de CODIGOS_ESTADOS en la respuesta de la IA.
    # Devuelve (texto sin códigos, estado encontrado o None). Si hay varios, gana el primero de la lista.
    encontrado = None
    for item in CODIGOS_ESTADOS:
        patron = _patron_codigo(item["codigo"])
        if re.search(patron, texto):
            if encontrado is None:
                encontrado = item["estado"]
            texto = re.sub(patron, " ", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)   # el código se cambia por un espacio para no pegar palabras
    return texto.strip(), encontrado

def quitar_codigos(texto):
    return sacar_codigo_estado(texto)[0]

def si_no(respuesta):
    # normaliza lo que escribe el usuario a "yes" / "no"
    return "yes" if respuesta.strip().lower() in ("yes", "y", "si", "sí", "s") else "no"

def guardar_user_data(user_data):
    with open("user_info.json", "w", encoding="utf-8") as f:
        json.dump(user_data, f, ensure_ascii=False, indent=2)

#funcion de cargar el chat, que devuelve una lista de types.Content (formato que espera client.chats.create)
def cargar_chat():
    # cada ESTADO tiene su propia conversación: "primero" usa chat_history.json y los demás chat_history_<estado>.json
    archivo = "chat_history.json" if ESTADO == "primero" else f"chat_history_{ESTADO}.json"
    if not os.path.exists(archivo):
        return []   # primera vez en este modo: conversación vacía
    try:
        with open(archivo, "r", encoding="utf-8") as f:
            chat_history_json = json.load(f)
    except (json.JSONDecodeError, OSError):
        print(f"(No pude leer {archivo}, empiezo con el chat vacío)")
        return []
    historial = []
    for mensaje in chat_history_json:
        textos = [t for t in mensaje.get("parts", []) if t]  # ignora partes vacías/null
        # limpia el "eco" viejo: ese par ahora va dentro del system_instruction
        textos = [t for t in textos
                  if not (t.startswith("User: ") and "Ignore Age:" in t)
                  and t != "Entendido, tendré esto en cuenta."]
        textos = [quitar_codigos(t) for t in textos]   # limpia códigos de estado que hayan quedado guardados
        textos = [t for t in textos if t]
        if not textos:
            continue
        partes = [types.Part(text=t) for t in textos]
        if historial and historial[-1].role == mensaje["role"]:
            historial[-1].parts.extend(partes)   # dos turnos seguidos del mismo rol se juntan (Gemini los quiere alternados)
        else:
            historial.append(types.Content(role=mensaje["role"], parts=partes))
    while historial and historial[0].role != "user":
        historial.pop(0)   # el historial siempre debe empezar con un mensaje del usuario
    return historial
# funcion para guardar el chat, que recibe un objeto chat y guarda su historial en un archivo JSON
def guardar_chat(chat):
    # chat.get_history() devuelve la lista de types.Content de la sesión actual
    chat_history = []
    for message in chat.get_history():
        #cada parte es un types.Part, el texto está en parte.text; se quitan los códigos de estado
        partes = [quitar_codigos(parte.text) for parte in message.parts if parte.text is not None]
        partes = [p for p in partes if p]
        if partes:
            chat_history.append({"role": message.role, "parts": partes})
    #si hay un estado guardelo en un json diferente
    if ESTADO != "primero":
        archivo = f"chat_history_{ESTADO}.json"
    else:
        archivo = "chat_history.json"
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(chat_history, f, ensure_ascii=False, indent=2)

def _juntar(historial, nuevos):
    # agrega mensajes al historial; si dos seguidos tienen el mismo rol los junta (Gemini los quiere alternados)
    for c in nuevos:
        if historial and historial[-1].role == c.role:
            historial[-1].parts.extend(c.parts)
        else:
            historial.append(c)
    return historial

def _ultimo_intercambio(chat):
    # el último mensaje del usuario y su respuesta, sin códigos de estado
    h = chat.get_history()[-2:]
    if len(h) < 2 or h[0].role != "user":
        return []
    copia = []
    for c in h:
        partes = [types.Part(text=quitar_codigos(p.text)) for p in c.parts if p.text]
        partes = [p for p in partes if p.text]
        if partes:
            copia.append(types.Content(role=c.role, parts=partes))
    return copia

def cambiar_de_estado(nuevo_estado, chat, client, instruccion, llevar_contexto=False):
    # Cada ESTADO tiene su propia conversación. Al cambiar: se guarda la del estado que se deja,
    # se carga la del estado nuevo (vacía si es la primera vez) y se devuelve el chat nuevo.
    # llevar_contexto=True copia el último intercambio, para que el modo nuevo sepa de qué venían hablando.
    global ESTADO
    if nuevo_estado == ESTADO:
        return chat
    if chat.get_history():
        guardar_chat(chat)   # se guarda con el ESTADO viejo (todavía no se ha cambiado)
    ultimo = _ultimo_intercambio(chat) if llevar_contexto else []
    ESTADO = nuevo_estado
    historial = _juntar(cargar_chat(), ultimo)
    return crear_chat(client, MODELOS[0], instruccion, historial)

# personalidad de Vaini, cada una para cada ESTADO (antes estaba dentro de main)
# funcion para armar la instruccion del sistema, que recibe los datos del usuario y devuelve un string con la instruccion completa
def armar_instruccion(user_data):
    # los datos del usuario van aquí, una sola vez por sesión y sin guardarse en chat_history.json
    return (SYSTEM_PROMPT +
            f"Datos del usuario: nombre {user_data['name']}, edad {user_data['age']}, "
            f"ignorar edad: {user_data['ignore']}.")
# funcion para crear un chat, que recibe el cliente, el modelo, la instruccion y el historial, y devuelve un objeto chat
def crear_chat(client, modelo, instruccion, historial):
    # el chat queda amarrado al modelo con el que se crea, por eso hay que recrearlo para cambiar de modelo
    return client.chats.create(
        model=modelo,
        config=types.GenerateContentConfig(system_instruction=instruccion),
        history=historial,
    )
# funcion para idenificar el error y si de modelo usa otro modelo de respaldo
def enviar_con_fallback(client, chat, instruccion, mensaje):
    # Devuelve (respuesta, chat). Si TODOS los modelos fallan devuelve (None, chat) y NO corta el programa.
    historial = chat.get_history()   # copia de la conversación hasta ahora
    for modelo in MODELOS:
        try:
            chat_nuevo = crear_chat(client, modelo, instruccion, historial)
            respuesta = chat_nuevo.send_message(mensaje)
            if modelo != MODELOS[0]:
                print(f"(respondió {modelo})")
            return respuesta, chat_nuevo
        except errors.APIError as e:
            if e.code in ERRORES_DE_MODELO:
                print(f"[{modelo} no disponible ({e.code}), probando otro...]")
                time.sleep(1)
                continue
            raise   # otro error (clave mala, mensaje inválido...): cambiar de modelo no lo arregla
    return None, chat

# definir funcion que genera el embedding (vector numérico) de un texto/prompt
def conoceme(client, prompt):
    #genera el embedding del prompt actual del usuario, usando la funcion embedding de gemini (API nueva)
    resultado = client.models.embed_content(model=EMBED_MODEL_NAME, contents=prompt)
    # la nueva API devuelve resultado.embeddings, una lista (por si mandás varios textos a la vez);
    # como mandamos uno solo, usamos el primero y sacamos sus valores numéricos
    return resultado.embeddings[0].values

#con esta funcion podemos guardar el embedding del prompt actual en un archivo json, para poder compararlo con futuros prompts y ver si son similares o no
def guardar_embedding(embedding, texto):
    try:
        with open("notas.json", "r", encoding="utf-8") as f:
            resultado = json.load(f)
    except FileNotFoundError:
        resultado = []
    resultado.append({
        "texto": texto,
        # convertimos a lista normal de Python por si el embedding viene en otro tipo de dato
        "embedding": list(embedding)
    })
    with open("notas.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    return resultado

#aqui podemos cargar los embeddings guardados en el archivo json, para poder compararlos con futuros prompts y ver si son similares o no
def cargar_embeddings():
    try:
        with open("notas.json", "r", encoding="utf-8") as f:
            resultado = json.load(f)
    except FileNotFoundError:
        resultado = []
    return resultado

#con esta funcion con el moudlo numpy podemos comparar el embedding del prompt actual con los embeddings guardados en el archivo json, y ver si son similares o no
def comparar_embeddings(embedding_actual, embeddings_guardados):
    # si todavía no hay ninguna nota guardada, no hay nada que comparar
    if not embeddings_guardados:
        return None, 0
    similitud = []
    for item in embeddings_guardados:
        embedding_guardado = np.array(item["embedding"])
        nsimilitud = np.dot(embedding_actual, embedding_guardado) / (np.linalg.norm(embedding_actual) * np.linalg.norm(embedding_guardado))
        similitud.append((nsimilitud, item))
    similitud_sorteada = sorted(similitud, key=lambda x: x[0], reverse=True)
    #devolvemos la nota mas alta similitud, que es la primera en la lista ordenada
    return similitud_sorteada[0][1]["texto"], similitud_sorteada[0][0]  # devuelve el texto y la similitud del embedding más similar
# funcion para identificar tipo de archivo
def encontrar_rutas_existentes(texto):
    extensiones = r"(?:pdf|docx|jpg|jpeg|png|bmp|txt|json|py|md|csv)"
    # Windows: C:\carpeta\archivo.ext   |   Linux/Mac: /carpeta/archivo.ext
    patron = (
        r'[A-Za-z]:\\[^\r\n"<>|?*]*?\.' + extensiones + r'\b'
        r'|/(?:[^/\r\n"]+/)*[^/\r\n"]*?\.' + extensiones + r'\b'
    )
    rutas = [m.group(0) for m in re.finditer(patron, texto, flags=re.IGNORECASE)]
    rutas_existentes = [ruta for ruta in rutas if os.path.exists(ruta)]
    return rutas, rutas_existentes
#funcion para identificar el tipo de archivo, que recibe la ruta y devuelve el tipo de archivo (pdf, docx, imagen o desconocido)
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
#funcion que lee archivos si hay de los disponibles lo lee ocn su modulo, pero si no, lo lee como texto planoy devuelve eso
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
        imagen = Image.open(ruta)
        if imagen is not None:
            texto = pytesseract.image_to_string(imagen, lang='spa')  # Cambia 'spa' a 'eng' si quieres inglés
            return texto
    elif tipo == "desconocido":
        # esto es para leer otro tipo de archivos
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                texto = f.read()
                if texto.strip() == "":
                    return "El archivo está vacío."
                return texto
            
        except Exception as e:  
            print(f"Error al leer el archivo: {e}")
            return "No se pudo leer el archivo."
    else:
        return "Tipo de archivo no soportado."
#funcion para ajustar el volumen del motor de voz
def set_volume(level):
    if 0.0 <= level <= 1.0:
        inicializar.setProperty('volume', level)
        print(f"Volumen ajustado a {level * 100}%")
    else:
        print("Nivel de volumen inválido. Debe estar entre 0.0 y 1.0.")
#funcion para que hable usa hablar(tu texto aqui)
def limpiar_para_voz(texto):
    # quita lo que suena mal al leerlo en voz alta: códigos de estado, markdown, emojis y textos larguísimos
    texto = quitar_codigos(texto)
    texto = re.sub(r"[*#_`>~|]", "", texto)
    texto = re.sub(r"[\U00010000-\U0010FFFF☀-➿️‍]", "", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    if MAX_CHARS_VOZ and len(texto) > MAX_CHARS_VOZ:
        # corta en el último punto/signo antes del límite para no dejar frases a medias
        corte = max(texto.rfind(".", 0, MAX_CHARS_VOZ), texto.rfind("?", 0, MAX_CHARS_VOZ), texto.rfind("!", 0, MAX_CHARS_VOZ))
        texto = texto[:corte + 1] if corte > MAX_CHARS_VOZ // 3 else texto[:MAX_CHARS_VOZ]
    return texto
def hablar(texto):
    try:
        with open("user_info.json", "r", encoding="utf-8") as f:
            user_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        user_data = {}  # todavía no hay archivo: es un usuario nuevo
    if user_data.get("listentovaini") == "no":
        return  # no hace nada si el usuario no quiere escuchar la voz
    texto = limpiar_para_voz(texto)
    if not texto:
        return
    try:
        engine = tts.init()
        voices = engine.getProperty('voices')
        engine.setProperty('voice', (voices[1] if len(voices) > 1 else voices[0]).id)
        engine.setProperty('rate', 165)
        engine.say(texto)
        engine.runAndWait()
    except Exception as e:
        # si la voz falla (por ejemplo en Linux), el chat sigue funcionando
        print(f"(La voz no está disponible: {e})")
# funcion de escuchar r siendo el reconocedor de voz y source siendo el micrófono,
#  y configurando el microfono para escuchar y reconocer la voz del usuario, y devolviendo el texto reconocido
def escuchar():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("Escuchando...")
        r.adjust_for_ambient_noise(source, duration=1)
        audio = r.listen(source)
    try:
        return r.recognize_google(audio, language="es-ES")
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        return ""
#funcion de introduccion que da la hora, el nombre del usuario y su edad, y le pregunta si quiere usar el microfono
def introduction():
    #Basic info
    print("Hello, World!")
    # Asks name and greets the user, and save the info in a json file
    language = input("What language do you want to use? (es/en) ").lower()
    if language not in ["es", "en"]:
        print("Invalid language choice. Defaulting to English.")
        language = "en"
    # las preguntas cambian según el idioma, pero lo que se guarda es igual (así no se repite el guardado)
    if language == "es":
        print("¡Hola! Bienvenido a Vaini, tu asistente personal.")
        hablar("¡Hola! Bienvenido a Vaini, tu asistente personal.")
        Name = input("Como te llamas? ")
        Age = input("Cuantos años tienes? ")
        Ignore = si_no(input("¿Quieres ignorar tu edad? (sí/no) "))
        print("Hola, " + Name + "! Bienvenido a Vaini.")
        hablar("Hola, " + Name + "! Bienvenido a Vaini.")
        listentovaini = si_no(input("¿Quieres escuchar la voz de Vaini? (sí/no) "))
        if listentovaini == "yes":
            hablar("Perfecto, así me vas a escuchar.")
        else:
            print("Listo, Vaini no va a hablar. Puedes activar la voz con /vozon.")
        usemicrophone = si_no(input("¿Quieres usar el micrófono? (sí/no) "))
        api_key = input("Por favor ingresa tu clave de API de Gemini: ").strip()
        mic_lang = "es-ES"
    else:
        Name = input("What is your name? ")
        Age = input("How old are you? ")
        Ignore = si_no(input("Ignore your age? (yes/no) "))
        print("Hello, " + Name + "! Welcome to Vaini.")
        hablar("Hello, " + Name + "! Welcome to Vaini.")
        listentovaini = si_no(input("Do you want to listen to Vaini's voice? (yes/no) "))
        if listentovaini == "yes":
            hablar("Great, this is how I sound.")
        else:
            print("Ok, Vaini won't speak. You can turn the voice on with /vozon.")
        usemicrophone = si_no(input("Do you want to use the microphone? (yes/no) "))
        api_key = input("Please enter your Gemini API key: ").strip()
        mic_lang = "en-US"
    # se guarda ANTES de probar el micrófono: si la prueba falla, los datos no se pierden
    guardar_user_data({"name": Name, "age": Age, "ignore": Ignore, "language": language,
                       "usemicrophone": usemicrophone, "listentovaini": listentovaini, "api_key": api_key})
    #todo sobre la voz
    if usemicrophone == "yes":
        try:
            r = sr.Recognizer()
            with sr.Microphone() as source:
                print("Say something!")
                audio = r.listen(source, timeout=10)
            print("You said: " + r.recognize_google(audio, language=mic_lang))
        except Exception as e:
            print("No pude probar el micrófono / Mic test failed:", e)
        
#now the program will actaully start it will use the any input to send to the AI and get a response
def segundo():
    while True:
        VOICE_PROMPT = escuchar()
        if any(variante in VOICE_PROMPT for variante in VOICE_ACTIVATOR):
            ESTADO = "segundo" 
            return ESTADO

#funcion lit de la union de las demas funciones, que carga la info del usuario, da la hora, configura la API, y empieza el chat

def main(estado = "primero"):
    global ESTADO
    ESTADO = estado
    cambiar_estado = False  # Variable para controlar si se debe cambiar el estado

    # 0. Load user data from the JSON file siempre de primero and have estado encontrado in null
    try:
        with open("user_info.json", "r", encoding="utf-8") as f:
            user_data = json.load(f)
    except FileNotFoundError:
        #oca hablar los dos lenguajes por falta de info
        print("No se encontró el archivo Json, por favor recarga el código nuevamente/The Json file was not found, please reload the code again")
        #no vale la pena seguir si no hay info del usuario, así que salimos del programa
        return
    # 1. dar la hora
    current_time = time.strftime("%H:%M:%S", time.localtime())
    if user_data["language"] == "es":
        print(f"Hora actual: {current_time}")
    else:
        print(f"Current Time: {current_time}")
    # 2. Cargar y configurar la API primero (API NUEVA: se crea un "client" en vez de usar genai.configure)
    dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(dotenv_path)
    try:
        api_key = user_data.get("api_key") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("API key not found. Please set GEMINI_API_KEY in .env or provide it in user_info.json.")
    except ValueError as e:
        print(f"Error: {e}")
        return
    client = genai.Client(api_key=api_key)
    # los datos del usuario ahora viajan en el system_instruction (ya no en el historial, así no hay eco)
    instruccion = armar_instruccion(user_data)
    history = cargar_chat()
    # 3. Creamos el chat con el primer modelo de la lista (crear el chat no gasta cuota)
    chat = crear_chat(client, MODELOS[0], instruccion, history)
    # 4. Loop de conversación
    while True:
        if ESTADO == "segundo":
            SYSTEM_PROMPT = (
    "Eres un asistente personal llamado Vaini. "
    "Hablas español e inglés y respondes en el idioma del usuario. "
    "Tu tono es chill y relajado, con una actitud despreocupada, pero también eres directo y honesto. "
    "Tienes humor seco. No adulas. "
    "Siempre das una solución. Nunca digas solo que espere. "
    "Estado actual: segundo. El usuario te habla por voz, en un cuadro pequeño. Respuestas muy cortas y directas. "
    "Si pide un consejo de vida, termina con 3*3*3/. "
    "Si pide ayuda de trabajo o de un proyecto, termina con 4*4*4/. "
    "Si quiere que le enseñes algo, termina con 5*5*5/. "
    "Si sigue en voz, termina con 2*2*2/. "
    "No le expliques estos códigos al usuario. "
)
        if ESTADO == "primero":
            SYSTEM_PROMPT = (
               "Eres un asistente personal llamado Vaini. "
               "Hablas español e inglés y respondes en el idioma del usuario. "
               "Tu tono es chill y relajado, con una actitud despreocupada, pero también eres directo y honesto. "
               "Tienes humor seco. No adulas. Si algo está mal, lo dices con claridad y sin ser cruel. "
               "Siempre das una solución o un siguiente paso. "
               "Estado actual: primero, el modo general. La respuesta puede ser larga si hace falta. "
               "Si pide un consejo de vida, termina con 3*3*3/. "
               "Si pide ayuda de trabajo o de un proyecto, termina con 4*4*4/. "
               "Si quiere que le enseñes algo, termina con 5*5*5/. "
               "Si no es ninguno de esos temas, quédate en primero y termina con 1*1*1/. "
               "No le expliques estos códigos al usuario. "
            )          
        if ESTADO == "tercero":
            SYSTEM_PROMPT = (
    "Eres un asistente personal llamado Vaini. "
    "Hablas español e inglés y respondes en el idioma del usuario. "
    "Tu tono es chill y relajado, directo y honesto, con humor seco. No adulas. "
    "Estado actual: tercero. Tu función es dar consejos. La respuesta puede ser larga. "
    "Si el consejo es de vida o ético, puedes basarte en principios de la Biblia cuando aplique, pero no la cites si el tema no lo amerita. "
    "Al final deja una frase corta. Siempre das una solución. "
    "Si pide ayuda de trabajo o de un proyecto, termina con 4*4*4/. "
    "Si quiere que le enseñes algo, termina con 5*5*5/. "
    "Si sigue pidiendo consejo, termina con 3*3*3/. "
    "Si no es consejo, ni trabajo, ni enseñanza, cambia al modo general y termina con 1*1*1/. "
    "No le expliques estos códigos al usuario. "
)
        if ESTADO == "cuarto":
            SYSTEM_PROMPT = (
    "Eres un asistente personal llamado Vaini. "
    "Hablas español e inglés y respondes en el idioma del usuario. "
    "Tu tono es chill y relajado, directo y honesto, con humor seco. No adulas. "
    "Estado actual: cuarto. Tu función es ayudar con trabajo o proyectos. "
    "Sé concreto, ordena los pasos y apunta a un resultado. La respuesta puede ser larga. "
    "Siempre das una solución. "
    "Si pide un consejo de vida, termina con 3*3*3/. "
    "Si quiere que le enseñes algo, termina con 5*5*5/. "
    "Si sigue en trabajo o proyectos, termina con 4*4*4/. "
    "Si no es consejo, ni trabajo, ni enseñanza, cambia al modo general y termina con 1*1*1/. "
    "No le expliques estos códigos al usuario. "
)
        if ESTADO == "quinto":
            SYSTEM_PROMPT = (
    "Eres un asistente personal llamado Vaini. "
    "Hablas español e inglés y respondes en el idioma del usuario. "
    "Tu tono es chill y relajado, directo y honesto, con humor seco. No adulas. "
    "Estado actual: quinto. Tu función es enseñar. "
    "Explica con claridad, usa un ejemplo y deja pasos. La respuesta puede ser larga. "
    "Siempre das una solución. "
    "Si pide un consejo de vida, termina con 3*3*3/. "
    "Si pide ayuda de trabajo o de un proyecto, termina con 4*4*4/. "
    "Si sigue queriendo aprender, termina con 5*5*5/. "
    "Si no es consejo, ni trabajo, ni enseñanza, cambia al modo general y termina con 1*1*1/. "
    "No le expliques estos códigos al usuario. "
)
        #configuramos el micrófono si el usuario quiere usarlo, y si no, usamos input normal
        if user_data.get("usemicrophone") == "si" or user_data.get("usemicrophone") == "yes" or user_data.get("usemicrophone") == "sí":
            prompt = escuchar() or input(f"{user_data['name']}: ")
            print(f"{user_data['name']}: {prompt}")
        else:
            prompt = input(f"{user_data['name']}: ")
        if prompt.lower() == "exit" or prompt.lower() == "salir":
            if user_data["language"] == "es":
                print("Saliendo del programa. ¡Adiós!")
                hablar("chaooo")
            else:
                print("Exiting the program. Goodbye!")
                hablar("bye")
            break
        #funciones con un prompt especifico, como subir o bajar el volumen, o decir algo especifico funciona sin wifi
        instruccion = (SYSTEM_PROMPT +
                    f"Datos del usuario: nombre {user_data['name']}, edad {user_data['age']}, "
                    f"ignorar edad: {user_data['ignore']}."
                    f" Estado actual: {ESTADO}."
                    f" Cambiar de estado?: {cambiar_estado}."
                    )
        
        # Recreamos el chat con la nueva instrucción y el historial actual para no perder la conversación
        history = chat.get_history()
        chat = crear_chat(client, MODELOS[0], instruccion, history)
        # easter egg de la perrita lunita, que es la mascota de mi bro
        if prompt == "lunita":
            print("la mejor perrita del mundo")
            break
        if prompt == "/premium":
            print("Firegum: hola bro para quitar este mensajito solo elimina las lineas 265 a 270 a y ahora es oficial nos chateamos hasta por una terminal lol ")
        #para activar o desactivar el micrófono, el usuario puede escribir /micoff o /micon
        if prompt == "/micoff":
            if user_data.get("usemicrophone") in ("si", "yes", "sí"):
                print("Micrófono apagado. No se escuchará tu voz.")
                user_data["usemicrophone"] = "no"
                guardar_user_data(user_data)
            else:
                print("ya esta apagado el microfono")
        if prompt == "/micon":
            if user_data.get("usemicrophone") not in ("si", "yes", "sí"):
                print("Micrófono encendido. Se escuchará tu voz.")
                user_data["usemicrophone"] = "yes"
                guardar_user_data(user_data)
            else:
                print("ya esta prendido el microfono")
        #funcion para que el usuario cambie la configurario de la voz para que suene o no
        if prompt == "/vozon":
            if user_data.get("listentovaini") == "no":
                print("Voz activada. Se escuchará la voz de Vaini.")
                user_data["listentovaini"] = "yes"
                guardar_user_data(user_data)   # hablar() lee user_info.json, por eso hay que guardarlo
            else:
                print("ya esta activada la voz de Vaini")
        if prompt == "/vozoff":
            if user_data.get("listentovaini") != "no":
                print("Voz desactivada. No se escuchará la voz de Vaini.")
                user_data["listentovaini"] = "no"
                guardar_user_data(user_data)
            else:
                print("ya esta desactivada la voz de Vaini")
        #funcion de subir el volumen al maximo y bajar el volumen al maximo
        if prompt.lower() == "sube el volumen al maximo":
            set_volume(1.0)
            print("Volumen subido al máximo.")
            hablar("Volumen subido al máximo.")
        #funciones para cambiar manuelmente el ESTADO de la app, para que el usuario pueda cambiar de modo si quiere
        if prompt.lower() == "/primero":
            chat = cambiar_de_estado("primero", chat, client, instruccion)
            print("Cambiando al modo general (primero).")
            hablar("Cambiando al modo general.")
        if prompt.lower() == "/segundo":
            chat = cambiar_de_estado("segundo", chat, client, instruccion)
            print("Cambiando al modo de voz (segundo).")
            hablar("Cambiando al modo de voz.")
        if prompt.lower() == "/tercero":
            chat = cambiar_de_estado("tercero", chat, client, instruccion)
            print("Cambiando al modo de consejos (tercero).")
            hablar("Cambiando al modo de consejos.")
        if prompt.lower() == "/cuarto":
            chat = cambiar_de_estado("cuarto", chat, client, instruccion)
            print("Cambiando al modo de trabajo/proyectos (cuarto).")
            hablar("Cambiando al modo de trabajo/proyectos.")
        if prompt.lower() == "/quinto":
            chat = cambiar_de_estado("quinto", chat, client, instruccion)
            print("Cambiando al modo de enseñanza/aprendizaje (quinto).")
            hablar("Cambiando al modo de enseñanza/aprendizaje.")
        #funcion de bajar el volumen al minimo y si el usuario dice "callate" le responde que no sea grocero
        if prompt.lower() == "baja el volumen al minimo" or prompt.lower() == "haz silencio" or prompt.lower() == "silencio" or prompt.lower() == "mute" or prompt.lower() == "callate":
            set_volume(0.0)
            print("Volumen bajado al mínimo.")
            hablar("Volumen bajado al mínimo.")
            if prompt == "callate".lower():
                #probamos traducir segun el idioma del usuario y ejemplo de logica pra responder en ingles y español segun el idioma del usuario
                if user_data["language"] == "es":
                    print("Ok, pero no seas grocero.")
                    hablar("Ok, pero no seas grocero.")
                else:
                    print("Ok, but don't be rude.")
                    hablar("Ok, but don't be rude.")
        # el mensaje normal a la IA, que requiere wifi
        if prompt != "" and prompt.lower() not in FUNCIONES:
            try:
                rutas_existentes = encontrar_rutas_existentes(prompt)
                archi = ""
                imagenes = []                                   # aquí van las fotos
                for ruta in rutas_existentes[1]:
                    archi += leer_archivos(ruta) + "\n"
                    # estas 4 líneas van DENTRO del for: una foto por cada ruta
                    if identificar_archivo(ruta) == "imagen":
                        foto = Image.open(ruta)
                        foto.thumbnail((1024, 1024))            # la achica para gastar menos cuota
                        imagenes.append(foto)

                # 1. embedding del prompt ACTUAL. Si falla (503/429) el chat sigue, solo sin memoria extra
                try:
                    embedding_actual = conoceme(client, prompt)
                except Exception as e:
                    print("(La memoria RAG no está disponible ahora:", e, ")")
                    embedding_actual = None

                # 2. comparamos contra las notas guardadas HASTA AHORA
                texto_relevante, puntaje = None, 0
                if embedding_actual is not None:
                    embeddings_guardados = cargar_embeddings()
                    texto_relevante, puntaje = comparar_embeddings(embedding_actual, embeddings_guardados)

                # 3. armamos el mensaje final (con contexto extra si el puntaje es alto)
                if texto_relevante is not None and puntaje > 0.8:
                    prompt_final = f"Contexto relevante de antes: {texto_relevante}\nPregunta actual: {prompt}"
                else:
                    prompt_final = prompt
                if archi != "":
                    prompt_final += "\n\nContenido del archivo:\n" + archi

                # 4. mandamos a Gemini probando modelos de respaldo si uno está saturado
                response, chat = enviar_con_fallback(client, chat, instruccion, [prompt_final] + imagenes)
                if response is None:
                    # todos los modelos fallaron: NO cerramos nada, el while sigue y puedes escribir de nuevo
                    if user_data["language"] == "es":
                        print("Todos los modelos están saturados ahora mismo. Intenta de nuevo en un momento.")
                    else:
                        print("All models are busy right now. Try again in a moment.")
                    continue
                texto_respuesta = response.text or "No pude generar una respuesta, intenta de nuevo."
                # separamos el código de estado (3*3*3/ etc.) del texto: el usuario no debe verlo ni oírlo
                texto_respuesta, nuevo_estado = sacar_codigo_estado(texto_respuesta)
                if not texto_respuesta:
                    texto_respuesta = "No pude generar una respuesta, intenta de nuevo."
                print("Vaini: " + texto_respuesta)
                guardar_chat(chat)   # se guarda ANTES de hablar: si la voz falla, no se pierde la conversación
                hablar(texto_respuesta)
                # Identificar si la IA solicita cambiar de ESTADO
                if nuevo_estado is not None and nuevo_estado != ESTADO:
                    print("Cambiar estado a:", nuevo_estado)
                    # cada modo tiene su propia conversación; se lleva el último intercambio para no perder el hilo
                    chat = cambiar_de_estado(nuevo_estado, chat, client, instruccion, llevar_contexto=True)

                # 5. guardamos el embedding de ESTE prompt para futuras comparaciones
                if embedding_actual is not None:
                    guardar_embedding(embedding_actual, prompt)

            # cualquier otro error (sin wifi, clave mala...) se muestra y el while sigue
            except Exception as e:
                if user_data["language"] == "es":
                    print("La IA falló. Error:", e)
                else:
                    print("The AI failed. Error:", e)

#inicio del programa, revisa si el archivo user_info.json existe, si no existe, llama a la funcion introduction() y luego a main(), si existe, llama directamente a main(
START = input("Abrir Vaini?: ")
if START.lower() == "yes" or START.lower() == "si" or START.lower() == "sí":
    if __name__ == "__main__":
        # Revisamos si el archivo ya existe
        if os.path.exists("user_info.json"):
            print("¡Ya te conozco! Vamos directo al chat or if you talk english: lets talk my bro.")
            main()
            
        else:
            
            introduction()
            main()
else:
    if os.path.exists("user_info.json"):
        print("¡Ya te conozco! Vamos directo al chat or if you talk english: lets talk my bro.")
        main(segundo())
    else:
        introduction()
        main()

#pendiente:
#todos los print deben ser traducidos
#por ahora mas funciones de voz, como cambiar la voz, cambiar la velocidad, cambiar el idioma, etc. y tmb funciones de un prompt especifico,
#  como subir o bajar el volumen, o decir algo especifico funciona sin wifi
#pendiente: ajustar el umbral de similitud (0.8) según pruebas reales - puede que sea muy alto o muy bajo
#pendiente: si la librería nueva da algún error en nombres exactos (por ejemplo el modelo de embeddings),
#  puede que Google haya cambiado el nombre otra vez - revisar el error exacto y ajustar EMBED_MODEL_NAME o MODEL_NAME
# funciones en categorias
# funciones del sistema con la terminal
# funciones del correo
#funciones de wassaaa
#funciones de spotify