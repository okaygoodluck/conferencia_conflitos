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

echo [3/3] Iniciando Servico Central Unificado...
:: Encerra processos antigos nas portas para evitar conflitos (Hub, Conflitos, Conferidor)
for %%p in (8765 8766 8767) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%%p ^| findstr LISTENING') do (
        taskkill /f /pid %%a >nul 2>&1
    )
)

:: Inicia o App Unificado (gerencia todos os subprocessos internamente e sem janelas extras)
start "HUB PLATAFORMA GDIS" /min python -m src.api.app_unificado

echo.
echo ============================================================
echo ✅ SERVIDOR CENTRAL PRONTO E ATIVO!
echo.
echo LINK DE ACESSO PARA OS USUARIOS (INTERNO / HOME OFFICE):
echo http://%IP%:%GDIS_PORT%/
echo.
echo TODOS os micro-servicos (Conflitos, Conferidor de Manobras)
echo e seus respectivos terminais estao centralizados no Web Dashboard!
echo ============================================================
echo.

pause

