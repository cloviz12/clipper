"""Transcripcion palabra por palabra (Whisper) y subtitulos animados .ass:
- palabra activa resaltada, palabras fuertes con color de acento y mas grandes
- maximo 2 lineas, dentro de la zona segura (lejos de los botones de TikTok/Reels/Shorts)
- tarjeta de 'hook' arriba en los primeros segundos y credito @canal"""
import random
import re
import shutil

from .base import MODELOS, log

_MODEL = {}

ESTILOS = [
    {"fuente": "Inter Display Black", "bold": 0, "tam": 96, "color": "FFFFFF", "activo": "FFE500", "acento": "6BFF3D", "borde": "000000", "outline": 7, "sombra": 3,
     "hook_fondo": "FFFFFF", "hook_texto": "000000"},
    {"fuente": "Poppins", "bold": 1, "tam": 124, "color": "FFFFFF", "activo": "5BFF3A", "acento": "FFD700", "borde": "000000", "outline": 7, "sombra": 2,
     "hook_fondo": "FFE100", "hook_texto": "000000"},
    {"fuente": "Inter ExtraBold", "bold": 0, "tam": 94, "color": "FFFFFF", "activo": "FF6B2E", "acento": "FFE500", "borde": "101010", "outline": 8, "sombra": 0,
     "hook_fondo": "000000", "hook_texto": "FFFFFF"},
    {"fuente": "Inter Display Black", "bold": 0, "tam": 92, "color": "FFF600", "activo": "FFFFFF", "acento": "FF5B5B", "borde": "000000", "outline": 7, "sombra": 3,
     "hook_fondo": "FF2B2B", "hook_texto": "FFFFFF"},
    {"fuente": "Poppins", "bold": 1, "tam": 120, "color": "FFFFFF", "activo": "D24DFF", "acento": "FFF600", "borde": "1A0A2B", "outline": 8, "sombra": 2,
     "hook_fondo": "D24DFF", "hook_texto": "FFFFFF"},
    {"fuente": "Inter ExtraBold", "bold": 0, "tam": 96, "color": "FFFFFF", "activo": "FFCC33", "acento": "B8FF4D", "borde": "000000", "outline": 6, "sombra": 4,
     "hook_fondo": "FFCC33", "hook_texto": "000000"},
]
FUERTES = re.compile(r"^(ja(ja)+\w*|no+|s[ií]+|qu[eé]+|wtf|omg|dios|brutal|incre[ií]ble|gol+|mira|nunca|siempre|todo|nada|\d[\d.,%]*)$", re.I)


def _ruta_modelo(nombre, rehacer=False):
    """Carpeta propia del modelo (archivos reales, sin la cache con enlaces de HuggingFace, que en Windows
    a veces deja un model.bin que no se puede abrir). Se baja una vez y se reutiliza."""
    destino = MODELOS / f"faster-whisper-{nombre}"
    if rehacer:
        shutil.rmtree(destino, ignore_errors=True)
    modelo = destino / "model.bin"
    if not modelo.exists() or modelo.stat().st_size < 10_000_000:     # falta o quedo a medias
        from huggingface_hub import snapshot_download
        log(f"bajando el modelo de subtitulos «{nombre}» (una sola vez, necesita internet)...", "aviso")
        shutil.rmtree(destino, ignore_errors=True)
        snapshot_download(f"Systran/faster-whisper-{nombre}", local_dir=str(destino))
    return str(destino)


def _modelo(nombre, dispositivo="auto"):
    if nombre not in _MODEL:
        from faster_whisper import WhisperModel
        if dispositivo in ("auto", "cuda"):
            try:
                _MODEL[nombre] = WhisperModel(nombre, device="cuda", compute_type="float16")
                return _MODEL[nombre]
            except Exception:
                pass
        try:
            _MODEL[nombre] = WhisperModel(_ruta_modelo(nombre), device="cpu", compute_type="int8")
        except Exception as e:
            log(f"whisper {nombre}: no pude abrir el modelo ({str(e)[:150]}); lo bajo de nuevo", "aviso")
            _MODEL[nombre] = WhisperModel(_ruta_modelo(nombre, rehacer=True), device="cpu", compute_type="int8")
        log(f"whisper {nombre} cargado en procesador")
    return _MODEL[nombre]


IDIOMAS_APP = {"es", "en", "pt"}      # los que ofrece Ajustes
IDIOMA_BASE = "es"


def transcribir(path, aj, idioma=None, pista=None):
    lang = idioma or aj.get("idioma") or IDIOMA_BASE
    auto = lang == "auto"
    modelo = _modelo(aj.get("whisper_modelo", "small"), aj.get("whisper_dispositivo", "auto"))

    def correr(l):
        return modelo.transcribe(str(path), language=l, word_timestamps=True, vad_filter=True, beam_size=5,
                                 condition_on_previous_text=False, initial_prompt=pista)
    segs, info = correr(None if auto else lang)
    if auto and (info.language not in IDIOMAS_APP or info.language_probability < 0.75):
        # la deteccion automatica se confunde con musica, ruido y dialogos del juego (sale italiano, gales...):
        # si no esta segura o sale un idioma raro, se usa el de siempre
        log(f"subtitulos: deteccion automatica dudosa ({info.language} {info.language_probability:.0%}); uso {IDIOMA_BASE}", "aviso")
        segs, info = correr(IDIOMA_BASE)
    palabras, frases = [], []
    for s in segs:
        frases.append({"t": float(s.start), "texto": s.text.strip()})
        for w in s.words or []:
            t = w.word.strip()
            if t:
                palabras.append({"w": t, "s": float(w.start), "e": float(w.end)})
    return palabras, frases


def _bloques(palabras, maxp=3, maxc=18, pausa=0.45):
    out, cur = [], []
    for w in palabras:
        if cur and (len(cur) >= maxp or len(" ".join(x["w"] for x in cur + [w])) > maxc
                    or w["s"] - cur[-1]["e"] > pausa or cur[-1]["w"][-1:] in ".?!"):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def _t(x):
    x = max(0.0, x)
    h, r = divmod(x, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _limpio(t, may):
    t = t.replace("{", "(").replace("}", ")").replace("\\", "")
    return t.upper() if may else t


def _partir_hook(h, maxc=22):
    pal, lineas, cur = h.split(), [], ""
    for p in pal:
        if cur and len(cur) + 1 + len(p) > maxc:
            lineas.append(cur)
            cur = p
        else:
            cur = (cur + " " + p).strip()
    lineas.append(cur)
    return "\\N".join(lineas[:3])


def escribir_ass(palabras, destino, aj, y_texto, credito=None, hook=None, hook_hasta=2.6, semilla=None):
    rnd = random.Random(semilla)
    e = rnd.choice(ESTILOS)
    may = aj.get("mayusculas", True)
    y = y_texto + rnd.randint(-25, 25)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{e['fuente']},{e['tam']},&H00{_bgr(e['color'])},&H000000FF,&H00{_bgr(e['borde'])},&H78000000,{-1 if e['bold'] else 0},0,0,0,100,100,1,0,1,{e['outline']},{e['sombra']},5,80,80,0,1
Style: Hook,{e['fuente']},{86 if e['fuente'] == 'Poppins' else 64},&H00{_bgr(e['hook_texto'])},&H000000FF,&H00{_bgr(e['hook_fondo'])},&H00{_bgr(e['hook_fondo'])},{-1 if e['bold'] else 0},0,0,0,100,100,0,0,3,18,0,8,90,90,300,1
Style: Cred,Inter ExtraBold,38,&H30FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,1,0,1,3,0,8,40,40,175,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    if credito:
        ev.append(f"Dialogue: 1,{_t(0)},{_t(9999)},Cred,,0,0,0,,{_limpio(credito, False)}")
    if hook:
        txt = _partir_hook(_limpio(hook, True))
        ev.append(f"Dialogue: 2,{_t(0.05)},{_t(hook_hasta)},Hook,,0,0,0,,"
                  f"{{\\fscx70\\fscy70\\t(0,120,\\fscx104\\fscy104)\\t(120,200,\\fscx100\\fscy100)\\fad(0,180)}}{txt}")
    bloques = _bloques(palabras, maxp=int(aj.get("palabras_por_linea", 3)))
    for i, b in enumerate(bloques):
        ini = b[0]["s"]
        fin = b[-1]["e"] + 0.25
        if i + 1 < len(bloques):
            fin = min(fin, bloques[i + 1][0]["s"])
        textos = [_limpio(w["w"], may) for w in b]
        fuertes = [bool(FUERTES.match(w["w"].strip(".,!?¡¿"))) for w in b]
        corte = len(textos) if len(" ".join(textos)) <= 14 or len(textos) < 3 else (len(textos) + 1) // 2
        for j, w in enumerate(b):
            a = ini if j == 0 else w["s"]
            z = b[j + 1]["s"] if j + 1 < len(b) else fin
            if z <= a:
                continue
            partes = []
            for k, tx in enumerate(textos):
                if k == corte and k:
                    partes.append("\\N")
                elif k:
                    partes.append(" ")
                if k == j:
                    col = e["acento"] if fuertes[k] else e["activo"]
                    esc = "\\fscx118\\fscy118" if fuertes[k] else "\\fscx106\\fscy106"
                    partes.append(f"{{\\c&H{_bgr(col)}&{esc}}}{tx}{{\\c&H{_bgr(e['color'])}&\\fscx100\\fscy100}}")
                else:
                    partes.append(tx)
            pop = "\\fscx86\\fscy86\\t(0,90,\\fscx100\\fscy100)" if j == 0 else ""
            ev.append(f"Dialogue: 0,{_t(a)},{_t(z)},Cap,,0,0,0,,{{\\pos(540,{y}){pop}}}{''.join(partes)}")
    with open(destino, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(ev) + "\n")
    return e


def _bgr(rgb):
    """Los colores se escriben RRGGBB arriba; ASS los quiere BBGGRR."""
    return rgb[4:6] + rgb[2:4] + rgb[0:2]
