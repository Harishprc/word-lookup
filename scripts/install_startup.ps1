# Creates two shortcuts to Kannada Lookup:
#   1. Startup folder  -> auto-starts on every Windows login
#   2. Desktop         -> manual start any time
# Run once:  powershell -ExecutionPolicy Bypass -File scripts\install_startup.ps1
# Undo with: scripts\uninstall_startup.ps1

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
$runScript = Join-Path $projectRoot "run.pyw"

if (-not (Test-Path $pythonw)) { throw "venv not found: $pythonw - create it first (see README)" }
if (-not (Test-Path $runScript)) { throw "run.pyw not found: $runScript" }

$ws = New-Object -ComObject WScript.Shell

foreach ($target in @(
    (Join-Path ([Environment]::GetFolderPath("Startup")) "Kannada Lookup.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop"))  "Kannada Lookup.lnk")
)) {
    $shortcut = $ws.CreateShortcut($target)
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = "`"$runScript`""
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = "English to Kannada lookup on mouse Forward button"
    $shortcut.Save()
    Write-Host "Created: $target"
}

Write-Host "Done. App will auto-start on next login; use the desktop icon to start it now."
