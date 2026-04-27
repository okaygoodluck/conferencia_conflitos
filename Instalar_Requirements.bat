@echo off
setlocal EnableExtensions DisableDelayedExpansion

pushd "%~dp0" >nul
set "BASE_DIR=%CD%"

if not exist "%BASE_DIR%\requirements.txt" (
  echo [ERRO] requirements.txt nao encontrado em:
  echo %BASE_DIR%
  popd >nul
  pause
  exit /b 1
)

set "PY_CMD=py -3"
where py >nul 2>nul
if errorlevel 1 set "PY_CMD=python"

call %PY_CMD% -c "import sys; print(sys.executable)" >nul 2>nul
if errorlevel 1 (
  echo [ERRO] Python nao encontrado no PC.
  echo Instale Python 64-bit e garanta que o comando ^(py ou python^) funcione.
  popd >nul
  pause
  exit /b 1
)

echo ========================================================
echo   Instalacao de dependencias (pip)
echo ========================================================
echo Pasta: %BASE_DIR%
echo Python: %PY_CMD%
echo.

call %PY_CMD% -m pip install -r "%BASE_DIR%\requirements.txt"
if errorlevel 1 (
  echo.
  echo [AVISO] Falhou sem permissao. Tentando instalar no perfil do usuario...
  call %PY_CMD% -m pip install --user -r "%BASE_DIR%\requirements.txt"
)

echo.
echo [OK] Concluido.
popd >nul
pause
