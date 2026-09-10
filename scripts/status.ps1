$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
docker compose ps
try { Invoke-RestMethod -Uri "http://localhost:8080/health/" -TimeoutSec 10 | ConvertTo-Json } catch { Write-Error "健康检查失败：$($_.Exception.Message)" }

