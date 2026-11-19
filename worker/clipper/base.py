"""Conexion a Supabase, ajustes compartidos, registro y rutas locales del motor."""
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RAIZ = Path(__file__).resolve().parent.parent
DATOS = Path(os.environ.get("CLIPPER_DATOS", RAIZ / "datos"))
TRABAJO = DATOS / "trabajo"
BUFFER = DATOS / "buffer"
SFX_DIR = DATOS / "sfx"
MODELOS = DATOS / "modelos"
FUENTES_TXT = RAIZ / "fuentes_letra"
for d in (TRABAJO, BUFFER, SFX_DIR, MODELOS):
    d.mkdir(parents=True, exist_ok=True)


def _cargar_env():
    p = RAIZ / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_cargar_env()
_links = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links"
if _links.exists():
    os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + str(_links)

WORKER = os.environ.get("WORKER_NOMBRE") or socket.gethostname()
VERSION = "2.0"

_sb = None
_lock = threading.Lock()


def sb():
    global _sb
    if _sb is None:
        from supabase import create_client
        url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise SystemExit("Faltan SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY en worker/.env")
        _sb = create_client(url, key)
    return _sb


DEFAULTS = {
    "duracion_clip": "20-45", "idioma": "es", "whisper_modelo": "small", "formato": "auto",
    "efectos_camara": "medio", "efectos_sonido": "medio", "hook_en_pantalla": True,
    "mostrar_credito": True, "mayusculas": True, "auto_puntaje_minimo": 70,
    "hashtags_base": ["#clips", "#streamer", "#viral", "#parati"], "horarios": [],
    "tiktok_modo": "borrador", "youtube_privacidad": "public", "youtube_categoria": "20",
    "ia_modelo": "claude-haiku-5-5", "dias_guardar_videos": 3,
}
_aj = {"t": 0, "d": dict(DEFAULTS)}


def ajustes():
    if time.time() - _aj["t"] > 30:
        try:
            r = sb().table("ajustes").select("datos").eq("id", 1).execute()
            d = dict(DEFAULTS)
            if r.data:
                d.update(r.data[0]["datos"] or {})
            _aj.update(t=time.time(), d=d)
        except Exception as e:
            print("no pude leer ajustes:", e)
    return _aj["d"]


def log(msg, nivel="info", **datos):
    line = f"{time.strftime('%H:%M:%S')} [{nivel}] {msg}"
    print(line, flush=True)
    try:
        sb().table("eventos").insert({"nivel": nivel, "mensaje": str(msg)[:1000], "datos": datos or None}).execute()
    except Exception:
        pass


def tool(name):
    p = shutil.which(name)
    if not p:
        raise RuntimeError(f"No encuentro {name} instalado")
    return p


def run(cmd, cwd=None, timeout=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{Path(cmd[0]).name} fallo: {r.stderr[-1500:]}")
    return r.stdout


def probe(path):
    out = run([tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    j = json.loads(out)
    v = next((s for s in j["streams"] if s.get("codec_type") == "video"), None)
    fps = 30.0
    if v and v.get("avg_frame_rate", "0/0") not in ("0/0", "0/1"):
        a, b = v["avg_frame_rate"].split("/")
        fps = float(a) / float(b) if float(b) else 30.0
    return {"w": int(v["width"]) if v else 0, "h": int(v["height"]) if v else 0, "fps": fps,
            "dur": float(j["format"].get("duration", 0) or 0),
            "audio": any(s.get("codec_type") == "audio" for s in j["streams"])}


def slug(s, n=40):
    import re
    s = re.sub(r"[^A-Za-z0-9]+", "_", str(s or "")).strip("_")
    return s[:n] or "x"


def parse_rango(txt, default="20-45"):
    import re
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", str(txt or ""))
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return min(a, b), max(a, b)
    m = re.match(r"^\s*(\d+)\s*$", str(txt or ""))
    if m:
        v = int(m.group(1))
        return max(8, v - 10), v
    return parse_rango(default, "20-45") if txt != default else (20, 45)


def hms(t):
    t = max(0, int(t))
    return f"{t // 60:02d}m{t % 60:02d}s"
