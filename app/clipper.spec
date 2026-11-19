# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: genera la carpeta dist/CLIPPER con CLIPPER.exe (sin consola).
from PyInstaller.utils.hooks import collect_all

datas, binaries, hidden = [], [], []
for pkg in ["faster_whisper", "ctranslate2", "onnxruntime", "tokenizers", "av", "yt_dlp", "yt_dlp_ejs",
            "streamlink", "chat_downloader", "webview", "supabase", "realtime", "postgrest", "storage3",
            "gotrue", "supabase_auth", "supabase_functions", "cv2", "pystray", "websocket"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hidden += h
    except Exception as e:
        print("aviso: no pude recolectar", pkg, e)

datas += [("../ui/out", "ui"), ("../worker/fuentes_letra", "fuentes_letra"), ("bin", "bin"), ("icono.ico", ".")]

a = Analysis(
    ["clipper_app.py"],
    pathex=["../worker", "."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden + ["main", "servidor", "clipper", "clipper.editor", "clipper.en_vivo", "clipper.trabajos",
                            "clipper.publicar", "clipper.efectos", "clipper.encuadre", "clipper.subtitulos", "clipper.ia",
                            "clipper.chat", "clipper.fuentes", "clipper.momentos", "clipper.render_tramo", "clipper.base",
                            "winreg"],
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="CLIPPER", console=False, icon="icono.ico",
          upx=False, version=None)
coll = COLLECT(exe, a.binaries, a.datas, name="CLIPPER", upx=False)
