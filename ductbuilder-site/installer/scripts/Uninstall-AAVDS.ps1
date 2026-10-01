[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$productName = 'AAVDS-duct-builder'
$installRoot = Join-Path $env:LOCALAPPDATA "Programs\$productName"
$startMenuRoot = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$productName"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) "$productName.lnk"

Set-Location $env:TEMP
Remove-Item -LiteralPath $startMenuRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $desktopShortcut -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $installRoot -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "$productName was removed. User projects were preserved."