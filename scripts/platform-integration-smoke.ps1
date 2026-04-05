param(
    [switch]$ManageStack
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendSecretsDir = Join-Path $repoRoot "backend\.secrets"
$baseUrl = "http://localhost:8000"
$composeArgs = @("compose")

function Initialize-DockerCliConfig {
    if (-not $env:DOCKER_CONFIG) {
        $dockerConfigDir = Join-Path ([System.IO.Path]::GetTempPath()) "anomalyguard-docker-config"
        New-Item -ItemType Directory -Force -Path $dockerConfigDir | Out-Null
        $env:DOCKER_CONFIG = $dockerConfigDir
    }
}

function Assert-DockerDaemonAvailable {
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "docker"
    $startInfo.Arguments = "version --format ""{{.Server.Version}}"""
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.UseShellExecute = $false

    $process = [System.Diagnostics.Process]::Start($startInfo)
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    if ($process.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($stdout.Trim())) {
        $details = if ([string]::IsNullOrWhiteSpace($stderr)) {
            "Start Docker Desktop or run this smoke test in CI."
        } else {
            $stderr.Trim()
        }
        throw "Docker daemon is not available. $details"
    }
}

function Wait-ForApi {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 120
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Method Get -Uri "$Url/health"
            if ($health.status -eq "ok") {
                return $health
            }
        } catch {
        }
        Start-Sleep -Seconds 2
    }

    throw "API did not become healthy within $TimeoutSeconds seconds."
}

function Invoke-JsonRequest {
    param(
        [string]$Method,
        [string]$Uri,
        [hashtable]$Headers = @{},
        [object]$Body = $null,
        [string]$ContentType = "application/json"
    )

    $requestParams = @{
        Method = $Method
        Uri = $Uri
        Headers = $Headers
    }

    if ($null -ne $Body) {
        if ($ContentType -eq "application/json") {
            $requestParams["Body"] = ($Body | ConvertTo-Json -Depth 10 -Compress)
        } else {
            $requestParams["Body"] = $Body
        }
        $requestParams["ContentType"] = $ContentType
    }

    return Invoke-RestMethod @requestParams
}

function Assert-Condition {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

if ($ManageStack) {
    Initialize-DockerCliConfig
    Assert-DockerDaemonAvailable
    & (Join-Path $PSScriptRoot "bootstrap-local-secrets.ps1")
    docker @composeArgs up -d db redis kafka backend | Out-Host
}

try {
    if (-not $ManageStack) {
        Initialize-DockerCliConfig
        Assert-DockerDaemonAvailable
    }

    $health = Wait-ForApi -Url $baseUrl
    Write-Host "API healthy with schema revision $($health.schema_revision)"

    $adminPassword = (Get-Content (Join-Path $backendSecretsDir "admin_password.txt") -Raw).Trim()
    $encodedPassword = [uri]::EscapeDataString($adminPassword)
    $tokenResponse = Invoke-JsonRequest `
        -Method Post `
        -Uri "$baseUrl/api/auth/token" `
        -ContentType "application/x-www-form-urlencoded" `
        -Body "username=ops-admin&password=$encodedPassword"
    $token = $tokenResponse.access_token
    Assert-Condition ($token.Length -gt 20) "Failed to obtain admin token."

    $authHeaders = @{ Authorization = "Bearer $token" }
    $stationId = "integration-device-$([Guid]::NewGuid().ToString('N').Substring(0, 8))"

    $rotateResponse = Invoke-JsonRequest `
        -Method Post `
        -Uri "$baseUrl/api/device/credentials/$stationId/rotate" `
        -Headers $authHeaders `
        -Body @{ note = "Integration smoke rotation" }
    Assert-Condition ($rotateResponse.station_id -eq $stationId) "Rotate endpoint returned wrong station."
    Assert-Condition ($rotateResponse.issued_key.Length -gt 20) "Rotate endpoint did not issue a usable key."

    $telemetryHeaders = @{ "X-Device-Key" = $rotateResponse.issued_key }
    $telemetryBody = @{
        station_id = $stationId
        station_name = "Integration Device"
        region = "Integration Lab"
        timezone = "UTC"
        latitude = 10.5
        longitude = 105.5
        ph = 11.7
        tds = 1350
        turbidity = 42
        do_mg_l = 1.8
        flow_l_min = 0.1
        waterTemp = 31.0
        temp = 31.0
        hum = 72.0
        weight = 250.0
        isFeeding = $false
    }
    $telemetryResponse = Invoke-JsonRequest `
        -Method Post `
        -Uri "$baseUrl/api/device/telemetry" `
        -Headers $telemetryHeaders `
        -Body $telemetryBody
    Assert-Condition ($telemetryResponse.generated_alert.id.Length -gt 0) "Telemetry did not generate an alert."

    $alerts = $null
    $alertDeadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $alertDeadline) {
        $alerts = Invoke-JsonRequest -Method Get -Uri "$baseUrl/api/alerts/latest?station_id=$stationId&since_minutes=15" -Headers $authHeaders
        if ($alerts.Count -ge 1) {
            break
        }
        Start-Sleep -Seconds 2
    }
    Assert-Condition (($alerts | Measure-Object).Count -ge 1) "Alert feed did not return the integration alert."

    $auditEntries = Invoke-JsonRequest `
        -Method Get `
        -Uri "$baseUrl/api/device/credentials/audit?station_id=$stationId&limit=10" `
        -Headers $authHeaders
    Assert-Condition (($auditEntries | Measure-Object).Count -ge 1) "Device credential audit is empty."
    Assert-Condition ($auditEntries[0].event_type -in @("provisioned", "rotated")) "Unexpected audit event type."

    $inventory = Invoke-JsonRequest -Method Get -Uri "$baseUrl/api/device/credentials" -Headers $authHeaders
    Assert-Condition (($inventory | Where-Object { $_.station_id -eq $stationId }).Count -eq 1) "Credential inventory missing rotated device."

    $consumerOutput = docker @composeArgs exec -T kafka sh -lc "/opt/bitnami/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic anomaly-alerts --from-beginning --timeout-ms 10000 --max-messages 20"
    Assert-Condition (($consumerOutput -join "`n") -match $stationId) "Kafka topic did not contain the integration alert."

    $revokeResponse = Invoke-JsonRequest `
        -Method Post `
        -Uri "$baseUrl/api/device/credentials/$stationId/revoke" `
        -Headers $authHeaders `
        -Body @{ note = "Integration smoke revoke" }
    Assert-Condition ($revokeResponse.event_type -eq "revoked") "Revoke endpoint did not return a revoke event."

    $inventoryAfterRevoke = Invoke-JsonRequest -Method Get -Uri "$baseUrl/api/device/credentials" -Headers $authHeaders
    Assert-Condition (($inventoryAfterRevoke | Where-Object { $_.station_id -eq $stationId }).Count -eq 0) "Revoked device still present in inventory."

    Write-Host "Integration smoke passed for station $stationId"
} finally {
    if ($ManageStack) {
        docker @composeArgs down -v | Out-Host
    }
}
