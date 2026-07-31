#Requires AutoHotkey v2.0
#SingleInstance Force

action := A_Args.Length ? A_Args[1] : "Auto"
script := A_ScriptDir "\FanManual.ps1"

if !FileExist(script) {
    MsgBox "FanManual.ps1 is missing.", "Monster Fan Reset", 16
    ExitApp
}

pwsh := "C:\Program Files\PowerShell\7\pwsh.exe"
host := FileExist(pwsh) ? pwsh : "powershell.exe"
Run '*RunAs "' host '" -NoProfile -ExecutionPolicy Bypass -File "' script '" -Action "' action '"'
