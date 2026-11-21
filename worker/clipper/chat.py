"""Escucha el chat del directo EN TIEMPO REAL y guarda cuanta 'reaccion' hay cada segundo."""
import json
import socket
import threading
import time
from collections import deque

import requests

from . import reacciones
from .base import log

class Chat:
    """Guarda el chat de los ultimos minutos ya analizado (quien escribio, si se rio, de que hablo)."""

    def __init__(self):
        self.msgs = deque(maxlen=30000)       # preparados: (t, usuario, tipos, palabras)
        self.textos = deque(maxlen=600)       # (t, texto) para que la IA entienda el momento
        self.vivo = True
        self.mensajes = 0

    def agregar(self, texto, usuario=None):
        t = time.time()
        m = reacciones.preparar(t, usuario, texto)
        if m is None:
            return
        self.msgs.append(m)
        self.textos.append((t, (texto or "")[:200]))
        self.mensajes += 1

    def _entre(self, a, b):
        return [m for m in list(self.msgs) if a <= m[0] < b]

    def serie(self, desde, hasta):
        """Personas distintas escribiendo en cada segundo (el spam de uno solo cuenta una vez)."""
        n = max(1, int(hasta - desde))
        s = [set() for _ in range(n)]
        for t, u, _, _ in self._entre(desde, hasta):
            s[int(t - desde)].add(u)
        return [float(len(x)) for x in s]

    def gente_entre(self, a, b):
        return len({m[1] for m in self._entre(a, b)})

    def gente_tipica(self, desde, hasta, ventana=10):
        """Mediana de personas distintas que escriben en ventanas de 'ventana' segundos: el tamano real
        de la audiencia que comenta (un chat colombiano chico tiene 2-4, uno grande 40+)."""
        msgs = self._entre(desde, hasta)
        if not msgs:
            return 0.0
        cajas = {}
        for t, u, _, _ in msgs:
            cajas.setdefault(int((t - desde) // ventana), set()).add(u)
        n = max(1, int((hasta - desde) // ventana))
        vals = sorted(len(cajas.get(i, ())) for i in range(n))
        return float(vals[len(vals) // 2])

    def lectura(self, a, b, antes=300):
        """Que paso en el chat entre a y b, comparado con lo normal de los minutos previos."""
        return reacciones.leer(self._entre(a, b), reacciones.palabras_normales(self._entre(a - antes, a)))

    def textos_entre(self, a, b, maximo=40):
        return [x for t, x in list(self.textos) if a <= t <= b][-maximo:]

    def parar(self):
        self.vivo = False


def twitch(canal, chat):
    """IRC anonimo de Twitch (no necesita cuenta)."""
    def bucle():
        while chat.vivo:
            try:
                s = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=30)
                s.sendall(b"NICK justinfan%d\r\n" % (int(time.time()) % 90000 + 10000))
                s.sendall(f"JOIN #{canal.lower()}\r\n".encode())
                buf = b""
                while chat.vivo:
                    data = s.recv(8192)
                    if not data:
                        break
                    buf += data
                    *lineas, buf = buf.split(b"\r\n")
                    for ln in lineas:
                        l = ln.decode("utf-8", "replace")
                        if l.startswith("PING"):
                            s.sendall(b"PONG :tmi.twitch.tv\r\n")
                        elif " PRIVMSG " in l:
                            quien = l[1:].split("!", 1)[0] if l.startswith(":") else None
                            chat.agregar(l.split(" :", 1)[-1], quien)
                s.close()
            except Exception:
                time.sleep(5)
    threading.Thread(target=bucle, daemon=True, name=f"chat-twitch-{canal}").start()


def _sala_kick(canal):
    """Id de la sala de chat de Kick. Devuelve (id o None, lista de motivos por los que fallaron los intentos).
    Kick protege su API con Cloudflare: si 'requests' no pasa, se prueba con el cliente de yt-dlp."""
    errores = []
    cab = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "application/json", "Referer": "https://kick.com/"}
    for ver in ("v2", "v1"):
        url = f"https://kick.com/api/{ver}/channels/{canal}"
        try:
            r = requests.get(url, timeout=20, headers=cab)
            if r.status_code == 200:
                return r.json()["chatroom"]["id"], errores
            errores.append(f"{ver}: HTTP {r.status_code}")
        except Exception as e:
            errores.append(f"{ver}: {type(e).__name__} {str(e)[:60]}")
    try:
        import yt_dlp
        from . import fuentes as F
        with F.ydl() as y:
            d = json.loads(y.urlopen(yt_dlp.networking.Request(
                f"https://kick.com/api/v2/channels/{canal}", headers={"Accept": "application/json"})).read())
        return d["chatroom"]["id"], errores
    except Exception as e:
        errores.append(f"yt-dlp: {type(e).__name__} {str(e)[:60]}")
    return None, errores


def kick(canal, chat):
    """Chat de Kick por su websocket publico (Pusher). Avisa en el Registro si no logra conectar,
    porque sin chat solo quedan el audio y los clips de la comunidad para detectar momentos."""
    def bucle():
        import websocket
        sala, errores = _sala_kick(canal)
        if sala is None:
            log(f"{canal}: no pude conectar el chat de Kick ({' | '.join(errores)[:300]}); detecto solo con audio y clips de la comunidad", "aviso")
            return
        url = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false"
        ult_err, conectado = 0, False
        while chat.vivo:
            try:
                ws = websocket.create_connection(url, timeout=60)
                ws.send(json.dumps({"event": "pusher:subscribe", "data": {"auth": "", "channel": f"chatrooms.{sala}.v2"}}))
                while chat.vivo:
                    m = json.loads(ws.recv())
                    ev = m.get("event", "")
                    if ev == "pusher:ping":
                        ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                    elif ev == "pusher_internal:subscription_succeeded" and not conectado:
                        conectado = True
                        log(f"{canal}: chat de Kick conectado", "vivo")
                    elif ev == "pusher:error":
                        raise RuntimeError(str(m.get("data"))[:150])
                    elif "ChatMessage" in ev:
                        d = json.loads(m["data"]) if isinstance(m.get("data"), str) else m.get("data", {})
                        chat.agregar(d.get("content", ""), (d.get("sender") or {}).get("username"))
            except Exception as e:
                if time.time() - ult_err > 300:       # sin llenar el Registro si se cae seguido
                    ult_err = time.time()
                    log(f"{canal}: el chat de Kick se cayo, reconecto ({type(e).__name__} {str(e)[:120]})", "aviso")
                time.sleep(5)
    threading.Thread(target=bucle, daemon=True, name=f"chat-kick-{canal}").start()


def youtube(url_video, chat):
    def bucle():
        try:
            from chat_downloader import ChatDownloader
            for m in ChatDownloader().get_chat(url_video, message_types=["text_message", "paid_message"]):
                if not chat.vivo:
                    break
                chat.agregar(m.get("message") or "", (m.get("author") or {}).get("name"))
        except Exception:
            pass
    threading.Thread(target=bucle, daemon=True, name="chat-youtube").start()
