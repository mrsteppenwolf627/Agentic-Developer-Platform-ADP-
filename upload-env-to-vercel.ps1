#Requires -Version 5.1
# upload-env-to-vercel.ps1
# Uploads all variables from .env to Vercel.
#
# Strategy:
#   production  -> vercel CLI (stdin pipe) — works reliably
#   preview     -> Vercel REST API — needed because CLI v51 requires --value flag
#                  for preview, which doesn't handle special chars well in cmd.exe
#
# Idempotent: removes existing vars before re-adding.
# Usage: powershell -ExecutionPolicy Bypass -File .\upload-env-to-vercel.ps1

$ErrorActionPreference = "Continue"

$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }
$envFile = Join-Path $root ".env"

# Vercel project identifiers (from .vercel/project.json)
$VERCEL_PROJECT_ID = "prj_zXsh4cnP6YDbxbIk4iPXfz9wvt6t"
$VERCEL_TEAM_ID    = "team_971ED0I0LMSbaiEMZhMRmjFd"
$VERCEL_AUTH_FILE  = "$env:APPDATA\com.vercel.cli\Data\auth.json"

if (-not (Get-Command vercel -ErrorAction SilentlyContinue)) {
    Write-Error "vercel CLI not found. Install with: npm install -g vercel"
    exit 1
}
if (-not (Test-Path $envFile)) {
    Write-Error ".env not found at: $envFile"
    exit 1
}

# Read auth token for REST API calls
$authToken = $null
if (Test-Path $VERCEL_AUTH_FILE) {
    $authToken = (Get-Content $VERCEL_AUTH_FILE -Raw | ConvertFrom-Json).token
}

# Parse .env: split on FIRST '=' only, preserving special chars in value
$vars = [ordered]@{}
foreach ($line in (Get-Content $envFile -Encoding UTF8)) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
    $idx = $trimmed.IndexOf('=')
    if ($idx -le 0) { continue }
    $k = $trimmed.Substring(0, $idx).Trim()
    $v = $trimmed.Substring($idx + 1)
    if ($k) { $vars[$k] = $v }
}

Write-Host ""
Write-Host "=== Vercel env upload ==="
Write-Host "Variables : $($vars.Count)"
Write-Host ""

# ------------------------------------------------------------------ #
# Production: vercel CLI via stdin (handles special chars cleanly)    #
# ------------------------------------------------------------------ #
function Add-ToProduction {
    param([string]$Key, [string]$Value)

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName               = "cmd.exe"
    $psi.Arguments              = "/c vercel env add `"$Key`" production"
    $psi.UseShellExecute        = $false
    $psi.RedirectStandardInput  = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true

    $proc = [System.Diagnostics.Process]::new()
    $proc.StartInfo = $psi
    $null = $proc.Start()
    $proc.StandardInput.Write($Value)
    $proc.StandardInput.Close()

    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $null   = $proc.WaitForExit(30000)

    return @{ ExitCode = $proc.ExitCode; Output = ($stdout + $stderr).Trim() }
}

# ------------------------------------------------------------------ #
# Preview: Vercel REST API (CLI v51 requires --value flag for preview) #
# ------------------------------------------------------------------ #
function Add-ToPreview {
    param([string]$Key, [string]$Value, [string]$Token, [string]$ProjectId, [string]$TeamId)

    if (-not $Token) {
        return @{ ExitCode = 1; Output = "No auth token found at $VERCEL_AUTH_FILE" }
    }
    $url     = "https://api.vercel.com/v10/projects/$ProjectId/env?teamId=$TeamId"
    $headers = @{ Authorization = "Bearer $Token"; "Content-Type" = "application/json" }
    $body    = @{ key = $Key; value = $Value; type = "encrypted"; target = @("preview") } | ConvertTo-Json

    try {
        $null = Invoke-RestMethod -Uri $url -Method Post -Headers $headers -Body $body -ErrorAction Stop
        return @{ ExitCode = 0; Output = "" }
    } catch {
        $msg = $_.ErrorDetails.Message
        if ($msg -match "ENV_CONFLICT") {
            return @{ ExitCode = 0; Output = "already exists" }
        }
        return @{ ExitCode = 1; Output = $msg }
    }
}

$ok = 0; $fail = 0; $failedItems = @()
$i = 0; $total = $vars.Count * 2   # production + preview

foreach ($key in $vars.Keys) {
    $val = $vars[$key]

    # --- production ---
    $i++
    Write-Host "  [$i/$total] $key -> production ..." -NoNewline
    $null = & cmd /c "vercel env rm `"$key`" production --yes" 2>&1
    $r = Add-ToProduction -Key $key -Value $val
    if ($r.ExitCode -eq 0) { $ok++; Write-Host " OK" -ForegroundColor Green }
    else {
        $fail++; $failedItems += "$key (production)"
        Write-Host " FAILED" -ForegroundColor Red
        if ($r.Output) { Write-Host "      $($r.Output -replace '`n',' ')" -ForegroundColor DarkYellow }
    }

    # --- preview (REST API) ---
    $i++
    Write-Host "  [$i/$total] $key -> preview ..." -NoNewline
    # Remove via CLI first (best-effort)
    $null = & cmd /c "vercel env rm `"$key`" preview --yes" 2>&1
    $r = Add-ToPreview -Key $key -Value $val -Token $authToken -ProjectId $VERCEL_PROJECT_ID -TeamId $VERCEL_TEAM_ID
    if ($r.ExitCode -eq 0) {
        $ok++
        $suffix = if ($r.Output) { " ($($r.Output))" } else { "" }
        Write-Host " OK$suffix" -ForegroundColor Green
    } else {
        $fail++; $failedItems += "$key (preview)"
        Write-Host " FAILED" -ForegroundColor Red
        if ($r.Output) { Write-Host "      $($r.Output -replace '`n',' ')" -ForegroundColor DarkYellow }
    }
}

Write-Host ""
Write-Host "==========================="
Write-Host "Uploaded : $ok / $total"
if ($fail -gt 0) {
    Write-Host "Failed   : $fail" -ForegroundColor Red
    foreach ($item in $failedItems) { Write-Host "  - $item" -ForegroundColor Red }
} else {
    Write-Host "Failed   : 0" -ForegroundColor Green
}
Write-Host "==========================="
Write-Host ""
