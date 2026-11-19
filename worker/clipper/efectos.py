"""Efectos de camara (zoom de golpe, sacudida, destello) y efectos de sonido.

Los sonidos base se fabrican aqui mismo (sin licencias de por medio). Si en el panel suben su propia
libreria (carpeta 'sfx' por categoria: whoosh, impacto, pop, riser, glitch, risa, meme), se usa esa
primero y se va rotando para que los clips no suenen iguales."""
import time
import wave

import numpy as np

from .base import SFX_DIR, log, sb

SR = 48000
CATEGORIAS = ["whoosh", "impacto", "pop", "riser", "glitch", "ding", "risa", "meme"]
INTENSIDAD = {"apagado": 0, "bajo": 1, "medio": 2, "alto": 3}


# ============================================================ sonidos base
def _guardar(path, x):
    x = np.clip(x, -1, 1)
    st = np.stack([x, x], axis=1) if x.ndim == 1 else x
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((st * 32000).astype(np.int16).tobytes())


def _env(n, ataque, caida):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(ataque, 1e-3)) * np.exp(-np.maximum(0, t - ataque) / max(caida, 1e-3))


def _lowpass(x, corte):
    """Paso-bajo de un polo con corte variable (array o numero)."""
    corte = np.broadcast_to(corte, x.shape)
    a = np.exp(-2 * np.pi * corte / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a[i]) * x[i] + a[i] * acc
        y[i] = acc
    return y


def fabricar_base():
    base = SFX_DIR / "base"
    base.mkdir(parents=True, exist_ok=True)
    if len(list(base.glob("*.wav"))) >= 18:
        return
    rng = np.random.default_rng(7)
    for v in range(3):
        # whoosh: ruido que barre de grave a agudo y se va
        d = 0.45 + 0.1 * v
        n = int(SR * d)
        t = np.arange(n) / SR
        ruido = rng.standard_normal(n)
        barrido = 300 + 5000 * np.sin(np.pi * t / d) ** 2
        x = _lowpass(ruido, barrido) * np.sin(np.pi * t / d) ** 1.5 * 0.9
        _guardar(base / f"whoosh_{v}.wav", x / (np.abs(x).max() + 1e-9) * 0.8)
        # impacto: golpe grave que cae de tono + chasquido
        d = 0.9
        n = int(SR * d)
        t = np.arange(n) / SR
        f = 70 - 35 * (t / d) - 6 * v
        golpe = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * (4.5 + v))
        click = _lowpass(rng.standard_normal(n), 2500) * np.exp(-t * 60) * 0.8
        x = np.tanh((golpe + click) * 2.2)
        _guardar(base / f"impacto_{v}.wav", x * 0.9)
        # pop
        d = 0.09
        n = int(SR * d)
        t = np.arange(n) / SR
        f = 900 + 200 * v - 5000 * t
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.002, 0.03)
        _guardar(base / f"pop_{v}.wav", x * 0.8)
        # riser: sube de tono y de volumen
        d = 1.1 + 0.2 * v
        n = int(SR * d)
        t = np.arange(n) / SR
        f = 180 + 1100 * (t / d) ** 2
        x = (np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.4 + _lowpass(rng.standard_normal(n), 800 + 6000 * t / d) * 0.6) * (t / d) ** 2
        _guardar(base / f"riser_{v}.wav", x / (np.abs(x).max() + 1e-9) * 0.7)
        # glitch: rafagas cortadas
        d = 0.28
        n = int(SR * d)
        x = np.zeros(n)
        for _ in range(7):
            a = rng.integers(0, n - 2000)
            L = rng.integers(400, 2000)
            x[a:a + L] = np.round(rng.standard_normal(L) * 3) / 3 * 0.6
        _guardar(base / f"glitch_{v}.wav", x)
        # ding
        d = 0.8
        n = int(SR * d)
        t = np.arange(n) / SR
        f0 = 1180 + 140 * v
        x = (np.sin(2 * np.pi * f0 * t) + 0.4 * np.sin(2 * np.pi * f0 * 2.01 * t)) * np.exp(-t * 6)
        _guardar(base / f"ding_{v}.wav", x * 0.45)


_sync = {"t": 0}


def sincronizar_libreria():
    """Baja los sonidos que suban en el panel (bucket 'sfx/<categoria>/archivo')."""
    if time.time() - _sync["t"] < 600:
        return
    _sync["t"] = time.time()
    try:
        st = sb().storage.from_("sfx")
        for cat in CATEGORIAS:
            for f in st.list(cat) or []:
                nombre = f.get("name")
                if not nombre or nombre.startswith("."):
                    continue
                dest = SFX_DIR / "libreria" / cat / nombre
                if dest.exists():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(st.download(f"{cat}/{nombre}"))
    except Exception as e:
        log(f"no pude sincronizar la libreria de sonidos: {e}", "aviso")


def elegir(cat, rnd):
    propios = list((SFX_DIR / "libreria" / cat).glob("*.*"))
    base = list((SFX_DIR / "base").glob(f"{cat}_*.wav"))
    pool = propios or base
    if not pool and cat in ("risa", "meme"):
        pool = list((SFX_DIR / "base").glob("pop_*.wav"))
    return rnd.choice(pool) if pool else None


# ============================================================ plan de efectos
def golpes(dur, pico, picos_audio, palabras, nivel, rnd):
    """Momentos del clip donde va un zoom de golpe (segundos)."""
    n = {0: 0, 1: 1, 2: 3, 3: 5}[nivel]
    cand = []
    if pico is not None and 0.8 < pico < dur - 0.5:
        cand.append((pico, 10))
    for t, v in picos_audio:
        cand.append((t, 5 + v))
    claves = ("jaja", "no", "qué", "que", "wtf", "dios", "mira", "brutal", "gol", "noo", "sí", "si", "omg", "what")
    for w in palabras:
        if w["w"].lower().strip(".,!?¡¿") in claves or w["w"].isupper() and len(w["w"]) > 2:
            cand.append((w["s"], 3))
    cand.sort(key=lambda x: -x[1])
    out = []
    for t, _ in cand:
        if len(out) >= n:
            break
        if 1.2 < t < dur - 0.4 and all(abs(t - o) > 2.5 for o in out):
            out.append(round(t, 2))
    return sorted(out)


def _env_expr(p, sube=0.07, queda=0.55, baja=0.4):
    u = f"(t-{p:.2f})"
    return (f"if(lt({u},0),0,if(lt({u},{sube}),{u}/{sube},if(lt({u},{sube + queda:.2f}),1,"
            f"if(lt({u},{sube + queda + baja:.2f}),1-({u}-{sube + queda:.2f})/{baja},0))))")


def filtro_camara(puntos, nivel):
    """[base] -> [cam]: zoom de entrada, zooms de golpe, sacudida y destello en cada golpe."""
    if nivel == 0:
        return "[base]null[cam]"
    amp = {1: 0.08, 2: 0.12, 3: 0.16}[nivel]
    z = "1+0.07*max(0,1-t/0.35)"
    sx, sy, fl = "0", "0", "0"
    for p in puntos:
        z += f"+{amp}*{_env_expr(p)}"
        u = f"(t-{p:.2f})"
        sx += f"+between({u},0,0.35)*{6 + 5 * nivel}*sin({u}*95)*exp(-{u}*9)"
        sy += f"+between({u},0,0.35)*{5 + 4 * nivel}*cos({u}*83)*exp(-{u}*9)"
        fl += f"+between({u},0,0.4)*{0.08 + 0.05 * nivel}*exp(-{u}*14)"
    return (f"[base]scale=w='trunc(1080*({z})/2)*2':h='trunc(1920*({z})/2)*2':eval=frame:flags=bicubic,"
            f"crop=1080:1920:x='(iw-1080)/2+({sx})':y='(ih-1920)/2+({sy})',"
            f"eq=brightness='{fl}':eval=frame[cam]")


def pistas_sonido(dur, puntos, hook_t, nivel, rnd):
    """[(archivo, segundo, volumen)] para mezclar con el audio del clip."""
    if nivel == 0:
        return []
    vol = {1: 0.35, 2: 0.5, 3: 0.65}[nivel]
    out = []
    w = elegir("whoosh", rnd)
    if w:
        out.append((w, 0.0, vol * 0.9))
    if hook_t is not None:
        p = elegir("pop", rnd)
        if p:
            out.append((p, hook_t, vol * 0.7))
    for i, t in enumerate(puntos):
        cat = "impacto" if i % 2 == 0 or nivel < 2 else rnd.choice(["glitch", "impacto", "meme"])
        s = elegir(cat, rnd)
        if s:
            out.append((s, max(0, t - 0.03), vol))
        if i == 0 and nivel >= 2 and t > 1.5:
            r = elegir("riser", rnd)
            if r:
                out.append((r, max(0, t - 1.15), vol * 0.55))
    if nivel >= 2:
        d = elegir("ding", rnd)
        if d and dur > 8:
            out.append((d, dur - 0.9, vol * 0.4))
    return out
