import os
import re
from dotenv import load_dotenv
from google import genai
from google.genai import types
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)
for m in ["gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite",
          "gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-flash-lite-latest"]:
    try:
        r = client.models.generate_content(model=m, contents="di hola")
        print(m, "OK")
    except Exception as e:
        print(m, "FALLÓ:", e)