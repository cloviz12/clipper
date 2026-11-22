"""Textos del clip (hook en pantalla, titulos, captions por red, hashtags) y veredicto de calidad.

Con ANTHROPIC_API_KEY en el .env los escribe Claude siguiendo las reglas de clips cortos:
- el clip tiene que entenderse solo (pensamiento completo, sin contexto previo) y tener gancho en 1-3 s
- el hook en pantalla se lee sin sonido, es VERDAD y lo paga el clip (nada de clickbait que no cumple)
- titulos de Shorts con palabras que la gente busca; captions nativos por red, no copiar y pegar
- 3 a 5 hashtags por red: el canal + nicho; nada de 30 hashtags genericos
Sin llave usa reglas simples."""
import json
import os
import re

import requests

from .base import log

SISTEMA = """Eres el editor de un canal de clips de streamers en espanol (Latinoamerica).
Recibes la transcripcion de un clip corto, el chat del momento y datos del directo.
Reglas:
1. Juzga si el clip se entiende SOLO: pensamiento completo, sin depender de algo que paso antes, y con un momento que paga (risa, sorpresa, jugada, frase fuerte).
2. El HOOK va escrito en pantalla los primeros 2-3 segundos: maximo 38 caracteres, en el tono del streamer, especifico, sin emojis, y tiene que ser VERDAD segun la transcripcion (abrir curiosidad, no mentir). Nunca inventes datos ni nombres que no esten.
3. titulo_youtube: maximo 70 caracteres, con el nombre del streamer y palabras que la gente buscaria; sin clickbait falso.
4. caption_tiktok y caption_instagram: 1-2 lineas naturales distintas entre si + pregunta corta que invite a comentar. Sin hashtags dentro.
5. hashtags: 4 o 5, siempre el del streamer, el del juego o tema si aplica y 2 de nicho; minusculas, con #.
6. correcciones: nombres propios o palabras que la transcripcion escribio mal (por el chat o el titulo del directo), como {"mal":"bien"}.
7. "reaccion_del_chat" dice como reacciono la gente en vivo (si se rio, se sorprendio o de que hablaban todos). Es la mejor pista de que es lo gracioso o fuerte del clip: usala para elegir el hook y el titulo (por ejemplo, si todos hablaban de "el gato", el hook va sobre eso). Si medio chat se rio, el clip casi seguro paga.
8. puntaje 0-100: que tan probable es que este clip funcione como Short independiente (que se vuelva viral). "fuerza_del_publico_0a1" dice que tanto exploto el chat y la gente frente a lo normal de ese canal; un chat chico (por ejemplo colombiano: "jsjsjs", "uy hp", "qué chimba") tambien cuenta si reacciono todo a la vez. Juzga sobre todo si se entiende sin contexto y si el momento paga.
Responde SOLO JSON con: sirve (bool), razon (corta), puntaje (int), hook, titulo_youtube, caption_tiktok, caption_instagram, hashtags (lista), correcciones (objeto)."""


def _heuristica(ctx):
    frases = [f["texto"] for f in ctx.get("frases", []) if len(f["texto"].split()) >= 3]
    canal = ctx.get("canal") or "streamer"
    base = frases[0] if frases else (ctx.get("titulo_fuente") or canal)
    hook = base.strip(" .,")
    if len(hook) > 38:
        hook = hook[:36].rsplit(" ", 1)[0] + "..."
    tag = "#" + re.sub(r"[^a-z0-9]", "", canal.lower())
    return {"sirve": True, "razon": "sin IA: textos automaticos", "puntaje": int(min(100, 40 + 40 * (ctx.get("puntaje") or 0))),
            "hook": hook, "titulo_youtube": f"{canal}: {base[:55]}".strip(),
            "caption_tiktok": f"{base[:120]}\n¿Qué hubieras hecho tú?",
            "caption_instagram": f"{canal} en directo: {base[:120]}\n¿Lo viste en vivo?",
            "hashtags": [tag], "correcciones": {}}


_aviso_sin_llave = []


def textos(ctx, aj):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        if not _aviso_sin_llave:                 # una vez por sesion: antes pasaba en silencio
            _aviso_sin_llave.append(True)
            log("sin llave de Claude: los hooks, titulos y descripciones salen con reglas simples "
                "(el hook es el inicio de lo que se dice). Ponla en Esta PC > Llave de Claude", "aviso")
        return _heuristica(ctx)
    usuario = json.dumps({
        "streamer": ctx.get("canal"), "titulo_del_directo": ctx.get("titulo_fuente"),
        "origen": ctx.get("origen"), "duracion_seg": ctx.get("duracion"),
        "transcripcion": [f"[{f['t']:.1f}s] {f['texto']}" for f in ctx.get("frases", [])][:60],
        "chat_en_ese_momento": ctx.get("chat", [])[:40],
        "reaccion_del_chat": ctx.get("reaccion_chat") or "",
        "senales": ctx.get("senales"), "segundo_del_pico": ctx.get("pico"),
        "categoria_del_directo": ctx.get("categoria"),
        "fuerza_del_publico_0a1": {k: v for k, v in (ctx.get("viral") or {}).items() if k != "reaccion"},
    }, ensure_ascii=False)
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=60, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": aj.get("ia_modelo", "claude-haiku-5-5"), "max_tokens": 900, "system": SISTEMA,
                  "messages": [{"role": "user", "content": usuario}]})
        r.raise_for_status()
        txt = "".join(b.get("text", "") for b in r.json().get("content", []))
        m = re.search(r"\{.*\}", txt, re.S)
        d = json.loads(m.group(0))
        base = _heuristica(ctx)
        base.update({k: v for k, v in d.items() if v not in (None, "")})
        base["hook"] = str(base["hook"])[:44]
        return base
    except Exception as e:
        log(f"IA no respondio, uso textos automaticos ({str(e)[:120]})", "aviso")
        return _heuristica(ctx)


def corregir(palabras, correcciones):
    if not correcciones:
        return palabras
    mapa = {k.lower(): v for k, v in correcciones.items() if isinstance(k, str) and isinstance(v, str) and " " not in k}
    for w in palabras:
        limpio = w["w"].strip(".,!?¡¿").lower()
        if limpio in mapa:
            w["w"] = w["w"].lower().replace(limpio, mapa[limpio])
    return palabras
