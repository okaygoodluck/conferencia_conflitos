# ============================================================
# GDIS PLATFORM - GERADOR DE VERSÃO PORTÁTIL (.ZIP)
# Este script cria um pacote que já contém Python + Navegador + Código.
# O usuário final não precisa instalar NADA.
# ============================================================

$packageName = "GDIS_Plataforma_HomeOffice"
$pythonVersion = "3.11.9"
$pythonUrl = "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-embed-amd64.zip"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "      GERANDO VERSÃO PORTÁTIL PARA HOME OFFICE" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Criar pasta do pacote
if (Test-Path $packageName) { Remove-Item -Recurse -Force $packageName }
New-Item -ItemType Directory -Path $packageName -Force | Out-Null
New-Item -ItemType Directory -Path "$packageName\python" -Force | Out-Null

# 2. Baixar Python Embeddable
Write-Host "[1/6] Baixando Python Portátil ($pythonVersion)..."
Invoke-WebRequest -Uri $pythonUrl -OutFile "python_embed.zip"
Expand-Archive -Path "python_embed.zip" -DestinationPath "$packageName\python"
Remove-Item "python_embed.zip"

# 3. Configurar Python para aceitar pacotes locais
Write-Host "[2/6] Configurando ambiente Python..."
$pthFile = Get-ChildItem "$packageName\python\python*._pth" | Select-Object -First 1
$content = Get-Content $pthFile.FullName
# Adiciona Lib\site-packages e ativa o site module
$newContent = @()
foreach ($line in $content) {
    if ($line -eq "#import site") {
        $newContent += "Lib\site-packages"
        $newContent += "import site"
    } else {
        $newContent += $line
    }
}
Set-Content -Path $pthFile.FullName -Value $newContent
# Cria a pasta Lib\site-packages antecipadamente
New-Item -ItemType Directory -Path "$packageName\python\Lib\site-packages" -Force | Out-Null

# 4. Instalar PIP
Write-Host "[3/6] Instalando gerenciador de pacotes (PIP)..."
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile "$packageName\python\get-pip.py"
& "$packageName\python\python.exe" "$packageName\python\get-pip.py" --no-warn-script-location
Remove-Item "$packageName\python\get-pip.py"

# 5. Instalar Dependências e Playwright
Write-Host "[4/6] Instalando dependências (Pandas, Playwright, Openpyxl)..."
& "$packageName\python\python.exe" -m pip install -r requirements.txt --target "$packageName\python\Lib\site-packages" --no-warn-script-location

# 6. Baixar Navegador para dentro da pasta (Portabilidade Total)
Write-Host "[5/6] Baixando Navegador Chromium (isso pode demorar)..."
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\$packageName\pw-browsers"
& "$packageName\python\python.exe" -m playwright install chromium

# 7. Copiar Código do Projeto
Write-Host "[6/6] Copiando código e assets..."
Copy-Item -Path "src" -Destination "$packageName\src" -Recurse
Copy-Item -Path "assets" -Destination "$packageName\assets" -Recurse
if (Test-Path "data") { Copy-Item -Path "data" -Destination "$packageName\data" -Recurse }

# 8. Criar o .bat de inicialização local
$batContent = @"
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
"@
$batContent | Out-File -FilePath "$packageName\INICIAR_PLATAFORMA_LOCAL.bat" -Encoding ascii

# 9. Criar ZIP se solicitado
if ($args -contains "-Zip") {
    Write-Host "[EXTRAS] Criando arquivo ZIP final..." -ForegroundColor Yellow
    if (Test-Path "$packageName.zip") { Remove-Item "$packageName.zip" }
    Compress-Archive -Path "$packageName" -DestinationPath "$packageName.zip"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "✅ SUCESSO! PACOTE GERADO." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

if (-not ($args -contains "-NoPause")) {
    pause
}
