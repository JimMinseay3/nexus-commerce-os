$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackupRoot = Join-Path $ProjectRoot "backups"
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupFile = Join-Path $BackupRoot "erp-$Stamp.sql"
$MediaFile = Join-Path $BackupRoot "media-$Stamp.tar.gz"
Set-Location -LiteralPath $ProjectRoot
docker compose exec -T db pg_dump --clean --if-exists --no-owner -U erp erp | Set-Content -LiteralPath $BackupFile -Encoding utf8
docker compose exec -T api tar -czf /tmp/erp-media.tar.gz -C /app/media .
docker compose cp api:/tmp/erp-media.tar.gz $MediaFile
docker compose exec -T api rm -f /tmp/erp-media.tar.gz
Get-ChildItem -LiteralPath $BackupRoot -Filter "erp-*.sql" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 | Remove-Item -Force
Get-ChildItem -LiteralPath $BackupRoot -Filter "media-*.tar.gz" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 | Remove-Item -Force
Write-Host "数据库备份：$BackupFile" -ForegroundColor Green
Write-Host "附件备份：$MediaFile" -ForegroundColor Green
