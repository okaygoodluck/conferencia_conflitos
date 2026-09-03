@echo off
setlocal enabledelayedexpansion
echo Encerrando servicos da Plataforma GDIS (Portas 8765, 8766, 8767)...
for %%p in (8765 8766 8767) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%%p ^| findstr LISTENING') do (
        taskkill /f /pid %%a >nul 2>&1
    )
)
echo [OK] Servidores GDIS encerrados com sucesso!
timeout /t 2 /nobreak >nul 2>&1
exit /b 0
