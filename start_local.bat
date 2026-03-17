@echo off
setlocal
cd /d "%~dp0"
set GDIS_PORT=8765

start "Verificador GDIS" /min cmd /c "title Verificador GDIS && python app_local.py"
timeout /t 1 /nobreak >nul
start "" "http://127.0.0.1:%GDIS_PORT%/"
