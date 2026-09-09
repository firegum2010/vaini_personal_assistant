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
    print(v.id, v.name)

print("Volumen actual:", inicializar.getProperty('volume'))
inicializar.setProperty('volume', 1.0)  # fuerza volumen al máximo
def hablar(texto):
    engine = tts.init()
    engine.say(texto)
    engine.runAndWait()
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
        with open("user_info.json", "w") as f:
            json.dump({"name": Name, "age": Age, "ignore": Ignore, "language": language}, f, ensure_ascii=False, indent=2)
        usemicrophone = input("¿Quieres usar el micrófono? (sí/no) ").lower()
        #todo sobre la voz
        if usemicrophone == "sí" or usemicrophone == "si":
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
        with open("user_info.json", "w") as f:
            json.dump({"name": Name, "age": Age, "ignore": Ignore, "language": language}, f, ensure_ascii=False, indent=2)
        usemicrophone = input("Do you want to use the microphone? (yes/no) ").lower()
        #todo sobre la voz
        if usemicrophone == "yes":
        # inicialr el micorfono
            r = sr.Recognizer()

            with sr.Microphone() as source:
                print("Say something!")
                audio = r.listen(source)
                print("You said: " + r.recognize_google(audio, language="en-US"))

    #now the program will actaully start it will use the any input to send to the AI and get a response
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

    # 3. Recién ahora podemos crear el chat, porque 'model' ya existe
    chat = model.start_chat(history=[
        {"role": "user", "parts": [context]},
        {"role": "model", "parts": ["Entendido, tendré esto en cuenta."]}
    ])

    # 4. Loop de conversación
    while True:
        prompt = input(f"{user_data['name']}: ")
        if prompt.lower() == "exit" or prompt.lower() == "salir":
            if user_data["language"] == "es":
                print("Saliendo del programa. ¡Adiós!")
                hablar("chaooo")
            else:
                print("Exiting the program. Goodbye!")
                hablar("bye")
            break
        if prompt != "":
            try:
                response = chat.send_message(prompt)
                print("Vaini: " + response.text)
                hablar(response.text)
            except Exception as e:
                if user_data["language"] == "es":
                    print("La IA falló, quizás no tengas wifi. Error:", e)
                else:
                    print("The AI failed, maybe you don't have wifi. Error:", e)
    # vemos si el archivo ya existe, si no existe lo creamos y guardamos la info del usuario
if __name__ == "__main__":
    # Revisamos si el archivo ya existe
    if os.path.exists("user_info.json"):
        print("¡Ya te conozco! Vamos directo al chat or if you talk english: lets talk my bro.")
        main()
    else:
        introduction()
        main()