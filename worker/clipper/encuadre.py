"""Decide el mejor encuadre vertical mirando las caras del clip:
- 'split'  : videojuego con facecam -> camara arriba + juego abajo. El recuadro de la camara se busca
             por sus bordes reales (el marco no se mueve y el juego si), asi no entra juego en la camara
             ni la camara en el juego
- 'seguir' : camara grande (IRL / charla) -> recorte 9:16 que sigue la cara
- 'blur'   : sin caras -> video completo sobre fondo desenfocado
- 'vertical': el video ya es vertical"""
import subprocess
import urllib.request

import numpy as np

from .base import MODELOS, tool

YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
_det = {}


def _detector(w, h):
    import cv2
    m = MODELOS / "yunet.onnx"
    if not m.exists():
        try:
            urllib.request.urlretrieve(YUNET_URL, m)
        except Exception:
            pass
    if m.exists() and m.stat().st_size > 100000:
        key = ("yunet", w, h)
        if key not in _det:
            _det[key] = cv2.FaceDetectorYN.create(str(m), "", (w, h), 0.75, 0.3, 50)
        return "yunet", _det[key]
    if "haar" not in _det:
        _det["haar"] = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    return "haar", _det["haar"]


def _cuadros(path, ancho, alto, paso):
    cmd = [tool("ffmpeg"), "-v", "error", "-i", str(path), "-vf", f"fps=1/{paso},scale={ancho}:{alto}",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = ancho * alto * 3
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield np.frombuffer(b, np.uint8).reshape(alto, ancho, 3)
    p.stdout.close()
    p.wait()


def caras(path, W, H, dur, guardar=None):
    """Lista por muestra: (t, x, y, w, h) de la cara mas grande en pixeles del video original, o (t, None).
    guardar: lista donde se dejan los cuadros en gris (640 de ancho) para buscar el borde de la facecam."""
    import cv2
    ancho = 640
    alto = int(round(H * ancho / W / 2)) * 2
    paso = 0.5 if dur <= 40 else 1.0
    tipo, det = _detector(ancho, alto)
    k = W / ancho
    out = []
    for i, fr in enumerate(_cuadros(path, ancho, alto, paso)):
        t = i * paso
        if guardar is not None and len(guardar) < 80:
            guardar.append(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY))
        if tipo == "yunet":
            _, f = det.detect(fr)
            boxes = [] if f is None else [b[:4] for b in f]
        else:
            g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
            boxes = det.detectMultiScale(g, 1.1, 6, minSize=(24, 24))
        if len(boxes):
            x, y, w, h = max(boxes, key=lambda b: b[2] * b[3])
            out.append((t, x * k, y * k, w * k, h * k))
        else:
            out.append((t, None))
    return out


def _bordes(cuadros):
    """Mapas para encontrar el recuadro de la facecam:
    - fijo: en que fraccion de cuadros hay un borde en cada pixel (el marco de la camara no se mueve,
      el juego si, asi que sus bordes se promedian a casi cero)
    - mov: cuanto cambia cada pixel en el tiempo (el juego cambia mucho, el cuarto del streamer poco)"""
    import cv2
    pila = np.stack(cuadros).astype(np.float32)
    fijo = np.mean([cv2.Canny(c, 60, 140) > 0 for c in cuadros], axis=0)
    # un borde de 1-2 px puede bailar por la compresion: se ensancha un pixel
    fijo = np.maximum(fijo, np.maximum(np.roll(fijo, 1, 0), np.roll(fijo, 1, 1)))
    mov = pila.std(axis=0)
    return fijo, mov / (np.percentile(mov, 98) + 1e-6)


def _linea(fijo, mov, eje, pos, desde, hasta, cam_despues):
    """Puntaje 0..1 de que haya un borde de facecam en 'pos' (columna si eje=1, fila si eje=0), medido
    solo en el tramo desde:hasta del otro eje. cam_despues: la camara queda a la derecha/abajo del borde."""
    lim = fijo.shape[1] if eje == 1 else fijo.shape[0]
    if pos < 3 or pos > lim - 4:
        return 0.0
    if eje == 1:
        tira = fijo[desde:hasta, pos - 1:pos + 2].max(axis=1)
        antes = mov[desde:hasta, max(0, pos - 8):pos - 1].mean()
        despues = mov[desde:hasta, pos + 2:pos + 9].mean()
    else:
        tira = fijo[pos - 1:pos + 2, desde:hasta].max(axis=0)
        antes = mov[max(0, pos - 8):pos - 1, desde:hasta].mean()
        despues = mov[pos + 2:pos + 9, desde:hasta].mean()
    continuo = float(np.mean(tira > 0.55))               # el marco es una linea recta y continua
    juego, cam = (antes, despues) if cam_despues else (despues, antes)
    contraste = float(np.clip((juego - cam) * 1.5, 0, 1))  # del lado del juego se mueve mas
    return 0.7 * continuo + 0.3 * contraste


def _buscar(fijo, mov, eje, ini, rango, lado, limite):
    """Busca el borde mas fuerte desde 'ini' (al lado de la cara) hasta 'limite'
    (lado -1: hacia la izquierda/arriba, +1: hacia la derecha/abajo)."""
    desde, hasta = rango
    if hasta - desde < 6:
        return None
    candidatos = range(int(ini), int(limite), lado)
    mejor, mpos = 0.0, None
    for pos in candidatos:
        v = _linea(fijo, mov, eje, pos, desde, hasta, lado < 0)
        if v > mejor + 0.02:
            mejor, mpos = v, pos
    return mpos if mejor >= 0.5 else None


def caja_camara(cuadros, cara, W, H):
    """Encuentra el recuadro de la facecam (en pixeles del video original) a partir de la cara media.
    Busca los cuatro bordes del overlay; el lado que no aparece se completa con el tamano tipico
    (o con el borde de la pantalla si la camara esta pegada a la orilla)."""
    cx, cy, fw, fh = cara                                 # centro y tamano de la cara (originales)
    h, w = cuadros[0].shape
    k = w / W
    fijo, mov = _bordes(cuadros)
    x0, x1 = (cx - fw / 2) * k, (cx + fw / 2) * k
    y0, y1 = (cy - fh / 2) * k, (cy + fh / 2) * k
    fwk, fhk = fw * k, fh * k
    banda_y = (int(max(0, y0 - 0.3 * fhk)), int(min(h, y1 + 0.6 * fhk)))
    banda_x = (int(max(0, x0 - 0.2 * fwk)), int(min(w, x1 + 0.2 * fwk)))
    izq = _buscar(fijo, mov, 1, x0 - 0.25 * fwk, banda_y, -1, max(0, int(x0 - 4.5 * fwk)) - 1)
    der = _buscar(fijo, mov, 1, x1 + 0.25 * fwk, banda_y, 1, min(w, int(x1 + 4.5 * fwk)) + 1)
    arr = _buscar(fijo, mov, 0, y0 - 0.35 * fhk, banda_x, -1, max(0, int(y0 - 3.0 * fhk)) - 1)
    aba = _buscar(fijo, mov, 0, y1 + 0.3 * fhk, banda_x, 1, min(h, int(y1 + 4.0 * fhk)) + 1)
    encontrados = sum(v is not None for v in (izq, der, arr, aba))

    # lo que no se encontro: tamano tipico de una facecam (~3.4 caras de alto, un poco mas ancha que alta);
    # si ese tamano se sale de la pantalla, la camara esta pegada a la orilla y el limite es la pantalla
    alto_t, ancho_t = fhk * 3.4, fhk * 3.4 * 1.3
    pega = 0.04
    if izq is None and der is None:
        izq, der = cx * k - ancho_t / 2, cx * k + ancho_t / 2
        izq, der = (0 if izq < w * pega else izq), (w if der > w * (1 - pega) else der)
    elif izq is None:
        izq = der - max(ancho_t, (der - cx * k) * 2)
        izq = 0 if izq < w * pega else izq
    elif der is None:
        der = izq + max(ancho_t, (cx * k - izq) * 2)
        der = w if der > w * (1 - pega) else der
    if arr is None and aba is None:
        arr, aba = cy * k - alto_t / 2.3, cy * k + alto_t * (1 - 1 / 2.3)
        arr, aba = (0 if arr < h * pega else arr), (h if aba > h * (1 - pega) else aba)
    elif arr is None:
        arr = aba - max(alto_t, (aba - cy * k) * 1.8)
        arr = 0 if arr < h * pega else arr
    elif aba is None:
        aba = arr + max(alto_t, (cy * k - arr) * 2.2)
        aba = h if aba > h * (1 - pega) else aba
    izq, der = max(0.0, izq), min(float(w), der)
    arr, aba = max(0.0, arr), min(float(h), aba)
    # se mete un poquito para que no salga la linea del marco ni un pedazo de juego
    mx, my = (der - izq) * 0.025, (aba - arr) * 0.025
    caja = [(izq + mx) / k, (arr + my) / k, (der - izq - 2 * mx) / k, (aba - arr - 2 * my) / k]
    return caja, encontrados


def _ajustar_panel(caja, cara, W, H):
    """Ajusta la caja de la camara a la proporcion del panel de arriba (1080 x alto entre 600 y 1000),
    recortando alrededor de la cara para que no se deforme ni se meta el juego."""
    x, y, bw, bh = caja
    cx, cy = cara[0], cara[1]
    cam_h = int(np.clip(1080 * bh / max(1.0, bw), 600, 1000)) // 2 * 2
    asp = 1080 / cam_h                                    # ancho/alto del panel
    if bw / bh > asp:                                     # camara mas ancha que el panel: se recorta a los lados
        nw = bh * asp
        x = float(np.clip(cx - nw / 2, x, x + bw - nw))
        bw = nw
    else:                                                 # mas alta: se recorta arriba/abajo (cara en el tercio alto)
        nh = bw / asp
        y = float(np.clip(cy - nh * 0.42, y, y + bh - nh))
        bh = nh
    x, y = max(0, min(x, W - bw)), max(0, min(y, H - bh))
    return [int(x), int(y), int(bw) // 2 * 2, int(bh) // 2 * 2], cam_h


def _recorte_juego(cam, W, H, cam_h):
    """Ventana del juego para el panel de abajo: lo mas centrada posible pero esquivando la facecam
    (para que la camara no salga dos veces)."""
    gh = 1920 - cam_h
    gw = min(W, int(H * 1080 / gh) // 2 * 2)
    cx0, cx1 = cam[0], cam[0] + cam[2]
    centro = (W - gw) / 2
    mejor, gx_m = None, int(centro)
    for gx in np.linspace(0, W - gw, 41):
        tapa = max(0.0, min(gx + gw, cx1) - max(gx, cx0)) / max(1, cam[2]) * cam[3] / max(1, H)
        costo = tapa + 1.5 * abs(gx - centro) / max(1, W)       # la accion casi siempre esta al centro
        if mejor is None or costo < mejor:
            mejor, gx_m = costo, int(gx)
    return gw, gx_m // 2 * 2


def planear(path, info, preferencia="auto", es_juego=None):
    """es_juego: True si el directo es de un videojuego (por la categoria), False si es charla/IRL,
    None si no se sabe (se decide mirando el video)."""
    W, H, dur = info["w"], info["h"], info["dur"]
    if H >= W * 1.2:
        return {"tipo": "vertical"}
    if preferencia in ("blur", "crop"):
        return {"tipo": preferencia}
    cuadros = []
    try:
        muestras = caras(path, W, H, dur, cuadros)
    except Exception:
        muestras = []
    con = [m for m in muestras if len(m) == 5]
    minimo = 0.25 if (es_juego or preferencia == "split") else 0.4
    if len(con) < max(2, minimo * len(muestras)):
        return {"tipo": "crop" if preferencia == "seguir" else "blur"}
    xs = np.array([m[1] + m[3] / 2 for m in con])
    ys = np.array([m[2] + m[4] / 2 for m in con])
    hs = np.array([m[4] for m in con])
    ws = np.array([m[3] for m in con])
    alto_rel = float(np.median(hs) / H)
    quieta = xs.std() < 0.06 * W and ys.std() < 0.06 * H
    if es_juego:
        # videojuego: siempre camara arriba + juego abajo, salvo que la camara sea la pantalla completa
        split = preferencia != "seguir" and alto_rel < 0.45 and (quieta or alto_rel < 0.25)
    elif es_juego is False:
        split = preferencia == "split"
    else:
        split = preferencia == "split" or (preferencia == "auto" and alto_rel < 0.22 and quieta)
    if split:
        # cara mas comun (la mediana ignora los cuadros donde se movio o detecto otra cosa)
        cerca = (np.abs(xs - np.median(xs)) < 0.08 * W) & (np.abs(ys - np.median(ys)) < 0.08 * H)
        cara = (float(np.median(xs[cerca])), float(np.median(ys[cerca])),
                float(np.median(ws[cerca])), float(np.median(hs[cerca])))
        try:
            caja, hallados = caja_camara(cuadros, cara, W, H) if len(cuadros) >= 4 else (None, 0)
        except Exception:
            caja, hallados = None, 0
        if caja is None:
            bh = min(H, cara[3] * 3.4)
            bw = min(W, bh * 1.3)
            caja = [min(max(0, cara[0] - bw / 2), W - bw), min(max(0, cara[1] - bh / 2.3), H - bh), bw, bh]
        cam, cam_h = _ajustar_panel(caja, cara, W, H)
        gw, gx = _recorte_juego(cam, W, H, cam_h)
        return {"tipo": "split", "cam": cam, "cam_h": cam_h, "gw": gw, "gx": gx, "bordes": hallados}
    # seguir la cara con un recorte 9:16, suavizado y con zona muerta
    cw = int(H * 9 / 16) // 2 * 2
    pts, ult = [], None
    for m in muestras:
        if len(m) == 5:
            ult = m[1] + m[3] / 2
        pts.append((m[0], ult))
    pri = next((p for _, p in pts if p is not None), W / 2)
    serie = np.array([p if p is not None else pri for _, p in pts], float)
    k = 5
    suave = np.convolve(np.pad(serie, k // 2, mode="edge"), np.ones(k) / k, mode="valid")
    llaves, actual = [], suave[0]
    for (t, _), v in zip(pts, suave):
        if abs(v - actual) > 0.06 * W:
            actual = v
        llaves.append((t, float(min(max(0, actual - cw / 2), W - cw))))
    return {"tipo": "seguir", "cw": cw, "llaves": llaves[:90]}


def _expr_x(llaves):
    """Expresion de ffmpeg que mueve el recorte entre puntos (interpolacion lineal)."""
    if not llaves:
        return "0"
    e = f"{llaves[-1][1]:.1f}"
    for (t0, x0), (t1, x1) in reversed(list(zip(llaves[:-1], llaves[1:]))):
        if abs(x1 - x0) < 1:
            tramo = f"{x0:.1f}"
        else:
            tramo = f"{x0:.1f}+({x1 - x0:.1f})*(t-{t0:.2f})/{max(0.01, t1 - t0):.2f}"
        e = f"if(lt(t,{t1:.2f}),{tramo},{e})"
    return e


def filtro_base(plan, info):
    """Filtro de ffmpeg [0:v] -> [base] 1080x1920."""
    t = plan["tipo"]
    if t in ("vertical", "crop"):
        return "[0:v]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1[base]"
    if t == "split":
        x, y, w, h = plan["cam"]
        W, H = info["w"], info["h"]
        ch = int(plan.get("cam_h") or 700)
        gh = 1920 - ch
        gw = int(plan.get("gw") or int(H * 1080 / gh) // 2 * 2)
        gx = int(plan.get("gx", (W - gw) // 2))
        return (f"[0:v]split=2[c][g];[c]crop={w}:{h}:{x}:{y},scale=1080:{ch}:flags=lanczos[cam];"
                f"[g]crop={gw}:{H}:{gx}:0,scale=1080:{gh}:flags=lanczos[jue];"
                f"[cam][jue]vstack=inputs=2,drawbox=x=0:y={ch - 3}:w=1080:h=6:color=black@0.9:t=fill,setsar=1[base]")
    if t == "seguir":
        cw = plan["cw"]
        return (f"[0:v]crop={cw}:{info['h']}:'{_expr_x(plan['llaves'])}':0,"
                f"scale=1080:1920:flags=lanczos,setsar=1[base]")
    return ("[0:v]split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            "gblur=sigma=28,eq=brightness=-0.07:saturation=1.15[bg];"
            "[b]scale=1080:-2:flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]")


def zona_subtitulos(plan, info):
    """Altura (y) donde van los subtitulos segun el encuadre, dentro de la zona segura."""
    t = plan["tipo"]
    if t == "split":
        return int(plan.get("cam_h") or 700)          # justo en la union camara/juego
    if t == "blur":
        hv = 1080 * info["h"] / max(1, info["w"])
        return int(min(1420, 960 + hv / 2 + 140))
    return 1240
