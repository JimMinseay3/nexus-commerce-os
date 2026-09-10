$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
& (Join-Path $PSScriptRoot "backup.ps1")
docker compose build --pull
docker compose up -d
docker compose exec api python manage.py migrate
docker compose ps

