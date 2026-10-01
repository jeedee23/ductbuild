[CmdletBinding()]
param(
    [string]$ProductVersion = 'AAVDS-2026-V01',
    [string]$SourceRoot,
    [string]$FreeCADRoot = 'C:\Program Files\FreeCAD 1.1',
    [string]$PdfRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$installerRoot = Split-Path -Parent $PSScriptRoot
$repositoryRoot = Split-Path -Parent $installerRoot
$SourceRoot = if ($SourceRoot) { $SourceRoot } else { Join-Path $repositoryRoot 'app' }
$PdfRoot = if ($PdfRoot) { $PdfRoot } else { Join-Path $repositoryRoot 'third_party\catalogues' }
$stageRoot = Join-Path $installerRoot 'work\manual-installer'
$stageApp = Join-Path $stageRoot 'payload\app'
$distRoot = Join-Path $installerRoot 'dist'
$archiveBaseName = "$ProductVersion-UNSIGNED"
$archivePath = Join-Path $distRoot "$archiveBaseName.zip"
$checksumPath = Join-Path $distRoot "$archiveBaseName.zip.sha256"
$legacyArchiveBaseName = "AAVDS-duct-builder-$ProductVersion-UNSIGNED-manual-installer"
$setupName = "AAVDS-duct-builder-Setup-$ProductVersion-UNSIGNED.exe"
$setupPath = Join-Path $stageRoot $setupName
$launcherSource = Join-Path $PSScriptRoot 'InstallerLauncher.cs'
$stagePayloadScript = Join-Path $PSScriptRoot 'Stage-AppPayload.ps1'
$payloadConfigPath = Join-Path $installerRoot 'config\payload-files.json'
$compilerCandidates = @(
    'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe',
    'C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe'
)

function Assert-File([string]$Path, [string]$Description) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Description not found: $Path"
    }
}

function Assert-Directory([string]$Path, [string]$Description) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Description not found: $Path"
    }
}

function Write-BuildStep([int]$Number, [string]$Message) {
    Write-Host ''
    Write-Host "[$Number/7] $Message" -ForegroundColor Cyan
}

Write-Host 'AAVDS-duct-builder manual installer build' -ForegroundColor White
Write-Host "Version: $ProductVersion"
Write-Host "Output:  $archivePath"

Write-BuildStep 1 'Validating source files and bundled runtime...'
Assert-Directory $SourceRoot 'Application source directory'
Assert-Directory $FreeCADRoot 'FreeCAD runtime directory'
Assert-Directory $PdfRoot 'Approved PDF directory'
Assert-File (Join-Path $SourceRoot 'Allshield_Project_GUI.py') 'Application entry point'
Assert-File (Join-Path $FreeCADRoot 'bin\python.exe') 'FreeCAD Python runtime'
Assert-File (Join-Path $FreeCADRoot 'bin\pythonw.exe') 'FreeCAD windowed Python runtime'
Assert-File (Join-Path $FreeCADRoot 'bin\FreeCAD.exe') 'FreeCAD executable'
Assert-File $launcherSource 'Setup launcher source'
Assert-File $stagePayloadScript 'Payload staging script'
Assert-File $payloadConfigPath 'Payload configuration'
$compiler = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
Assert-File $compiler 'Windows C# compiler'

$runtimeVersion = (& (Join-Path $FreeCADRoot 'bin\python.exe') -c "import FreeCAD as App; print('.'.join(App.Version()[:3]))").Trim()
if ($LASTEXITCODE -ne 0 -or $runtimeVersion.Trim() -ne '1.1.1') {
    throw "Expected FreeCAD 1.1.1, found '$runtimeVersion'."
}
$tkVersion = (& (Join-Path $FreeCADRoot 'bin\python.exe') -c 'import tkinter; print(tkinter.TkVersion)').Trim()
if ($LASTEXITCODE -ne 0) {
    throw 'The bundled FreeCAD Python runtime does not provide Tkinter.'
}
Write-Host "  Application source: $SourceRoot"
Write-Host "  FreeCAD runtime:    $runtimeVersion"
Write-Host "  Tk runtime:         $tkVersion"
Write-Host "  PDF source:         $PdfRoot"

Write-BuildStep 2 'Staging the application and approved PDF sources...'
Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $stageApp, $distRoot -Force | Out-Null
$stageResult = & $stagePayloadScript `
    -SourceRoot $SourceRoot `
    -PdfRoot $PdfRoot `
    -Destination $stageApp `
    -PayloadConfigPath $payloadConfigPath
Write-Host "  Staged application files: $($stageResult.ApplicationFiles)"
Write-Host "  Included PDF files:       $($stageResult.CatalogueFiles)"

Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Install-AAVDS.ps1') -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Install-AAVDS.cmd') -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Uninstall-AAVDS.ps1') -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Uninstall-AAVDS.cmd') -Destination $stageRoot

Write-BuildStep 3 'Compiling the Windows Setup launcher...'
& $compiler /nologo /target:exe /platform:anycpu /optimize+ "/out:$setupPath" $launcherSource
if ($LASTEXITCODE -ne 0) {
    throw "Setup launcher compilation failed with exit code $LASTEXITCODE."
}
Assert-File $setupPath 'Compiled setup launcher'
Write-Host "  Setup launcher: $setupName"

Write-BuildStep 4 'Generating the payload manifest and install notes...'
$contents = Get-ChildItem -LiteralPath $stageApp -File -Recurse | Sort-Object FullName | ForEach-Object {
    [ordered]@{
        path = [IO.Path]::GetRelativePath($stageApp, $_.FullName).Replace('\', '/')
        bytes = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
[ordered]@{
    schema = 'aavds-manual-installer-payload-v1'
    version = $ProductVersion
    generated_utc = [DateTime]::UtcNow.ToString('o')
    contents = @($contents)
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $stageApp 'MANIFEST.json') -Encoding utf8
Write-Host "  Manifest entries: $($contents.Count)"

@"
AAVDS-duct-builder $ProductVersion

1. Extract this complete ZIP to a local folder.
2. Double-click $setupName.
3. Use the Start menu shortcut named AAVDS-duct-builder.

For best Windows Explorer compatibility, extract directly under Downloads or C:\AAVDS.

Install-AAVDS.cmd is provided as a fallback launcher.

The installation is per user and does not require administrator rights.
Application files are installed under %LOCALAPPDATA%\Programs\AAVDS-duct-builder.
Projects are stored under Documents\AAVDSProjects and are preserved by uninstall.

IMPORTANT: This package is UNSIGNED and intended for local installation testing only.
"@ | Set-Content -LiteralPath (Join-Path $stageRoot 'README-INSTALL.txt') -Encoding ascii

Write-BuildStep 5 'Creating the ZIP archive (the FreeCAD runtime can take several minutes)...'
Remove-Item -LiteralPath @(
    $archivePath,
    $checksumPath,
    (Join-Path $distRoot "$legacyArchiveBaseName.zip"),
    (Join-Path $distRoot "$legacyArchiveBaseName.zip.sha256")
) -Force -ErrorAction SilentlyContinue
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stageArchiveFiles = @(Get-ChildItem -LiteralPath $stageRoot -File -Recurse)
$freeCadArchiveFiles = @(
    Get-ChildItem -LiteralPath $FreeCADRoot -File -Recurse |
        Where-Object { $_.Name -notin @('install.log', 'Uninstall-FreeCAD.exe') }
)
$totalFiles = $stageArchiveFiles.Count + $freeCadArchiveFiles.Count
$totalBytes = [long](($stageArchiveFiles | Measure-Object -Property Length -Sum).Sum + ($freeCadArchiveFiles | Measure-Object -Property Length -Sum).Sum)
$processedFiles = 0
$processedBytes = 0L
$nextProgressMessage = 10
$longestArchivePath = @(
    $stageArchiveFiles | ForEach-Object { [IO.Path]::GetRelativePath($stageRoot, $_.FullName).Length }
    $freeCadArchiveFiles | ForEach-Object { ("payload/FreeCAD/" + [IO.Path]::GetRelativePath($FreeCADRoot, $_.FullName)).Length }
) | Measure-Object -Maximum | Select-Object -ExpandProperty Maximum
if ($longestArchivePath -gt 180) {
    throw "The longest ZIP path is $longestArchivePath characters; keep internal paths at or below 180 for Windows Explorer compatibility."
}
Write-Host ("  Archiving {0:N0} files ({1:N2} GiB before compression)..." -f $totalFiles, ($totalBytes / 1GB))
Write-Host "  Longest internal ZIP path: $longestArchivePath characters"
$stream = [IO.File]::Open($archivePath, [IO.FileMode]::CreateNew)
$archive = [IO.Compression.ZipArchive]::new($stream, [IO.Compression.ZipArchiveMode]::Create, $false)
try {
    $stageArchiveFiles | ForEach-Object {
        $relative = [IO.Path]::GetRelativePath($stageRoot, $_.FullName).Replace('\', '/')
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $_.FullName,
            $relative,
            [IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
        $processedFiles++
        $processedBytes += $_.Length
    }
    $freeCadArchiveFiles | ForEach-Object {
            $relative = [IO.Path]::GetRelativePath($FreeCADRoot, $_.FullName).Replace('\', '/')
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive,
                $_.FullName,
                "payload/FreeCAD/$relative",
                [IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
            $processedFiles++
            $processedBytes += $_.Length
            $percent = [Math]::Min(100, [int][Math]::Floor(100.0 * $processedBytes / $totalBytes))
            Write-Progress -Activity 'Creating installer ZIP' -Status "$processedFiles of $totalFiles files" -PercentComplete $percent
            if ($percent -ge $nextProgressMessage) {
                Write-Host ("  ZIP progress: {0}% ({1:N2} of {2:N2} GiB processed)" -f $percent, ($processedBytes / 1GB), ($totalBytes / 1GB))
                $nextProgressMessage += 10
            }
        }
} finally {
    Write-Progress -Activity 'Creating installer ZIP' -Completed
    $archive.Dispose()
    $stream.Dispose()
}
Write-Host ("  Compressed ZIP size: {0:N2} MiB" -f ((Get-Item -LiteralPath $archivePath).Length / 1MB))

Write-BuildStep 6 'Calculating the SHA-256 checksum...'
$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
"$archiveHash  $([IO.Path]::GetFileName($archivePath))" | Set-Content -LiteralPath $checksumPath -Encoding ascii
$result = [ordered]@{
    productVersion = $ProductVersion
    signed = $false
    uploadZip = $archivePath
    uploadZipBytes = (Get-Item -LiteralPath $archivePath).Length
    uploadZipSha256 = $archiveHash
    checksum = $checksumPath
    setupEntry = $setupName
}
$result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $distRoot 'manual-build-result.json') -Encoding utf8

Write-BuildStep 7 'Build complete.'
Write-Host '  Ready for manual upload:' -ForegroundColor Green
Write-Host "  ZIP:      $archivePath"
Write-Host "  Checksum: $checksumPath"
Write-Host "  SHA-256:  $archiveHash"
Write-Host '  Status:   UNSIGNED - installation testing only' -ForegroundColor Yellow
Write-Host ''
$result | ConvertTo-Json