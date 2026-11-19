"""Vigila un directo EN TIEMPO REAL:
- graba los ultimos minutos en pedacitos de ~4 s (buffer circular, nunca el directo completo)
- escucha el chat y mide el volumen del audio segundo a segundo
- cuando el chat y/o el audio explotan frente a lo normal del directo, corta ese momento
  (lo de antes + la reaccion) y lo manda a editar al instante
- en Twitch, ademas, toma al momento los clips que la gente va creando"""
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

import numpy as np

from . import chat as chatmod
from . import fuentes as F
from .base import BUFFER, TRABAJO, ajustes, log, parse_rango, slug, tool

REACCION_S = 5          # lo que tarda el chat en reaccionar a lo que vio
GUARDAR_S = 360         # minutos de buffer que se guardan
ESPERA_INICIAL = 90     # segundos para aprender lo "normal" del directo


class Monitor(threading.Thread):
    def __init__(self, fuente, cola, info_directo):
        super().__init__(daemon=True, name=f"vivo-{fuente.get('nombre') or fuente['id'][:6]}")
        self.f = fuente
        self.cola = cola
        self.plat = F.plataforma_de(fuente["url"])
        self.canal = fuente.get("nombre") or F.nombre_canal(fuente["url"])
        self.titulo = info_directo.get("title") or ""
        self.url_vivo = info_directo.get("webpage_url") or F.url_directo(fuente["url"])
        self.dir = BUFFER / slug(f"{self.plat}_{self.canal}")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.chat = chatmod.Chat()
        self.audio = {}            # segundo_epoch -> dB
        self.vivo = True
        self.ultimo_corte = 0
        self.inicio = time.time()
        self.procs = []
        self.clips_vistos = set()
        self.cortes = 0

    # ------------------------------------------------------------ grabacion
    def _grabar(self):
        seg = str(self.dir / "%Y%m%d-%H%M%S.ts")
        ff = [tool("ffmpeg"), "-v", "error", "-i", "pipe:0", "-map", "0:v:0?", "-map", "0:a:0?", "-c", "copy",
              "-f", "segment", "-segment_time", "4", "-reset_timestamps", "1", "-strftime", "1", seg]
        sl = [sys.executable, "-m", "streamlink", "--stdout", "--retry-streams", "5", "--retry-max", "3",
              "--hls-live-edge", "2", "--stream-segment-threads", "2"]
        if self.plat == "twitch":
            sl += ["--twitch-disable-ads", "--twitch-low-latency"]
        sl += [self.url_vivo, "1080p60,1080p,936p60,720p60,720p,best"]
        try:
            a = subprocess.Popen(sl, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            b = subprocess.Popen(ff, stdin=a.stdout, stderr=subprocess.DEVNULL)
            self.procs = [a, b]
            b.wait()
        except Exception as e:
            log(f"{self.canal}: streamlink no pudo ({e}); pruebo directo con yt-dlp", "aviso")
        if not self.vivo:
            return
        # respaldo: URL HLS que da yt-dlp, la lee ffmpeg directo
        try:
            with F.ydl({"format": "best[height<=1080]/best"}) as y:
                url = y.extract_info(self.url_vivo, download=False)["url"]
            b = subprocess.Popen([tool("ffmpeg"), "-v", "error", "-i", url] + ff[6:], stderr=subprocess.DEVNULL)
            self.procs = [b]
            b.wait()
        except Exception as e:
            log(f"{self.canal}: no pude grabar el directo ({str(e)[:200]})", "error")

    def _segmentos(self):
        out = []
        for p in self.dir.glob("*.ts"):
            try:
                t = datetime.strptime(p.stem, "%Y%m%d-%H%M%S").timestamp()
                out.append((t, p))
            except ValueError:
                pass
        return sorted(out)

    # ------------------------------------------------------------ audio por segundo
    def _medir_audio(self):
        medidos = set()
        while self.vivo:
            segs = self._segmentos()
            for t, p in segs[:-1]:            # el ultimo se esta escribiendo
                if p in medidos:
                    continue
                medidos.add(p)
                try:
                    r = subprocess.run([tool("ffmpeg"), "-v", "error", "-i", str(p), "-vn", "-ac", "1", "-ar", "8000",
                                        "-f", "s16le", "-"], capture_output=True, timeout=30)
                    x = np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768
                    for i in range(len(x) // 8000):
                        b = x[i * 8000:(i + 1) * 8000]
                        self.audio[int(t) + i] = float(20 * np.log10(np.sqrt(np.mean(b * b)) + 1e-6))
                except Exception:
                    pass
            # limpieza del buffer
            limite = time.time() - GUARDAR_S
            for t, p in segs:
                if t < limite:
                    p.unlink(missing_ok=True)
                    medidos.discard(p)
            for k in [k for k in self.audio if k < limite]:
                del self.audio[k]
            time.sleep(1.5)

    # ------------------------------------------------------------ deteccion
    def _puntaje(self, ahora):
        """Que tanto se sale de lo normal el momento (ahora - reaccion)."""
        ventana = 8
        serie = self.chat.serie(ahora - 300, ahora)
        if len(serie) < 60 or self.chat.mensajes < 30:
            z_chat = 0.0
        else:
            tramos = [sum(serie[i:i + ventana]) / ventana for i in range(0, len(serie) - ventana, 4)]
            base = statistics.median(tramos)
            mad = statistics.median([abs(x - base) for x in tramos]) * 1.4826
            actual = sum(serie[-ventana:]) / ventana
            z_chat = (actual - base) / (mad + 0.4 + 0.15 * base)
        claves = sorted(self.audio)
        z_audio = 0.0
        if len(claves) > 60:
            recientes = [self.audio[k] for k in claves if k >= ahora - REACCION_S - 8]
            normal = [self.audio[k] for k in claves if k >= ahora - 180]
            if recientes and normal:
                z_audio = (max(recientes) - statistics.median(normal)) / 4.0
        return z_chat + 0.5 * max(0.0, z_audio), z_chat, z_audio

    def _detectar(self):
        while self.vivo:
            time.sleep(1)
            ahora = time.time()
            if ahora - self.inicio < ESPERA_INICIAL or ahora - self.ultimo_corte < 75:
                continue
            p, zc, za = self._puntaje(ahora)
            umbral = 4.0 * float(self.f.get("sensibilidad") or 1.0)
            if p >= umbral:
                self.ultimo_corte = ahora
                momento = ahora - REACCION_S
                threading.Thread(target=self._cortar, args=(momento, p, zc, za), daemon=True).start()

    def _cortar(self, momento, p, zc, za):
        lmin, lmax = parse_rango(self.f.get("opciones", {}).get("duracion") or ajustes().get("duracion_clip"))
        L = (lmin + lmax) / 2
        antes, despues = L * 0.7, L * 0.3
        a, b = momento - antes, momento + despues
        while time.time() < b + 6 and self.vivo:       # espera a que se grabe la reaccion
            time.sleep(1)
        segs = [(t, s) for t, s in self._segmentos() if t <= b and t >= a - 8]
        if len(segs) < 2:
            return
        lista = TRABAJO / f"vivo_{int(momento)}.txt"
        lista.write_text("".join(f"file '{s.as_posix()}'\n" for _, s in segs), encoding="utf-8")
        salida = TRABAJO / f"vivo_{slug(self.canal, 16)}_{int(momento)}.mp4"
        off = max(0.0, a - segs[0][0])
        try:
            subprocess.run([tool("ffmpeg"), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
                            "-ss", f"{off:.2f}", "-t", f"{antes + despues:.2f}", "-c:v", "libx264", "-preset", "ultrafast",
                            "-crf", "17", "-c:a", "aac", "-b:a", "192k", str(salida)], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            log(f"{self.canal}: no pude cortar el momento ({e.stderr[-300:]!r})", "error")
            return
        finally:
            lista.unlink(missing_ok=True)
        self.cortes += 1
        log(f"PICO en {self.canal} (fuerza {p:.1f}: chat {zc:.1f}, audio {za:.1f}) — editando", "pico")
        self.cola.put((0, time.time(), {
            "archivo": salida, "canal": self.canal, "origen": "en_vivo", "url_fuente": self.url_vivo,
            "titulo_fuente": self.titulo, "pico": antes, "puntaje": min(1.0, p / 10), "senales": ["chat", "audio"],
            "chat": self.chat.textos_entre(momento - 10, momento + despues), "fuente": self.f,
            "detectado_en": datetime.fromtimestamp(momento, timezone.utc).isoformat()}))

    # ------------------------------------------------------------ clips que crea la gente (Twitch)
    def _clips_twitch(self):
        primero = True
        while self.vivo:
            try:
                for c in F.clips_recientes_twitch(self.canal, 20):
                    if c["id"] in self.clips_vistos:
                        continue
                    self.clips_vistos.add(c["id"])
                    if primero:
                        continue                       # los que ya existian al empezar no cuentan
                    if time.time() - self.ultimo_corte < 60:
                        continue                       # ese momento ya lo cortamos nosotros
                    self.ultimo_corte = time.time()
                    from .render_tramo import bajar
                    arch = bajar(c["url"], nombre=f"twclip_{slug(c['id'], 30)}")
                    log(f"{self.canal}: clip nuevo de la comunidad '{c['titulo'][:50]}' — editando", "pico")
                    self.cola.put((0, time.time(), {
                        "archivo": arch, "canal": self.canal, "origen": "clip_twitch", "url_fuente": c["url"],
                        "titulo_fuente": c["titulo"] or self.titulo, "pico": None, "puntaje": 0.7,
                        "senales": ["clip de la comunidad"], "chat": self.chat.textos_entre(time.time() - 60, time.time()),
                        "fuente": self.f}))
                primero = False
            except Exception as e:
                log(f"{self.canal}: no pude leer clips nuevos ({str(e)[:150]})", "aviso")
            time.sleep(40)

    # ------------------------------------------------------------
    def run(self):
        log(f"EN VIVO: {self.canal} ({self.plat}) — {self.titulo[:80]}", "vivo")
        if self.plat == "twitch":
            chatmod.twitch(self.canal, self.chat)
            threading.Thread(target=self._clips_twitch, daemon=True).start()
        elif self.plat == "kick":
            chatmod.kick(self.canal, self.chat)
        elif self.plat == "youtube":
            chatmod.youtube(self.url_vivo, self.chat)
        threading.Thread(target=self._medir_audio, daemon=True).start()
        threading.Thread(target=self._detectar, daemon=True).start()
        self._grabar()
        self.parar()
        log(f"{self.canal} termino el directo ({self.cortes} momentos cortados)", "vivo")

    def parar(self):
        self.vivo = False
        self.chat.parar()
        for p in self.procs:
            try:
                p.kill()
            except Exception:
                pass
        for _, s in self._segmentos():
            s.unlink(missing_ok=True)
