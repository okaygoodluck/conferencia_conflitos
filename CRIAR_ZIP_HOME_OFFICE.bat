@echo off
echo [INFO] Iniciando criador de versao portatil...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0GERAR_VERSAO_PORTATIL.ps1"
pause
