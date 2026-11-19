"""Lee el chat como lo leeria una persona: no cuenta mensajes, cuenta GENTE reaccionando a lo mismo.

Un momento es entretenido cuando muchos espectadores distintos, a la vez:
- se rien (KEKW, jajaja, xd, LUL, ICANT...)
- se sorprenden o se emocionan (WTF, Pog, NOOO, QUEEE, GOOOL, ???)
- o hablan de una misma cosa (todos escriben "penal", "el gato", "F", "clip"...)

Lo que NO es un momento: un raid saludando, alguien haciendo spam solo, bots, comandos (!discord),
gente pidiendo cosas o saludando. Por eso:
- cada persona cuenta UNA vez por ventana (el spam de uno solo no infla nada)
- se ignoran bots y comandos
- un tema cuenta solo si se dispara frente a lo normal del directo y no es un saludo"""
import re
import unicodedata
from collections import Counter, defaultdict

BOTS = {"nightbot", "streamelements", "streamlabs", "moobot", "fossabot", "wizebot", "botrixoficial",
        "kicklet", "sery_bot", "soundalerts", "commanderroot", "streamstickers", "pokemoncommunitygame",
        "kofistreambot", "tangiabot", "blerp", "own3d", "deepbot", "coebot", "phantombot"}

TIPOS = {
    "risa": re.compile(
        r"(kekw|lul\w*|omegalul|icant|lmao+|lmfao|rofl|xd+|jsjs\w*|jaja\w*|jeje\w*|jiji\w*|ajaj\w*|haha\w*|"
        r"jajs\w*|kek\b|pffs?t|muero|me mue+ro|me ca(i|igo) de risa|ctm+|😂|🤣|💀|kappa|4head|pepelaugh|aware|"
        r"\bwkwk\w*|\bkkk+)"),
    "sorpresa": re.compile(
        r"(wtf+|\bque{3,}|\bqu[eé] (pas[oó]|fue eso|carajo|verga)|\bqu[eé]+\?+|no+ ?ma(m|ms)es|nooo+|omg+|pog\w*|monka\w*|"
        r"wow+|\?{2,}|ah+ ?re+|c[oó]mo+\?+|o+ ?h+ ?no+|dios m[ií]o|asust|susto|que miedo|😱|😳|🤯|🫢|holy|"
        r"insane|no puede ser|naaa+|bro+ ?what)"),
    "hype": re.compile(
        r"(go+l+|vamo+s?|lets go+|let'?s go+|ez+\b|clutch|godlike|bestia|crack|grande+|tremend|epic[oa]|"
        r"\bw+\b|\bgg+\b|🔥|💪|🐐|goat|si+u+|aguante|toma+|po+g+|ole+|bien+ ?ah[ií])"),
    "triste": re.compile(r"(\bf+\b|sadge|rip+\b|nooo+ ?(por|porque)|que pena|pobre+|😢|😭|💔|biblethump|\bl\b)"),
    "clip": re.compile(r"(\bclip+\b|clipea|clipeen|clipealo|clip it|clipp?ed|alguien clip)"),
}
# lo que no hace a un clip aunque lo escriba todo el chat
NO_TEMA = set("""
hola holi holaa buenas buenos dias tardes noches saludos saludo bienvenido bienvenida bienvenidos gracias raid
sub subs prime follow seguir sigueme hello hi hey bro wey we pana parce che boludo amigo amigos gente chat
que con por para los las una uno del pero como mas muy ese esa eso esto este esta aqui ahi alla ya si no
the and you that this for what with have are was just like lol
jaja jajaja xd kekw lul pog wtf omg clip gg ez w f l mames mame verga carajo chingado
""".split())
VACIAS = set("""
a al de el en es la le lo me mi mis se su sus te tu tus y o u un e ni yo vos que q k xq pq porq porque
cuando donde quien cual hay ser fue era son estan esta estoy tiene tengo hace hizo voy va van
desde hasta sobre todo todos toda nada algo solo ahora aca alguien otro otra tambien asi entonces
mexico argentina chile peru colombia espana venezuela ecuador uruguay bolivia
""".split())

PALABRA = re.compile(r"[a-z0-9ñ]+|[\U0001F300-\U0001FAFF]")


def _limpiar(texto):
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c) or c == "̃")
    return unicodedata.normalize("NFC", t)


def _corta(w):
    """'goooool' -> 'gol', 'siiiii' -> 'si': las letras estiradas son la misma palabra."""
    return re.sub(r"(.)\1{2,}", r"\1", w) if not w.isdigit() else w


def tipos_de(texto):
    t = _limpiar(texto)
    return {k for k, rx in TIPOS.items() if rx.search(t)}


def palabras_de(texto):
    vistas = set()
    for w in PALABRA.findall(_limpiar(texto)):
        w = _corta(w)
        if len(w) < 3 and not (len(w) == 1 and ord(w) > 0x2000):
            continue
        if w in VACIAS or w.isdigit():
            continue
        vistas.add(w)
    return vistas


def valido(usuario, texto):
    u = (usuario or "").lower().lstrip("@")
    t = (texto or "").strip()
    return bool(t) and u not in BOTS and not t.startswith("!") and not u.endswith("bot")


def preparar(t, usuario, texto):
    """Analiza un mensaje UNA vez: (t, usuario, tipos, palabras) o None si es de un bot o un comando."""
    if not valido(usuario, texto):
        return None
    return (t, (usuario or "?").lower().lstrip("@"), frozenset(tipos_de(texto)), frozenset(palabras_de(texto)))


def _por_usuario(mensajes):
    out = defaultdict(lambda: [set(), set()])
    for _, u, tp, pal in mensajes:
        out[u][0] |= tp
        out[u][1] |= pal
    return out


def palabras_normales(mensajes):
    """(gente, Counter palabra->gente) de un tramo 'normal' del directo."""
    pu = _por_usuario(mensajes)
    return max(1, len(pu)), Counter(w for _, pal in pu.values() for w in pal)


class Lectura:
    """Lo que paso en el chat en una ventana."""

    def __init__(self, gente=0, tipo=None, frac_tipo=0.0, tema=None, frac_tema=0.0, por_tipo=None):
        self.gente = gente                # personas distintas que escribieron
        self.tipo = tipo                  # reaccion dominante: risa / sorpresa / hype / triste / clip
        self.frac_tipo = frac_tipo        # que parte de esa gente reacciono asi
        self.tema = tema                  # palabra que todos repiten (si es un disparo real)
        self.frac_tema = frac_tema
        self.por_tipo = por_tipo or {}

    @property
    def consenso(self):
        """0..1: que tan de acuerdo esta el chat en lo que siente o de lo que habla."""
        if self.gente < 4:
            return 0.0
        r = self.frac_tipo * (1.15 if self.tipo == "risa" else 1.0)
        return min(1.0, max(r, self.frac_tema * 1.1))

    def etiquetas(self):
        out = []
        if self.tipo and self.frac_tipo >= 0.25:
            out.append(f"chat: {self.tipo} ({int(self.frac_tipo * 100)}%)")
        if self.tema and self.frac_tema >= 0.2:
            out.append(f"chat habla de «{self.tema}»")
        return out

    def describir(self):
        """Frase para la IA: que le paso al chat en ese momento."""
        partes = []
        if self.tipo and self.frac_tipo >= 0.2:
            nombre = {"risa": "se rio", "sorpresa": "reacciono sorprendido", "hype": "exploto de emocion",
                      "triste": "se lamento", "clip": "pidio clip"}[self.tipo]
            partes.append(f"el {int(self.frac_tipo * 100)}% de {self.gente} personas en el chat {nombre}")
        if self.tema and self.frac_tema >= 0.2:
            partes.append(f"el {int(self.frac_tema * 100)}% hablaba de '{self.tema}'")
        return "; ".join(partes)


def leer(mensajes, normal=None):
    """mensajes: preparados (ver preparar) de la ventana. normal: palabras_normales() de lo de antes,
    para saber si una palabra es un disparo o algo que siempre se escribe en ese chat."""
    pu = _por_usuario(m for m in mensajes if m)
    gente = len(pu)
    if not gente:
        return Lectura()
    cuenta_tipo = Counter(t for tp, _ in pu.values() for t in tp)
    por_tipo = {k: v / gente for k, v in cuenta_tipo.items()}
    tipo, frac_tipo = max(por_tipo.items(), key=lambda kv: kv[1]) if por_tipo else (None, 0.0)

    gente_base, cuenta_base = normal or (1, Counter())
    tema, frac_tema = None, 0.0
    for w, c in Counter(w for _, pal in pu.values() for w in pal).most_common(8):
        if c < 3 or w in NO_TEMA or tipos_de(w):        # 'jajaja' ya cuenta como risa, no como tema
            continue
        f = c / gente
        if f >= 0.2 and f > 3 * cuenta_base.get(w, 0) / gente_base + 0.05:   # se disparo ahora
            tema, frac_tema = w, f
            break
    return Lectura(gente, tipo, frac_tipo, tema, frac_tema, por_tipo)


def serie(mensajes, dur, ventana=8):
    """Para videos ya terminados: puntaje por segundo = gente distinta x que tan de acuerdo esta.
    mensajes: preparados, con t en segundos del video."""
    import numpy as np
    n = int(dur) + 1
    por_seg = defaultdict(list)
    for m in mensajes:
        if m and 0 <= m[0] <= dur:
            por_seg[int(m[0])].append(m)
    gente = np.zeros(n)
    consenso = np.zeros(n)
    bloques = {}                                          # lo normal, en bloques de 30 s
    for i in range(0, n, 4):
        vent = [m for j in range(i, min(n, i + ventana)) for m in por_seg.get(j, [])]
        gente[i:i + 4] = len({m[1] for m in vent})       # una persona cuenta una vez: el spam no infla
        if len(vent) < 4:
            continue
        b0 = (i // 30) * 30
        clave = b0
        if clave not in bloques:
            bloques[clave] = palabras_normales([m for j in range(max(0, b0 - 300), b0) for m in por_seg.get(j, [])])
        consenso[i:i + 4] = leer(vent, bloques[clave]).consenso
    return gente * (0.6 + 1.6 * consenso)
