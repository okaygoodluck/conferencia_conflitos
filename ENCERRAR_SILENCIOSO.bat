@echo off
taskkill /f /im pythonw.exe
echo [OK] Servidores encerados com sucesso!
timeout /t 2 >nul
exit /b 0
