# ============================================================
# GDIS PLATFORM - GERADOR DE PACOTE SERVIDOR CENTRAL (.ZIP)
# Este script cria um pacote limpo e atualizado para ser implantado no servidor central.
# ============================================================

$packageName = "PACOTE_PARA_SERVIDOR"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "      GERANDO PACOTE PARA SERVIDOR CENTRAL" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Criar/Limpar pasta do pacote
if (Test-Path $packageName) { Remove-Item -Recurse -Force $packageName }
New-Item -ItemType Directory -Path $packageName -Force | Out-Null

# 2. Copiar Arquivos e Pastas do Projeto
Write-Host "[1/3] Copiando scripts do servidor e documentação..." -ForegroundColor Yellow
Copy-Item -Path "SERVIDOR_CENTRAL.bat" -Destination "$packageName\SERVIDOR_CENTRAL.bat"
Copy-Item -Path "COMO_CONFIGURAR_SERVIDOR.md" -Destination "$packageName\COMO_CONFIGURAR_SERVIDOR.md"
Copy-Item -Path "requirements.txt" -Destination "$packageName\requirements.txt"
if (Test-Path "config_admin.json") { Copy-Item -Path "config_admin.json" -Destination "$packageName\config_admin.json" }

Write-Host "[2/3] Copiando código-fonte (src) e assets..." -ForegroundColor Yellow
Copy-Item -Path "src" -Destination "$packageName\src" -Recurse
Copy-Item -Path "assets" -Destination "$packageName\assets" -Recurse
if (Test-Path "data") { Copy-Item -Path "data" -Destination "$packageName\data" -Recurse }

# 3. Criar ZIP se solicitado
if ($args -contains "-Zip") {
    Write-Host "[3/3] Criando arquivo ZIP final ($packageName.zip)..." -ForegroundColor Yellow
    if (Test-Path "$packageName.zip") { Remove-Item "$packageName.zip" }
    Compress-Archive -Path "$packageName" -DestinationPath "$packageName.zip"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "✅ SUCESSO! PACOTE PARA SERVIDOR GERADO." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

if (-not ($args -contains "-NoPause")) {
    pause
}
