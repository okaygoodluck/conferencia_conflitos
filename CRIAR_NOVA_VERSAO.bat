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

:: Tenta localizar o Git se nao estiver no PATH
where git >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [!] Git nao encontrado no PATH. Tentando localizar no GitHub Desktop...
    set GIT_PATH="D:\Users\c057573\AppData\Local\GitHubDesktop\app-3.5.6\resources\app\git\cmd\git.exe"
    if not exist !GIT_PATH! (
        echo [ERRO] Git nao encontrado. Por favor, instale o Git para Windows.
        pause
        exit /b
    )
    set GIT_CMD=!GIT_PATH!
) else (
    set GIT_CMD=git
)

:: 1. Verificar se ha alteracoes nao commitadas
%GIT_CMD% status --short
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
%GIT_CMD% add .
%GIT_CMD% commit -m "Release %TAG%"
%GIT_CMD% tag -a "%TAG%" -m "Versao %TAG%"
%GIT_CMD% push origin HEAD
%GIT_CMD% push origin "%TAG%"

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
