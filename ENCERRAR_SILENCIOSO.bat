@echo off
taskkill /f /im pythonw.exe >nul 2>&1
echo [OK] Servidores encerrados com sucesso!
timeout /t 2 /nobreak >nul 2>&1
exit /b 0
