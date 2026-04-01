param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$DeviceKey = "anomalyguard-device-key",
    [string]$DeviceId = "esp32-device-001",
    [string]$DeviceName = "Smoke Test Device",
    [string]$Region = "Local Debug",
    [string]$AdminUser = "admin",
    [string]$AdminPassword = "admin123",
    [int]$Direction = 0,
    [switch]$SkipControl,
    [switch]$SkipLogin,
    [switch]$StatusOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function New-DeviceTelemetry {
    param(
        [string]$StationId,
        [string]$StationName,
        [string]$StationRegion
    )

    $now = Get-Date
    $utcIso = $now.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $localTime = $now.ToString("HH:mm")

    return @{
        station_id = $StationId
        station_name = $StationName
        region = $StationRegion
        timezone = "Asia/Ho_Chi_Minh"
        clientID = "smoke-test"
        timestamp = $utcIso
        time = $localTime
        ph = 7.18
        tds = 422.0
        temp = 31.1
        hum = 68.5
        weight = 350.0
        waterTemp = 28.4
        isFeeding = $false
    }
}

function Invoke-JsonRequest {
    param(
        [ValidateSet("GET", "POST", "PUT")]
        [string]$Method,
        [string]$Uri,
        [hashtable]$Headers = @{},
        [object]$Body
    )

    $params = @{
        Method = $Method
        Uri = $Uri
        Headers = $Headers
    }

    if ($PSBoundParameters.ContainsKey("Body")) {
        $params["ContentType"] = "application/json"
        $params["Body"] = ($Body | ConvertTo-Json -Depth 10)
    }

    return Invoke-RestMethod @params
}

Write-Step "Sending device telemetry"
$telemetry = New-DeviceTelemetry -StationId $DeviceId -StationName $DeviceName -StationRegion $Region
$telemetryResponse = Invoke-JsonRequest -Method POST -Uri "$BaseUrl/api/device/telemetry" -Headers @{ "X-Device-Key" = $DeviceKey } -Body $telemetry
$telemetryResponse | ConvertTo-Json -Depth 10

if ($StatusOnly) {
    Write-Step "Fetching device status"
    $statusResponse = Invoke-JsonRequest -Method GET -Uri "$BaseUrl/api/device/status?station_id=$DeviceId"
    $statusResponse | ConvertTo-Json -Depth 10
    exit 0
}

if (-not $SkipControl) {
    $accessToken = $null

    if (-not $SkipLogin) {
        Write-Step "Logging in as admin"
        $tokenResponse = Invoke-RestMethod -Method POST -Uri "$BaseUrl/api/auth/token" -ContentType "application/x-www-form-urlencoded" -Body "username=$AdminUser&password=$AdminPassword"
        $accessToken = $tokenResponse.access_token
        Write-Host "Token acquired" -ForegroundColor Green
    }

    if (-not $accessToken) {
        throw "Admin token not available. Use -SkipControl only if you just want telemetry."
    }

    Write-Step "Pushing device control"
    $controlPayload = @{
        direction = $Direction
        pump = $true
        isFeeding = $false
        weight = 120
        hour = 8
        minute = 30
    }
    $controlResponse = Invoke-JsonRequest -Method PUT -Uri "$BaseUrl/api/device/control/$DeviceId" -Headers @{ Authorization = "Bearer $accessToken" } -Body $controlPayload
    $controlResponse | ConvertTo-Json -Depth 10
}

Write-Step "Fetching latest device control"
$polledControl = Invoke-JsonRequest -Method GET -Uri "$BaseUrl/api/device/control/$DeviceId" -Headers @{ "X-Device-Key" = $DeviceKey }
$polledControl | ConvertTo-Json -Depth 10

Write-Step "Fetching device status"
$status = Invoke-JsonRequest -Method GET -Uri "$BaseUrl/api/device/status?station_id=$DeviceId"
$status | ConvertTo-Json -Depth 10

Write-Step "Done"
Write-Host "Use this script before bringing the ESP32 online to verify backend endpoints and dashboard readiness." -ForegroundColor Green
