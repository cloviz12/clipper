"""Motor de CLIPPER. Corre solo, sin ventanas, en el PC o en un servidor:
- vigila los canales 'En vivo' del panel y corta los picos en tiempo real
- atiende los pedidos sueltos del panel
- edita (un clip a la vez, los directos primero) y publica lo aprobado"""
import queue
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from clipper import efectos, editor, fuentes as F, publicar
from clipper.base import TRABAJO, VERSION, WORKER, log, sb
from clipper.en_vivo import Monitor
from clipper.trabajos import Pedido

cola = queue.PriorityQueue()
monitores = {}
estado = {"editando": None}


def editar():
    while True:
        _, _, ctx = cola.get()
        arch = Path(ctx.pop("archivo"))
        estado["editando"] = ctx.get("canal")
        try:
            editor.renderizar(arch, ctx)
        except Exception as e:
            log(f"no pude editar el clip de {ctx.get('canal')}: {str(e)[:400]}", "error")
            traceback.print_exc()
            if ctx.get("trabajo_id"):
                fallos_por_trabajo.setdefault(ctx["trabajo_id"], []).append(str(e))
        finally:
            arch.unlink(missing_ok=True)
            estado["editando"] = None
            if ctx.get("trabajo_id"):
                _cerrar_trabajo_si_toca(ctx["trabajo_id"])


pendientes_por_trabajo = {}
totales_por_trabajo = {}
fallos_por_trabajo = {}


def _cerrar_trabajo_si_toca(tid):
    pendientes_por_trabajo[tid] = pendientes_por_trabajo.get(tid, 1) - 1
    if pendientes_por_trabajo[tid] > 0:
        return
    pendientes_por_trabajo.pop(tid, None)
    total = totales_por_trabajo.pop(tid, 0)
    fallos = fallos_por_trabajo.pop(tid, [])
    ahora = datetime.now(timezone.utc).isoformat()
    if fallos and len(fallos) >= max(total, 1):
        # no salio ningun clip: que se vea como error y no como "terminado"
        cambios = {"estado": "error", "terminado": ahora, "progreso": "no se pudo editar ningun clip",
                   "error": fallos[0][:500]}
    else:
        aviso = f" ({len(fallos)} de {total} fallaron)" if fallos else ""
        cambios = {"estado": "terminado", "terminado": ahora, "error": None,
                   "progreso": "listo: revisa los clips" + aviso}
    sb().table("trabajos").update(cambios).eq("id", tid).execute()


def pedidos():
    while True:
        try:
            r = sb().rpc("tomar_trabajo", {"p_worker": WORKER}).execute()
            if not r.data:
                time.sleep(4)
                continue
            t = r.data[0]

            def progreso(msg, tid=t["id"]):
                sb().table("trabajos").update({"progreso": msg[:300]}).eq("id", tid).execute()
            log(f"pedido: {t['url']}")
            n = Pedido(t, cola, progreso).ejecutar()
            if n == 0:
                sb().table("trabajos").update({"estado": "terminado", "progreso": "no habia momentos nuevos",
                                               "terminado": datetime.now(timezone.utc).isoformat()}).eq("id", t["id"]).execute()
            else:
                pendientes_por_trabajo[t["id"]] = pendientes_por_trabajo.get(t["id"], 0) + n
                totales_por_trabajo[t["id"]] = totales_por_trabajo.get(t["id"], 0) + n
                progreso(f"{n} momentos en edicion...")
        except Exception as e:
            log(f"pedido fallo: {str(e)[:400]}", "error")
            try:
                sb().table("trabajos").update({"estado": "error", "error": str(e)[:500]}).eq("id", t["id"]).execute()
            except Exception:
                pass
            time.sleep(3)


def vigilar_directos():
    ultimo_destacados = {}
    while True:
        try:
            fs = sb().table("fuentes").select("*").eq("activo", True).execute().data or []
            ids = {f["id"] for f in fs}
            for fid in list(monitores):
                m = monitores[fid]
                if fid not in ids or not m.is_alive():
                    m.parar()
                    del monitores[fid]
                    sb().rpc("soltar_fuente", {"p_id": fid, "p_worker": WORKER}).execute()
            for f in fs:
                ahora = datetime.now(timezone.utc).isoformat()
                if f["modo"] == "en_vivo":
                    if f["id"] in monitores:
                        monitores[f["id"]].f = f            # toma cambios de sensibilidad/modo al vuelo
                        sb().rpc("reclamar_fuente", {"p_id": f["id"], "p_worker": WORKER}).execute()
                        continue
                    # otra PC ya lo esta vigilando
                    if f.get("vigilado_por") and f["vigilado_por"] != WORKER and f.get("vigilado_hasta") \
                            and f["vigilado_hasta"] > ahora:
                        continue
                    inf = F.estado_directo(f["url"])
                    if not inf:
                        sb().table("fuentes").update({"en_vivo": False, "ultimo_chequeo": ahora}).eq("id", f["id"]).execute()
                        continue
                    if not sb().rpc("reclamar_fuente", {"p_id": f["id"], "p_worker": WORKER}).execute().data:
                        continue
                    sb().table("fuentes").update({"en_vivo": True, "ultimo_chequeo": ahora,
                                                  "titulo_directo": inf.get("title")}).eq("id", f["id"]).execute()
                    m = Monitor(f, cola, inf)
                    monitores[f["id"]] = m
                    m.start()
                else:  # destacados / videos: revisa cada X horas (solo la PC que lo reclame)
                    cada = float((f.get("opciones") or {}).get("cada_horas", 3)) * 3600
                    if time.time() - ultimo_destacados.get(f["id"], 0) > cada:
                        ultimo_destacados[f["id"]] = time.time()
                        ult = f.get("ultimo_chequeo")
                        if ult and (datetime.now(timezone.utc) - datetime.fromisoformat(ult.replace("Z", "+00:00"))).total_seconds() < cada:
                            continue
                        sb().table("fuentes").update({"ultimo_chequeo": ahora}).eq("id", f["id"]).execute()
                        sb().table("trabajos").insert({
                            "url": f["url"], "clips": int((f.get("opciones") or {}).get("clips", 3)),
                            "opciones": dict(f.get("opciones") or {}, rango="24h", ultimos=2,
                                             publicar=f["publicacion"], plataformas=f["plataformas"]),
                            "creado_por": "automatico"}).execute()
        except Exception as e:
            log(f"revisando canales: {str(e)[:300]}", "error")
        time.sleep(30)


def publicador():
    ultimo_limpio = 0
    while True:
        try:
            if not publicar.publicar_siguiente():
                time.sleep(5)
            if time.time() - ultimo_limpio > 3600:
                ultimo_limpio = time.time()
                publicar.limpiar()
                efectos.sincronizar_libreria()
        except Exception as e:
            log(f"publicador: {str(e)[:300]}", "error")
            time.sleep(10)


def latido():
    while True:
        try:
            sb().table("workers").upsert({"nombre": WORKER, "visto": datetime.now(timezone.utc).isoformat(),
                                          "version": VERSION, "estado": {
                                              "en_vivo": [m.canal for m in monitores.values()],
                                              "cola": cola.qsize(), "editando": estado["editando"]}}).execute()
        except Exception:
            pass
        time.sleep(15)


_arrancado = []


def arrancar():
    """Enciende el motor en hilos de fondo (lo usa la app de escritorio)."""
    if _arrancado:
        return
    _arrancado.append(True)
    import os
    from clipper.base import DATOS
    (DATOS / "motor.pid").write_text(str(os.getpid()))
    efectos.fabricar_base()
    efectos.sincronizar_libreria()
    for p in TRABAJO.glob("*.*"):
        if p.suffix in (".mp4", ".ts", ".part", ".ass", ".jpg", ".txt", ".webm", ".mkv", ".m4a"):
            p.unlink(missing_ok=True)
    log(f"motor {WORKER} encendido (v{VERSION})")
    for fn in (editar, pedidos, vigilar_directos, publicador, latido):
        threading.Thread(target=fn, daemon=True, name=fn.__name__).start()


def apagar():
    for fid, m in list(monitores.items()):
        m.parar()
        try:
            sb().rpc("soltar_fuente", {"p_id": fid, "p_worker": WORKER}).execute()
        except Exception:
            pass


def encendido():
    return bool(_arrancado)


if __name__ == "__main__":
    arrancar()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        apagar()
