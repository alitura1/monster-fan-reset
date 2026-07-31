#requires -version 5.1
<#
Monster Fan Reset

Validated only on Monster Abra A5 V21.1 / Tongfang GM5MU.
This script uses the firmware's own Clevo/Tongfang WMI fan methods.
It never leaves a fan in manual mode: SetFanAutoDuty runs in finally.
#>

param([string]$TargetFan = '')

$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$holdSeconds = 4
$tempAbort = 85
$maxHoldSeconds = 10

function Show-Result([string]$Message, [string]$Title = 'Monster Fan Reset', [int]$Icon = 64) {
    try { (New-Object -ComObject WScript.Shell).Popup($Message, 6, $Title, $Icon) | Out-Null }
    catch { Write-Host "$Title`: $Message" }
}

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Show-Result 'Run this script as Administrator.' 'Monster Fan Reset - Admin required' 16
    exit 1
}

# Optional local configuration; never committed to Git.
$iniPath = Join-Path $base 'FanReset.ini'
if (Test-Path -LiteralPath $iniPath) {
    foreach ($line in Get-Content -LiteralPath $iniPath -Encoding UTF8) {
        if ($line -match '^\s*HoldSeconds\s*=\s*(\d+)\s*$') { $holdSeconds = [Math]::Min(10, [Math]::Max(1, [int]$matches[1])) }
        if ($line -match '^\s*TempAbort\s*=\s*(\d+)\s*$') { $tempAbort = [Math]::Min(95, [Math]::Max(60, [int]$matches[1])) }
        if ([string]::IsNullOrWhiteSpace($TargetFan) -and $line -match '^\s*TargetFan\s*=\s*(CPU|GPU|Both)\s*$') { $TargetFan = $matches[1] }
    }
}

if ([string]::IsNullOrWhiteSpace($TargetFan)) { $TargetFan = 'Both' }
if ($TargetFan -notin @('CPU', 'GPU', 'Both')) { throw "TargetFan must be CPU, GPU, or Both; received '$TargetFan'." }

# The firmware's four-duty-byte request puts every fan in manual mode. Keep the
# fan that is *not* being reset at 100% until automatic control is restored.
switch ($TargetFan) {
    'CPU'  { $duty = [uint32]0x0000C801; $label = 'CPU fan' }
    'GPU'  { $duty = [uint32]0x000001C8; $label = 'GPU fan' }
    default { $duty = [uint32]0x00000101; $label = 'CPU and GPU fans' }
}

$mofPath = Join-Path $base 'clevo_fan.mof'
if (-not (Test-Path -LiteralPath $mofPath)) { throw 'clevo_fan.mof is missing.' }

try { $fan = @(Get-CimInstance -Namespace root/wmi -ClassName CLEVO_GET -ErrorAction Stop)[0] }
catch {
    & "$env:WINDIR\System32\wbem\mofcomp.exe" $mofPath | Out-Null
    Start-Sleep -Milliseconds 500
    $fan = @(Get-CimInstance -Namespace root/wmi -ClassName CLEVO_GET -ErrorAction Stop)[0]
}

function Get-EcTemperature {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) { return -1 }
    $output = & $python (Join-Path $base 'rpm8.py') 2>&1 | Out-String
    if ($output -match 'TEMP=(\d+)') { return [int]$matches[1] }
    return -1
}

function Set-Auto { Invoke-CimMethod -InputObject $fan -MethodName SetFanAutoDuty -Arguments @{ Data = [uint32]0x0F } | Out-Null }

$beforeTemp = Get-EcTemperature
if ($beforeTemp -lt 0) { Show-Result "Temperature could not be read. $label was not changed." 'Monster Fan Reset - Safety stop' 48; exit 1 }
if ($beforeTemp -ge $tempAbort) { Show-Result "$beforeTemp C is at or above the safety limit. $label was not changed." 'Monster Fan Reset - Safety stop' 48; exit 1 }

$aborted = $false
try {
    Invoke-CimMethod -InputObject $fan -MethodName SetFanDuty -Arguments @{ Data = $duty } | Out-Null
    $deadline = (Get-Date).AddSeconds([Math]::Min($holdSeconds, $maxHoldSeconds))
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
        if ((Get-EcTemperature) -ge $tempAbort) { $aborted = $true; break }
    }
}
finally {
    Set-Auto
    Start-Sleep -Milliseconds 150
    Set-Auto
}

$afterTemp = Get-EcTemperature
if ($aborted) { Show-Result "$label returned to automatic control early because the temperature reached the configured limit." 'Monster Fan Reset - Safety stop' 48 }
else { Show-Result "$label reset complete. Temperature: $beforeTemp C -> $afterTemp C." }
