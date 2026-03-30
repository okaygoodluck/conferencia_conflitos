@echo off
setlocal
cd /d "%~dp0"
set REGRAS_PORT=8766
start "Verificador de Manobras" python -m src.api.app_regras_local
timeout /t 1 /nobreak >nul
start "" "http://127.0.0.1:%REGRAS_PORT%/"
