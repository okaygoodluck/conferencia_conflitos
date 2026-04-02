@echo off
setlocal
cd /d "%~dp0"
set GDIS_PORT=8765
echo [1/3] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 ( exit /b )
echo [2/3] Verificando Dependencias...
python -c "import playwright, pandas, openpyxl" >nul 2>&1
if %errorlevel% neq 0 ( python -m pip install -r requirements.txt )
echo [3/3] Iniciando Plataforma GDIS...
call ENCERRAR_SILENCIOSO.bat
start "Plataforma GDIS" python -m src.api.app_unificado
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:%GDIS_PORT%/"
