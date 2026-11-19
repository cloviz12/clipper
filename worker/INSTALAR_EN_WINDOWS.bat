@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Instalando el motor de CLIPPER
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
if not exist ".env" (
  echo Falta el archivo .env ^(copia .env.example como .env y llenalo^).
  pause
  exit /b
)
echo === Instalando Python, ffmpeg y deno (solo la primera vez) ===
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY (
  winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
  set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
where ffmpeg >nul 2>nul || winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
where deno   >nul 2>nul || winget install -e --id DenoLand.Deno --accept-source-agreements --accept-package-agreements
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo === Dejando el motor encendido en segundo plano (arranca solo al prender el PC) ===
schtasks /Create /TN "CLIPPER motor" /TR "wscript.exe \"%~dp0iniciar_oculto.vbs\"" /SC ONLOGON /RL LIMITED /F
schtasks /Run /TN "CLIPPER motor"
echo.
echo LISTO. El motor ya esta corriendo sin ventanas. Todo se maneja desde el panel web.
pause
