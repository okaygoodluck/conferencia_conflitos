@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: GDIS PLATFORM - SERVIDOR CENTRAL
:: Este script inicia a plataforma para acesso via rede (VPN)
:: ============================================================

title SERVIDOR CENTRAL - GDIS PLATFORM
cd /d "%~dp0"
set GDIS_PORT=8765

echo.
echo ============================================================
echo      INICIALIZANDO SERVIDOR CENTRAL (PORTA %GDIS_PORT%)
echo ============================================================
echo.

:: 1. Obter o IP do Servidor
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "127.0.0.1"') do (
    set IP=%%a
    set IP=!IP: ^=!
    goto :found_ip
)
:found_ip

echo [1/3] Verificando Ambiente...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao encontrado. Instale o Python para rodar o servidor.
    pause
    exit /b
)

echo [2/3] Verificando Dependencias...
python -c "import playwright, pandas, openpyxl" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Instalando bibliotecas necessarias...
    python -m pip install -r requirements.txt
)

:: Garante que o navegador Chromium do Playwright esta presente
python -m playwright install chromium

echo [3/3] Iniciando Servicos...
:: Encerra processos antigos na porta para evitar conflitos
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%GDIS_PORT%') do (
    taskkill /f /pid %%a >nul 2>&1
)

:: Inicia o App Unificado em segundo plano (novo console)
start "BACKEND - GDIS" /min python -m src.api.app_unificado

echo.
echo ============================================================
echo ✅ SERVIDOR PRONTO E ATIVO!
echo.
echo LINK DE ACESSO PARA OS USUARIOS (INTERNO / HOME OFFICE):
echo http://%IP%:%GDIS_PORT%/
echo.
echo Mantenha esta janela aberta para manter o servidor online.
echo ============================================================
echo.

:: Nao abre o navegador automaticamente para nao poluir o servidor
:: Mas deixa o link visivel para o administrador
pause
