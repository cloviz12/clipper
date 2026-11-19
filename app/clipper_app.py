"""CLIPPER — app de escritorio.

Una sola ventana con el panel del equipo + el motor trabajando por detras. Al cerrar la ventana
sigue en la bandeja (junto al reloj) vigilando directos y publicando; se sale desde la bandeja."""
import json
import os
import sys
import threading
import time
from pathlib import Path

VERSION = "1.0.0"
NOMBRE = "CLIPPER"
PUERTO = 47821  # fijo: es el que se registra como regreso en Google y TikTok

# ------------------------------------------------------------------ rutas
CONGELADO = getattr(sys, "frozen", False)
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
CARPETA = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / NOMBRE
CARPETA.mkdir(parents=True, exist_ok=True)
CONFIG = CARPETA / "config.json"
UI = BASE / "ui" if CONGELADO else BASE / "ui" / "out"

# herramientas incluidas en el instalador (ffmpeg, ffprobe, deno)
for d in (BASE / "bin", Path(sys.executable).parent / "bin"):
    if d.exists():
        os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
os.environ.setdefault("CLIPPER_DATOS", str(CARPETA / "datos"))
os.environ.setdefault("CLIPPER_LETRAS", str(BASE / "fuentes_letra" if CONGELADO else BASE / "worker" / "fuentes_letra"))
os.environ.setdefault("PYTHONUTF8", "1")
if not CONGELADO:
    sys.path.insert(0, str(BASE / "worker"))

# sin consola (app con ventana), las salidas van a un archivo de registro
if CONGELADO or sys.stdout is None:
    _log = open(CARPETA / "clipper.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _log


def leer_config():
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def guardar_config(nueva):
    actual = leer_config()
    for k, v in nueva.items():
        if k.endswith("_guardada"):
            continue
        if isinstance(v, str) and v.strip() == "" and k in SECRETOS and actual.get(k):
            continue  # secreto vacio = no cambiarlo
        actual[k] = v.strip() if isinstance(v, str) else v
    CONFIG.write_text(json.dumps(actual, indent=1), encoding="utf-8")
    iniciar_con_windows(bool(actual.get("iniciar_con_windows")))
    if configurado(actual):
        try:
            subir_al_equipo(actual)
        except Exception as e:
            print("no pude compartir las llaves con el equipo:", e)
    return actual


SECRETOS = {"supabase_service", "anthropic_key", "google_client_secret", "tiktok_client_secret"}
# lo que el dueno llena una vez y los companeros invitados reciben solos (tabla config_equipo)
COMPARTIDOS = ("supabase_service", "anthropic_key", "google_client_id", "google_client_secret",
               "tiktok_client_key", "tiktok_client_secret")


def _admin(c):
    from supabase import create_client
    return create_client(c["supabase_url"], c["supabase_service"])


def subir_al_equipo(c, previo=None):
    datos = dict(previo or {})
    datos.update({k: c[k] for k in COMPARTIDOS if c.get(k)})
    _admin(c).table("config_equipo").upsert({"id": 1, "datos": datos,
                                             "actualizado": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}).execute()


def sincronizar_equipo(c):
    """Al abrir: toma las llaves que el equipo tenga guardadas (si el dueno cambio alguna, llega sola)
    y comparte las que esta PC tenga y el equipo aun no."""
    if not configurado(c):
        return c
    try:
        r = _admin(c).table("config_equipo").select("datos").eq("id", 1).execute()
        equipo = (r.data[0]["datos"] if r.data else {}) or {}
        cambio = False
        for k in COMPARTIDOS:
            if equipo.get(k) and equipo[k] != c.get(k):
                c[k], cambio = equipo[k], True
        if cambio:
            CONFIG.write_text(json.dumps(c, indent=1), encoding="utf-8")
        if any(c.get(k) and not equipo.get(k) for k in COMPARTIDOS):
            subir_al_equipo(c, equipo)
    except Exception as e:
        print("no pude sincronizar las llaves del equipo:", e)
    return c


def configurado(c):
    return bool(c.get("supabase_url") and c.get("supabase_anon") and c.get("supabase_service"))


def aplicar_entorno(c):
    pares = {
        "SUPABASE_URL": c.get("supabase_url"), "SUPABASE_SERVICE_ROLE_KEY": c.get("supabase_service"),
        "ANTHROPIC_API_KEY": c.get("anthropic_key"), "GOOGLE_CLIENT_ID": c.get("google_client_id"),
        "GOOGLE_CLIENT_SECRET": c.get("google_client_secret"), "TIKTOK_CLIENT_KEY": c.get("tiktok_client_key"),
        "TIKTOK_CLIENT_SECRET": c.get("tiktok_client_secret"), "WORKER_NOMBRE": c.get("nombre_motor"),
    }
    for k, v in pares.items():
        if v:
            os.environ[k] = v


def iniciar_con_windows(si):
    if os.name != "nt" or not CONGELADO:
        return
    try:
        import winreg
        clave = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        if si:
            winreg.SetValueEx(clave, NOMBRE, 0, winreg.REG_SZ, f'"{sys.executable}" --bandeja')
        else:
            try:
                winreg.DeleteValue(clave, NOMBRE)
            except FileNotFoundError:
                pass
        winreg.CloseKey(clave)
    except Exception as e:
        print("no pude configurar el inicio con Windows:", e)


def reiniciar():
    """Vuelve a abrir la app (para tomar una configuracion nueva)."""
    import subprocess
    try:
        import main as motor
        motor.apagar()
    except Exception:
        pass
    args = [sys.executable] + ([] if CONGELADO else [str(Path(__file__).resolve())])
    subprocess.Popen(args + ["--reinicio"], close_fds=True)
    os._exit(0)


# ------------------------------------------------------------------ motor
estado = {"motor": False, "error": None}


def encender_motor(c):
    if not configurado(c) or c.get("motor_activo") is False:
        return
    try:
        aplicar_entorno(c)
        import main as motor
        motor.arrancar()
        estado["motor"] = True
    except Exception as e:
        estado["error"] = str(e)
        print("el motor no arranco:", e)


# ------------------------------------------------------------------ ventana y bandeja
ventana = {"w": None}


def mostrar():
    w = ventana["w"]
    if w is not None:
        try:
            w.show()
            w.restore()
            return
        except Exception:
            pass


def bandeja(salir):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
        return None
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 4, 60, 60), 14, fill=(198, 255, 61, 255))
    d.polygon([(25, 18), (25, 46), (47, 32)], fill=(16, 20, 10, 255))
    icono = pystray.Icon(NOMBRE, img, f"{NOMBRE} — trabajando", menu=pystray.Menu(
        pystray.MenuItem("Abrir CLIPPER", lambda: mostrar(), default=True),
        pystray.MenuItem("Salir del todo", lambda: salir())))
    threading.Thread(target=icono.run, daemon=True).start()
    return icono


def main():
    c = sincronizar_equipo(leer_config())
    from servidor import Servidor
    srv = Servidor(PUERTO, UI, leer_config, guardar_config, reiniciar, estado, VERSION, CARPETA,
                   al_mostrar=mostrar, secretos=SECRETOS)
    srv.arrancar()
    encender_motor(c)

    import webview

    def salir():
        try:
            import main as motor
            motor.apagar()
        except Exception:
            pass
        os._exit(0)

    icono = bandeja(salir)
    oculto = "--bandeja" in sys.argv
    w = webview.create_window(NOMBRE, f"http://127.0.0.1:{PUERTO}/", width=1320, height=880, min_size=(420, 600),
                              background_color="#0b0c0f", hidden=oculto)
    ventana["w"] = w

    def al_cerrar():
        if icono is None:
            return True                      # sin bandeja: cerrar es salir
        w.hide()                             # con bandeja: sigue trabajando
        return False
    w.events.closing += al_cerrar
    webview.start(private_mode=False, storage_path=str(CARPETA / "webview"))
    salir()


def prueba():
    """Usado por GitHub al construir: verifica que el instalador trae todo lo necesario."""
    import shutil
    import subprocess
    import cv2  # noqa: F401
    import faster_whisper  # noqa: F401
    import streamlink  # noqa: F401
    import supabase  # noqa: F401
    import webview  # noqa: F401
    import yt_dlp  # noqa: F401
    import main as motor  # noqa: F401
    from clipper import editor, efectos, en_vivo, encuadre, publicar, subtitulos, trabajos  # noqa: F401
    for h in ("ffmpeg", "ffprobe", "deno"):
        assert shutil.which(h), f"falta {h}"
    subprocess.run([shutil.which("ffmpeg"), "-version"], check=True, capture_output=True)
    assert (UI / "index.html").exists(), "falta la interfaz"
    assert any(Path(os.environ["CLIPPER_LETRAS"]).glob("*.otf")), "faltan las letras"
    efectos.fabricar_base()
    print("PRUEBA OK", VERSION)


if __name__ == "__main__":
    if "--prueba" in sys.argv:
        try:
            prueba()
            sys.exit(0)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("PRUEBA FALLO:", e)
            sys.exit(1)
    # una sola copia abierta: si ya hay una, solo se trae al frente
    import socket
    s = socket.socket()
    try:
        s.connect(("127.0.0.1", PUERTO))
        s.close()
        if "--reinicio" not in sys.argv:
            import urllib.request
            try:
                urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PUERTO}/api/mostrar", method="POST",
                                                              headers={"X-Clipper": "1"}), timeout=3)
            except Exception:
                pass
            sys.exit(0)
        time.sleep(3)
    except OSError:
        pass
    main()
