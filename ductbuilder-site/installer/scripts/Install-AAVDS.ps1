[CmdletBinding()]
param(
    [switch]$DesktopShortcut
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$productName = 'AAVDS-duct-builder'
$packageRoot = $PSScriptRoot
$payloadRoot = Join-Path $packageRoot 'payload'
$installRoot = Join-Path $env:LOCALAPPDATA "Programs\$productName"
$stagingRoot = "$installRoot.installing-$PID"
$projectRoot = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'AAVDSProjects'
$startMenuRoot = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$productName"
$desktopRoot = [Environment]::GetFolderPath('Desktop')

function Assert-File([string]$Path, [string]$Description) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Description not found: $Path"
    }
}

function New-AppShortcut([string]$Path, [string]$TargetPath, [string]$Arguments, [string]$WorkingDirectory, [string]$IconLocation) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $TargetPath
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.IconLocation = $IconLocation
    $shortcut.Save()
}

Assert-File (Join-Path $payloadRoot 'app\Allshield_Project_GUI.py') 'Application entry point'
Assert-File (Join-Path $payloadRoot 'FreeCAD\bin\pythonw.exe') 'FreeCAD Python runtime'
Assert-File (Join-Path $payloadRoot 'FreeCAD\bin\FreeCAD.exe') 'FreeCAD executable'

Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

try {
    Copy-Item -LiteralPath (Join-Path $payloadRoot 'app') -Destination $stagingRoot -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $payloadRoot 'FreeCAD') -Destination $stagingRoot -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $packageRoot 'Uninstall-AAVDS.ps1') -Destination $stagingRoot -Force
    Copy-Item -LiteralPath (Join-Path $packageRoot 'Uninstall-AAVDS.cmd') -Destination $stagingRoot -Force

    if (Test-Path -LiteralPath $installRoot) {
        Remove-Item -LiteralPath $installRoot -Recurse -Force
    }
    Move-Item -LiteralPath $stagingRoot -Destination $installRoot
} catch {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
    throw
}

New-Item -ItemType Directory -Path $projectRoot, $startMenuRoot -Force | Out-Null
$pythonw = Join-Path $installRoot 'FreeCAD\bin\pythonw.exe'
$application = Join-Path $installRoot 'app\Allshield_Project_GUI.py'
$freecad = Join-Path $installRoot 'FreeCAD\bin\FreeCAD.exe'
$arguments = "`"$application`" --project `"$projectRoot`""
$powershell = Join-Path ([Environment]::GetFolderPath('System')) 'WindowsPowerShell\v1.0\powershell.exe'
$uninstaller = Join-Path $installRoot 'Uninstall-AAVDS.ps1'

New-AppShortcut `
    -Path (Join-Path $startMenuRoot "$productName.lnk") `
    -TargetPath $pythonw `
    -Arguments $arguments `
    -WorkingDirectory (Join-Path $installRoot 'app') `
    -IconLocation $freecad
New-AppShortcut `
    -Path (Join-Path $startMenuRoot "Uninstall $productName.lnk") `
    -TargetPath $powershell `
    -Arguments "-NoProfile -ExecutionPolicy Bypass -File `"$uninstaller`"" `
    -WorkingDirectory $env:TEMP `
    -IconLocation $freecad

$createDesktopShortcut = $DesktopShortcut.IsPresent
if (-not $createDesktopShortcut) {
    $answer = Read-Host 'Create a desktop shortcut? [y/N]'
    $createDesktopShortcut = $answer -match '^(y|yes)$'
}
if ($createDesktopShortcut) {
    New-AppShortcut `
        -Path (Join-Path $desktopRoot "$productName.lnk") `
        -TargetPath $pythonw `
        -Arguments $arguments `
        -WorkingDirectory (Join-Path $installRoot 'app') `
        -IconLocation $freecad
}

[ordered]@{
    product = $productName
    version = 'AAVDS-2026-V01'
    installedUtc = [DateTime]::UtcNow.ToString('o')
    installRoot = $installRoot
    projectRoot = $projectRoot
    signed = $false
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $installRoot 'install.json') -Encoding utf8

Write-Host ''
Write-Host "$productName was installed successfully."
Write-Host "Start menu: $productName"
Write-Host "Projects: $projectRoot"