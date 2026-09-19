<#
Builds DataRework.exe and SerialStoreSync.exe from DataRework.spec.

Why this exists rather than calling pyinstaller directly: once the sync service
is installed, NSSM keeps dist\SerialStoreSync.exe open, and PyInstaller fails
with "WinError 5: Access is denied" when it tries to overwrite it. This stops
the service first and restarts it afterwards (only if it was running before).

.env is bundled into both exes by the spec, so dist\ ships without a plaintext
credentials file. That is obfuscation, NOT encryption -- the onefile archive can
be unpacked to recover .env. Treat dist\*.exe as secret material.

Usage (elevated prompt, for the service stop/start):
    powershell -ExecutionPolicy Bypass -File build.ps1
#>
[CmdletBinding()]
param(
    # Skip the service stop/start; fails if the service currently holds the exe.
    [switch]$SkipService
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$ServiceName = 'DataReworkSerialStoreSync'
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

function Get-ServiceStateOrNull {
    # Get-Service errors when the service isn't installed; treat that as
    # "absent" rather than failing, since a first-time build has no service yet.
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($null -eq $svc) { return $null }
    return $svc.Status
}

# --- preflight ---------------------------------------------------------------
if (-not (Test-Path -LiteralPath '.env')) {
    throw ".env not found in $PSScriptRoot. The spec bundles it into both exes, so the build cannot proceed without it."
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtualenv interpreter not found at $Python."
}

$wasRunning = $false

if (-not $SkipService -and (Get-ServiceStateOrNull) -eq 'Running') {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        throw "$ServiceName is running and holds dist\SerialStoreSync.exe, but stopping it needs elevation. Re-run from an administrator prompt, or pass -SkipService if you only changed the GUI."
    }
    Write-Host "Stopping $ServiceName ..." -ForegroundColor Cyan
    Stop-Service -Name $ServiceName
    (Get-Service -Name $ServiceName).WaitForStatus('Stopped', '00:00:30')
    $wasRunning = $true
}

# Stopping the service is not always enough: running an exe by hand to test it
# leaves a process holding the file, and PyInstaller then fails with a bare
# "WinError 5: Access is denied" that says nothing about why.
$held = Get-CimInstance Win32_Process |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith(
        (Join-Path $PSScriptRoot 'dist'), [StringComparison]::OrdinalIgnoreCase) }
if ($held) {
    $detail = ($held | ForEach-Object { "  PID $($_.ProcessId)  $($_.ExecutablePath)" }) -join "`n"
    throw "These processes still hold files in dist\ and would make PyInstaller fail:`n$detail`nClose them (or Stop-Process -Id <pid> -Force) and re-run."
}

# --- build -------------------------------------------------------------------
try {
    Write-Host 'Running PyInstaller ...' -ForegroundColor Cyan
    & $Python -m PyInstaller --noconfirm DataRework.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
}
finally {
    # Restart even if the build failed, so a broken build never leaves the sync
    # loop permanently stopped.
    if ($wasRunning) {
        Write-Host "Starting $ServiceName ..." -ForegroundColor Cyan
        Start-Service -Name $ServiceName
    }
}

# --- verify ------------------------------------------------------------------
# A .env left over in dist/ from an earlier deploy would defeat the whole point
# of bundling it, and nothing else would ever flag it.
$strayEnv = Join-Path $PSScriptRoot 'dist\.env'
if (Test-Path -LiteralPath $strayEnv) {
    Write-Warning "dist\.env still exists from an earlier build. The exes now carry their own copy; delete it before deploying."
}

Write-Host ''
Write-Host 'Build complete:' -ForegroundColor Green
Get-ChildItem -LiteralPath 'dist' -Filter '*.exe' |
    Select-Object Name, @{n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } }, LastWriteTime |
    Format-Table -AutoSize

Write-Host 'Reminder: dist\*.exe embed .env. Do not commit or publish them.' -ForegroundColor Yellow
