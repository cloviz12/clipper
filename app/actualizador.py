"""Actualizaciones automaticas desde GitHub Releases.

Cada vez que se mergea algo a main, GitHub construye una version nueva y la publica en Releases.
La app revisa cada 30 min, baja el instalador nuevo y lo instala en silencio cuando no hay ningun
clip editandose; despues se vuelve a abrir sola (en la bandeja si estaba asi)."""
import os
import re
import subprocess
import threading
import time
from pathlib import Path

import requests

REPO = os.environ.get("CLIPPER_REPO", "cloviz12/clipper")
CADA = 30 * 60


def _numeros(v):
    return tuple(int(x) for x in re.findall(r"\d+", (v or "").split("-")[0])[:3]) or (0,)


def es_mas_nueva(remota, local):
    a, b = _numeros(remota), _numeros(local)
    if a != b:
        return a > b
    return "-" in (local or "") and "-" not in (remota or "")   # 1.0.3 gana sobre 1.0.3-pr7


class Actualizador:
    def __init__(self, version, carpeta, token_fn, ocupado_fn, antes_de_salir, congelado):
        self.version = version
        self.dir = Path(carpeta) / "actualizacion"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.token_fn, self.ocupado_fn, self.antes_de_salir = token_fn, ocupado_fn, antes_de_salir
        self.congelado = congelado
        self.estado = {"version": version, "ultima": None, "mensaje": "sin revisar", "revisado": None, "descargada": None}
        self._lock = threading.Lock()
        self.token_nuevo = None

    def _headers(self, binario=False):
        h = {"Accept": "application/octet-stream" if binario else "application/vnd.github+json",
             "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "CLIPPER-actualizador"}
        tok = self.token_nuevo or self.token_fn()
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        return h

    def revisar(self, instalar=True):
        with self._lock:
            try:
                r = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest", headers=self._headers(), timeout=30)
                self.estado["revisado"] = time.time()
                if r.status_code == 404:
                    self.estado["mensaje"] = ("todavía no hay versiones publicadas" if (self.token_nuevo or self.token_fn())
                                              else "falta el token de GitHub (pestaña Esta PC)")
                    return self.estado
                if r.status_code in (401, 403):
                    self.estado["mensaje"] = "el token de GitHub no sirve o venció"
                    return self.estado
                r.raise_for_status()
                rel = r.json()
                remota = rel.get("tag_name", "").lstrip("v")
                self.estado["ultima"] = remota
                if not es_mas_nueva(remota, self.version):
                    self.estado["mensaje"] = "estás en la última versión"
                    return self.estado
                asset = next((a for a in rel.get("assets", []) if a["name"].lower().endswith(".exe")), None)
                if not asset:
                    self.estado["mensaje"] = f"la versión {remota} no trae instalador"
                    return self.estado
                destino = self.dir / asset["name"]
                if not destino.exists() or destino.stat().st_size != asset["size"]:
                    self.estado["mensaje"] = f"bajando la versión {remota}..."
                    tmp = destino.with_suffix(".parte")
                    with requests.get(asset["url"], headers=self._headers(binario=True), stream=True, timeout=60) as d:
                        d.raise_for_status()
                        with open(tmp, "wb") as f:
                            for b in d.iter_content(1 << 20):
                                f.write(b)
                    if tmp.stat().st_size != asset["size"]:
                        tmp.unlink(missing_ok=True)
                        raise RuntimeError("la descarga llegó incompleta")
                    tmp.replace(destino)
                for viejo in self.dir.glob("*.exe"):
                    if viejo != destino:
                        viejo.unlink(missing_ok=True)
                self.estado["descargada"] = remota
                self.estado["mensaje"] = f"versión {remota} lista para instalar"
                if instalar:
                    self._instalar_cuando_se_pueda(destino, remota)
            except Exception as e:
                self.estado["mensaje"] = f"no pude revisar: {str(e)[:160]}"
            return self.estado

    def _instalar_cuando_se_pueda(self, instalador, remota):
        if not self.congelado or os.name != "nt":
            self.estado["mensaje"] = f"versión {remota} lista (solo se instala sola en la app de Windows)"
            return
        espera = time.time()
        while self.ocupado_fn() and time.time() - espera < 3 * 3600:   # no cortar un clip a medias
            self.estado["mensaje"] = f"versión {remota}: se instala al terminar el clip que está editando"
            time.sleep(20)
        self.estado["mensaje"] = f"instalando la versión {remota}..."
        try:
            self.antes_de_salir()
        except Exception:
            pass
        subprocess.Popen([str(instalador), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"], close_fds=True, creationflags=0x00000008 | 0x00000200)
        os._exit(0)

    def arrancar(self):
        def bucle():
            time.sleep(60)
            while True:
                self.revisar()
                time.sleep(CADA)
        threading.Thread(target=bucle, daemon=True, name="actualizador").start()
