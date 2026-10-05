# Screenshot-folder example runner (PowerShell): load this folder's .env
# (or repo-root .env), then check the demo login screenshots.
# Results land in examples\screenshot-folder\reports\check-*\.
#
# Usage:  .\examples\screenshot-folder\run.ps1    (extra CLI flags pass through)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # repo root

$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) { $envFile = Join-Path $root ".env" }
if (Test-Path $envFile) {
    Get-Content -Encoding UTF8 $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line -split "=", 2
            if ($parts.Count -eq 2 -and $parts[0].Trim()) {
                $v = ($parts[1].Trim() -split "\s+#", 2)[0]  # drop inline comment
                if ($v.Length -ge 2 -and (
                    ($v.StartsWith('"') -and $v.EndsWith('"')) -or
                    ($v.StartsWith("'") -and $v.EndsWith("'")))) {
                    $v = $v.Substring(1, $v.Length - 2)      # drop matching quotes
                }
                Set-Item -Path ("Env:" + $parts[0].Trim()) -Value $v
            }
        }
    }
    Write-Host "Loaded env from $envFile"
} else {
    Write-Host "No .env found (looked in this folder and repo root) - using current shell env."
}

Push-Location $root
uv run python -m jev_ui_agent check-screenshots `
    --dir examples/screenshot-folder/screens/login `
    --rules examples/screenshot-folder/rules/login.yaml `
    --out examples/screenshot-folder/reports @args
$code = $LASTEXITCODE
Pop-Location
exit $code
