#import some modules
import os
from dotenv import load_dotenv
import google.generativeai as genai
import json
import time
import speech_recognition as sr
import pyttsx3 as tts
#import pyaudio
#incia motor de voz
inicializar = tts.init()
voices = inicializar.getProperty('voices')
for v in voices:
    print(v.id, "-", v.name, "-", v.gender)
print("Volumen actual:", inicializar.getProperty('volume'))
inicializar.setProperty('volume', 1.0)  # fuerza volumen al máximo
# definir funcion que actualize el tiempo
#definir la función para guardar el historial del chat en un archivo JSON
def cargar_chat():
    if os.path.exists("chat_history.json"):
        with open("chat_history.json", "r", encoding="utf-8") as f:
            chat_history = json.load(f)
        return chat_history
    else:
        return []
def guardar_chat(chat):
    chat_history = []
    for message in chat.history:
        chat_history.append({
            #role es el rol del mensaje (usuario o modelo) y parts es una lista de partes del mensaje
            "role": message.role,
            #parts es una lista de partes del mensaje, cada parte es un objeto con un atributo text que contiene el texto del mensaje
            "parts": [parte.text for parte in message.parts]
        })

    with open("chat_history.json", "w", encoding="utf-8") as f:
        json.dump(chat_history, f, ensure_ascii=False, indent=2)
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
    # 2. Cargar y configurar la API primero
    dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(dotenv_path)
    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.6-flash")
    context = f"User: {user_data['name']}, Age: {user_data['age']}, Ignore Age: {user_data['ignore']}"
    history = cargar_chat()
    # 3. Recién ahora podemos crear el chat, porque 'model' ya existe
    chat = model.start_chat(history=[
        {"role": "user", "parts": [context]},
        {"role": "model", "parts": ["Entendido, tendré esto en cuenta."]},
        *history
    ])
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
                # la respuesta de la IA se guarda en la variable response, y se imprime en pantalla y se lee en voz alta
                response = chat.send_message(prompt)
                print("Vaini: " + response.text)
                hablar(response.text)
                guardar_chat(chat)
            # si hay un error, como que no hay wifi, se imprime un mensaje de error
            except Exception as e:
                if user_data["language"] == "es":
                    print("La IA falló, quizás no tengas wifi. Error:", e)
                else:
                    print("The AI failed, maybe you don't have wifi. Error:", e)
#incio del porgrama, revisa si el archivo user_info.json existe, si no existe, llama a la funcion introduction() y luego a main(), si existe, llama directamente a main()
if __name__ == "__main__":
    # Revisamos si el archivo ya existe
    if os.path.exists("user_info.json"):
        print("¡Ya te conozco! Vamos directo al chat or if you talk english: lets talk my bro.")
        main()
    else:
        introduction()
        main()