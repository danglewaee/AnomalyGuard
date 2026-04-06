param(
    [switch]$ManageStack,
    [string]$SummaryPath = ""
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

function Invoke-ComposeCommand {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    return & docker @composeArgs @Arguments
}

function Format-SqlLiteral {
    param([string]$Value)
    return "'$($Value.Replace("'", "''"))'"
}

function Invoke-PostgresScalar {
    param([string]$Sql)

    $output = Invoke-ComposeCommand "exec" "-T" "db" "psql" "-U" "anomaly" "-d" "anomalyguard" "-tA" "-c" $Sql
    return (($output | Out-String).Trim())
}

function Invoke-PostgresRow {
    param([string]$Sql)

    $output = Invoke-ComposeCommand "exec" "-T" "db" "psql" "-U" "anomaly" "-d" "anomalyguard" "-tA" "-F" "|" "-c" $Sql
    return (($output | Out-String).Trim())
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

function Wait-ForJob {
    param(
        [string]$JobId,
        [hashtable]$Headers,
        [int]$TimeoutSeconds = 90
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $job = Invoke-JsonRequest -Method Get -Uri "$baseUrl/api/jobs/$JobId" -Headers $Headers
        if ($job.status -in @("succeeded", "failed")) {
            return $job
        }
        Start-Sleep -Seconds 2
    }

    throw "Job $JobId did not finish within $TimeoutSeconds seconds."
}

function Open-WebSocketClient {
    param([string]$Url)

    $webSocket = New-Object System.Net.WebSockets.ClientWebSocket
    $webSocket.Options.KeepAliveInterval = [TimeSpan]::FromSeconds(20)
    $cts = New-Object System.Threading.CancellationTokenSource
    try {
        $webSocket.ConnectAsync([Uri]$Url, $cts.Token).GetAwaiter().GetResult()
    } finally {
        $cts.Dispose()
    }
    return $webSocket
}

function Get-JsonPropertyValue {
    param(
        [object]$Object,
        [string]$Name
    )

    if ($null -eq $Object) {
        return $null
    }

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Receive-WebSocketJson {
    param(
        [System.Net.WebSockets.ClientWebSocket]$WebSocket,
        [int]$TimeoutSeconds = 15
    )

    $buffer = New-Object byte[] 4096
    $segment = New-Object 'System.ArraySegment[byte]' -ArgumentList @(,$buffer)
    $stream = New-Object System.IO.MemoryStream
    $cts = New-Object System.Threading.CancellationTokenSource
    $cts.CancelAfter([TimeSpan]::FromSeconds($TimeoutSeconds))

    try {
        do {
            $result = $WebSocket.ReceiveAsync($segment, $cts.Token).GetAwaiter().GetResult()
            if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
                throw "WebSocket closed by server."
            }
            if ($result.Count -gt 0) {
                $stream.Write($buffer, 0, $result.Count)
            }
        } while (-not $result.EndOfMessage)

        $jsonText = [System.Text.Encoding]::UTF8.GetString($stream.ToArray())
        return ($jsonText | ConvertFrom-Json)
    } catch [System.OperationCanceledException] {
        throw "Timed out waiting for WebSocket message."
    } finally {
        $cts.Dispose()
        $stream.Dispose()
    }
}

function Test-WebSocketEventMatch {
    param(
        [object]$Message,
        [string]$EventName,
        [string]$ExpectedStationId = "",
        [string]$ExpectedAlertId = "",
        [string]$ExpectedPayloadKey = "",
        [string]$ExpectedPayloadValue = ""
    )

    if ((Get-JsonPropertyValue $Message "event") -ne $EventName) {
        return $false
    }

    $payload = Get-JsonPropertyValue $Message "payload"
    if (-not [string]::IsNullOrWhiteSpace($ExpectedStationId)) {
        if ((Get-JsonPropertyValue $payload "station_id") -ne $ExpectedStationId) {
            return $false
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($ExpectedAlertId)) {
        $candidateAlertId = Get-JsonPropertyValue $payload "id"
        if ([string]::IsNullOrWhiteSpace($candidateAlertId)) {
            $candidateAlertId = Get-JsonPropertyValue $payload "alert_id"
        }
        if ($candidateAlertId -ne $ExpectedAlertId) {
            return $false
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($ExpectedPayloadKey)) {
        $candidateValue = Get-JsonPropertyValue $payload $ExpectedPayloadKey
        if ("$candidateValue" -ne $ExpectedPayloadValue) {
            return $false
        }
    }

    return $true
}

function Wait-ForWebSocketEvent {
    param(
        [System.Net.WebSockets.ClientWebSocket]$WebSocket,
        [System.Collections.ArrayList]$Buffer,
        [string]$EventName,
        [int]$TimeoutSeconds = 20,
        [string]$ExpectedStationId = "",
        [string]$ExpectedAlertId = "",
        [string]$ExpectedPayloadKey = "",
        [string]$ExpectedPayloadValue = ""
    )

    for ($index = 0; $index -lt $Buffer.Count; $index++) {
        $buffered = $Buffer[$index]
        if (Test-WebSocketEventMatch -Message $buffered -EventName $EventName -ExpectedStationId $ExpectedStationId -ExpectedAlertId $ExpectedAlertId -ExpectedPayloadKey $ExpectedPayloadKey -ExpectedPayloadValue $ExpectedPayloadValue) {
            $Buffer.RemoveAt($index)
            return $buffered
        }
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $remaining = [Math]::Max(1, [int][Math]::Ceiling(($deadline - (Get-Date)).TotalSeconds))
        $message = Receive-WebSocketJson -WebSocket $WebSocket -TimeoutSeconds $remaining
        if (Test-WebSocketEventMatch -Message $message -EventName $EventName -ExpectedStationId $ExpectedStationId -ExpectedAlertId $ExpectedAlertId -ExpectedPayloadKey $ExpectedPayloadKey -ExpectedPayloadValue $ExpectedPayloadValue) {
            return $message
        }
        [void]$Buffer.Add($message)
    }

    throw "Timed out waiting for WebSocket event '$EventName'."
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

$summary = [ordered]@{
    checked_at = [DateTime]::UtcNow.ToString("o")
    status = "running"
    error = ""
    station_id = ""
    alert_id = ""
    schema_revision = ""
    api = [ordered]@{}
    database = [ordered]@{}
    kafka = [ordered]@{}
    websocket = [ordered]@{
        bootstrap = [ordered]@{}
        observed_events = @()
    }
    device_credentials = [ordered]@{}
    jobs = [ordered]@{}
}
$stackStarted = $false
$webSocket = $null
$webSocketBuffer = New-Object System.Collections.ArrayList

try {
    Initialize-DockerCliConfig
    Assert-DockerDaemonAvailable

    if ($ManageStack) {
        & (Join-Path $PSScriptRoot "bootstrap-local-secrets.ps1")
        Invoke-ComposeCommand "up" "-d" "db" "redis" "kafka" "backend" "celery-worker" | Out-Host
        $stackStarted = $true
    }

    $health = Wait-ForApi -Url $baseUrl
    $summary.schema_revision = $health.schema_revision
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
    $metaBefore = Invoke-JsonRequest -Method Get -Uri "$baseUrl/api/meta" -Headers $authHeaders
    $webSocket = Open-WebSocketClient -Url "ws://localhost:8000/ws/stream"
    $bootstrapMessage = Wait-ForWebSocketEvent -WebSocket $webSocket -Buffer $webSocketBuffer -EventName "bootstrap" -TimeoutSeconds 20
    $bootstrapPayload = Get-JsonPropertyValue $bootstrapMessage "payload"
    Assert-Condition ($null -ne (Get-JsonPropertyValue $bootstrapPayload "meta")) "WebSocket bootstrap payload is missing meta."
    Assert-Condition ($null -ne (Get-JsonPropertyValue $bootstrapPayload "stations")) "WebSocket bootstrap payload is missing stations."
    Assert-Condition ($null -ne (Get-JsonPropertyValue $bootstrapPayload "readings")) "WebSocket bootstrap payload is missing readings."
    Assert-Condition ($null -ne (Get-JsonPropertyValue $bootstrapPayload "alerts")) "WebSocket bootstrap payload is missing alerts."
    Assert-Condition ($null -ne (Get-JsonPropertyValue $bootstrapPayload "device_statuses")) "WebSocket bootstrap payload is missing device_statuses."
    Assert-Condition ((Get-JsonPropertyValue (Get-JsonPropertyValue $bootstrapPayload "meta") "schema_revision") -eq $health.schema_revision) "WebSocket bootstrap schema revision does not match /health."
    $summary.websocket.bootstrap = [ordered]@{
        schema_revision = Get-JsonPropertyValue (Get-JsonPropertyValue $bootstrapPayload "meta") "schema_revision"
        stations = @((Get-JsonPropertyValue $bootstrapPayload "stations")).Count
        readings = @((Get-JsonPropertyValue $bootstrapPayload "readings")).Count
        alerts = @((Get-JsonPropertyValue $bootstrapPayload "alerts")).Count
        device_statuses = @((Get-JsonPropertyValue $bootstrapPayload "device_statuses")).Count
    }
    $stationId = "integration-device-$([Guid]::NewGuid().ToString('N').Substring(0, 8))"
    $summary.station_id = $stationId

    $rotateResponse = Invoke-JsonRequest `
        -Method Post `
        -Uri "$baseUrl/api/device/credentials/$stationId/rotate" `
        -Headers $authHeaders `
        -Body @{ note = "Integration smoke rotation" }
    Assert-Condition ($rotateResponse.station_id -eq $stationId) "Rotate endpoint returned wrong station."
    Assert-Condition ($rotateResponse.issued_key.Length -gt 20) "Rotate endpoint did not issue a usable key."
    $summary.device_credentials.rotate_event_type = $rotateResponse.event_type
    $summary.device_credentials.key_fingerprint = $rotateResponse.key_fingerprint
    $rotateWsEvent = Wait-ForWebSocketEvent -WebSocket $webSocket -Buffer $webSocketBuffer -EventName "device_credential_event" -TimeoutSeconds 20 -ExpectedStationId $stationId -ExpectedPayloadKey "event_type" -ExpectedPayloadValue $rotateResponse.event_type
    $summary.websocket.observed_events += [ordered]@{
        event = Get-JsonPropertyValue $rotateWsEvent "event"
        station_id = Get-JsonPropertyValue (Get-JsonPropertyValue $rotateWsEvent "payload") "station_id"
        event_type = Get-JsonPropertyValue (Get-JsonPropertyValue $rotateWsEvent "payload") "event_type"
    }

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
    $summary.alert_id = $telemetryResponse.generated_alert.id
    $summary.api.generated_alert = [ordered]@{
        id = $telemetryResponse.generated_alert.id
        station_id = $telemetryResponse.generated_alert.station_id
        severity = $telemetryResponse.generated_alert.severity
        score = $telemetryResponse.generated_alert.score
    }
    $deviceStatusWsEvent = Wait-ForWebSocketEvent -WebSocket $webSocket -Buffer $webSocketBuffer -EventName "device_status" -TimeoutSeconds 20 -ExpectedStationId $stationId
    $readingWsEvent = Wait-ForWebSocketEvent -WebSocket $webSocket -Buffer $webSocketBuffer -EventName "reading" -TimeoutSeconds 20 -ExpectedStationId $stationId
    $alertWsEvent = Wait-ForWebSocketEvent -WebSocket $webSocket -Buffer $webSocketBuffer -EventName "alert" -TimeoutSeconds 20 -ExpectedStationId $stationId -ExpectedAlertId $telemetryResponse.generated_alert.id
    $summary.websocket.observed_events += [ordered]@{
        event = Get-JsonPropertyValue $deviceStatusWsEvent "event"
        station_id = Get-JsonPropertyValue (Get-JsonPropertyValue $deviceStatusWsEvent "payload") "station_id"
    }
    $summary.websocket.observed_events += [ordered]@{
        event = Get-JsonPropertyValue $readingWsEvent "event"
        station_id = Get-JsonPropertyValue (Get-JsonPropertyValue $readingWsEvent "payload") "station_id"
    }
    $summary.websocket.observed_events += [ordered]@{
        event = Get-JsonPropertyValue $alertWsEvent "event"
        station_id = Get-JsonPropertyValue (Get-JsonPropertyValue $alertWsEvent "payload") "station_id"
        alert_id = Get-JsonPropertyValue (Get-JsonPropertyValue $alertWsEvent "payload") "id"
    }

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
    $apiAlert = $alerts | Where-Object { $_.id -eq $telemetryResponse.generated_alert.id } | Select-Object -First 1
    Assert-Condition ($null -ne $apiAlert) "Alert feed did not return the generated alert id."
    $summary.api.latest_alert = [ordered]@{
        id = $apiAlert.id
        station_id = $apiAlert.station_id
        severity = $apiAlert.severity
        score = $apiAlert.score
        incident_status = $apiAlert.incident_status
    }

    $stationSql = Format-SqlLiteral $stationId
    $alertSql = Format-SqlLiteral $telemetryResponse.generated_alert.id
    $dbAlertRow = Invoke-PostgresRow "SELECT id, station_id, severity, score::text FROM alerts WHERE id = $alertSql LIMIT 1;"
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($dbAlertRow)) "Alert record was not persisted to PostgreSQL."
    $dbAlertParts = $dbAlertRow.Split("|")
    Assert-Condition ($dbAlertParts.Length -ge 4) "Alert record query returned an unexpected shape."
    Assert-Condition ($dbAlertParts[0] -eq $telemetryResponse.generated_alert.id) "PostgreSQL alert id does not match API alert."
    Assert-Condition ($dbAlertParts[1] -eq $stationId) "PostgreSQL alert station does not match API alert."
    Assert-Condition ($dbAlertParts[2] -eq $telemetryResponse.generated_alert.severity) "PostgreSQL alert severity does not match API alert."

    $readingCount = [int](Invoke-PostgresScalar "SELECT COUNT(*) FROM readings WHERE station_id = $stationSql;")
    $alertCount = [int](Invoke-PostgresScalar "SELECT COUNT(*) FROM alerts WHERE station_id = $stationSql;")
    $incidentCount = [int](Invoke-PostgresScalar "SELECT COUNT(*) FROM incidents WHERE station_id = $stationSql;")
    $incidentEventCount = [int](Invoke-PostgresScalar "SELECT COUNT(*) FROM incident_events WHERE alert_id = $alertSql;")
    $deviceStateCount = [int](Invoke-PostgresScalar "SELECT COUNT(*) FROM device_states WHERE station_id = $stationSql;")
    Assert-Condition ($readingCount -ge 1) "Expected at least one reading record for the integration station."
    Assert-Condition ($alertCount -ge 1) "Expected at least one alert record for the integration station."
    Assert-Condition ($incidentCount -ge 1) "Expected an incident record for the integration station."
    Assert-Condition ($incidentEventCount -ge 1) "Expected at least one incident history entry for the integration alert."
    Assert-Condition ($deviceStateCount -eq 1) "Expected exactly one device state record for the integration station."
    $summary.database = [ordered]@{
        readings = $readingCount
        alerts = $alertCount
        incidents = $incidentCount
        incident_events = $incidentEventCount
        device_states = $deviceStateCount
        alert_row = [ordered]@{
            id = $dbAlertParts[0]
            station_id = $dbAlertParts[1]
            severity = $dbAlertParts[2]
            score = $dbAlertParts[3]
        }
    }

    $auditEntries = Invoke-JsonRequest `
        -Method Get `
        -Uri "$baseUrl/api/device/credentials/audit?station_id=$stationId&limit=10" `
        -Headers $authHeaders
    Assert-Condition (($auditEntries | Measure-Object).Count -ge 1) "Device credential audit is empty."
    Assert-Condition ($auditEntries[0].event_type -in @("provisioned", "rotated")) "Unexpected audit event type."
    $summary.device_credentials.audit_events_before_revoke = ($auditEntries | Measure-Object).Count

    $inventory = Invoke-JsonRequest -Method Get -Uri "$baseUrl/api/device/credentials" -Headers $authHeaders
    Assert-Condition (($inventory | Where-Object { $_.station_id -eq $stationId }).Count -eq 1) "Credential inventory missing rotated device."
    $summary.device_credentials.inventory_count_before_revoke = (($inventory | Where-Object { $_.station_id -eq $stationId }) | Measure-Object).Count

    $ackResponse = Invoke-JsonRequest `
        -Method Post `
        -Uri "$baseUrl/api/incidents/$($telemetryResponse.generated_alert.id)/acknowledge" `
        -Headers $authHeaders `
        -Body @{ note = "Integration smoke acknowledge" }
    Assert-Condition ($ackResponse.incident_status -eq "acknowledged") "Incident acknowledge did not persist the expected status."
    $incidentWsEvent = Wait-ForWebSocketEvent -WebSocket $webSocket -Buffer $webSocketBuffer -EventName "incident_status" -TimeoutSeconds 20 -ExpectedStationId $stationId -ExpectedAlertId $telemetryResponse.generated_alert.id
    $summary.websocket.observed_events += [ordered]@{
        event = Get-JsonPropertyValue $incidentWsEvent "event"
        station_id = Get-JsonPropertyValue (Get-JsonPropertyValue $incidentWsEvent "payload") "station_id"
        alert_id = Get-JsonPropertyValue (Get-JsonPropertyValue $incidentWsEvent "payload") "id"
        incident_status = Get-JsonPropertyValue (Get-JsonPropertyValue $incidentWsEvent "payload") "incident_status"
    }

    $reviewResponse = Invoke-JsonRequest `
        -Method Post `
        -Uri "$baseUrl/api/alerts/$($telemetryResponse.generated_alert.id)/review" `
        -Headers $authHeaders `
        -Body @{ label = "true_anomaly"; note = "Integration smoke review" }
    Assert-Condition ($reviewResponse.review_label -eq "true_anomaly") "Alert review did not persist the expected label."
    $reviewWsEvent = Wait-ForWebSocketEvent -WebSocket $webSocket -Buffer $webSocketBuffer -EventName "alert_review" -TimeoutSeconds 20 -ExpectedStationId $stationId -ExpectedAlertId $telemetryResponse.generated_alert.id
    $summary.api.reviewed_alert = [ordered]@{
        id = $reviewResponse.id
        review_label = $reviewResponse.review_label
        reviewed_by = $reviewResponse.reviewed_by
    }
    $summary.websocket.observed_events += [ordered]@{
        event = Get-JsonPropertyValue $reviewWsEvent "event"
        station_id = Get-JsonPropertyValue (Get-JsonPropertyValue $reviewWsEvent "payload") "station_id"
        alert_id = Get-JsonPropertyValue (Get-JsonPropertyValue $reviewWsEvent "payload") "id"
        review_label = Get-JsonPropertyValue (Get-JsonPropertyValue $reviewWsEvent "payload") "review_label"
    }

    $trainingJob = Invoke-JsonRequest `
        -Method Post `
        -Uri "$baseUrl/api/alerts/labeled/retraining-jobs" `
        -Headers $authHeaders `
        -Body @{
            station_id = $stationId
            since_minutes = 60
            limit = 100
            recent_count = 10
        }
    Assert-Condition ($trainingJob.job_type -eq "prepare_retraining_run") "Retraining prep endpoint returned the wrong job type."

    $completedTrainingJob = Wait-ForJob -JobId $trainingJob.id -Headers $authHeaders -TimeoutSeconds 90
    Assert-Condition ($completedTrainingJob.status -eq "succeeded") "Retraining prep job did not succeed."
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($completedTrainingJob.started_at)) "Retraining prep job never recorded started_at."
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($completedTrainingJob.completed_at)) "Retraining prep job never recorded completed_at."
    Assert-Condition ($completedTrainingJob.result_payload.manifest.manifest_id.Length -gt 0) "Retraining prep job manifest is missing."
    Assert-Condition ($completedTrainingJob.result_payload.export_urls.json.Length -gt 0) "Retraining prep job export URLs are missing."
    $summary.jobs.retraining_job = [ordered]@{
        id = $completedTrainingJob.id
        status = $completedTrainingJob.status
        started_at = $completedTrainingJob.started_at
        completed_at = $completedTrainingJob.completed_at
        ready_for_training = $completedTrainingJob.result_payload.ready_for_training
        recommendation = $completedTrainingJob.result_payload.recommendation
        manifest_id = $completedTrainingJob.result_payload.manifest.manifest_id
    }

    $jobSql = Format-SqlLiteral $completedTrainingJob.id
    $dbJobRow = Invoke-PostgresRow "SELECT id, job_type, status, COALESCE(started_at::text, ''), COALESCE(completed_at::text, '') FROM jobs WHERE id = $jobSql LIMIT 1;"
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($dbJobRow)) "Retraining job record was not persisted to PostgreSQL."
    $dbJobParts = $dbJobRow.Split("|")
    Assert-Condition ($dbJobParts.Length -ge 5) "Job record query returned an unexpected shape."
    Assert-Condition ($dbJobParts[0] -eq $completedTrainingJob.id) "PostgreSQL job id does not match API job."
    Assert-Condition ($dbJobParts[1] -eq "prepare_retraining_run") "PostgreSQL job type does not match retraining flow."
    Assert-Condition ($dbJobParts[2] -eq "succeeded") "PostgreSQL job status does not match API job."
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($dbJobParts[3])) "PostgreSQL job started_at is missing."
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($dbJobParts[4])) "PostgreSQL job completed_at is missing."
    $summary.jobs.database_row = [ordered]@{
        id = $dbJobParts[0]
        job_type = $dbJobParts[1]
        status = $dbJobParts[2]
        started_at = $dbJobParts[3]
        completed_at = $dbJobParts[4]
    }

    $metaAfterTrainingJob = Invoke-JsonRequest -Method Get -Uri "$baseUrl/api/meta" -Headers $authHeaders
    Assert-Condition ($metaAfterTrainingJob.data_source -eq $metaBefore.data_source -or $metaAfterTrainingJob.data_source -eq "device/esp32") "Retraining job unexpectedly changed runtime data_source."
    $summary.jobs.meta_after_retraining = [ordered]@{
        data_source = $metaAfterTrainingJob.data_source
        last_ingest_note = $metaAfterTrainingJob.last_ingest_note
    }

    $consumerOutput = Invoke-ComposeCommand "exec" "-T" "kafka" "sh" "-lc" "/opt/bitnami/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic anomaly-alerts --from-beginning --timeout-ms 10000 --max-messages 20"
    $consumerLines = @($consumerOutput | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $matchingKafkaLines = @($consumerLines | Where-Object { $_ -match $stationId })
    Assert-Condition ($matchingKafkaLines.Count -ge 1) "Kafka topic did not contain the integration alert."
    $matchingKafkaMessage = $null
    foreach ($line in $matchingKafkaLines) {
        try {
            $message = $line | ConvertFrom-Json
        } catch {
            continue
        }
        if ($message.id -eq $telemetryResponse.generated_alert.id) {
            $matchingKafkaMessage = $message
            break
        }
    }
    Assert-Condition ($null -ne $matchingKafkaMessage) "Kafka topic did not contain the generated alert id."
    Assert-Condition ($matchingKafkaMessage.station_id -eq $stationId) "Kafka alert station does not match API alert."
    Assert-Condition ($matchingKafkaMessage.severity -eq $telemetryResponse.generated_alert.severity) "Kafka alert severity does not match API alert."
    $summary.kafka = [ordered]@{
        matched_messages = $matchingKafkaLines.Count
        alert = [ordered]@{
            id = $matchingKafkaMessage.id
            station_id = $matchingKafkaMessage.station_id
            severity = $matchingKafkaMessage.severity
            score = $matchingKafkaMessage.score
        }
    }

    $revokeResponse = Invoke-JsonRequest `
        -Method Post `
        -Uri "$baseUrl/api/device/credentials/$stationId/revoke" `
        -Headers $authHeaders `
        -Body @{ note = "Integration smoke revoke" }
    Assert-Condition ($revokeResponse.event_type -eq "revoked") "Revoke endpoint did not return a revoke event."
    $summary.device_credentials.revoke_event_type = $revokeResponse.event_type
    $revokeWsEvent = Wait-ForWebSocketEvent -WebSocket $webSocket -Buffer $webSocketBuffer -EventName "device_credential_event" -TimeoutSeconds 20 -ExpectedStationId $stationId -ExpectedPayloadKey "event_type" -ExpectedPayloadValue "revoked"
    $summary.websocket.observed_events += [ordered]@{
        event = Get-JsonPropertyValue $revokeWsEvent "event"
        station_id = Get-JsonPropertyValue (Get-JsonPropertyValue $revokeWsEvent "payload") "station_id"
        event_type = Get-JsonPropertyValue (Get-JsonPropertyValue $revokeWsEvent "payload") "event_type"
    }

    $inventoryAfterRevoke = Invoke-JsonRequest -Method Get -Uri "$baseUrl/api/device/credentials" -Headers $authHeaders
    Assert-Condition (($inventoryAfterRevoke | Where-Object { $_.station_id -eq $stationId }).Count -eq 0) "Revoked device still present in inventory."
    $credentialEventCount = [int](Invoke-PostgresScalar "SELECT COUNT(*) FROM device_credential_events WHERE station_id = $stationSql;")
    Assert-Condition ($credentialEventCount -ge 2) "Expected both rotate and revoke credential events in PostgreSQL."
    $summary.device_credentials.inventory_count_after_revoke = (($inventoryAfterRevoke | Where-Object { $_.station_id -eq $stationId }) | Measure-Object).Count
    $summary.device_credentials.audit_events_in_db = $credentialEventCount

    $summary.status = "passed"
    Write-Host "Integration smoke passed for station $stationId"
} catch {
    $summary.status = "failed"
    $summary.error = $_.Exception.Message
    throw
} finally {
    if (-not [string]::IsNullOrWhiteSpace($SummaryPath)) {
        $summaryDir = Split-Path -Parent $SummaryPath
        if (-not [string]::IsNullOrWhiteSpace($summaryDir)) {
            New-Item -ItemType Directory -Force -Path $summaryDir | Out-Null
        }
        $summary | ConvertTo-Json -Depth 10 | Set-Content -Path $SummaryPath
    }

    if ($null -ne $webSocket) {
        try {
            if ($webSocket.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
                $cts = New-Object System.Threading.CancellationTokenSource
                try {
                    $webSocket.CloseAsync(
                        [System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
                        "integration-complete",
                        $cts.Token
                    ).GetAwaiter().GetResult()
                } finally {
                    $cts.Dispose()
                }
            }
        } catch {
        } finally {
            $webSocket.Dispose()
        }
    }

    if ($ManageStack -and $stackStarted) {
        Invoke-ComposeCommand "down" "-v" | Out-Host
    }
}
