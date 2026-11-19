"""Probabilidad de que un clip se haga viral (0-100), juntando lo que paso EN EL STREAM con la IA:

- chat:     que parte del chat reacciono a lo mismo (risa, sorpresa, hype, todos hablando de algo)
- publico:  cuanta gente aparecio frente a lo normal de ESE canal y si la comunidad saco clips
- momento:  que tan raro fue el pico para ese streamer (percentil en su directo) y si el audio exploto
- ia:       el puntaje que le da la IA al clip como Short independiente

Cada parte va de 0 a 1. Las que no hay (un VOD sin chat, sin IA...) no cuentan: se reparte el peso
entre las que si hay. La risa y la sorpresa se comparten mas que el hype, por eso pesan un poco mas."""

PESOS = {"chat": 0.30, "publico": 0.20, "momento": 0.20, "ia": 0.30}
EXTRA_TIPO = {"risa": 1.15, "sorpresa": 1.12, "hype": 1.0, "clip": 1.05, "triste": 0.9}


def _c(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None


def senales_vivo(lect, gente_ahora, gente_tipica, rareza, z_audio, clips_comunidad=0):
    """Partes medidas en el directo. lect: reacciones.Lectura del momento."""
    chat = lect.consenso * EXTRA_TIPO.get(lect.tipo, 1.0) if lect.gente else None
    ratio = gente_ahora / max(1.0, gente_tipica)
    publico = min(1.0, max(0.0, (ratio - 1) / 2.5))           # 3.5x la gente normal = lleno
    if clips_comunidad:
        publico = max(publico, min(1.0, 0.45 + 0.15 * clips_comunidad))
    momento = 0.75 * rareza + 0.25 * min(1.0, max(0.0, z_audio / 3))
    return {"chat": _c(chat), "publico": _c(publico) if (gente_tipica or clips_comunidad) else None,
            "momento": _c(momento), "reaccion": lect.tipo if lect.frac_tipo >= 0.2 else None}


def calcular(senales, puntaje_ia=None, sirve=True):
    """senales: dict de senales_vivo (o lo que se sepa). Devuelve {'total', 'partes', 'nivel'}."""
    partes = {k: _c((senales or {}).get(k)) for k in ("chat", "publico", "momento")}
    partes["ia"] = _c(puntaje_ia / 100) if puntaje_ia is not None else None
    hay = {k: v for k, v in partes.items() if v is not None}
    if not hay:
        return None
    peso = sum(PESOS[k] for k in hay)
    total = sum(PESOS[k] * v for k, v in hay.items()) / peso
    # un clip que el chat y la IA aman a la vez es mucho mas probable que pegue
    if (hay.get("chat") or 0) >= 0.5 and (hay.get("ia") or 0) >= 0.7:
        total = min(1.0, total * 1.1)
    if sirve is False:
        total *= 0.6                                           # no se entiende solo: rara vez se comparte
    total = round(100 * total)
    return {"total": total, "partes": {k: (round(100 * v) if v is not None else None) for k, v in partes.items()},
            "nivel": "alta" if total >= 70 else "media" if total >= 45 else "baja",
            "reaccion": (senales or {}).get("reaccion")}
