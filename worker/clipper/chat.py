"""Escucha el chat del directo EN TIEMPO REAL y guarda cuanta 'reaccion' hay cada segundo."""
import json
import re
import socket
import threading
import time
from collections import deque

import requests

REACCION = re.compile(
    r"(KEKW|LUL|LULW|OMEGALUL|ICANT|Pog|POGGERS|PogU|monkaS|monkaW|Sadge|xdd|XD+|xD+|jaja\w*|JAJA\w*|"
    r"ajaj\w*|lmao|LMAO|wtf|WTF|NO+\b|SI+\b|GOO+L|\?\?+|!!+|clip|CLIP|ALV|alv|qu[eé]+ ?|omg|OMG|W\b|L\b)")


class Chat:
    """Cuenta mensajes por segundo (con peso extra por emotes de risa/sorpresa)."""

    def __init__(self):
        self.puntos = deque(maxlen=60 * 30)   # (segundo_epoch, peso)
        self.textos = deque(maxlen=400)       # (t, texto) para que la IA entienda el momento
        self.vivo = True
        self.mensajes = 0

    def agregar(self, texto):
        t = time.time()
        w = 1.0 + 0.5 * min(4, len(REACCION.findall(texto or "")))
        self.puntos.append((t, w))
        self.textos.append((t, (texto or "")[:200]))
        self.mensajes += 1

    def serie(self, desde, hasta):
        """Suma de pesos por segundo entre dos tiempos epoch."""
        n = max(1, int(hasta - desde))
        s = [0.0] * n
        for t, w in list(self.puntos):
            i = int(t - desde)
            if 0 <= i < n:
                s[i] += w
        return s

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
                            chat.agregar(l.split(" :", 1)[-1])
                s.close()
            except Exception:
                time.sleep(5)
    threading.Thread(target=bucle, daemon=True, name=f"chat-twitch-{canal}").start()


def kick(canal, chat):
    """Chat de Kick por su websocket publico (Pusher)."""
    def bucle():
        import websocket
        try:
            info = requests.get(f"https://kick.com/api/v2/channels/{canal}", timeout=20,
                                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}).json()
            sala = info["chatroom"]["id"]
        except Exception:
            return
        url = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false"
        while chat.vivo:
            try:
                ws = websocket.create_connection(url, timeout=60)
                ws.send(json.dumps({"event": "pusher:subscribe", "data": {"auth": "", "channel": f"chatrooms.{sala}.v2"}}))
                while chat.vivo:
                    m = json.loads(ws.recv())
                    if m.get("event") == "pusher:ping":
                        ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                    elif "ChatMessage" in m.get("event", ""):
                        d = json.loads(m["data"]) if isinstance(m.get("data"), str) else m.get("data", {})
                        chat.agregar(d.get("content", ""))
            except Exception:
                time.sleep(5)
    threading.Thread(target=bucle, daemon=True, name=f"chat-kick-{canal}").start()


def youtube(url_video, chat):
    def bucle():
        try:
            from chat_downloader import ChatDownloader
            for m in ChatDownloader().get_chat(url_video, message_types=["text_message", "paid_message"]):
                if not chat.vivo:
                    break
                chat.agregar(m.get("message") or "")
        except Exception:
            pass
    threading.Thread(target=bucle, daemon=True, name="chat-youtube").start()
