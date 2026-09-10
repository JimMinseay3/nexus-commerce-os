param([Parameter(Mandatory=$true)][string]$BackupFile)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Resolved = (Resolve-Path -LiteralPath $BackupFile).Path
if ([IO.Path]::GetExtension($Resolved) -ne ".sql") { throw "只允许恢复 .sql 备份文件" }
Set-Location -LiteralPath $ProjectRoot
Get-Content -LiteralPath $Resolved -Raw | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U erp erp
$Stamp = [IO.Path]::GetFileNameWithoutExtension($Resolved).Substring(4)
$MediaFile = Join-Path ([IO.Path]::GetDirectoryName($Resolved)) "media-$Stamp.tar.gz"
if (Test-Path -LiteralPath $MediaFile) {
    docker compose cp $MediaFile api:/tmp/erp-media.tar.gz
    docker compose exec -T api sh -c "rm -rf /app/media/* && tar -xzf /tmp/erp-media.tar.gz -C /app/media && rm -f /tmp/erp-media.tar.gz"
    Write-Host "附件恢复完成：$MediaFile" -ForegroundColor Green
}
Write-Host "恢复完成：$Resolved" -ForegroundColor Green
