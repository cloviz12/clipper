"""Decide el mejor encuadre vertical mirando las caras del clip:
- 'split'  : stream con facecam pequena -> camara arriba + juego abajo
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


def caras(path, W, H, dur):
    """Lista por muestra: (t, x, y, w, h) de la cara mas grande en pixeles del video original, o None."""
    import cv2
    ancho = 640
    alto = int(round(H * ancho / W / 2)) * 2
    paso = 0.5 if dur <= 40 else 1.0
    tipo, det = _detector(ancho, alto)
    k = W / ancho
    out = []
    for i, fr in enumerate(_cuadros(path, ancho, alto, paso)):
        t = i * paso
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


def planear(path, info, preferencia="auto"):
    W, H, dur = info["w"], info["h"], info["dur"]
    if H >= W * 1.2:
        return {"tipo": "vertical"}
    if preferencia in ("blur", "crop"):
        return {"tipo": preferencia}
    try:
        muestras = caras(path, W, H, dur)
    except Exception:
        muestras = []
    con = [m for m in muestras if len(m) == 5]
    if len(con) < max(2, 0.4 * len(muestras)):
        return {"tipo": "crop" if preferencia == "seguir" else "blur"}
    xs = np.array([m[1] + m[3] / 2 for m in con])
    ys = np.array([m[2] + m[4] / 2 for m in con])
    hs = np.array([m[4] for m in con])
    alto_rel = float(np.median(hs) / H)
    quieta = xs.std() < 0.05 * W and ys.std() < 0.05 * H
    if preferencia == "split" or (preferencia == "auto" and alto_rel < 0.2 and quieta):
        cx, cy, fh = float(np.median(xs)), float(np.median(ys)), float(np.median(hs))
        # recuadro de la facecam: ~3.4 caras de alto, proporcion 1080x700
        bh = min(H, fh * 3.4)
        bw = min(W, bh * 1080 / 700)
        bh = bw * 700 / 1080
        x0 = min(max(0, cx - bw / 2), W - bw)
        y0 = min(max(0, cy - bh / 2.3), H - bh)
        return {"tipo": "split", "cam": [int(x0), int(y0), int(bw) // 2 * 2, int(bh) // 2 * 2]}
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
        gw = int(H * 1080 / 1220) // 2 * 2
        gx = (W - gw) // 2
        return (f"[0:v]split=2[c][g];[c]crop={w}:{h}:{x}:{y},scale=1080:700:flags=lanczos[cam];"
                f"[g]crop={gw}:{H}:{gx}:0,scale=1080:1220:flags=lanczos[jue];"
                f"[cam][jue]vstack=inputs=2,drawbox=x=0:y=697:w=1080:h=6:color=black@0.9:t=fill,setsar=1[base]")
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
        return 700          # justo en la union camara/juego
    if t == "blur":
        hv = 1080 * info["h"] / max(1, info["w"])
        return int(min(1420, 960 + hv / 2 + 140))
    return 1240
