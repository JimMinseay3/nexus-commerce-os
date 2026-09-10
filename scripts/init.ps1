$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    $Bytes = New-Object byte[] 48
    [Security.Cryptography.RandomNumberGenerator]::Fill($Bytes)
    $Secret = [Convert]::ToBase64String($Bytes)
    [Security.Cryptography.RandomNumberGenerator]::Fill($Bytes)
    $FieldKey = [Convert]::ToBase64String($Bytes)
    [Security.Cryptography.RandomNumberGenerator]::Fill($Bytes)
    $DatabasePassword = ([Convert]::ToBase64String($Bytes) -replace '[^A-Za-z0-9]', '').Substring(0,32)
    $Environment = Get-Content -LiteralPath ".env" -Raw
    $Environment = $Environment -replace '(?m)^SECRET_KEY=.*$', "SECRET_KEY=$Secret"
    $Environment = $Environment -replace '(?m)^FIELD_ENCRYPTION_KEY=.*$', "FIELD_ENCRYPTION_KEY=$FieldKey"
    $Environment = $Environment -replace '(?m)^POSTGRES_PASSWORD=.*$', "POSTGRES_PASSWORD=$DatabasePassword"
    Set-Content -LiteralPath ".env" -Value $Environment -Encoding utf8
    Write-Host "已创建 .env 并生成独立的应用、字段加密和数据库密钥。" -ForegroundColor Green
}
docker compose up -d --build
docker compose exec api python manage.py seed_demo
Write-Host "ERP 已启动：http://localhost:8080（admin / Admin123!）" -ForegroundColor Green
