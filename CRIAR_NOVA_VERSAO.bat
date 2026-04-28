@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: GDIS PLATFORM - DISPARADOR DE NOVA VERSAO (GITHUB)
:: ============================================================

title LANÇAR NOVA VERSÃO - GDIS

echo.
echo ============================================================
echo      PREPARANDO NOVO LANÇAMENTO PARA GITHUB
echo ============================================================
echo.

:: 1. Verificar se ha alteracoes nao commitadas
git status --short
echo.
echo Verifique se todas as alteracoes acima devem ser enviadas.
set /p CONFIRM="Deseja continuar? (S/N): "
if /i "%CONFIRM%" neq "S" exit /b

:: 2. Solicitar numero da versao
echo.
echo Digite o numero da versao (ex: 1.0.5):
set /p VERSION="v"
set TAG=v%VERSION%

echo.
echo Criando tag %TAG%...

:: 3. Commit e Push
git add .
git commit -m "Release %TAG%"
git tag -a %TAG% -m "Versao %TAG%"
git push origin HEAD
git push origin %TAG%

echo.
echo ============================================================
echo ✅ SUCESSO! Tag %TAG% enviada para o GitHub.
echo.
echo A automacao (GitHub Actions) foi iniciada.
echo Em alguns minutos o pacote estara disponivel em:
echo https://github.com/okaygoodluck/conferencia_conflitos/releases
echo ============================================================
echo.
pause
