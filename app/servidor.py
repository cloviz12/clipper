"""Servidor local de la app (solo 127.0.0.1): sirve la interfaz y hace lo que el navegador no debe hacer
(guardar la configuracion de esta PC y conectar las redes sin exponer secretos)."""
import base64
import hashlib
import json
import mimetypes
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

SCOPES_YT = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
LISTO_HTML = """<!doctype html><meta charset="utf-8"><title>CLIPPER</title>
<body style="background:#0b0c0f;color:#eceef3;font:16px system-ui;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center"><h2 style="color:%s">%s</h2><p>%s</p></div></body>"""


class Servidor:
    def __init__(self, puerto, ui, leer_config, guardar_config, reiniciar, estado, version, carpeta, al_mostrar=None, secretos=(), actualizador=None):
        self.puerto, self.ui = puerto, Path(ui)
        self.leer_config, self.guardar_config, self.reiniciar = leer_config, guardar_config, reiniciar
        self.estado, self.version, self.carpeta, self.al_mostrar = estado, version, carpeta, al_mostrar
        self.secretos = set(secretos)
        self.act = actualizador
        self.pendientes = {}   # state -> {red, verifier, t}

    # -------------------------------------------------------------- utilidades
    def redirect(self, red):
        return f"http://127.0.0.1:{self.puerto}/api/oauth/{red}/callback"

    def _admin(self):
        from supabase import create_client
        c = self.leer_config()
        return create_client(c["supabase_url"], c["supabase_service"])

    def miembro(self, token):
        if not token:
            return None
        try:
            db = self._admin()
            u = db.auth.get_user(token)
            email = (u.user.email or "").lower()
            r = db.table("miembros").select("email").eq("email", email).execute()
            return email if r.data else None
        except Exception:
            return None

    def unirse(self, token):
        """PC invitada: con la sesion del companero baja las llaves que el dueno dejo en el equipo."""
        c = self.leer_config()
        if not token or not c.get("supabase_url"):
            raise ValueError("Primero inicia sesión")
        r = requests.post(c["supabase_url"].rstrip("/") + "/rest/v1/rpc/config_del_equipo", json={}, timeout=30,
                          headers={"apikey": c["supabase_anon"], "Authorization": f"Bearer {token}"})
        if r.status_code == 404:
            raise ValueError("Falta preparar Supabase: tu compañero tiene que correr la migración "
                             "20261120000000_config_equipo.sql")
        r.raise_for_status()
        datos = r.json()
        if datos is None:
            raise ValueError("Tu correo todavía no está en el equipo. Pídele a tu compañero que lo agregue en "
                             "la pestaña Equipo y vuelve a intentar.")
        if not (datos or {}).get("supabase_service"):
            raise ValueError("Tu compañero todavía no ha compartido sus llaves. Pídele que abra CLIPPER "
                             "(versión nueva) una vez y vuelve a intentar.")
        self.guardar_config({k: v for k, v in datos.items() if isinstance(v, str)})

    def tiktok_creador(self):
        """Lo que TikTok exige mostrar antes de publicar: la cuenta, las privacidades que permite,
        si tiene apagados comentarios/duo/stitch y la duracion maxima."""
        db = self._admin()
        r = db.table("cuentas").select("datos").eq("plataforma", "tiktok").limit(1).execute()
        if not r.data:
            raise ValueError("TikTok no está conectado: conéctalo en la pestaña Cuentas")
        d = r.data[0]["datos"]
        if time.time() > d.get("expira", 0) - 300:
            c = self.leer_config()
            t = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=30, data={
                "client_key": c.get("tiktok_client_key", ""), "client_secret": c.get("tiktok_client_secret", ""),
                "grant_type": "refresh_token", "refresh_token": d["refresh_token"]}).json()
            if "access_token" not in t:
                raise ValueError("TikTok pidió volver a conectar la cuenta (pestaña Cuentas)")
            d.update(access_token=t["access_token"], refresh_token=t.get("refresh_token", d["refresh_token"]),
                     expira=time.time() + int(t.get("expires_in", 86400)))
            db.table("cuentas").update({"datos": d}).eq("plataforma", "tiktok").execute()
        info = requests.post("https://open.tiktokapis.com/v2/post/publish/creator_info/query/", timeout=30,
                             headers={"Authorization": f"Bearer {d['access_token']}",
                                      "Content-Type": "application/json; charset=UTF-8"}).json()
        err = info.get("error") or {}
        if err.get("code") not in (None, "ok"):
            if err.get("code") == "spam_risk_too_many_posts":
                raise ValueError("Esta cuenta llegó al límite de publicaciones de TikTok por hoy. Intenta mañana.")
            raise ValueError(f"TikTok: {err.get('message') or err.get('code')}")
        return info.get("data") or {}

    def guardar_cuenta(self, red, cuenta, datos):
        self._admin().table("cuentas").upsert({"plataforma": red, "cuenta": cuenta, "datos": datos,
                                               "conectado": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}).execute()

    # -------------------------------------------------------------- OAuth
    def iniciar_oauth(self, red):
        c = self.leer_config()
        state = secrets.token_urlsafe(16)
        verifier = secrets.token_urlsafe(48)
        if red == "youtube":
            if not c.get("google_client_id"):
                raise ValueError("Falta el Client ID de Google en 'Esta PC'")
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
                "client_id": c["google_client_id"], "redirect_uri": self.redirect(red), "response_type": "code",
                "scope": SCOPES_YT, "access_type": "offline", "prompt": "consent", "state": state,
                "code_challenge": challenge, "code_challenge_method": "S256"})
        elif red == "tiktok":
            if not c.get("tiktok_client_key"):
                raise ValueError("Falta el Client key de TikTok en 'Esta PC'")
            # TikTok de escritorio: PKCE con el hash SHA256 en hexadecimal
            challenge = hashlib.sha256(verifier.encode()).hexdigest()
            url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
                "client_key": c["tiktok_client_key"], "redirect_uri": self.redirect(red), "response_type": "code",
                "scope": "user.info.basic,video.upload,video.publish", "state": state,
                "code_challenge": challenge, "code_challenge_method": "S256"})
        else:
            raise ValueError("red desconocida")
        self.pendientes[state] = {"red": red, "verifier": verifier, "t": time.time()}
        webbrowser.open(url)

    def terminar_oauth(self, red, q):
        st = self.pendientes.pop(q.get("state", [""])[0], None)
        if not st or st["red"] != red or time.time() - st["t"] > 900:
            raise ValueError("La conexión venció. Vuelve a darle Conectar en CLIPPER.")
        if q.get("error"):
            raise ValueError(q.get("error_description", q["error"])[0])
        code = q["code"][0]
        c = self.leer_config()
        if red == "youtube":
            t = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
                "code": code, "client_id": c["google_client_id"], "client_secret": c.get("google_client_secret", ""),
                "redirect_uri": self.redirect(red), "grant_type": "authorization_code", "code_verifier": st["verifier"]}).json()
            if not t.get("refresh_token"):
                raise ValueError(f"Google no entregó acceso permanente: {t}")
            ch = requests.get("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true", timeout=30,
                              headers={"Authorization": f"Bearer {t['access_token']}"}).json()
            cuenta = (ch.get("items") or [{}])[0].get("snippet", {}).get("title", "canal de YouTube")
            self.guardar_cuenta(red, cuenta, {"access_token": t["access_token"], "refresh_token": t["refresh_token"],
                                              "expira": time.time() + int(t.get("expires_in", 3600))})
        else:
            t = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=30, data={
                "client_key": c["tiktok_client_key"], "client_secret": c.get("tiktok_client_secret", ""), "code": code,
                "grant_type": "authorization_code", "redirect_uri": self.redirect(red), "code_verifier": st["verifier"]}).json()
            if not t.get("access_token"):
                raise ValueError(f"TikTok no aceptó: {t}")
            u = requests.get("https://open.tiktokapis.com/v2/user/info/?fields=display_name", timeout=30,
                             headers={"Authorization": f"Bearer {t['access_token']}"}).json()
            cuenta = u.get("data", {}).get("user", {}).get("display_name", "cuenta de TikTok")
            self.guardar_cuenta(red, cuenta, {"access_token": t["access_token"], "refresh_token": t["refresh_token"],
                                              "open_id": t.get("open_id"), "expira": time.time() + int(t.get("expires_in", 86400))})
        return cuenta

    def instagram(self, ig_token):
        me = requests.get("https://graph.instagram.com/v21.0/me", timeout=30,
                          params={"fields": "user_id,username", "access_token": ig_token}).json()
        if not me.get("user_id") and not me.get("id"):
            raise ValueError(f"Instagram no aceptó el token: {me.get('error', {}).get('message', me)}")
        cuenta = "@" + me.get("username", "instagram")
        self.guardar_cuenta("instagram", cuenta, {"access_token": ig_token, "ig_user_id": me.get("user_id") or me.get("id"),
                                                  "renovado": 0})
        return cuenta

    # -------------------------------------------------------------- HTTP
    def arrancar(self):
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(b)

            def _html(self, code, html):
                b = html.encode()
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def _local_ok(self):
                return self.headers.get("X-Clipper") == "1" and \
                    self.headers.get("Host", "").split(":")[0] in ("127.0.0.1", "localhost")

            def do_GET(self):
                url = urllib.parse.urlparse(self.path)
                ruta = url.path
                if ruta.startswith("/api/oauth/") and ruta.endswith("/callback"):
                    red = ruta.split("/")[3]
                    try:
                        cuenta = srv.terminar_oauth(red, urllib.parse.parse_qs(url.query))
                        return self._html(200, LISTO_HTML % ("#c6ff3d", f"{red.title()} conectado", f"{cuenta}. Ya puedes cerrar esta pestaña y volver a CLIPPER."))
                    except Exception as e:
                        return self._html(400, LISTO_HTML % ("#ff4d5e", "No se pudo conectar", str(e)[:400]))
                if ruta.startswith("/api/"):
                    if not self._local_ok():
                        return self._json(403, {"error": "solo desde la app"})
                    c = srv.leer_config()
                    if ruta == "/api/config":
                        # configurado: ya sabe a que proyecto entrar. completo: ya tiene las llaves para trabajar
                        # (un invitado pega solo el codigo y recibe el resto al iniciar sesion)
                        return self._json(200, {"configurado": bool(c.get("supabase_url") and c.get("supabase_anon")),
                                                "completo": bool(c.get("supabase_service")),
                                                "supabase_url": c.get("supabase_url"), "supabase_anon": c.get("supabase_anon")})
                    if ruta == "/api/configuracion":
                        pub = {k: v for k, v in c.items() if k not in srv.secretos}
                        pub.update({f"{k}_guardada": bool(c.get(k)) for k in srv.secretos})
                        return self._json(200, pub)
                    if ruta == "/api/actualizacion":
                        return self._json(200, srv.act.estado if srv.act else {"mensaje": "sin actualizador"})
                    if ruta == "/api/motor":
                        return self._json(200, {"version": srv.version, "encendido": srv.estado.get("motor"),
                                                "error": srv.estado.get("error"), "carpeta": str(srv.carpeta)})
                    return self._json(404, {"error": "no existe"})
                # archivos de la interfaz
                rel = urllib.parse.unquote(ruta).lstrip("/") or "index.html"
                f = (srv.ui / rel).resolve()
                if srv.ui.resolve() not in f.parents and f != srv.ui.resolve():
                    return self._json(403, {"error": "ruta"})
                if f.is_dir():
                    f = f / "index.html"
                if not f.exists() and (srv.ui / (rel + ".html")).exists():
                    f = srv.ui / (rel + ".html")
                if not f.exists():
                    f = srv.ui / "index.html"
                b = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(str(f))[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_POST(self):
                if not self._local_ok():
                    return self._json(403, {"error": "solo desde la app"})
                ruta = urllib.parse.urlparse(self.path).path
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    datos = json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    datos = {}
                try:
                    if ruta == "/api/configuracion":
                        srv.guardar_config(datos)
                        threading.Timer(0.8, srv.reiniciar).start()
                        return self._json(200, {"ok": True})
                    if ruta == "/api/actualizacion/revisar":
                        if srv.act:
                            threading.Thread(target=srv.act.revisar, daemon=True).start()
                        return self._json(200, {"ok": True})
                    if ruta == "/api/github_token":
                        if not srv.miembro(datos.get("token")):
                            return self._json(403, {"error": "Tu sesión no es de un miembro del equipo"})
                        gt = (datos.get("github_token") or "").strip()
                        r = requests.get("https://api.github.com/repos/cloviz12/clipper", timeout=20,
                                         headers={"Authorization": f"Bearer {gt}", "User-Agent": "CLIPPER"})
                        if r.status_code != 200:
                            return self._json(400, {"error": f"GitHub no aceptó el token ({r.status_code})"})
                        srv._admin().table("secretos").upsert({"clave": "github_token", "valor": gt}).execute()
                        if srv.act:
                            srv.act.token_nuevo = gt
                            threading.Thread(target=srv.act.revisar, daemon=True).start()
                        return self._json(200, {"ok": True})
                    if ruta == "/api/unirse":
                        srv.unirse(datos.get("token"))
                        threading.Timer(0.8, srv.reiniciar).start()
                        return self._json(200, {"ok": True})
                    if ruta == "/api/mostrar":
                        if srv.al_mostrar:
                            srv.al_mostrar()
                        return self._json(200, {"ok": True})
                    if ruta.startswith("/api/oauth/"):
                        if not srv.miembro(datos.get("token")):
                            return self._json(403, {"error": "Tu sesión no es de un miembro del equipo"})
                        srv.iniciar_oauth(ruta.split("/")[3])
                        return self._json(200, {"ok": True})
                    if ruta == "/api/tiktok/creador":
                        if not srv.miembro(datos.get("token")):
                            return self._json(403, {"error": "Tu sesión no es de un miembro del equipo"})
                        return self._json(200, srv.tiktok_creador())
                    if ruta == "/api/instagram":
                        if not srv.miembro(datos.get("token")):
                            return self._json(403, {"error": "Tu sesión no es de un miembro del equipo"})
                        return self._json(200, {"cuenta": srv.instagram(datos.get("ig_token", ""))})
                except Exception as e:
                    return self._json(400, {"error": str(e)[:500]})
                return self._json(404, {"error": "no existe"})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.puerto), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="servidor").start()
