import subprocess
import difflib
import os

RUTAS_PARA_BUSCAR = [
    "/usr/share/applications",
    "~/.local/share/applications",
    "/var/lib/snapd/desktop/applications",
    "/var/lib/flatpak/exports/share/applications",
]


# Busca todos los archivos .desktop en las carpetas donde viven las apps
def buscar_archivos_desktop():
    archivos_desktop = []
    for ruta in RUTAS_PARA_BUSCAR:
        for root, dirs, files in os.walk(os.path.expanduser(ruta)):
            for file in files:
                if file.endswith(".desktop"):
                    archivos_desktop.append(os.path.join(root, file))
    return archivos_desktop


# Lee un .desktop y devuelve (nombre, oculta)
def leer_desktop(ruta):
    nombre = None
    oculta = False
    with open(ruta, encoding="utf-8", errors="ignore") as f:
        for linea in f:
            linea = linea.strip()
            if linea.startswith("[") and linea != "[Desktop Entry]":
                break  # terminó la sección que me interesa
            if linea.startswith("Name="):
                nombre = linea[5:]
            if linea.startswith("NoDisplay=true"):
                oculta = True
    return nombre, oculta


# Se queda solo con las apps que sí se pueden abrir: lista de (nombre, ruta)
def filtrar_apps(archivos_desktop):
    apps_filtradas = []
    for ruta in archivos_desktop:
        nombre, oculta = leer_desktop(ruta)
        if nombre is not None and not oculta:
            apps_filtradas.append((nombre, ruta))
    return apps_filtradas


# Busca la ruta de una app a partir de lo que escribió el usuario o dijo la IA
def buscar_app(apps_disponibles, nombre_app):
    texto = nombre_app.lower().strip()
    if not texto:
        return None

    # 0. nombre exacto
    if texto in apps_disponibles:
        return apps_disponibles[texto]

    # 1. nombre parcial: "fire" -> "firefox", "vlc" -> "vlc media player"
    if len(texto) >= 3:
        for nombre, ruta in apps_disponibles.items():
            if texto in nombre:
                return ruta

    # 2. errores de escritura, comparando contra cada PALABRA de los nombres
    #    ("bave" -> "brave" dentro de "brave origin")
    palabras = {}
    for nombre in apps_disponibles:
        for palabra in nombre.split():
            palabras.setdefault(palabra, nombre)
    matches = difflib.get_close_matches(texto, list(palabras), n=1, cutoff=0.6)
    if matches:
        return apps_disponibles[palabras[matches[0]]]

    # 3. último intento: contra el nombre completo
    matches = difflib.get_close_matches(texto, list(apps_disponibles), n=1, cutoff=0.6)
    if matches:
        return apps_disponibles[matches[0]]

    return None


# Esta es la función que Gemini puede llamar
def abrir_app(nombre_app: str) -> str:
    """Abre una aplicación instalada en el computador del usuario.
    Pasa el nombre de la app, preferiblemente en inglés como aparece en el sistema
    (por ejemplo: Calculator, Settings, VLC, Spotify, Firefox).
    """
    ruta_app = buscar_app(apps_disponibles, nombre_app)
    if not ruta_app:
        return f"No encontré la aplicación '{nombre_app}'."

    try:
        proceso = subprocess.Popen(
            ["gio", "launch", ruta_app],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            # gio termina rápido después de lanzar la app; si falla, lo sabemos aquí
            if proceso.wait(timeout=5) != 0:
                return f"Encontré '{nombre_app}' pero no se pudo abrir ({ruta_app})."
        except subprocess.TimeoutExpired:
            pass  # sigue arrancando, lo damos por bueno
    except FileNotFoundError:
        return "No puedo abrir apps: falta el comando 'gio' en este sistema."

    return f"Abrí {nombre_app}."


# Se escanea UNA sola vez al importar el módulo
raw_apps = buscar_archivos_desktop()
# diccionario {nombre en minúsculas: ruta del .desktop}
apps_disponibles = {nombre.lower(): ruta for nombre, ruta in filtrar_apps(raw_apps)}


# Esto solo corre si ejecutas "python apps.py" directamente, NO cuando Main.py lo importa
if __name__ == "__main__":
    print(f"Se encontraron {len(apps_disponibles)} aplicaciones disponibles.")
    while True:
        pedido = input("App a abrir (enter para salir): ").strip()
        if not pedido:
            break
        print(abrir_app(pedido))