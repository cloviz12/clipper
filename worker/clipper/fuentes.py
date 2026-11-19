"""Lee las fuentes (YouTube, Twitch, Kick) y saca las senales para encontrar los mejores momentos
SIN bajar el video completo: 'lo mas visto' de YouTube, chat del directo, subtitulos y, como
ultimo recurso, solo el audio en baja calidad."""
import json
import os
import re
import subprocess

import numpy as np
import yt_dlp
import yt_dlp.networking

from . import reacciones
from .base import TRABAJO, log, tool

PALABRAS_DEFECTO = [
    r"ja(ja)+", r"\bxd+\b", r"\blol\b", r"no puede ser", r"qu[eé] (es eso|pas[oó])", r"dios m[ií]o",
    r"\bwtf\b", r"incre[ií]ble", r"\bmira\b", r"\bbrutal\b", r"\bgol\b", r"\bnoo+\b", r"\bsii+\b",
    r"\bomg\b", r"no way", r"oh my god", r"\bwhat\b", r"risas", r"aplausos", r"laughter", r"applause",
    r"gritos?", r"\bclip\b",
]
def clasificar(url):
    u = url.strip()
    if re.search(r"twitch\.tv/videos/\d+", u):
        return "twitch_vod"
    if re.search(r"(clips\.twitch\.tv/|twitch\.tv/[^/]+/clip/)", u):
        return "clip_suelto"
    if re.search(r"twitch\.tv/[A-Za-z0-9_]+/?(\?.*)?$", u) or re.search(r"twitch\.tv/[A-Za-z0-9_]+/clips", u):
        return "twitch_canal"
    if re.search(r"kick\.com/.+(/clips/|\?clip=)clip_", u):
        return "clip_suelto"
    if re.search(r"kick\.com/[^/]+/videos/", u) or re.search(r"kick\.com/video/", u):
        return "kick_vod"
    if re.search(r"kick\.com/[A-Za-z0-9_\-]+/?$", u):
        return "kick_canal"
    if re.search(r"youtube\.com/(@[^/?]+|channel/|c/|user/)", u) and "watch" not in u:
        return "yt_canal"
    if re.search(r"(youtube\.com/(watch|live/|shorts/)|youtu\.be/)", u):
        return "yt_video"
    return "otro"


def ydl(extra=None):
    o = {"quiet": True, "no_warnings": True, "noplaylist": True, "socket_timeout": 30, "retries": 5}
    galletas = os.environ.get("YTDLP_COOKIES")
    if galletas and os.path.exists(galletas):
        o["cookiefile"] = galletas      # ayuda a que YouTube no bloquee las descargas desde un servidor
    o.update(extra or {})
    return yt_dlp.YoutubeDL(o)


def info(url):
    with ydl({"skip_download": True}) as y:
        return y.extract_info(url, download=False)


def canal_de(inf):
    return inf.get("channel") or inf.get("uploader") or inf.get("creator") or inf.get("uploader_id") or "canal"


# ---------------------------------------------------------------- listados
def ultimos_videos(url_canal, n, pestana="videos"):
    base = re.sub(r"/(videos|streams|shorts|featured|live)/?$", "", url_canal.rstrip("/"))
    with ydl({"extract_flat": "in_playlist", "playlistend": n, "noplaylist": False}) as y:
        r = y.extract_info(f"{base}/{pestana}", download=False)
    out = []
    for e in (r.get("entries") or [])[:n]:
        vid = e.get("id")
        if vid:
            out.append(f"https://www.youtube.com/watch?v={vid}")
    return out


def clips_destacados_twitch(canal_url, n, rango="7d"):
    m = re.search(r"twitch\.tv/([A-Za-z0-9_]+)", canal_url)
    ch = m.group(1)
    rmap = {"24h": "24hr", "1d": "24hr", "7d": "7d", "30d": "30d", "todo": "all", "all": "all"}
    url = f"https://www.twitch.tv/{ch}/clips?filter=clips&range={rmap.get(rango, '7d')}"
    with ydl({"extract_flat": "in_playlist", "playlistend": max(n * 3, 10), "noplaylist": False}) as y:
        r = y.extract_info(url, download=False)
    items = []
    for e in r.get("entries") or []:
        u = e.get("url") or e.get("webpage_url")
        if not u:
            continue
        if not u.startswith("http"):
            u = f"https://clips.twitch.tv/{u}"
        items.append({"url": u, "id": e.get("id") or u, "titulo": e.get("title") or "",
                      "vistas": e.get("view_count") or 0, "canal": ch})
    items.sort(key=lambda x: -(x["vistas"] or 0))
    return items


def clips_destacados_kick(canal_url, n, rango="7d"):
    slug_ = re.search(r"kick\.com/([A-Za-z0-9_\-]+)", canal_url).group(1)
    tmap = {"24h": "day", "1d": "day", "7d": "week", "30d": "month", "todo": "all", "all": "all"}
    api = f"https://kick.com/api/v2/channels/{slug_}/clips?sort=view&time={tmap.get(rango, 'week')}"
    with ydl() as y:
        data = json.loads(y.urlopen(yt_dlp.networking.Request(api, headers={"Accept": "application/json"})).read())
    items = []
    for c in data.get("clips", [])[: n * 2]:
        items.append({"url": f"https://kick.com/{slug_}/clips/{c['id']}", "id": c["id"],
                      "titulo": c.get("title") or "", "vistas": c.get("views") or c.get("view_count") or 0,
                      "canal": slug_})
    return items


# ---------------------------------------------------------------- senales (1 valor por segundo)
def senal_heatmap(inf, dur):
    hm = inf.get("heatmap") or []
    if not hm:
        return None
    s = np.zeros(int(dur) + 1)
    for h in hm:
        a, b = int(h["start_time"]), int(min(dur, h["end_time"]))
        s[a:b + 1] = np.maximum(s[a:b + 1], h.get("value", 0))
    return s


def _parse_json3(txt):
    cues = []
    for ev in json.loads(txt).get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        t = "".join(x.get("utf8", "") for x in segs).strip()
        if t:
            a = ev.get("tStartMs", 0) / 1000
            cues.append((a, a + ev.get("dDurationMs", 0) / 1000, t))
    return cues


def _parse_vtt(txt):
    cues, cur = [], None

    def ts(x):
        p = x.replace(",", ".").split(":")
        v = 0.0
        for q in p:
            v = v * 60 + float(q)
        return v
    for line in txt.splitlines():
        m = re.match(r"\s*([\d:.,]+)\s+-->\s+([\d:.,]+)", line)
        if m:
            cur = [ts(m.group(1)), ts(m.group(2)), ""]
            cues.append(cur)
        elif cur is not None and line.strip():
            cur[2] = (cur[2] + " " + re.sub(r"<[^>]+>", "", line)).strip()
    return [(a, b, t) for a, b, t in cues if t]


def subtitulos_fuente(inf, idioma="es"):
    """Subtitulos del propio YouTube (sin bajar video). Devuelve [(ini, fin, texto)]."""
    pools = [inf.get("subtitles") or {}, inf.get("automatic_captions") or {}]
    orig = inf.get("language") or idioma
    prefer = [f"{orig}-orig", orig, f"{idioma}-orig", idioma]
    for pool in pools:
        keys = list(pool.keys())
        cand = [k for k in prefer if k in pool] + [k for k in keys if k.endswith("-orig")]
        cand += [k for k in keys if k.split("-")[0] in (orig, idioma)]
        for k in cand:
            fmts = pool[k]
            f = next((x for x in fmts if x.get("ext") == "json3"), None) or next((x for x in fmts if x.get("ext") == "vtt"), None)
            if not f:
                continue
            try:
                with ydl() as y:
                    txt = y.urlopen(f["url"]).read().decode("utf-8", "replace")
                cues = _parse_json3(txt) if f.get("ext") == "json3" else _parse_vtt(txt)
                if cues:
                    return cues
            except Exception as e:
                log(f"    subtitulos {k}: {e}")
    return []


def senal_palabras(cues, dur, extra):
    if not cues:
        return None
    rx = re.compile("|".join(PALABRAS_DEFECTO + list(extra or [])), re.I)
    s = np.zeros(int(dur) + 1)
    for a, b, t in cues:
        k = len(rx.findall(t))
        k += t.count("!") * 0.5
        if k:
            s[int(a):int(b) + 1] += k
    return s


def senal_chat(url, dur):
    """Chat del directo (Twitch y YouTube): gente distinta reaccionando a lo mismo, segundo a segundo.
    Devuelve (serie, preparados, crudos) o None; los mensajes sirven para explicar cada momento."""
    try:
        from chat_downloader import ChatDownloader
    except Exception:
        return None
    prep, crudos = [], []
    try:
        for m in ChatDownloader().get_chat(url, message_types=["text_message"]):
            t = m.get("time_in_seconds")
            if t is None or t < 0 or t > dur:
                continue
            x = m.get("message") or ""
            p = reacciones.preparar(float(t), (m.get("author") or {}).get("name"), x)
            if p:
                prep.append(p)
                crudos.append((float(t), x[:200]))
    except Exception as e:
        log(f"    chat no disponible ({type(e).__name__})")
    if len(prep) < 50:
        return None
    log(f"    chat leido: {len(prep)} mensajes de {len({p[1] for p in prep})} personas")
    return reacciones.serie(prep, dur), prep, crudos


def senal_audio(url, dur, vid):
    """Baja SOLO el audio en la peor calidad (pocos MB) y mide picos de volumen: gritos, risas, hype."""
    out = TRABAJO / f"audio_{vid}"
    with ydl({"format": "worstaudio/ba/w", "outtmpl": str(out) + ".%(ext)s"}) as y:
        y.download([url])
    f = next((p for p in TRABAJO.glob(f"audio_{vid}.*") if p.suffix not in (".part", ".ytdl")), None)
    if not f:
        return None
    sr = 8000
    proc = subprocess.Popen([tool("ffmpeg"), "-v", "error", "-i", str(f), "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                            stdout=subprocess.PIPE)
    rms = []
    while True:
        buf = proc.stdout.read(sr * 2)
        if not buf:
            break
        x = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768
        rms.append(20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-6))
    proc.wait()
    try:
        f.unlink()
    except Exception:
        pass
    r = np.array(rms)
    if len(r) < 10:
        return None
    # que tan por encima esta cada segundo del volumen normal de su alrededor (60 s)
    k = 61
    pad = np.pad(r, k // 2, mode="edge")
    med = np.array([np.median(pad[i:i + k]) for i in range(len(r))])
    exc = np.clip(r - med, 0, None)
    exc[r < -45] = 0  # silencio
    return exc


# ---------------------------------------------------------------- directos
def plataforma_de(url):
    u = url.lower()
    if "twitch.tv" in u:
        return "twitch"
    if "kick.com" in u:
        return "kick"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    return "otro"


def nombre_canal(url):
    m = re.search(r"(?:twitch\.tv|kick\.com)/([A-Za-z0-9_\-]+)", url) or re.search(r"youtube\.com/(@[^/?]+)", url)
    return m.group(1) if m else url


def url_directo(url):
    """URL que muestra el directo actual del canal."""
    p = plataforma_de(url)
    if p == "youtube" and "watch" not in url and "/live" not in url:
        return url.rstrip("/") + "/live"
    if p in ("twitch", "kick"):
        return f"https://{'www.twitch.tv' if p == 'twitch' else 'kick.com'}/{nombre_canal(url)}"
    return url


def estado_directo(url):
    """Devuelve info del directo si el canal esta EN VIVO ahora, si no None."""
    try:
        with ydl({"skip_download": True}) as y:
            inf = y.extract_info(url_directo(url), download=False)
    except Exception:
        return None
    if inf and (inf.get("is_live") or inf.get("live_status") == "is_live"):
        return inf
    return None


TWITCH_GQL = "https://gql.twitch.tv/gql"
TWITCH_WEB_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"     # el client-id publico que usa la web de Twitch


def _epoch(iso):
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _clips_gql(canal, periodo, orden, primero=50, despues=None):
    import requests
    cursor = f', after:"{despues}"' if despues else ""
    q = ('query{user(login:"%s"){clips(first:%d%s,criteria:{period:%s,sort:%s}){edges{cursor node{'
         'id slug title createdAt viewCount durationSeconds videoOffsetSeconds curator{login} video{id} url}}'
         'pageInfo{hasNextPage}}}}' % (canal.lower(), primero, cursor, periodo, orden))
    r = requests.post(TWITCH_GQL, json={"query": q}, timeout=20, headers={"Client-Id": TWITCH_WEB_ID})
    r.raise_for_status()
    clips = ((r.json().get("data") or {}).get("user") or {}).get("clips") or {}
    return clips.get("edges") or [], (clips.get("pageInfo") or {}).get("hasNextPage")


def clips_recientes_twitch(canal, limite=30):
    """Clips que la gente acaba de crear en Twitch, del MAS NUEVO al mas viejo, con quien y cuando lo hizo.
    Si la consulta directa falla, usa la lista de yt-dlp (sin saber quien lo creo)."""
    try:
        edges, _ = _clips_gql(canal, "LAST_DAY", "CREATED_AT_DESC", limite)
        out = []
        for e in edges:
            n = e.get("node") or {}
            out.append({"url": n.get("url") or f"https://clips.twitch.tv/{n.get('slug')}", "id": n.get("id") or n.get("slug"),
                        "titulo": n.get("title") or "", "vistas": n.get("viewCount") or 0, "canal": canal,
                        "ts": _epoch(n.get("createdAt")), "creador": ((n.get("curator") or {}).get("login") or "").lower(),
                        "dur": n.get("durationSeconds") or 30})
        if out:
            return out
    except Exception:
        pass
    url = f"https://www.twitch.tv/{canal}/clips?filter=clips&range=24hr"
    with ydl({"extract_flat": "in_playlist", "playlistend": limite, "noplaylist": False}) as y:
        r = y.extract_info(url, download=False)
    out = []
    for e in r.get("entries") or []:
        u = e.get("url") or e.get("webpage_url")
        if not u:
            continue
        if not u.startswith("http"):
            u = f"https://clips.twitch.tv/{u}"
        out.append({"url": u, "id": e.get("id") or u, "titulo": e.get("title") or "",
                    "vistas": e.get("view_count") or 0, "canal": canal, "ts": e.get("timestamp"),
                    "creador": (e.get("uploader_id") or e.get("creator") or "").lower(), "dur": e.get("duration") or 30})
    return out


def clips_recientes_kick(canal, limite=30):
    """Clips nuevos de Kick (del mas nuevo al mas viejo)."""
    api = f"https://kick.com/api/v2/channels/{canal}/clips?sort=date&time=day"
    with ydl() as y:
        data = json.loads(y.urlopen(yt_dlp.networking.Request(api, headers={"Accept": "application/json"})).read())
    out = []
    for c in (data.get("clips") or [])[:limite]:
        out.append({"url": f"https://kick.com/{canal}/clips/{c['id']}", "id": c["id"], "titulo": c.get("title") or "",
                    "vistas": c.get("views") or c.get("view_count") or 0, "canal": canal, "ts": _epoch(c.get("created_at")),
                    "creador": ((c.get("creator") or {}).get("username") or "").lower(), "dur": c.get("duration") or 30})
    return out


def senal_clips_vod(inf, dur):
    """En un VOD de Twitch: donde saco clip la gente. Varias personas clipeando el mismo tramo es la
    mejor senal de que ahi paso algo. Devuelve (serie, [(segundo, creador)]) o None."""
    vid = str(inf.get("id") or "").lstrip("v")
    canal = inf.get("uploader_id") or inf.get("channel") or inf.get("uploader")
    if not vid or not canal:
        return None
    marcas, despues = [], None
    try:
        for _ in range(10):                                  # hasta 1000 clips del ultimo mes
            edges, hay_mas = _clips_gql(canal, "LAST_MONTH", "VIEWS_DESC", 100, despues)
            for e in edges:
                n = e.get("node") or {}
                if str((n.get("video") or {}).get("id")) == vid and n.get("videoOffsetSeconds") is not None:
                    fin = float(n["videoOffsetSeconds"]) + float(n.get("durationSeconds") or 30)
                    marcas.append((fin, ((n.get("curator") or {}).get("login") or "?").lower(),
                                   float(n.get("durationSeconds") or 30)))
            if not hay_mas or not edges:
                break
            despues = edges[-1].get("cursor")
    except Exception as e:
        log(f"    clips del VOD no disponibles ({type(e).__name__})")
    if len(marcas) < 2:
        return None
    s = np.zeros(int(dur) + 1)
    for fin, _, d in marcas:
        a, b = int(max(0, fin - d)), int(min(dur, fin))
        s[a:b + 1] += 0.4
        s[int(max(0, fin - 10)):b + 1] += 1.0             # lo que se clipea es lo de justo antes de cortar
    log(f"    clips de la comunidad en este VOD: {len(marcas)} de {len({m[1] for m in marcas})} personas")
    return s, [(fin, c) for fin, c, _ in marcas]
