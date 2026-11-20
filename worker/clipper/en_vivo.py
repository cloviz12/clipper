"""Vigila un directo EN TIEMPO REAL:
- graba los ultimos minutos en pedacitos de ~4 s (buffer circular, nunca el directo completo)
- escucha el chat y mide el volumen del audio segundo a segundo
- cuando el chat y/o el audio explotan frente a lo normal del directo, corta ese momento
  (lo de antes + la reaccion) y lo manda a editar al instante
- en Twitch y Kick vigila los clips que crea la gente: si varias personas clipean lo mismo a la vez,
  corta ese momento de la grabacion propia (mejor calidad y con la reaccion completa)"""
import statistics
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timezone

import numpy as np

from . import chat as chatmod
from . import fuentes as F
from . import viralidad
from .base import BUFFER, TRABAJO, _sin_ventana, ajustes, log, parse_rango, sb, slug, tool

REACCION_S = 5          # lo que tarda el chat en reaccionar a lo que vio
GUARDAR_S = 360         # minutos de buffer que se guardan
ESPERA_INICIAL = 90     # segundos para aprender lo "normal" del directo
RAFAGA_S = 45           # clips creados con menos de esto entre si son del mismo momento
RAFAGA_MIN = 2          # personas distintas clipeando lo mismo = momento seguro

# Umbral POR STREAMER: cada audiencia reacciona distinto (un chat colombiano de 15 personas que escribe
# "jsjsjs" y "uy hp" nunca va a llegar a la fuerza de un chat de 20 mil). En vez de un numero fijo,
# se aprende la fuerza normal de ESE directo y se corta lo que se sale de lo normal para ese publico.
UMBRAL_TECHO = 4.0      # el umbral fijo de antes: nunca se pide mas que esto
UMBRAL_PISO = 1.3       # ni menos (si no, en un directo muerto cualquier ruido seria clip)
CLIPS_HORA = 4          # cuantos momentos por hora se buscan por defecto (se cambia por canal)
APRENDER_S = 600        # segundos de historia para confiar solo en lo de este directo
PERFIL_MIN_S = 300      # con esta historia ya se guarda lo aprendido (si la app se cierra, no se pierde)
PERFIL_CADA_S = 300     # cada cuanto se guarda lo aprendido

# Varios canales pueden pedir corte a la vez: se recorta de a 2 para no saturar el PC (ffmpeg x264)
_CORTES = threading.Semaphore(2)


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
        self.clips_pend = []       # clips nuevos de la comunidad que aun no usamos
        self.momentos = []         # segundos epoch de los momentos que ya cortamos
        self.cortes = 0
        self.hist = deque(maxlen=3 * 3600)   # fuerza de cada segundo de este directo
        self.gente_tip = 0.0       # personas que comentan normalmente en 10 s (tamano de la audiencia)
        self.info_directo = info_directo
        self.categoria = None      # juego o categoria actual (se lee al arrancar y cada 5 min)
        self.perfil = dict((fuente.get("opciones") or {}).get("perfil") or {})
        self._ult_perfil = time.time()

    # ------------------------------------------------------------ grabacion
    def _grabar(self):
        """Lee el directo con streamlink (dentro de la app, sin programas aparte) y lo parte en pedacitos."""
        seg = str(self.dir / "%Y%m%d-%H%M%S.ts")
        salida = ["-map", "0:v:0?", "-map", "0:a:0?", "-c", "copy", "-f", "segment", "-segment_time", "4",
                  "-reset_timestamps", "1", "-strftime", "1", seg]
        try:
            from streamlink import Streamlink
            ses = Streamlink()
            ses.set_option("hls-live-edge", 2)
            ses.set_option("stream-segment-threads", 2)
            streams = ses.streams(self.url_vivo)
            st = next((streams[q] for q in ("1080p60", "1080p", "936p60", "720p60", "720p", "best") if q in streams), None)
            if st is None:
                raise RuntimeError("streamlink no encontro calidades")
            ff = subprocess.Popen([tool("ffmpeg"), "-v", "error", "-i", "pipe:0"] + salida,
                                  stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, **_sin_ventana())
            self.procs = [ff]
            fd = st.open()
            try:
                while self.vivo:
                    data = fd.read(65536)
                    if not data:
                        break
                    ff.stdin.write(data)
            finally:
                fd.close()
                try:
                    ff.stdin.close()
                except Exception:
                    pass
                try:
                    ff.wait(timeout=20)
                except Exception:
                    ff.kill()
            return
        except Exception as e:
            if not self.vivo:
                return
            log(f"{self.canal}: streamlink no pudo ({str(e)[:150]}); pruebo directo con yt-dlp", "aviso")
        for p in self.procs:                       # que no quede un ffmpeg viejo escribiendo los mismos pedacitos
            try:
                p.kill()
            except Exception:
                pass
        try:
            with F.ydl({"format": "best[height<=1080]/best"}) as y:
                url = y.extract_info(self.url_vivo, download=False)["url"]
            b = subprocess.Popen([tool("ffmpeg"), "-v", "error", "-i", url] + salida, stderr=subprocess.DEVNULL, **_sin_ventana())
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
            try:
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
                # limpieza del buffer (en Windows borrar un archivo en uso falla: no debe matar el hilo)
                limite = time.time() - GUARDAR_S
                for t, p in segs:
                    if t < limite:
                        try:
                            p.unlink(missing_ok=True)
                        except OSError:
                            continue
                        medidos.discard(p)
                for k in [k for k in list(self.audio) if k < limite]:
                    self.audio.pop(k, None)
            except Exception as e:
                log(f"{self.canal}: error midiendo el audio, sigo ({str(e)[:150]})", "aviso")
            time.sleep(1.5)

    # ------------------------------------------------------------ deteccion
    def _puntaje(self, ahora):
        """Que tanto se sale de lo normal el momento (ahora - reaccion), adaptado al tamano del chat."""
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
        # no basta con que escriban mucho: tienen que estar reaccionando A LO MISMO
        lect = self.chat.lectura(ahora - 10, ahora)
        consenso = lect.consenso
        claves = sorted(self.audio)
        z_audio = 0.0
        if len(claves) > 60:
            recientes = [self.audio[k] for k in claves if k >= ahora - REACCION_S - 8]
            normal = [self.audio[k] for k in claves if k >= ahora - 180]
            if recientes and normal:
                z_audio = (max(recientes) - statistics.median(normal)) / 4.0
        tip = self.gente_tip
        # en un chat chico "medio chat riendose" son 3 personas; en uno grande, 6 o mas
        min_gente = max(3, min(6, round(tip * 0.9)))
        fuerza = max(0.0, z_chat) * (0.5 + 1.3 * consenso)
        if lect.gente >= min_gente:
            fuerza += 2.6 * consenso                 # medio chat riendose ya es un momento, aunque sea chico
            if consenso < 0.15:
                fuerza *= 0.55                       # mucho texto pero sin reaccion: raid, saludos, spam
        # chat chico: que 4 personas reaccionen a la vez cuando normalmente comentan 2 es enorme
        if tip < 6 and consenso >= 0.3:
            reaccionan = lect.gente * max(lect.frac_reaccion, lect.frac_tema)
            fuerza += min(3.0, 0.9 * max(0.0, reaccionan / max(1.0, tip) - 1)) * (6 - tip) / 6
        # con poco chat, el grito del streamer dice mas que el chat
        peso_audio = 0.5 + 0.7 * max(0.0, (6 - tip) / 6)
        return fuerza + peso_audio * max(0.0, z_audio), z_chat, z_audio

    def _umbral(self):
        """Umbral de ESTE canal: el percentil de la fuerza que deja pasar ~N momentos por hora,
        entre un piso y el umbral fijo de antes, por la sensibilidad que se elige en la app."""
        sens = float(self.f.get("sensibilidad") or 1.0)
        op = self.f.get("opciones") or {}
        por_hora = float(op.get("clips_por_hora") or ajustes().get("clips_por_hora") or CLIPS_HORA)
        vals = [v for _, v in self.hist]
        q = 1 - min(0.06, max(0.002, por_hora * 7 / 3600))      # un momento dura ~7 s por encima
        propio = float(np.quantile(vals, q)) if len(vals) >= 120 else None
        guardado = self.perfil.get("umbral")
        if propio is not None and len(vals) >= APRENDER_S:
            base = propio
        elif propio is not None and guardado:
            m = len(vals) / APRENDER_S                         # pasa de lo guardado a lo de hoy
            base = m * propio + (1 - m) * float(guardado)
        elif guardado:
            base = float(guardado)
        elif propio is not None:
            base = propio * (1.5 - 0.5 * len(vals) / APRENDER_S)   # al principio, mas exigente
        else:
            base = UMBRAL_TECHO
        return min(UMBRAL_TECHO, max(UMBRAL_PISO, base)) * sens, propio

    def _guardar_perfil(self, final=False):
        """Guarda lo aprendido del canal para que el proximo directo arranque ya calibrado."""
        vals = [v for _, v in self.hist]
        if len(vals) < PERFIL_MIN_S:
            return
        _, propio = self._umbral()
        if propio is None:
            return
        viejo = self.perfil.get("umbral")
        nuevo = propio if not viejo else 0.6 * propio + 0.4 * float(viejo)
        self.perfil.update({
            "umbral": round(nuevo, 3), "gente_tipica": round(self.gente_tip, 1),
            "categoria": self.categoria, "actualizado": datetime.now(timezone.utc).isoformat(),
            "directos": int(self.perfil.get("directos", 0)) + (1 if final else 0),
            "fuerza_mediana": round(float(np.median(vals)), 3)})
        try:
            fila = sb().table("fuentes").select("opciones").eq("id", self.f["id"]).execute().data
            op = dict((fila[0].get("opciones") if fila else None) or {})
            op["perfil"] = self.perfil
            sb().table("fuentes").update({"opciones": op}).eq("id", self.f["id"]).execute()
        except Exception as e:
            log(f"{self.canal}: no pude guardar lo aprendido del canal ({str(e)[:120]})", "aviso")

    def _detectar(self):
        ult_tip, ult_cat, ult_err = 0, time.time(), 0
        while self.vivo:
            time.sleep(1)
            try:
                self._paso_deteccion(ult_tip, ult_cat)
            except Exception as e:
                # un error aqui antes mataba el hilo en silencio: el canal seguia "en vivo" pero nunca clipeaba
                if time.time() - ult_err > 60:
                    ult_err = time.time()
                    log(f"{self.canal}: error detectando, sigo ({type(e).__name__}: {str(e)[:150]})", "aviso")
            else:
                ult_tip, ult_cat = self._tip_t, self._cat_t

    def _paso_deteccion(self, ult_tip, ult_cat):
        self._tip_t, self._cat_t = ult_tip, ult_cat
        ahora = time.time()
        if ahora - ult_tip > 15:
            self.gente_tip = self.chat.gente_tipica(ahora - 300, ahora)
            self._tip_t = ahora
        if ahora - ult_cat > 300:                          # el streamer cambia de juego o se pone a charlar
            self._cat_t = ahora
            threading.Thread(target=self._refrescar_categoria, daemon=True).start()
        if ahora - self._ult_perfil > PERFIL_CADA_S:
            self._ult_perfil = ahora
            threading.Thread(target=self._guardar_perfil, daemon=True).start()
        if ahora - self.inicio < ESPERA_INICIAL:
            return
        p, zc, za = self._puntaje(ahora)
        self.hist.append((ahora, p))
        if ahora - self.ultimo_corte < 75:
            return
        umbral, _ = self._umbral()
        if p >= umbral and not self._ya_cortado(ahora - REACCION_S):
            self.ultimo_corte = ahora
            momento = ahora - REACCION_S
            self.momentos.append(momento)
            threading.Thread(target=self._cortar, args=(momento, p, zc, za), daemon=True).start()

    def _refrescar_categoria(self):
        c = F.categoria_directo(self.f["url"])
        if c and c != self.categoria:
            log(f"{self.canal}: ahora esta en «{c}»", "vivo")
            self.categoria = c

    def _rareza(self, p):
        """0..1: que tan raro es esta fuerza para este directo (percentil)."""
        vals = [v for _, v in self.hist]
        if len(vals) < 60:
            return min(1.0, p / UMBRAL_TECHO)
        return float(np.mean(np.array(vals) < p))

    def _cortar(self, momento, p, zc, za, extra=None):
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
            with _CORTES:
                subprocess.run([tool("ffmpeg"), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
                                "-ss", f"{off:.2f}", "-t", f"{antes + despues:.2f}", "-c:v", "libx264", "-preset", "ultrafast",
                                "-threads", "2", "-crf", "17", "-c:a", "aac", "-b:a", "192k", str(salida)],
                               check=True, capture_output=True, timeout=300)
        except Exception as e:
            log(f"{self.canal}: no pude cortar el momento ({str(getattr(e, 'stderr', None) or e)[-300:]!r})", "error")
            return
        finally:
            lista.unlink(missing_ok=True)
        self.cortes += 1
        lect = self.chat.lectura(momento - 6, momento + despues)
        extra = extra or {}
        que = "; ".join(x for x in (extra.get("motivo"), lect.describir()) if x)
        viral = viralidad.senales_vivo(lect, self.chat.gente_entre(momento - 2, momento + 8), self.gente_tip,
                                       self._rareza(p), za, extra.get("clips", 0))
        umbral, _ = self._umbral()
        log(f"PICO en {self.canal} (fuerza {p:.1f} / umbral {umbral:.1f}: chat {zc:.1f}, audio {za:.1f})"
            f"{' — ' + que if que else ''} — editando", "pico")
        self.cola.put((0, time.time(), {
            "archivo": salida, "canal": self.canal, "origen": "en_vivo", "url_fuente": self.url_vivo,
            "titulo_fuente": self.titulo, "pico": antes, "puntaje": min(1.0, p / 10),
            "senales": extra.get("senales", ["chat", "audio"]) + lect.etiquetas(), "reaccion_chat": que,
            "chat": self.chat.textos_entre(momento - 10, momento + despues), "fuente": self.f,
            "viral": viral, "categoria": self.categoria,
            "detectado_en": datetime.fromtimestamp(momento, timezone.utc).isoformat()}))

    # ------------------------------------------------------------ clips que crea la gente (Twitch y Kick)
    def _ya_cortado(self, momento, margen=40):
        return any(abs(m - momento) < margen for m in self.momentos)

    def _grupos(self):
        """Junta los clips pendientes que se crearon casi al mismo tiempo (mismo momento del directo)."""
        grupos = []
        for c in sorted(self.clips_pend, key=lambda c: c["ts"]):
            if grupos and c["ts"] - grupos[-1][-1]["ts"] <= RAFAGA_S:
                grupos[-1].append(c)
            else:
                grupos.append([c])
        return grupos

    def _revisar_clips(self, ahora):
        usados = set()
        for g in self._grupos():
            gente = {c.get("creador") or c["id"] for c in g}
            momento = min(c["ts"] for c in g) - 3          # se clipea justo despues de ver el momento
            if len(gente) >= RAFAGA_MIN:
                usados |= {c["id"] for c in g}
                if self._ya_cortado(momento) or ahora - momento > GUARDAR_S - 40:
                    continue
                self.momentos.append(momento)
                self.ultimo_corte = ahora
                motivo = f"{len(gente)} personas sacaron clip al mismo tiempo"
                log(f"{self.canal}: {motivo} — corto ese momento", "pico")
                threading.Thread(target=self._cortar, daemon=True, args=(momento, 6.0 + len(gente), 0.0, 0.0, {
                    "senales": [f"{len(gente)} clips de la comunidad a la vez", "chat", "audio"],
                    "motivo": motivo, "clips": len(gente)})).start()
            elif ahora - g[-1]["ts"] > RAFAGA_S + 10:
                # nadie mas lo clipeo: igual vale, pero se usa el clip tal cual (si no lo cortamos ya)
                usados |= {c["id"] for c in g}
                if not self._ya_cortado(momento, 60):
                    self.momentos.append(momento)
                    self._usar_clip(g[0])
        self.clips_pend = [c for c in self.clips_pend if c["id"] not in usados and ahora - c["ts"] < GUARDAR_S]

    def _usar_clip(self, c):
        try:
            from .render_tramo import bajar
            arch = bajar(c["url"], nombre=f"clip_{slug(str(c['id']), 30)}")
        except Exception as e:
            log(f"{self.canal}: no pude bajar el clip {c['url']} ({str(e)[:150]})", "aviso")
            return
        log(f"{self.canal}: clip nuevo de la comunidad '{c['titulo'][:50]}' — editando", "pico")
        self.cola.put((0, time.time(), {
            "archivo": arch, "canal": self.canal, "origen": f"clip_{self.plat}", "url_fuente": c["url"],
            "titulo_fuente": c["titulo"] or self.titulo, "pico": None, "puntaje": 0.7,
            "senales": ["clip de la comunidad"], "chat": self.chat.textos_entre(c["ts"] - 40, c["ts"] + 10),
            "fuente": self.f, "categoria": self.categoria,
            "viral": viralidad.senales_vivo(self.chat.lectura(c["ts"] - 30, c["ts"]),
                                            self.chat.gente_entre(c["ts"] - 30, c["ts"] - 20), self.gente_tip,
                                            0.6, 0.0, 1)}))

    def _clips_comunidad(self):
        leer = F.clips_recientes_twitch if self.plat == "twitch" else F.clips_recientes_kick
        primero = True
        while self.vivo:
            ahora = time.time()
            try:
                for c in leer(self.canal, 30):
                    if c["id"] in self.clips_vistos:
                        continue
                    self.clips_vistos.add(c["id"])
                    if primero:
                        continue                       # los que ya existian al empezar no cuentan
                    c["ts"] = min(ahora, c.get("ts") or ahora)
                    self.clips_pend.append(c)
                primero = False
                self._revisar_clips(ahora)
            except Exception as e:
                log(f"{self.canal}: no pude leer clips nuevos ({str(e)[:150]})", "aviso")
            time.sleep(20)

    # ------------------------------------------------------------
    def run(self):
        self.categoria = F.categoria_directo(self.f["url"], self.info_directo)
        aprendido = f", umbral aprendido {self.perfil['umbral']:.1f}" if self.perfil.get("umbral") else ""
        log(f"EN VIVO: {self.canal} ({self.plat}) — {self.titulo[:80]}"
            f"{' — ' + self.categoria if self.categoria else ''}{aprendido}", "vivo")
        if self.plat == "twitch":
            chatmod.twitch(self.canal, self.chat)
            threading.Thread(target=self._clips_comunidad, daemon=True).start()
        elif self.plat == "kick":
            chatmod.kick(self.canal, self.chat)
            threading.Thread(target=self._clips_comunidad, daemon=True).start()
        elif self.plat == "youtube":
            chatmod.youtube(self.url_vivo, self.chat)
        threading.Thread(target=self._medir_audio, daemon=True).start()
        threading.Thread(target=self._detectar, daemon=True).start()
        self._grabar()
        self.parar()
        self._guardar_perfil(final=True)
        umbral, _ = self._umbral()
        log(f"{self.canal} termino el directo ({self.cortes} momentos cortados; umbral aprendido "
            f"{umbral:.1f}, audiencia ~{self.gente_tip:.0f} personas comentando cada 10 s)", "vivo")

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
