<#
.SYNOPSIS
    Creates Desktop Shortcuts for War Impact Platform on the User's Windows Desktop.
#>

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)

$WshShell = New-Object -ComObject WScript.Shell

# 1. Start Platform Shortcut
$ShortcutPath = Join-Path $DesktopPath "War Impact Platform.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = (Join-Path $ProjectRoot "scripts\start_platform.bat")
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.Description = "Launch War Impact Geopolitical & Trade Platform"
$Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,14" # Globe/Radar Icon
$Shortcut.Save()
Write-Host "Created Desktop Shortcut: $ShortcutPath" -ForegroundColor Green

# 2. Stop Platform Shortcut
$StopShortcutPath = Join-Path $DesktopPath "Stop War Impact Platform.lnk"
$StopShortcut = $WshShell.CreateShortcut($StopShortcutPath)
$StopShortcut.TargetPath = (Join-Path $ProjectRoot "scripts\stop_platform.bat")
$StopShortcut.WorkingDirectory = $ProjectRoot
$StopShortcut.Description = "Stop all War Impact Platform background services"
$StopShortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,27" # Stop Icon
$StopShortcut.Save()
Write-Host "Created Desktop Shortcut: $StopShortcutPath" -ForegroundColor Green
