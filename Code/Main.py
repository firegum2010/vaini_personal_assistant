#import some modules
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
import json
import time
import speech_recognition as sr
import pyttsx3 as tts
import numpy as np
import pyaudio
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\etiop\AppData\Local\Tesseract-OCR\tesseract.exe'
from pypdf import PdfReader
from docx import Document
from PIL import ImageGrab
#incia motor de voz
inicializar = tts.init()
voices = inicializar.getProperty('voices')
for v in voices:
    print(v.id, "-", v.name, "-", v.gender)
print("Volumen actual:", inicializar.getProperty('volume'))
inicializar.setProperty('volume', 1.0)  # fuerza volumen al máximo

# NOMBRE DEL MODELO: con la librería nueva se pasa el nombre del modelo en cada llamada,
# no una sola vez al crear un "GenerativeModel" como antes.
MODEL_NAME = "gemini-3.6-flash"
EMBED_MODEL_NAME = "gemini-embedding-001"
#Frase activadora para que la IA sepa que es un prompt de voz y no de texto, y responda con voz usamos varias frases pues es dificl que google entienda aveces
VOICE_ACTIVATOR = ["vaini", "va", "baini", "vainilla", "bahini"]
ESTADO = ""
VOICE_PROMPT = "" # el pormpt de voz inicial para el llamado de la app
#definir la función para guardar el historial del chat en un archivo JSON
def cargar_chat():
    # Devuelve una lista de types.Content (formato que espera client.chats.create)
    if os.path.exists("chat_history.json"):
        with open("chat_history.json", "r", encoding="utf-8") as f:
            chat_history_json = json.load(f)
        historial = []
        for mensaje in chat_history_json:
            historial.append(
                types.Content(
                    role=mensaje["role"],
                    parts=[types.Part(text=texto) for texto in mensaje["parts"]]
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
            "parts": [parte.text for parte in message.parts]
        })

    with open("chat_history.json", "w", encoding="utf-8") as f:
        json.dump(chat_history, f, ensure_ascii=False, indent=2)

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

#funcion para ajustar el volumen del motor de voz
def set_volume(level):
    if 0.0 <= level <= 1.0:
        inicializar.setProperty('volume', level)
        print(f"Volumen ajustado a {level * 100}%")
    else:
        print("Nivel de volumen inválido. Debe estar entre 0.0 y 1.0.")

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

# recibe el texto lo leee PENDIENTE: que la voz sea mas natural y no suene gringo xd
def hablar(texto):
    engine = tts.init()
    voices = engine.getProperty('voices')
    engine.setProperty('voice', voices[1].id)  # cambiá el índice [1] según cuál sea la femenina en tu lista
    engine.setProperty('rate', 165)  # velocidad más pausada/chill (default suele ser ~200)
    engine.say(texto)
    engine.runAndWait()

#funcion de introduccion que da la hora, el nombre del usuario y su edad, y le pregunta si quiere usar el microfono
def introduction():
    #Basic info
    print("Current Working Directory:", os.getcwd())
    print("Python Version:", os.sys.version)
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
        usemicrophone = input("¿Quieres usar el micrófono? (sí/no) ").lower()
        with open("user_info.json", "w") as f:
                    json.dump({"name": Name, "age": Age, "ignore": Ignore, "language": language, "usemicrophone": usemicrophone}, f, ensure_ascii=False, indent=2)
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
        with open("user_info.json", "w") as f:
                    json.dump({"name": Name, "age": Age, "ignore": Ignore, "language": language, "usemicrophone": usemicrophone}, f, ensure_ascii=False, indent=2)
        #todo sobre la voz
        if usemicrophone == "yes":
        # inicialr el micorfono
            r = sr.Recognizer()

            with sr.Microphone() as source:
                print("Say something!")
                audio = r.listen(source)
                print("You said: " + r.recognize_google(audio, language="en-US"))

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
    context = f"User: {user_data['name']}, Age: {user_data['age']}, Ignore Age: {user_data['ignore']}"
    history = cargar_chat()
    # 3. Recién ahora podemos crear el chat (API NUEVA: client.chats.create en vez de model.start_chat)
    #    El historial inicial (contexto fijo) también se arma con types.Content, no con diccionarios sueltos
    chat = client.chats.create(
        model=MODEL_NAME,
        config=types.GenerateContentConfig(
            system_instruction="Eres un asistente personal llamado Vaini, que habla español e inglés. "
    "revisa el estado en el que te habla el usario si es SEGUNDO es da respuestas cortas pues lo habra texto en un cuadro pequeño, si el ESTADO es igual a PRIMERO da respuestas normales"
    #ESTADO
    "Respondes con un tono chill y relajado, con la actitud despreocupada de un conejo, esto es lo que te DEFINE "
    "Cuando el usuario pida un consejo de vida o ético, basa tu respuesta en principios "
    "de la Biblia si aplica, pero no la menciones ni la cites si el tema no lo amerita "
    "(por ejemplo, en preguntas técnicas o cotidianas)."
    "(Si el usuario habla en inglés, responde en inglés; si habla en español, responde en español.)"
    "Al final de cada mensaje deja una frase o versiculo aleatorio"
    "Nunca le digas al usuario que no haga nada o que espera, siempre tienes que darle opciones en problemas"

    
    
        ),
        history=[
            types.Content(role="user", parts=[types.Part(text=context)]),
            types.Content(role="model", parts=[types.Part(text="Entendido, tendré esto en cuenta.")]),
            *history,
        ],
    )
    # 4. Loop de conversación
    while True:
        #configuramos el micrófono si el usuario quiere usarlo, y si no, usamos input normal
        if user_data.get("usemicrophone") == "si" or user_data.get("usemicrophone") == "yes":
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
            print(f"Firegum: mira bro esta ia te ayuda pues para darte consejo, pero algo que si me dijiste es eso que de que esta bajando y primero {user_data['name']} animos bro estare orando ")
            print("Firegum: SEGUNDOOOOOOOO")
            print("Firegum: LEEE la biblia ora , y mira one piece")
            print("Firegum: bn ya lo ultimo bro es que es verdad que te acercas peroooo te reco,minedo SUPER aprovechar el momento del hogareño osea ahi es donde pues crecio todo o algo asi y si estoy diciendo bobadas perdoname , ya mi Ia te ayuda xd, bn byeee")
        #para activar o desactivar el micrófono, el usuario puede escribir /micoff o /micon
        if prompt == "/micoff":
            print("Micrófono apagado. No se escuchará tu voz.")
            if user_data.get("usemicrophone") == "si" or user_data.get("usemicrophone") == "yes":
                user_data["usemicrophone"] = "no"
            else:
                print("ya esta apagado el microfono")
        if prompt == "/micon":
            if user_data.get("usemicrophone") == "no":
                print("Micrófono encendido. Se escuchará tu voz.")
                user_data["usemicrophone"] = "yes"
            else:
                print("ya esta prendido el microfono")
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
        if prompt != "":
            try:
                # 1. generamos el embedding del prompt ACTUAL (API NUEVA: conoceme ahora necesita el client)
                embedding_actual = conoceme(client, prompt)

                # 2. cargamos las notas guardadas HASTA AHORA (antes de agregar la de este turno)
                #    y comparamos el prompt actual contra ellas para encontrar la más relevante
                embeddings_guardados = cargar_embeddings()
                texto_relevante, puntaje = comparar_embeddings(embedding_actual, embeddings_guardados)

                # 3. armamos el mensaje final: si encontramos algo relevante (puntaje alto),
                #    se lo agregamos como contexto extra antes de la pregunta real
                if texto_relevante is not None and puntaje > 0.8:
                    prompt_final = f"Contexto relevante de antes: {texto_relevante}\nPregunta actual: {prompt}"
                else:
                    prompt_final = prompt

                # 4. recién ahora mandamos el mensaje (con o sin contexto extra) a Gemini
                response = chat.send_message(prompt_final)
                print("Vaini: " + response.text)
                hablar(response.text)
                guardar_chat(chat)

                # 5. guardamos el embedding de ESTE prompt para que esté disponible en futuras comparaciones
                guardar_embedding(embedding_actual, prompt)

            # si hay un error, como que no hay wifi, se imprime un mensaje de error
            except Exception as e:
                if user_data["language"] == "es":
                    print("La IA falló, quizás no tengas wifi. Error:", e)
                else:
                    print("The AI failed, maybe you don't have wifi. Error:", e)

#incio del porgrama, revisa si el archivo user_info.json existe, si no existe, llama a la funcion introduction() y luego a main(), si existe, llama directamente a main(
START = input("Abrir Vaini?: ")
if START.lower() == "yes" or START.lower() == "si":
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