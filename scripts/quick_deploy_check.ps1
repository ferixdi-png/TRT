# Quick deploy check script for PowerShell
# Checks Render deploy status and fetches recent logs

param(
    [int]$Minutes = 30
)

$ErrorActionPreference = "Stop"

# Load config
$desktop = [Environment]::GetFolderPath("Desktop")
$envFile = Join-Path $desktop "TRT_RENDER.env"

if (-not (Test-Path $envFile)) {
    Write-Host "❌ Config file not found: $envFile"
    Write-Host "   Create it with RENDER_API_KEY and RENDER_SERVICE_ID"
    exit 1
}

# Parse config
$config = @{}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') {
        $config[$matches[1].Trim()] = $matches[2].Trim()
    }
}

$apiKey = $config["RENDER_API_KEY"]
$serviceId = $config["RENDER_SERVICE_ID"]

if (-not $apiKey -or -not $serviceId) {
    Write-Host "❌ RENDER_API_KEY or RENDER_SERVICE_ID missing"
    exit 1
}

Write-Host "🔍 Checking deploy status for service: $serviceId"
Write-Host ""

# Check latest deploy
$deployUrl = "https://api.render.com/v1/services/$serviceId/deploys?limit=1"
$headers = @{
    "Authorization" = "Bearer $apiKey"
    "Accept" = "application/json"
}

try {
    $deployResponse = Invoke-RestMethod -Uri $deployUrl -Headers $headers -Method Get
    $latestDeploy = if ($deployResponse -is [Array]) { $deployResponse[0] } else { $deployResponse.deploys[0] }
    
    if ($latestDeploy) {
        Write-Host "✅ Latest Deploy:"
        Write-Host "   Status: $($latestDeploy.status)"
        Write-Host "   Created: $($latestDeploy.createdAt)"
        Write-Host "   Finished: $($latestDeploy.finishedAt)"
        Write-Host "   Commit: $($latestDeploy.commit.id)"
        Write-Host ""
    }
} catch {
    Write-Host "⚠️  Failed to check deploy status: $_"
}

# Fetch recent logs
$since = (Get-Date).AddMinutes(-$Minutes).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$logsUrl = "https://api.render.com/v1/services/$serviceId/logs"
$logsParams = @{
    since = $since
    limit = 500
}

Write-Host "📥 Fetching logs (last $Minutes minutes)..."
try {
    $logsResponse = Invoke-RestMethod -Uri $logsUrl -Headers $headers -Method Get -Body $logsParams
    $logs = if ($logsResponse.logs) { $logsResponse.logs } else { $logsResponse }
    
    if ($logs -is [String]) {
        $logLines = $logs -split "`n"
    } elseif ($logs -is [Array]) {
        $logLines = $logs | ForEach-Object { if ($_ -is [String]) { $_ } else { $_.message } }
    } else {
        $logLines = @()
    }
    
    Write-Host "✅ Fetched $($logLines.Count) log lines"
    Write-Host ""
    
    # Analyze
    $errors = $logLines | Select-String -Pattern "error|exception|traceback" -CaseSensitive:$false
    $importErrors = $logLines | Select-String -Pattern "import.*error|cannot import" -CaseSensitive:$false
    $tracebacks = $logLines | Select-String -Pattern "traceback|File.*line" -CaseSensitive:$false
    
    Write-Host "📊 Analysis:"
    Write-Host "   Total lines: $($logLines.Count)"
    Write-Host "   Errors/Exceptions: $($errors.Count)"
    Write-Host "   Import Errors: $($importErrors.Count)"
    Write-Host "   Tracebacks: $($tracebacks.Count)"
    Write-Host ""
    
    if ($importErrors) {
        Write-Host "⚠️  IMPORT ERRORS FOUND:"
        $importErrors | Select-Object -First 5 | ForEach-Object { Write-Host "   - $($_.Line.Substring(0, [Math]::Min(100, $_.Line.Length)))" }
        Write-Host ""
    }
    
    if ($tracebacks) {
        Write-Host "⚠️  TRACEBACKS FOUND:"
        $tracebacks | Select-Object -First 3 | ForEach-Object { Write-Host "   - $($_.Line.Substring(0, [Math]::Min(100, $_.Line.Length)))" }
        Write-Host ""
    }
    
    if (-not $importErrors -and -not $tracebacks) {
        Write-Host "✅ NO CRITICAL ERRORS (ImportError/Traceback) in startup logs!"
    }
    
    # Save to artifacts
    $artifactsDir = Join-Path $PSScriptRoot ".." "artifacts"
    New-Item -ItemType Directory -Force -Path $artifactsDir | Out-Null
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $outputFile = Join-Path $artifactsDir "render_logs_after_$timestamp.txt"
    $logLines | Out-File -FilePath $outputFile -Encoding UTF8
    Write-Host "Saved logs to: $outputFile"
    
} catch {
    Write-Host "❌ Failed to fetch logs: $_"
    exit 1
}

