"""Combina las senales y escoge las ventanas (clips) con mas 'momento'."""
import numpy as np

PESOS = {"heatmap": 1.0, "chat": 0.9, "audio": 0.6, "palabras": 0.45}


def _norm(s):
    s = np.asarray(s, dtype=float)
    lo, hi = np.percentile(s, 50), np.percentile(s, 99.5)
    if hi - lo < 1e-9:
        return np.zeros_like(s)
    return np.clip((s - lo) / (hi - lo), 0, 1.5)


def _suave(s, sigma=4):
    r = int(sigma * 3)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    return np.convolve(np.pad(s, r, mode="edge"), k, mode="valid")


def combinar(senales, dur):
    n = int(dur) + 1
    total = np.zeros(n)
    usadas = []
    for nombre, s in senales.items():
        if s is None or len(s) == 0 or np.max(s) <= 0:
            continue
        s = np.resize(np.asarray(s, float), n) if len(s) != n else np.asarray(s, float)
        total += PESOS.get(nombre, 0.5) * _norm(_suave(s, 2 if nombre == "heatmap" else 4))
        usadas.append(nombre)
    return _suave(total, 3), usadas


def _ajustar(t, cues, lado, holgura):
    """Mueve un corte al inicio/fin de una frase cercana para no cortar a mitad de palabra."""
    if not cues:
        return t
    mejores = [c[0] if lado == "ini" else c[1] for c in cues]
    cerca = [x for x in mejores if abs(x - t) <= holgura]
    return min(cerca, key=lambda x: abs(x - t)) if cerca else t


def escoger(score, dur, n, lmin, lmax, cues=None, evitar_inicio=None):
    """Devuelve [(inicio, fin, puntaje)] sin solaparse, de mejor a peor."""
    s = score.copy()
    L = (lmin + lmax) / 2
    ev = evitar_inicio if evitar_inicio is not None else min(30, dur * 0.04)
    s[: int(ev)] = 0                       # el arranque siempre sale "visto"; no cuenta
    s[max(0, int(dur - 5)):] = 0
    if s.max() <= 0:
        return []
    piso = s.max() * 0.22
    out = []
    while len(out) < n:
        p = int(np.argmax(s))
        if s[p] <= piso:
            break
        # extiende mientras siga habiendo accion, entre lmin y lmax
        a, b = p - L * 0.4, p + L * 0.6
        umbral = s[p] * 0.45
        while b - a < lmax and b < dur - 1 and s[min(int(b) + 1, len(s) - 1)] > umbral:
            b += 1
        while b - a < lmax and a > 1 and s[max(int(a) - 1, 0)] > umbral:
            a -= 1
        a, b = max(0.0, a), min(float(dur), b)
        if b - a < lmin:
            falta = lmin - (b - a)
            a, b = max(0.0, a - falta * 0.4), min(float(dur), b + falta * 0.6)
        a = _ajustar(a, cues, "ini", 3)
        b = _ajustar(b, cues, "fin", 3)
        b = min(b, a + lmax)
        val = float(score[int(a):int(b) + 1].mean()) if b > a else 0
        out.append((round(a, 1), round(b, 1), round(val, 3)))
        s[max(0, int(a - L * 0.5)): int(b + L * 0.5) + 1] = 0
    return out
