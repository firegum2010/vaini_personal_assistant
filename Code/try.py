import pyttsx3 as tts
engine = tts.init()
voices = engine.getProperty('voices')
print("Cantidad de voces encontradas:", len(voices))
for v in voices:
    print(v.id, "-", v.name, "-", v.gender)
#voz suave y femenina pero que hable español
engine.setProperty('voice', voices[1].id)  # cambiá el índice [1] según cuál sea la femenina en tu lista
engine.setProperty('rate', 165)  # velocidad más pausada/chill (default suele ser ~200)
engine.setProperty('volume', 0.9)
engine.say("prueba de audio, hola, soy Vaini, tu asistente personal")
engine.runAndWait()
    