#requires -version 5.1
<#
Exclusive manual fan mode for the validated Tongfang GM5MU firmware.

CPUOff: CPU off, GPU held at 100%.
GPUOff: GPU off, CPU held at 100%.
Auto:   both fans returned to firmware automatic control.

A single background monitor owns the manual state. It keeps checking EC
temperature and immediately restores automatic control on errors or limits.
#>

param(
    [ValidateSet('CPUOff', 'GPUOff', 'Auto')]
    [string]$Action = 'Auto',
    [switch]$Monitor
)

$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$stateDirectory = Join-Path $env:ProgramData 'MonsterFanReset'
$statePath = Join-Path $stateDirectory 'manual-state.json'
$mutex = New-Object System.Threading.Mutex($false, 'Global\MonsterFanResetManualMode')
$mofPath = Join-Path $base 'clevo_fan.mof'

function Notify([string]$message, [string]$title = 'Monster Fan Reset', [int]$icon = 64) {
    try { (New-Object -ComObject WScript.Shell).Popup($message, 5, $title, $icon) | Out-Null }
    catch { Write-Host "$title`: $message" }
}

function Require-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { return $true }
    Notify 'Run the launcher as Administrator.' 'Monster Fan Reset - Admin required' 16
    return $false
}

function Get-Configuration {
    $temperatureLimit = 85
    $iniPath = Join-Path $base 'FanReset.ini'
    if (Test-Path -LiteralPath $iniPath) {
        foreach ($line in Get-Content -LiteralPath $iniPath -Encoding UTF8) {
            if ($line -match '^\s*TempAbort\s*=\s*(\d+)\s*$') {
                $temperatureLimit = [Math]::Min(95, [Math]::Max(60, [int]$matches[1]))
            }
        }
    }
    return $temperatureLimit
}

function Get-FirmwareFan {
    try { return @(Get-CimInstance -Namespace root/wmi -ClassName CLEVO_GET -ErrorAction Stop)[0] }
    catch {
        & "$env:WINDIR\System32\wbem\mofcomp.exe" $mofPath | Out-Null
        Start-Sleep -Milliseconds 500
        return @(Get-CimInstance -Namespace root/wmi -ClassName CLEVO_GET -ErrorAction Stop)[0]
    }
}

function Get-EcTemperature {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) { return -1 }
    $result = & $python (Join-Path $base 'rpm8.py') 2>&1 | Out-String
    if ($result -match 'TEMP=(\d+)') { return [int]$matches[1] }
    return -1
}

function Write-RequestedState([string]$requestedAction) {
    New-Item -ItemType Directory -Force $stateDirectory | Out-Null
    @{ Action = $requestedAction; UpdatedAt = (Get-Date).ToUniversalTime().ToString('o') } |
        ConvertTo-Json -Compress |
        Set-Content -LiteralPath $statePath -Encoding UTF8
}

function Read-RequestedState {
    if (-not (Test-Path -LiteralPath $statePath)) { return 'Auto' }
    try {
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($state.Action -in @('CPUOff', 'GPUOff', 'Auto')) { return [string]$state.Action }
    } catch {}
    return 'Auto'
}

if (-not (Require-Administrator)) { exit 1 }

if (-not $Monitor) {
    Write-RequestedState $Action
    if ($Action -eq 'Auto') {
        # If no resident monitor is running, restore immediately here as well.
        try {
            $fan = Get-FirmwareFan
            Invoke-CimMethod -InputObject $fan -MethodName SetFanAutoDuty -Arguments @{ Data = [uint32]0x0F } | Out-Null
        } catch {}
        Notify 'All fans returned to automatic firmware control.'
        exit 0
    }

    $self = $MyInvocation.MyCommand.Path
    $hostPath = (Get-Process -Id $PID).Path
    Start-Process -FilePath $hostPath -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$self`"", '-Monitor' -WindowStyle Hidden
    Notify "$Action requested. The safety monitor is starting."
    exit 0
}

if (-not $mutex.WaitOne(0, $false)) { exit 0 }

$fan = $null
try {
    $fan = Get-FirmwareFan
    $limit = Get-Configuration
    $activeAction = 'Auto'

    while ($true) {
        $requested = Read-RequestedState
        if ($requested -eq 'Auto') { break }

        $temperature = Get-EcTemperature
        if ($temperature -lt 0 -or $temperature -ge $limit) {
            Invoke-CimMethod -InputObject $fan -MethodName SetFanAutoDuty -Arguments @{ Data = [uint32]0x0F } | Out-Null
            Write-RequestedState 'Auto'
            $reason = if ($temperature -lt 0) { 'Temperature could not be read.' } else { "Temperature reached $temperature C." }
            Notify "$reason All fans were returned to automatic control." 'Monster Fan Reset - Safety stop' 48
            break
        }

        if ($requested -ne $activeAction) {
            # Never switch directly between two off modes. Restore first, then apply the next mode.
            Invoke-CimMethod -InputObject $fan -MethodName SetFanAutoDuty -Arguments @{ Data = [uint32]0x0F } | Out-Null
            Start-Sleep -Milliseconds 250

            $duty = if ($requested -eq 'CPUOff') { [uint32]0x0000C801 } else { [uint32]0x000001C8 }
            Invoke-CimMethod -InputObject $fan -MethodName SetFanDuty -Arguments @{ Data = $duty } | Out-Null
            $activeAction = $requested
        }

        Start-Sleep -Milliseconds 500
    }
}
finally {
    if ($fan) {
        try { Invoke-CimMethod -InputObject $fan -MethodName SetFanAutoDuty -Arguments @{ Data = [uint32]0x0F } | Out-Null } catch {}
    }
    $mutex.ReleaseMutex() | Out-Null
    $mutex.Dispose()
}
