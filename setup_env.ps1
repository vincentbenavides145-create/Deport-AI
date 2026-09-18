# Script de configuración automática de entorno virtual para DEPORT AI (Windows / PowerShell)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Configurando entorno virtual reproducible para DEPORT AI" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Crear entorno virtual si no existe
if (-not (Test-Path ".venv")) {
    Write-Host "`n1. Creando entorno virtual .venv..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "`n1. Entorno virtual .venv ya existe." -ForegroundColor Green
}

# 2. Instalar dependencias fijadas
Write-Host "`n2. Instalando dependencias congeladas desde requirements-dev.txt..." -ForegroundColor Yellow
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
& .\.venv\Scripts\python.exe -m pip install -e .

# 3. Ejecutar pruebas unitarias de verificación
Write-Host "`n3. Ejecutando suite de pruebas automatizadas..." -ForegroundColor Yellow
& .\.venv\Scripts\pytest.exe -v

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host " ✅ Entorno configurado con éxito." -ForegroundColor Green
Write-Host " Para activar en tu terminal ejecuta: .\.venv\Scripts\Activate.ps1" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
