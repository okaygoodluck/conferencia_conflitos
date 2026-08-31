@echo off
title GERAR PACOTES - HOME OFFICE E SERVIDOR
cd /d "%~dp0"

echo ============================================================
echo      GERANDO AMBOS OS PACOTES (HOME OFFICE E SERVIDOR)
echo ============================================================
echo.

echo [1/2] Gerando pacote Servidor Central (PACOTE_PARA_SERVIDOR.zip)...
powershell -ExecutionPolicy Bypass -File "%~dp0GERAR_PACOTE_SERVIDOR.ps1" -Zip -NoPause

echo.
echo [2/2] Gerando pacote Home Office Portatil (GDIS_Plataforma_HomeOffice.zip)...
echo (Isso pode levar alguns minutos pois instala o Python e o Chromium localmente...)
powershell -ExecutionPolicy Bypass -File "%~dp0GERAR_VERSAO_PORTATIL.ps1" -Zip -NoPause

echo.
echo ============================================================
echo ✅ AMBOS OS PACOTES FORAM GERADOS COM SUCESSO!
echo.
echo Files criados:
echo  1. PACOTE_PARA_SERVIDOR.zip
echo  2. GDIS_Plataforma_HomeOffice.zip
echo ============================================================
echo.
pause
