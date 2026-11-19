"""Convierte un tramo crudo en un Short terminado y lo deja en el panel:
transcribe -> textos con IA -> encuadre por caras -> zooms/sacudidas/destellos -> subtitulos + hook ->
efectos de sonido -> render -> sube a Supabase y crea el clip (para revisar o publicar ya)."""
import random
import subprocess
import time
import uuid
from datetime import datetime, timezone

import numpy as np

from . import efectos, encuadre, ia, subtitulos, viralidad
from .fuentes import es_videojuego
from .base import FUENTES_TXT, TRABAJO, WORKER, ajustes, log, probe, run, sb, slug, tool


def _picos_audio(path, dur):
    sr = 8000
    p = subprocess.run([tool("ffmpeg"), "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                       capture_output=True)
    x = np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768
    paso = sr // 10
    n = len(x) // paso
    if n < 20:
        return []
    rms = np.array([np.sqrt(np.mean(x[i * paso:(i + 1) * paso] ** 2)) + 1e-6 for i in range(n)])
    db = 20 * np.log10(rms)
    umbral = np.mean(db) + 1.4 * np.std(db)
    out = []
    for i in range(3, n - 3):
        if db[i] > umbral and db[i] == db[i - 3:i + 4].max():
            out.append((i / 10, float((db[i] - umbral) / 6)))
    return out


def renderizar(src, ctx, carpeta=None):
    """ctx: canal, origen, url_fuente, titulo_fuente, pico (s dentro del tramo), puntaje, senales, chat,
    fuente (fila de fuentes o None), trabajo_id, plataformas, inicio, detectado_en."""
    aj = ajustes()
    cid = str(uuid.uuid4())
    nombre = f"{slug(ctx.get('canal'), 18)}_{cid[:8]}"
    t0 = time.time()
    info = probe(src)
    if not info["w"]:
        raise RuntimeError("el tramo no tiene video")

    # 1. que se dice (los nombres del canal/directo ayudan a Whisper a escribirlos bien)
    palabras, frases = ([], [])
    if info["audio"]:
        pista = f"{ctx.get('canal', '')}. {ctx.get('titulo_fuente', '')}"[:200]
        palabras, frases = subtitulos.transcribir(src, aj, ctx.get("idioma"), pista)

    # 2. arrancar sin relleno: si nadie habla al inicio, se recorta (salvo que el pico este ahi)
    corte = 0.0
    pico = ctx.get("pico")
    if palabras and palabras[0]["s"] > 0.9 and (pico is None or pico > palabras[0]["s"]):
        corte = round(palabras[0]["s"] - 0.3, 2)
        for w in palabras:
            w["s"] -= corte
            w["e"] -= corte
        for f in frases:
            f["t"] = max(0, f["t"] - corte)
        if pico is not None:
            pico -= corte
    dur = info["dur"] - corte

    # 3. textos y veredicto
    ctxia = dict(ctx, frases=frases, duracion=round(dur, 1), pico=pico)
    tx = ia.textos(ctxia, aj)
    palabras = ia.corregir(palabras, tx.get("correcciones"))

    # 4. encuadre y efectos
    plan = encuadre.planear(src, info, aj.get("formato", "auto"), es_videojuego(ctx.get("categoria")))
    rnd = random.Random(cid)
    ncam = efectos.INTENSIDAD.get(aj.get("efectos_camara", "medio"), 2)
    nsfx = efectos.INTENSIDAD.get(aj.get("efectos_sonido", "medio"), 2)
    picos = [(t - corte, v) for t, v in _picos_audio(src, info["dur"]) if t > corte]
    puntos = efectos.golpes(dur, pico, picos, palabras, ncam, rnd)
    hook = tx.get("hook") if aj.get("hook_en_pantalla", True) else None
    ass = TRABAJO / f"{nombre}.ass"
    estilo = subtitulos.escribir_ass(palabras, ass, aj, encuadre.zona_subtitulos(plan, info),
                                     f"@{ctx.get('canal')}" if aj.get("mostrar_credito", True) else None,
                                     hook, semilla=cid)
    sonidos = efectos.pistas_sonido(dur, puntos, 0.05 if hook else None, nsfx, rnd)

    # 5. render
    fps = min(60.0, info["fps"] or 30)
    letras = TRABAJO / "letras"
    if not letras.exists():
        import shutil
        shutil.copytree(FUENTES_TXT, letras)
    vf = (encuadre.filtro_base(plan, info) + ";" + efectos.filtro_camara(puntos, ncam) +
          f";[cam]fps={fps:.3f},ass={ass.name}:fontsdir=letras[v]")
    cmd = [tool("ffmpeg"), "-y", "-v", "error"]
    if corte:
        cmd += ["-ss", f"{corte}"]
    cmd += ["-i", str(src)]
    for f, _, _ in sonidos:
        cmd += ["-i", str(f)]
    af = []
    if info["audio"]:
        mezcla = ["[a0]"]
        af.append("[0:a]aresample=48000,aformat=channel_layouts=stereo[a0]")
        for i, (_, t, vol) in enumerate(sonidos, start=1):
            ms = int(t * 1000)
            af.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,volume={vol:.2f},adelay={ms}|{ms}[s{i}]")
            mezcla.append(f"[s{i}]")
        af.append(f"{''.join(mezcla)}amix=inputs={len(mezcla)}:normalize=0:duration=first,"
                  f"loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    salida = TRABAJO / f"{nombre}.mp4"
    cmd += ["-filter_complex", ";".join([vf] + af), "-map", "[v]"]
    if info["audio"]:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-maxrate", "9M", "-bufsize", "18M",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-t", f"{dur:.2f}", str(salida)]
    run(cmd, cwd=str(TRABAJO))
    mini = TRABAJO / f"{nombre}.jpg"
    run([tool("ffmpeg"), "-y", "-v", "error", "-ss", f"{max(0.5, (pico or dur / 2))}", "-i", str(salida),
         "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "4", str(mini)])

    # 6. guardar y avisar al panel
    dia = datetime.now().strftime("%Y-%m-%d")
    vpath, mpath = f"{dia}/{nombre}.mp4", f"{dia}/{nombre}.jpg"
    st = sb().storage.from_("clips")
    st.upload(vpath, salida.read_bytes(), {"content-type": "video/mp4", "upsert": "true"})
    st.upload(mpath, mini.read_bytes(), {"content-type": "image/jpeg", "upsert": "true"})

    canal = ctx.get("canal") or "canal"
    tags = list(dict.fromkeys([h if h.startswith("#") else "#" + h for h in (tx.get("hashtags") or [])] +
                              list(aj.get("hashtags_base", []))))[:7]
    credito = f"Clip de {canal} — {ctx.get('url_fuente', '')}".strip(" —")
    textos = {
        "youtube": {"titulo": tx["titulo_youtube"][:95], "descripcion": f"{tx['titulo_youtube']}\n\n{credito}\n\n{' '.join(tags)}"},
        "tiktok": {"caption": f"{tx['caption_tiktok']}\n\n{' '.join(tags[:5])}"},
        "instagram": {"caption": f"{tx['caption_instagram']}\n\n{credito}\n\n{' '.join(tags[:5])}"},
    }
    # probabilidad de viralidad: lo que paso en el stream (chat, publico, rareza del pico) + la IA
    senales_v = ctx.get("viral") or {"momento": ctx.get("puntaje")}
    viral = viralidad.calcular(senales_v, tx.get("puntaje"), tx.get("sirve", True))
    fuente = ctx.get("fuente") or {}
    auto = (fuente.get("publicacion") == "auto" or ctx.get("auto")) and tx.get("sirve", True) \
        and int(tx.get("puntaje", 0)) >= int(aj.get("auto_puntaje_minimo", 70))
    fila = {
        "id": cid, "fuente_id": fuente.get("id"), "trabajo_id": ctx.get("trabajo_id"), "canal": canal,
        "origen": ctx.get("origen"), "url_fuente": ctx.get("url_fuente"), "inicio": ctx.get("inicio"),
        "duracion": round(dur, 1), "puntaje": tx.get("puntaje"), "senales": ctx.get("senales") or [],
        "transcripcion": " ".join(f["texto"] for f in frases)[:4000], "hook": tx.get("hook"),
        "titulo": tx["titulo_youtube"][:95], "descripcion": textos["youtube"]["descripcion"], "textos": textos,
        "hashtags": tags, "ia": {"sirve": tx.get("sirve"), "razon": tx.get("razon"), "encuadre": plan["tipo"], "viralidad": viral,
                                 "categoria": ctx.get("categoria"),
                                 "letra": estilo["fuente"], "golpes": puntos, "sonidos": len(sonidos)},
        "video_path": vpath, "miniatura_path": mpath,
        "estado": "aprobado" if auto else "revisar",
        "plataformas": ctx.get("plataformas") or fuente.get("plataformas") or ["youtube", "tiktok", "instagram"],
        "detectado_en": ctx.get("detectado_en") or datetime.now(timezone.utc).isoformat(),
        "aprobado_por": f"auto ({WORKER})" if auto else None,
    }
    sb().table("clips").insert(fila).execute()
    for p in (ass, mini):
        p.unlink(missing_ok=True)
    if carpeta is None:
        salida.unlink(missing_ok=True)
    log(f"clip listo de {canal} en {time.time() - t0:.0f}s — {plan['tipo']}, {len(puntos)} golpes, "
        f"{len(sonidos)} sonidos — {'PUBLICANDO YA' if auto else 'para revisar'}"
        f"{f' (viralidad {viral["total"]}%)' if viral else ''}: {tx.get('hook')}",
        "clip", clip=cid)
    return cid
