@echo off
setlocal
cd /d "%~dp0"
set GDIS_PORT=8765

start "Conferidor GDIS" python -m src.api.app_local
timeout /t 1 /nobreak >nul
start "" "http://127.0.0.1:%GDIS_PORT%/"