"""Baja SOLO un tramo (o un clip corto completo) en la mejor calidad hasta 1080p."""
from yt_dlp.utils import download_range_func

from .base import TRABAJO
from .fuentes import ydl


def bajar(url, a=None, b=None, nombre="tramo"):
    for p in TRABAJO.glob(nombre + ".*"):
        p.unlink(missing_ok=True)
    o = {"format": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
         "format_sort": ["res:1080", "fps", "vcodec:h264", "acodec:m4a"],
         "merge_output_format": "mp4", "outtmpl": str(TRABAJO / nombre) + ".%(ext)s",
         "concurrent_fragment_downloads": 6}
    if a is not None and b is not None:
        o["download_ranges"] = download_range_func(None, [(float(a), float(b))])
        o["force_keyframes_at_cuts"] = True
    with ydl(o) as y:
        y.download([url])
    hechos = [p for p in TRABAJO.glob(nombre + ".*") if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")]
    if not hechos:
        raise RuntimeError("no se descargo nada")
    return max(hechos, key=lambda p: p.stat().st_size)
