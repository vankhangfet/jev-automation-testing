# Demo runner (PowerShell): load demo\.env (or repo-root .env), then check
# the demo login screenshots. Results land in demo\reports\check-*\.
#
# Usage:  .\demo\run.ps1              (extra CLI flags pass through)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) { $envFile = Join-Path $root ".env" }
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line -split "=", 2
            if ($parts.Count -eq 2 -and $parts[0].Trim()) {
                Set-Item -Path ("Env:" + $parts[0].Trim()) -Value $parts[1].Trim()
            }
        }
    }
    Write-Host "Loaded env from $envFile"
} else {
    Write-Host "No .env found (looked in demo\ and repo root) - using current shell env."
}

Push-Location $root
uv run python -m jev_ui_agent check-screenshots `
    --dir demo/screens/login `
    --rules demo/rules/login.yaml `
    --out demo/reports @args
$code = $LASTEXITCODE
Pop-Location
exit $code
