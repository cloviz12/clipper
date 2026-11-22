"""Publica los clips aprobados en YouTube Shorts, TikTok e Instagram Reels.
Los accesos de cada red se conectan desde el panel (quedan en la tabla 'cuentas', que solo lee el motor)."""
import math
import os
import shutil
import time
from datetime import datetime, timezone

import requests

from .base import TRABAJO, WORKER, ajustes, log, sb

TT = "https://open.tiktokapis.com"


def _cuenta(plat):
    r = sb().table("cuentas").select("*").eq("plataforma", plat).limit(1).execute()
    return r.data[0] if r.data else None


def _guardar(plat, datos):
    sb().table("cuentas").update({"datos": datos}).eq("plataforma", plat).execute()


def conectadas():
    r = sb().table("cuentas").select("plataforma").execute()
    return [x["plataforma"] for x in r.data or []]


# ============================================================ YOUTUBE
def _yt_token(d):
    if time.time() < d.get("expira", 0) - 120:
        return d["access_token"]
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": d["refresh_token"], "grant_type": "refresh_token"}).json()
    if "access_token" not in r:
        raise RuntimeError(f"YouTube no renovo el acceso: {r}")
    d.update(access_token=r["access_token"], expira=time.time() + int(r.get("expires_in", 3600)))
    _guardar("youtube", d)
    return d["access_token"]


def subir_youtube(video, clip, aj):
    d = _cuenta("youtube")["datos"]
    tok = _yt_token(d)
    t = clip["textos"].get("youtube", {})
    titulo = (t.get("titulo") or clip.get("titulo") or "Clip")[:90]
    if "#shorts" not in titulo.lower():
        titulo = (titulo + " #Shorts")[:100]
    meta = {"snippet": {"title": titulo, "description": (t.get("descripcion") or "")[:4900],
                        "tags": [h.strip("#") for h in clip.get("hashtags") or []][:15],
                        "categoryId": str(aj.get("youtube_categoria", "20"))},
            "status": {"privacyStatus": aj.get("youtube_privacidad", "public"), "selfDeclaredMadeForKids": False}}
    size = video.stat().st_size
    ini = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                        json=meta, timeout=60, headers={"Authorization": f"Bearer {tok}", "X-Upload-Content-Type": "video/mp4",
                                                        "X-Upload-Content-Length": str(size)})
    if ini.status_code != 200:
        raise RuntimeError(f"YouTube: {ini.status_code} {ini.text[:300]}")
    with open(video, "rb") as f:
        r = requests.put(ini.headers["Location"], data=f, timeout=1800, headers={"Content-Type": "video/mp4"})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"YouTube rechazo el video: {r.status_code} {r.text[:300]}")
    vid = r.json()["id"]
    return {"id": vid, "url": f"https://youtube.com/shorts/{vid}"}


# ============================================================ TIKTOK
def _tt_token(d):
    if time.time() < d.get("expira", 0) - 300:
        return d["access_token"]
    r = requests.post(f"{TT}/v2/oauth/token/", timeout=30, data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token", "refresh_token": d["refresh_token"]}).json()
    if "access_token" not in r:
        raise RuntimeError(f"TikTok no renovo el acceso: {r}")
    d.update(access_token=r["access_token"], refresh_token=r.get("refresh_token", d["refresh_token"]),
             expira=time.time() + int(r.get("expires_in", 86400)))
    _guardar("tiktok", d)
    return d["access_token"]


def subir_tiktok(video, clip, aj, post=None):
    """post = lo que la persona confirmo en la pestana TikTok (privacidad, interacciones, divulgacion).
    Sin post se manda como borrador a la bandeja de TikTok (la persona termina de publicar en la app)."""
    d = _cuenta("tiktok")["datos"]
    H = {"Authorization": f"Bearer {_tt_token(d)}", "Content-Type": "application/json; charset=UTF-8"}
    size = video.stat().st_size
    chunk = size if size <= 64 * 1024 * 1024 else 10 * 1024 * 1024
    n = 1 if chunk == size else math.floor(size / chunk)
    src = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": n}
    if post:
        info = requests.post(f"{TT}/v2/post/publish/creator_info/query/", headers=H, timeout=30).json().get("data", {})
        if post.get("privacy_level") not in (info.get("privacy_level_options") or []):
            raise RuntimeError("la privacidad elegida ya no está disponible en la cuenta: vuelve a confirmarlo")
        r = requests.post(f"{TT}/v2/post/publish/video/init/", headers=H, timeout=60, json={
            "post_info": {"title": (post.get("title") or "")[:2200], "privacy_level": post["privacy_level"],
                          "disable_comment": bool(post.get("disable_comment", True) or info.get("comment_disabled")),
                          "disable_duet": bool(post.get("disable_duet", True) or info.get("duet_disabled")),
                          "disable_stitch": bool(post.get("disable_stitch", True) or info.get("stitch_disabled")),
                          "brand_content_toggle": bool(post.get("brand_content_toggle")),
                          "brand_organic_toggle": bool(post.get("brand_organic_toggle"))},
            "source_info": src}).json()
    else:
        r = requests.post(f"{TT}/v2/post/publish/inbox/video/init/", headers=H, json={"source_info": src}, timeout=60).json()
    if r.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok: {r['error']}")
    up, pid = r["data"]["upload_url"], r["data"]["publish_id"]
    with open(video, "rb") as f:
        for i in range(n):
            a = i * chunk
            b = size - 1 if i == n - 1 else a + chunk - 1
            f.seek(a)
            data = f.read(b - a + 1)
            rr = requests.put(up, data=data, timeout=600, headers={"Content-Type": "video/mp4", "Content-Length": str(len(data)),
                                                                   "Content-Range": f"bytes {a}-{b}/{size}"})
            if rr.status_code not in (200, 201, 206):
                raise RuntimeError(f"TikTok rechazo el archivo ({rr.status_code})")
    for _ in range(40):
        time.sleep(5)
        s = requests.post(f"{TT}/v2/post/publish/status/fetch/", headers=H, json={"publish_id": pid}, timeout=30).json()
        st = s.get("data", {}).get("status", "")
        if st in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            return {"id": pid, "estado": "publicado" if st == "PUBLISH_COMPLETE" else "en borradores de TikTok"}
        if st == "FAILED":
            raise RuntimeError(f"TikTok fallo: {s.get('data', {}).get('fail_reason')}")
    return {"id": pid, "estado": "procesando en TikTok"}


# ============================================================ INSTAGRAM
def subir_instagram(video, clip, aj):
    c = _cuenta("instagram")
    d = c["datos"]
    tok, uid = d["access_token"], d["ig_user_id"]
    if d.get("tipo") == "portfolio":      # token de usuario del sistema: otro servidor y no caduca
        host, ver = "https://graph.facebook.com", "v23.0"
    else:
        host, ver = "https://graph.instagram.com", "v21.0"
    if d.get("tipo") != "portfolio" and time.time() - d.get("renovado", 0) > 7 * 86400:
        r = requests.get(f"{host}/refresh_access_token", params={"grant_type": "ig_refresh_token", "access_token": tok}, timeout=30).json()
        if "access_token" in r:
            d.update(access_token=r["access_token"], renovado=time.time())
            _guardar("instagram", d)
            tok = d["access_token"]
    caption = (clip["textos"].get("instagram", {}).get("caption") or clip.get("titulo") or "")[:2200]
    errores = []
    log(f"instagram: se envia con descripcion de {len(caption)} caracteres", "info", clip=clip.get("id"))
    for modo in ("url", "subida"):
        try:
            cid = _ig_contenedor(modo, host, ver, uid, tok, caption, video, clip)
            if cid is None:
                continue
            res = _ig_publicar(host, ver, uid, tok, cid)
            _ig_verificar_descripcion(host, ver, tok, res["id"], caption, clip)
            return res
        except Exception as e:
            errores.append(f"{modo}: {str(e)[:250]}")
            log(f"instagram ({modo}) fallo, {'pruebo otra forma' if modo == 'url' else 'sin mas intentos'}: {str(e)[:200]}", "aviso")
    raise RuntimeError("Instagram no publico. " + " | ".join(errores))


def _url_firmada(clip):
    """URL temporal del video en el almacenamiento, para que Meta lo descargue."""
    path = clip.get("video_path")
    if not path:
        return None
    r = sb().storage.from_("clips").create_signed_url(path, 3600)
    u = r.get("signedURL") or r.get("signedUrl")
    if u and u.startswith("/"):
        u = os.environ["SUPABASE_URL"].rstrip("/") + "/storage/v1" + u
    return u


def _ig_contenedor(modo, host, ver, uid, tok, caption, video, clip):
    """Crea el contenedor del Reel. modo 'url': Meta baja el video de una URL temporal (lo habitual).
    modo 'subida': se sube el archivo directo. Devuelve el id del contenedor ya procesado, o None si no aplica."""
    datos = {"media_type": "REELS", "caption": caption, "share_to_feed": "true", "access_token": tok}
    if modo == "url":
        url = _url_firmada(clip)
        if not url:
            return None
        datos["video_url"] = url
    else:
        datos["upload_type"] = "resumable"
    r = requests.post(f"{host}/{ver}/{uid}/media", timeout=60, data=datos).json()
    if "id" not in r:
        raise RuntimeError(f"no se creo el contenedor: {r}")
    cid = r["id"]
    if modo == "subida":
        up = r.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{ver}/{cid}"
        with open(video, "rb") as f:
            rr = requests.post(up, data=f, timeout=900, headers={"Authorization": f"OAuth {tok}", "offset": "0",
                                                                 "file_size": str(video.stat().st_size)})
        if rr.status_code != 200:
            raise RuntimeError(f"Instagram rechazo el archivo ({rr.status_code}): {rr.text[:200]}")
    for _ in range(60):
        time.sleep(6)
        s = requests.get(f"{host}/{ver}/{cid}", params={"fields": "status_code,status", "access_token": tok}, timeout=30).json()
        if s.get("status_code") == "FINISHED":
            return cid
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram no proceso el video: {s.get('status')}")
    raise RuntimeError("Instagram tardo demasiado en procesar el video")


def _ig_verificar_descripcion(host, ver, tok, media_id, caption, clip):
    """Despues de publicar, le pregunta a Instagram que descripcion quedo, y lo avisa si llego vacia."""
    try:
        r = requests.get(f"{host}/{ver}/{media_id}", params={"fields": "caption", "access_token": tok}, timeout=30).json()
        quedo = (r.get("caption") or "").strip()
        if caption.strip() and not quedo:
            log(f"instagram: se envio la descripcion ({len(caption)} caracteres) pero el Reel quedo SIN descripcion "
                f"(respuesta: {str(r)[:150]})", "aviso", clip=clip.get("id"))
        else:
            log(f"instagram: descripcion publicada ({len(quedo)} caracteres)", "info", clip=clip.get("id"))
    except Exception as e:
        log(f"instagram: no pude verificar la descripcion ({str(e)[:100]})", "info", clip=clip.get("id"))


def _ig_publicar(host, ver, uid, tok, cid):
    p = requests.post(f"{host}/{ver}/{uid}/media_publish", data={"creation_id": cid, "access_token": tok}, timeout=60).json()
    if "id" not in p:
        raise RuntimeError(f"Instagram no publico: {p}")
    return {"id": p["id"]}


SUBIDORES = {"youtube": subir_youtube, "tiktok": subir_tiktok, "instagram": subir_instagram}


def _archivo(clip):
    """Baja el video del clip a la carpeta de trabajo. Se escribe como .part y se renombra al terminar:
    si la descarga o la escritura se corta, no queda un archivo a medias que se reutilice despues
    (las redes lo rechazan: 'Request processing failed')."""
    local = TRABAJO / clip["video_path"].split("/")[-1]
    if local.exists():
        return local
    parcial = local.with_name(local.name + ".part")
    try:
        parcial.write_bytes(sb().storage.from_("clips").download(clip["video_path"]))
        parcial.replace(local)
    except OSError as e:
        parcial.unlink(missing_ok=True)
        try:
            libre = f"{shutil.disk_usage(TRABAJO).free / 1e9:.1f} GB libres"
        except Exception:
            libre = "espacio libre desconocido"
        raise RuntimeError(f"no pude guardar el video en {TRABAJO} ({libre}): {e}") from e
    return local


# Cuando una red dice que se llego a su limite diario, se deja de intentar un rato en vez de gastar cada clip
# (y de insistirle a la red, que puede tomarlo como spam): palabras del error -> horas de pausa
LIMITES = {
    "youtube": (("exceeded the number of videos", "uploadlimitexceeded", "quota exceeded", "quotaexceeded"), 6),
    "instagram": (("2207042", "too many actions", "reached the maximum"), 6),
    "tiktok": (("spam_risk", "too_many_pending"), 3),    # demasiados borradores sin terminar en la app de TikTok
}
_pausa = {}


def _pausada(red):
    return _pausa.get(red, 0) > time.time()


def _limite(red, mensaje):
    """Horas de pausa si el error de esta red es un limite diario; 0 si es otro tipo de error."""
    palabras, horas = LIMITES.get(red, ((), 0))
    m = mensaje.lower()
    return horas if any(w in m for w in palabras) else 0


def _estado_espera(clip):
    """Estado al que vuelve un clip que no se pudo publicar por una pausa: sigue esperando su turno."""
    return "programado" if clip.get("publicar_en") else "aprobado"


def publicar_siguiente():
    r = sb().rpc("tomar_clip_para_publicar", {"p_worker": WORKER}).execute()
    if not r.data:
        return False
    clip = r.data[0]
    aj = ajustes()
    activas = conectadas()
    plats = [p for p in clip.get("plataformas") or [] if p in activas]
    pubs, errs = dict(clip.get("publicaciones") or {}), dict(clip.get("errores") or {})
    if not plats:
        sb().table("clips").update({"estado": "error", "errores": {"general": "no hay redes conectadas para este clip"}}).eq("id", clip["id"]).execute()
        log("no hay redes conectadas: conecta las cuentas en el panel", "error")
        return True
    pausadas = [p for p in plats if _pausada(p) and p not in pubs]
    plats = [p for p in plats if p not in pubs and p not in pausadas]
    if not plats and pausadas:
        # todas sus redes estan en pausa por limite: el clip espera, sin descargar nada ni gastar intentos
        sb().table("clips").update({"estado": _estado_espera(clip)}).eq("id", clip["id"]).execute()
        time.sleep(25)
        return False
    # TikTok directo: TikTok exige que una persona confirme cada video. Queda esperando en la pestana TikTok
    esperando_tt = False
    if "tiktok" in plats and aj.get("tiktok_modo", "borrador") == "directo":
        plats.remove("tiktok")
        if not clip.get("tiktok"):
            sb().table("clips").update({"tiktok": {"estado": "esperando"}}).eq("id", clip["id"]).execute()
            log(f"TikTok: '{clip.get('hook') or clip.get('titulo')}' espera confirmación en la pestaña TikTok", "info",
                clip=clip["id"])
        esperando_tt = True
    if not plats:
        # solo faltaba TikTok: queda 'programado' sin hora hasta que se confirme
        sb().table("clips").update({"estado": "programado", "publicar_en": None}).eq("id", clip["id"]).execute()
        return True
    video = _archivo(clip)
    for p in plats:
        if p in pubs:
            continue
        try:
            pubs[p] = SUBIDORES[p](video, clip, aj)
            pubs[p]["cuando"] = datetime.now(timezone.utc).isoformat()
            errs.pop(p, None)
            log(f"publicado en {p}: {clip.get('hook') or clip.get('titulo')}", "publicado", clip=clip["id"])
        except Exception as e:
            errs[p] = str(e)[:500]
            log(f"{p}: no se pudo publicar ({str(e)[:200]})", "error", clip=clip["id"])
            horas = _limite(p, str(e))
            if horas:
                _pausa[p] = time.time() + horas * 3600
                pausadas.append(p)
                log(f"{p}: llego a su limite diario; no se intenta de nuevo en {horas} h y estos clips esperan", "aviso")
    estado = "publicado" if pubs else "error"
    if esperando_tt and not pubs:
        estado = "programado"
    if any(p not in pubs for p in pausadas):
        estado = _estado_espera(clip)         # le falta una red en pausa: sigue en la cola para cuando se libere
    sb().table("clips").update({"estado": estado, "publicaciones": pubs, "errores": errs}).eq("id", clip["id"]).execute()
    video.unlink(missing_ok=True)
    return True


def publicar_tiktok_programado():
    """Publica en TikTok el siguiente clip confirmado cuya hora ya llego."""
    if "tiktok" not in conectadas():
        return False
    r = sb().rpc("tomar_tiktok", {"p_worker": WORKER}).execute()
    if not r.data:
        return False
    clip = r.data[0]
    tt = dict(clip.get("tiktok") or {})
    pubs, errs = dict(clip.get("publicaciones") or {}), dict(clip.get("errores") or {})
    video = None
    try:
        video = _archivo(clip)
        res = subir_tiktok(video, clip, ajustes(), tt.get("post") or {})
        res["cuando"] = datetime.now(timezone.utc).isoformat()
        pubs["tiktok"] = res
        errs.pop("tiktok", None)
        tt.update(estado="publicado", resultado=res.get("estado"))
        log(f"publicado en tiktok: {clip.get('hook') or clip.get('titulo')}", "publicado", clip=clip["id"])
    except Exception as e:
        errs["tiktok"] = str(e)[:500]
        tt.update(estado="error", error=str(e)[:300])
        log(f"tiktok: no se pudo publicar ({str(e)[:200]})", "error", clip=clip["id"])
    cambios = {"tiktok": tt, "publicaciones": pubs, "errores": errs}
    if clip.get("estado") in ("programado", "publicando") and not clip.get("publicar_en"):
        cambios["estado"] = "publicado" if pubs else "error"
    sb().table("clips").update(cambios).eq("id", clip["id"]).execute()
    if video:
        video.unlink(missing_ok=True)
    return True


def _borrar_videos(clips):
    """Quita de la nube el video y la miniatura de estos clips y limpia las rutas."""
    rutas = [r for c in clips for r in (c.get("video_path"), c.get("miniatura_path")) if r]
    if rutas:
        sb().storage.from_("clips").remove(rutas)
    for c in clips:
        sb().table("clips").update({"video_path": None, "miniatura_path": None}).eq("id", c["id"]).execute()


def limpiar():
    """Libera espacio en la nube (el plan gratis tiene 1 GB):
    - sin revisar: solo se conservan los mas nuevos (Ajustes: maximo de clips por revisar)
    - descartados: se borra el video apenas se descartan
    - publicados: se borra a los N dias (Ajustes), salvo los que siguen esperando TikTok"""
    # los clips sin revisar se acumulaban sin limite y llenaban el almacenamiento: se queda el tope mas nuevo
    tope = int(ajustes().get("max_clips_revisar", 40))
    if tope > 0:
        r = sb().table("clips").select("id").eq("estado", "revisar").order("creado", desc=True) \
            .range(tope, tope + 499).execute()
        viejos = [c["id"] for c in r.data or []]
        if viejos:
            sb().table("clips").update({"estado": "descartado"}).in_("id", viejos).execute()
            log(f"almacenamiento: se descartaron {len(viejos)} clips viejos sin revisar (maximo {tope}; se cambia en Ajustes)", "aviso")
    for _ in range(10):                      # por tandas, hasta vaciar los descartados
        r = sb().table("clips").select("id,video_path,miniatura_path").eq("estado", "descartado") \
            .not_.is_("video_path", "null").limit(100).execute()
        if not r.data:
            break
        _borrar_videos(r.data)
    dias = int(ajustes().get("dias_guardar_videos", 3))
    limite = datetime.fromtimestamp(time.time() - dias * 86400, timezone.utc).isoformat()
    r = sb().table("clips").select("id,video_path,miniatura_path,tiktok").eq("estado", "publicado") \
        .lt("creado", limite).not_.is_("video_path", "null").limit(100).execute()
    viejos = [c for c in r.data or []
              if (c.get("tiktok") or {}).get("estado") not in ("esperando", "programado", "publicando")]
    if viejos:
        _borrar_videos(viejos)
