"""Pedidos sueltos desde el panel: un video, un VOD, un canal (sus clips mas vistos o sus ultimos videos).
Encuentra los mejores momentos SIN bajar el video completo y manda cada tramo a la cola de edicion."""
import time

from . import fuentes as F
from . import momentos, reacciones
from .base import ajustes, hms, log, parse_rango, sb, slug
from .render_tramo import bajar


def _ya_existe(url_fuente):
    r = sb().table("clips").select("id").eq("url_fuente", url_fuente).limit(1).execute()
    return bool(r.data)


def _con_tiempo(url, a):
    if "youtube.com/watch" in url or "youtu.be/" in url:
        return f"{url}{'&' if '?' in url else '?'}t={int(a)}s"
    if "twitch.tv/videos/" in url:
        return f"{url}{'&' if '?' in url else '?'}t={int(a // 3600)}h{int(a % 3600 // 60)}m{int(a % 60)}s"
    return url


class Pedido:
    def __init__(self, fila, cola, progreso):
        self.t = fila
        self.cola = cola
        self.progreso = progreso
        self.op = fila.get("opciones") or {}
        self.n = int(fila.get("clips") or 3)
        self.lmin, self.lmax = parse_rango(fila.get("duracion"), ajustes().get("duracion_clip"))
        self.enviados = 0

    def _encolar(self, ctx):
        ctx.update(trabajo_id=self.t["id"], plataformas=self.op.get("plataformas"), auto=self.op.get("publicar") == "auto",
                   idioma=self.op.get("idioma"))
        self.cola.put((1, time.time(), ctx))
        self.enviados += 1

    def video(self, url):
        inf = F.info(url)
        vid, dur = inf.get("id") or slug(url), float(inf.get("duration") or 0)
        canal = F.canal_de(inf)
        base = inf.get("webpage_url") or url
        self.progreso(f"{canal}: {inf.get('title', '')[:60]} ({hms(dur)})")
        if inf.get("is_live"):
            raise RuntimeError("ese directo sigue en vivo: agregalo en 'En vivo' para sacar clips en tiempo real")
        if dur and dur <= self.lmax + 8:
            if _ya_existe(base):
                return
            arch = bajar(url, nombre=f"job_{slug(vid, 24)}")
            self._encolar({"archivo": arch, "canal": canal, "origen": "video", "url_fuente": base, "inicio": 0,
                           "titulo_fuente": inf.get("title", ""), "pico": None, "puntaje": 0.5, "senales": ["clip completo"]})
            return
        senales, cues, charla = {}, [], None
        hm = F.senal_heatmap(inf, dur)
        if hm is not None:
            senales["heatmap"] = hm
        if inf.get("extractor_key", "").startswith("Youtube"):
            cues = F.subtitulos_fuente(inf, self.op.get("idioma") or ajustes().get("idioma", "es"))
            senales["palabras"] = F.senal_palabras(cues, dur, [])
        if inf.get("was_live") or inf.get("live_status") == "was_live" or "twitch" in inf.get("extractor_key", "").lower():
            self.progreso(f"{canal}: leyendo el chat del directo...")
            charla = F.senal_chat(base, dur)
            if charla:
                senales["chat"] = charla[0]
        if senales.get("heatmap") is None and senales.get("chat") is None:
            self.progreso(f"{canal}: analizando solo el audio...")
            try:
                senales["audio"] = F.senal_audio(url, dur, slug(vid, 30))
            except Exception as e:
                log(f"no pude analizar el audio: {e}", "aviso")
        score, usadas = momentos.combinar(senales, dur)
        ventanas = momentos.escoger(score, dur, self.n * 2, self.lmin, self.lmax, cues) if usadas else \
            [(max(0, dur / 2 - self.lmax / 2), min(dur, dur / 2 + self.lmax / 2), 0)]
        hechos = 0
        for a, b, val in ventanas:
            if hechos >= self.n:
                break
            uf = _con_tiempo(base, a)
            if _ya_existe(uf):
                continue
            self.progreso(f"{canal}: bajando solo {hms(a)}–{hms(b)} ({', '.join(usadas) or 'sin señales'})")
            try:
                arch = bajar(url, a, b, f"job_{slug(vid, 20)}_{int(a)}")
            except Exception as e:
                log(f"no pude bajar el tramo {hms(a)}: {str(e)[:200]}", "error")
                continue
            # el pico real dentro del tramo
            seg = score[int(a):int(b) + 1]
            pico = float(seg.argmax()) if len(seg) and seg.max() > 0 else None
            extra = {}
            if charla:
                _, prep, crudos = charla
                lect = reacciones.leer([m for m in prep if a <= m[0] <= b],
                                       reacciones.palabras_normales([m for m in prep if a - 300 <= m[0] < a]))
                extra = {"senales": usadas + lect.etiquetas(), "reaccion_chat": lect.describir(),
                         "chat": [x for t, x in crudos if a <= t <= b][-40:]}
            self._encolar({"archivo": arch, "canal": canal, "origen": "vod" if inf.get("was_live") else "video",
                           "url_fuente": uf, "inicio": a, "titulo_fuente": inf.get("title", ""), "pico": pico,
                           "puntaje": float(val), "senales": usadas, **extra})
            hechos += 1

    def destacados(self, url):
        plat = F.plataforma_de(url)
        rango = self.op.get("rango", "7d")
        items = F.clips_destacados_twitch(url, self.n, rango) if plat == "twitch" else F.clips_destacados_kick(url, self.n, rango)
        hechos = 0
        for it in items:
            if hechos >= self.n:
                break
            if _ya_existe(it["url"]):
                continue
            self.progreso(f"{it['canal']}: clip '{it['titulo'][:50]}' ({it['vistas']} vistas)")
            try:
                arch = bajar(it["url"], nombre=f"dest_{slug(it['id'], 30)}")
            except Exception as e:
                log(f"no pude bajar {it['url']}: {str(e)[:200]}", "error")
                continue
            self._encolar({"archivo": arch, "canal": it["canal"], "origen": f"clip_{plat}", "url_fuente": it["url"],
                           "titulo_fuente": it["titulo"], "pico": None, "puntaje": 0.6, "senales": ["clips mas vistos"]})
            hechos += 1

    def ejecutar(self):
        url = self.t["url"].strip()
        tipo = F.clasificar(url)
        if tipo in ("twitch_canal", "kick_canal"):
            self.destacados(url)
        elif tipo == "yt_canal":
            for v in F.ultimos_videos(url, int(self.op.get("ultimos", 3)), self.op.get("pestana", "videos")):
                try:
                    self.video(v)
                except Exception as e:
                    log(f"{v}: {str(e)[:200]}", "error")
        else:
            self.video(url)
        return self.enviados
