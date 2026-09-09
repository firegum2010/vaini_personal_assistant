import pyttsx3 as tts
engine = tts.init()
voices = engine.getProperty('voices')
print("Cantidad de voces encontradas:", len(voices))
for v in voices:
    print(v.id, v.name)
engine.say("prueba de audio")
engine.runAndWait()
    