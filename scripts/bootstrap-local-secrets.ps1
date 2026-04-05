param(
    [string]$OutputDir = (Join-Path (Split-Path -Parent $PSScriptRoot) "backend\.secrets")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-RandomSecret {
    param([int]$Bytes = 32)
    $buffer = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$jwtSecretPath = Join-Path $OutputDir "jwt_secret_key.txt"
$adminPasswordPath = Join-Path $OutputDir "admin_password.txt"
$deviceKeysPath = Join-Path $OutputDir "device_keys.json"

if (-not (Test-Path $jwtSecretPath)) {
    Set-Content -Path $jwtSecretPath -Value (New-RandomSecret -Bytes 48) -NoNewline
}

if (-not (Test-Path $adminPasswordPath)) {
    Set-Content -Path $adminPasswordPath -Value (New-RandomSecret -Bytes 24) -NoNewline
}

if (-not (Test-Path $deviceKeysPath)) {
    $deviceKeys = @{
        "esp32-device-001" = (New-RandomSecret -Bytes 24)
        "esp32-device-002" = (New-RandomSecret -Bytes 24)
    }
    $deviceKeys | ConvertTo-Json -Depth 3 | Set-Content -Path $deviceKeysPath
}

Write-Host "Local secrets are ready in $OutputDir"
Write-Host "Next steps:"
Write-Host "  1. copy backend\\.env.example backend\\.env"
Write-Host "  2. cd backend"
Write-Host "  3. alembic upgrade head"
Write-Host "  4. uvicorn app.main:app --reload --port 8000"
