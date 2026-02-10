# Verification script for Windows PowerShell
# Run: .\scripts\verify.ps1

$ErrorActionPreference = "Stop"
$ArtifactsDir = "artifacts\verify"

Write-Host "=== QA Verification Script ===" -ForegroundColor Cyan
Write-Host "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Commit: $(git rev-parse HEAD)"
Write-Host "Python: $(python --version)"
Write-Host ""

# Create artifacts directory
New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null

# Step 1: Unit + Integration tests
Write-Host "=== Running Unit + Integration Tests ===" -ForegroundColor Yellow
python -m pytest tests/test_critical_flows.py tests/test_mvp_invariants.py tests/test_balance_idempotency.py -v --tb=short 2>&1 | Tee-Object -FilePath "$ArtifactsDir\unit_integration.txt"
$unitResult = $LASTEXITCODE

# Step 2: Bot smoke tests
Write-Host "=== Running Bot Smoke Tests ===" -ForegroundColor Yellow
python -m pytest tests/test_callbacks_smoke.py tests/test_buttons_smoke.py tests/test_confirm_generation_20clicks_single_charge.py -v --tb=short 2>&1 | Tee-Object -FilePath "$ArtifactsDir\bot_smoke.txt"
$botResult = $LASTEXITCODE

# Step 3: Webapp integration tests
Write-Host "=== Running Mini App Smoke Tests ===" -ForegroundColor Yellow
python -m pytest tests/test_webapp_integration.py -v --tb=short 2>&1 | Tee-Object -FilePath "$ArtifactsDir\miniapp_smoke.txt"
$miniappResult = $LASTEXITCODE

# Summary
Write-Host ""
Write-Host "=== SUMMARY ===" -ForegroundColor Cyan
Write-Host "Unit/Integration: $(if($unitResult -eq 0){'PASS'}else{'FAIL'})"
Write-Host "Bot Smoke: $(if($botResult -eq 0){'PASS'}else{'FAIL'})"
Write-Host "Mini App Smoke: $(if($miniappResult -eq 0){'PASS'}else{'FAIL'})"

# Create summary JSON
$summary = @{
    timestamp = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss')
    commit = (git rev-parse HEAD)
    unit_integration = if($unitResult -eq 0){"PASS"}else{"FAIL"}
    bot_smoke = if($botResult -eq 0){"PASS"}else{"FAIL"}
    miniapp_smoke = if($miniappResult -eq 0){"PASS"}else{"FAIL"}
    overall = if(($unitResult -eq 0) -and ($botResult -eq 0) -and ($miniappResult -eq 0)){"PASS"}else{"FAIL"}
}
$summary | ConvertTo-Json | Out-File "$ArtifactsDir\summary.json" -Encoding UTF8

if (($unitResult -ne 0) -or ($botResult -ne 0) -or ($miniappResult -ne 0)) {
    Write-Host "VERIFICATION FAILED" -ForegroundColor Red
    exit 1
} else {
    Write-Host "VERIFICATION PASSED" -ForegroundColor Green
    exit 0
}
