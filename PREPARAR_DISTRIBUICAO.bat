@echo off
setlocal

:: ============================================================
:: GDIS PLATFORM - GERADOR DE PACOTE DE DISTRIBUICAO
:: Este script prepara uma pasta limpa para ser copiada para o servidor.
:: ============================================================

set DIST_DIR=PACOTE_PARA_SERVIDOR
set SOURCE_DIR=%~dp0

echo.
echo ============================================================
echo      PREPARANDO PACOTE PARA COPIAR PARA O SERVIDOR
echo ============================================================
echo.

:: 1. Limpeza
if exist "%DIST_DIR%" (
    echo [1/4] Removendo versao anterior do pacote...
    rd /s /q "%DIST_DIR%"
)

:: 2. Criacao da estrutura
echo [2/4] Criando nova estrutura de pastas...
mkdir "%DIST_DIR%"
mkdir "%DIST_DIR%\src"
mkdir "%DIST_DIR%\assets"
if exist "data" mkdir "%DIST_DIR%\data"

:: 3. Copia de Arquivos Essenciais
echo [3/4] Copiando arquivos essenciais (ignorando lixo)...

:: Cria lista de exclusao temporaria
echo __pycache__> exclude_list.txt
echo .git>> exclude_list.txt
echo .vscode>> exclude_list.txt

:: Copia SRC (Backend e Frontend) ignorando __pycache__
xcopy /s /e /y /i /exclude:exclude_list.txt "src" "%DIST_DIR%\src" >nul

:: Copia Assets e Data
xcopy /s /e /y /i "assets" "%DIST_DIR%\assets" >nul
if exist "data" xcopy /s /e /y /i "data" "%DIST_DIR%\data" >nul

:: Copia scripts e config
copy /y "requirements.txt" "%DIST_DIR%\" >nul
copy /y "SERVIDOR_CENTRAL.bat" "%DIST_DIR%\" >nul
copy /y "COMO_CONFIGURAR_SERVIDOR.md" "%DIST_DIR%\" >nul

:: 4. Finalizacao
echo [4/4] Pacote pronto!
echo.
echo ============================================================
echo ✅ SUCESSO!
echo.
echo A pasta "%DIST_DIR%" foi criada. 
echo Agora basta COPIAR essa pasta e COLAR no seu Servidor Central.
echo ============================================================
echo.

:: Limpa arquivo temporario de exclusao
if exist exclude_list.txt del exclude_list.txt

pause
