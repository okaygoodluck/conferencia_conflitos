@echo off
setlocal
cd /d "%~dp0"
set GDIS_PORT=8765

echo Iniciando Plataforma Integrada GDIS (Conflitos + Regras)...
start "Plataforma GDIS" python -m src.api.app_unificado
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:%GDIS_PORT%/"
