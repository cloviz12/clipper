@echo off
cd /d "%~dp0"
schtasks /End /TN "CLIPPER motor" >nul 2>nul
if exist "datos\motor.pid" for /f %%p in (datos\motor.pid) do taskkill /F /PID %%p >nul 2>nul
".venv\Scripts\python.exe" -m pip install -q -U -r requirements.txt
schtasks /Run /TN "CLIPPER motor"
echo Motor actualizado y encendido.
timeout /t 4 >nul
