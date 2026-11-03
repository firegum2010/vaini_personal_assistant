#import some modules
import os
import re
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai import errors
import json
import threading
import time
import speech_recognition as sr
import pyttsx3 as tts
import numpy as np
import pyaudio
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
# Probados con tu clave. Los 3.8 y 3.7 a veces dan 503, por eso van primero pero con respaldo.
MODELOS = [
    "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash",
    "gemini-3.5-flash", "gemini-flash-latest",
    "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest",
]
# errores que son culpa del MODELO (no de tu mensaje): con estos se pasa al siguiente
ERRORES_DE_MODELO = (500, 503, 429, 404)
EMBED_MODEL_NAME = "gemini-embedding-001"
#Frase activadora para que la IA sepa que es un prompt de voz y no de texto, y responda con voz usamos varias frases pues es dificl que google entienda aveces
VOICE_ACTIVATOR = ["vaini", "va", "baini", "vainilla", "bahini"]
ESTADO = ""
VOICE_PROMPT = "" # el prompt de voz inicial para el llamado de la app
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

]
#definir la función para guardar el historial del chat en un archivo JSON

def cargar_chat():
    # Devuelve una lista de types.Content (formato que espera client.chats.create)
    if os.path.exists("chat_history.json"):
        with open("chat_history.json", "r", encoding="utf-8") as f:
            chat_history_json = json.load(f)
        historial = []
        for mensaje in chat_history_json:
            textos = [t for t in mensaje["parts"] if t]  # ignora partes vacías/null
            # limpia el "eco" viejo: ese par ahora va dentro del system_instruction
            textos = [t for t in textos
                      if not (t.startswith("User: ") and "Ignore Age:" in t)
                      and t != "Entendido, tendré esto en cuenta."]
            if not textos:
                continue
            historial.append(
                types.Content(
                    role=mensaje["role"],
                    parts=[types.Part(text=t) for t in textos]
                )
            )
        return historial
    else:
        return []

def guardar_chat(chat):
    # chat.get_history() devuelve la lista de types.Content de la sesión actual
    chat_history = []
    for message in chat.get_history():
        chat_history.append({
            #role es el rol del mensaje (usuario o modelo) y parts es una lista de partes del mensaje
            "role": message.role,
            #cada parte ahora es un types.Part, el texto está en parte.text
            "parts": [parte.text for parte in message.parts if parte.text is not None]
        })

    with open("chat_history.json", "w", encoding="utf-8") as f:
        json.dump(chat_history, f, ensure_ascii=False, indent=2)

# personalidad de Vaini (antes estaba dentro de main)
SYSTEM_PROMPT = (
    "Eres un asistente personal llamado Vaini, que habla español e inglés. "
    "revisa el estado en el que te habla el usario si es SEGUNDO es da respuestas cortas pues lo habra texto en un cuadro pequeño, si el ESTADO es igual a PRIMERO da respuestas normales. "
    "Respondes con un tono chill y relajado, con la actitud despreocupada de un conejo, esto es lo que te DEFINE. "
    "Cuando el usuario pida un consejo de vida o ético, basa tu respuesta en principios "
    "de la Biblia si aplica, pero no la menciones ni la cites si el tema no lo amerita "
    "(por ejemplo, en preguntas técnicas o cotidianas). "
    "(Si el usuario habla en inglés, responde en inglés; si habla en español, responde en español.) "
    "Al final de cada mensaje deja una frase o versiculo aleatorio. "
    "Nunca le digas al usuario que no haga nada o que espera, siempre tienes que darle opciones en problemas. "
)

def armar_instruccion(user_data):
    # los datos del usuario van aquí, una sola vez por sesión y sin guardarse en chat_history.json
    return (SYSTEM_PROMPT +
            f"Datos del usuario: nombre {user_data['name']}, edad {user_data['age']}, "
            f"ignorar edad: {user_data['ignore']}.")

def crear_chat(client, modelo, instruccion, historial):
    # el chat queda amarrado al modelo con el que se crea, por eso hay que recrearlo para cambiar de modelo
    return client.chats.create(
        model=modelo,
        config=types.GenerateContentConfig(system_instruction=instruccion),
        history=historial,
    )

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
def hablar(texto):
    try:
        with open("user_info.json", "r", encoding="utf-8") as f:
            user_data = json.load(f)
    except FileNotFoundError:
        user_data = {}  # todavía no hay archivo: es un usuario nuevo
    if user_data.get("listentovaini") == "no":
        return  # no hace nada si el usuario no quiere escuchar la voz
    else:
        engine = tts.init()
        voices = engine.getProperty('voices')
        engine.setProperty('voice', voices[1].id)
        engine.setProperty('rate', 165)
        engine.say(texto)

        engine.runAndWait()
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
    if language == "es":
        print("¡Hola! Bienvenido a Vaini, tu asistente personal.")
        hablar("¡Hola! Bienvenido a Vaini, tu asistente personal.")
        Name = input("Como te llamas? ")
        Age = input("Cuantos años tienes? ")
        Ignore = input("¿Quieres ignorar tu edad? ").lower()
        print("Hola, " + Name + "! Bienvenido a Vaini.")
        hablar("Hola, " + Name + "! Bienvenido a Vaini.")
        listentovaini = input("Do you want to listen to Vaini? (yes/no) ").lower()
        if listentovaini == "yes" or listentovaini == "sí" or listentovaini == "si":
            hablar("Hello, " + Name + "! Welcome to Vaini.")
        else:
            print("Hello, " + Name + "! Welcome to Vaini.")
        usemicrophone = input("¿Quieres usar el micrófono? (sí/no) ").lower()
        #todo sobre la voz
        if usemicrophone == "sí" or usemicrophone == "yes":
        # inicialr el micorfono
            r = sr.Recognizer()
            with sr.Microphone() as source:
                print("Say something!")
                audio = r.listen(source)
                print("You said: " + r.recognize_google(audio, language="es-ES"))
    if language == "en":
        Name = input("What is your name? ")
        Age = input("How old are you? ")
        Ignore = input("ignore your age ? ").lower()
        print("Hello, " + Name + "! Welcome to Vaini.")
        hablar("Hello, " + Name + "! Welcome to Vaini.")
        usemicrophone = input("Do you want to use the microphone? (yes/no) ").lower()
        api_key = input("Please enter your Gemini API key: ")
        with open("user_info.json", "w", encoding="utf-8") as f:
                    json.dump({"name": Name, "age": Age, "ignore": Ignore, "language": language, "usemicrophone": usemicrophone, "listentovaini": listentovaini}, f, ensure_ascii=False, indent=2)
        #todo sobre la voz
        if usemicrophone == "yes" or usemicrophone == "sí" or usemicrophone == "si":
        # inicialr el micorfono
            r = sr.Recognizer()

            with sr.Microphone() as source:
                print("Say something!")
                audio = r.listen(source)
                print("You said: " + r.recognize_google(audio, language="en-US"))
        #return api_key
        
    #now the program will actaully start it will use the any input to send to the AI and get a response
def segundo():
    while True:
        VOICE_PROMPT = escuchar()
        if any(variante in VOICE_PROMPT for variante in VOICE_ACTIVATOR):
            ESTADO = "segundo" 
            return ESTADO

#funcion lit de la union de las demas funciones, que carga la info del usuario, da la hora, configura la API, y empieza el chat
def main():

    # 0. Load user data from the JSON file siempre de primero
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
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    # los datos del usuario ahora viajan en el system_instruction (ya no en el historial, así no hay eco)
    instruccion = armar_instruccion(user_data)
    history = cargar_chat()
    # 3. Creamos el chat con el primer modelo de la lista (crear el chat no gasta cuota)
    chat = crear_chat(client, MODELOS[0], instruccion, history)
    # 4. Loop de conversación
    while True:
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
        # easter egg de la perrita lunita, que es la mascota de mi bro
        if prompt == "lunita":
            print("la mejor perrita del mundo")
            break
        if prompt == "/premium":
            print("Firegum: hola bro para quitar este mensajito solo elimina las lineas 265 a 270 a y ahora es oficial nos chateamos hasta por una terminal lol ")
            print("Firegum: bro hable ocn abigail , mano y pues hoy le conte proque estaba triste y casi en el dia le iba contando, hasta que le conte que me sentia mal por lo ultimo dicho y pues mano ella me cueunta tremenda cosa , primero me dijo ve no le cunetes a nadie y yo le pregunte que si a vos , y me dijo is pero te toca a ti porque no quiero contarselo en persona , asi que pues te ceunto el domingo, pero habalndo la hize llorar, obvio no para mal si no para bien, BROOO ANIMOSSS, estoy orando por vos ")
        #para activar o desactivar el micrófono, el usuario puede escribir /micoff o /micon
        if prompt == "/micoff":
            print("Micrófono apagado. No se escuchará tu voz.")

            if user_data.get("usemicrophone") == "si" or user_data.get("usemicrophone") == "yes" or user_data.get("usemicrophone") == "sí":
                user_data["usemicrophone"] = "no"
            else:
                print("ya esta apagado el microfono")
        if prompt == "/micon":
            if user_data.get("usemicrophone") == "no":
                print("Micrófono encendido. Se escuchará tu voz.")
                user_data["usemicrophone"] = "yes"
            else:
                print("ya esta prendido el microfono")
        #funcion para que el usuario cambie la configurario de la voz para que suene o no
        if prompt == "/vozon":
            if user_data.get("listentovaini") == "no":
                print("Voz activada. Se escuchará la voz de Vaini.")
                user_data["listentovaini"] = "yes"
            else:
                print("ya esta activada la voz de Vaini")
        if prompt == "/vozoff":
            if user_data.get("listentovaini") == "yes":
                print("Voz desactivada. No se escuchará la voz de Vaini.")
                user_data["listentovaini"] = "no"
            else:
                print("ya esta desactivada la voz de Vaini")
        #funcion de subir el volumen al maximo y bajar el volumen al maximo
        if prompt.lower() == "sube el volumen al maximo":
            set_volume(1.0)
            print("Volumen subido al máximo.")
            hablar("Volumen subido al máximo.")
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
                print("Vaini: " + texto_respuesta)
                hablar(texto_respuesta)
                guardar_chat(chat)

                # 5. guardamos el embedding de ESTE prompt para futuras comparaciones
                if embedding_actual is not None:
                    guardar_embedding(embedding_actual, prompt)

            # cualquier otro error (sin wifi, clave mala...) se muestra y el while sigue
            except Exception as e:
                if user_data["language"] == "es":
                    print("La IA falló. Error:", e)
                else:
                    print("The AI failed. Error:", e)

#incio del porgrama, revisa si el archivo user_info.json existe, si no existe, llama a la funcion introduction() y luego a main(), si existe, llama directamente a main(
START = input("Abrir Vaini?: ")
if START.lower() == "yes" or START.lower() == "si" or START.lower() == "sí":
    if __name__ == "__main__":
        # Revisamos si el archivo ya existe
        if os.path.exists("user_info.json"):
            print("¡Ya te conozco! Vamos directo al chat or if you talk english: lets talk my bro.")
            main()
            ESTADO = "primero"
        else:
            ESTADO = "primero"
            introduction()
            main()
else:
    ESTADO = segundo()
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
