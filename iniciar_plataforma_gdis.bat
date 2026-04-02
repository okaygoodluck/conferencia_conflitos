@echo off
setlocal
cd /d "%~dp0"
set GDIS_PORT=8765

echo [1/3] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao encontrado no PATH. Por favor, instale o Python ou use a versao portatil.
    pause
    exit /b
)

echo [2/3] Verificando Dependencias...
python -c "import playwright, pandas, openpyxl, cryptography" >nul 2>&1
if %errorlevel% neq 0 (
    echo [AVISO] Algumas bibliotecas estao faltando. Tentando instalar...
    python -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERRO] Falha ao instalar dependencias. Verifique sua conexao com a internet.
        pause
        exit /b
    )
)

echo [3/3] Iniciando Plataforma GDIS (Porta %GDIS_PORT%)...
call ENCERRAR_SILENCIOSO.bat
start "Plataforma GDIS" python -m src.api.app_unificado

timeout /t 3 /nobreak >nul
start "" "https://127.0.0.1:%GDIS_PORT%/"
echo Plataforma pronta!
