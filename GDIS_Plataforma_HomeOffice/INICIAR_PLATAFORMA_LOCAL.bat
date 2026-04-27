@echo off
setlocal
title GDIS PLATFORM - HOME OFFICE
cd /d "%~dp0"

:: Configura o caminho do navegador para ser LOCAL (nao no AppData do usuario)
set PLAYWRIGHT_BROWSERS_PATH=%~dp0pw-browsers

echo.
echo ============================================================
echo      INICIALIZANDO GDIS PLATFORM (VERSAO PORTATIL)
echo ============================================================
echo.

start "GDIS BACKEND" /min "%~dp0python\python.exe" -m src.api.app_unificado

timeout /t 5 /nobreak >nul
start "" "http://127.0.0.1:8765/"

echo Plataforma pronta! 
echo Mantenha esta janela aberta enquanto estiver usando.
echo.
pause
