[CmdletBinding()]
param(
    [string]$ProductVersion = 'AAVDS-2026-V01',
    [string]$SourceRoot,
    [string]$FreeCADRoot = 'C:\Program Files\FreeCAD 1.1',
    [string]$PdfRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($ProductVersion -ne 'AAVDS-2026-V01') {
    throw 'Update BuildIdentity.ProductVersion before building a different product version.'
}

$installerRoot = Split-Path -Parent $PSScriptRoot
$repositoryRoot = Split-Path -Parent $installerRoot
$SourceRoot = if ($SourceRoot) { $SourceRoot } else { Join-Path $repositoryRoot 'app' }
$PdfRoot = if ($PdfRoot) { $PdfRoot } else { Join-Path $repositoryRoot 'third_party\catalogues' }
$workRoot = Join-Path $installerRoot 'work\self-extracting-installer'
$stageApp = Join-Path $workRoot 'app'
$payloadPath = Join-Path $workRoot 'payload.zip'
$launcherPath = Join-Path $workRoot 'setup-launcher.exe'
$distRoot = Join-Path $installerRoot 'dist'
$installerName = "AAVDS-duct-builder-Setup-$ProductVersion-UNSIGNED.exe"
$installerPath = Join-Path $distRoot $installerName
$checksumPath = "$installerPath.sha256"
$resultPath = Join-Path $distRoot 'self-extracting-build-result.json'
$launcherSource = Join-Path $PSScriptRoot 'InstallerLauncher.cs'
$installerSource = Join-Path $PSScriptRoot 'SelfExtractingInstaller.cs'
$uninstallerSource = Join-Path $PSScriptRoot 'Uninstall-AAVDS.ps1'
$stagePayloadScript = Join-Path $PSScriptRoot 'Stage-AppPayload.ps1'
$payloadConfigPath = Join-Path $installerRoot 'config\payload-files.json'
$payloadMarker = [Text.Encoding]::ASCII.GetBytes('AAVDS_PAYLOAD_V1')
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

function New-ArchiveItem([IO.FileInfo]$File, [string]$Root, [string]$Prefix) {
    [pscustomobject]@{
        Source = $File.FullName
        Entry = "$Prefix/$([IO.Path]::GetRelativePath($Root, $File.FullName).Replace('\', '/'))"
        Bytes = $File.Length
    }
}

Write-Host 'AAVDS-duct-builder self-extracting installer build' -ForegroundColor White
Write-Host "Version: $ProductVersion"
Write-Host "Output:  $installerPath"

Write-BuildStep 1 'Validating application and runtime inputs...'
Assert-Directory $SourceRoot 'Application source directory'
Assert-Directory $FreeCADRoot 'FreeCAD runtime directory'
Assert-Directory $PdfRoot 'Approved PDF directory'
Assert-File (Join-Path $SourceRoot 'Allshield_Project_GUI.py') 'Application entry point'
Assert-File (Join-Path $FreeCADRoot 'bin\python.exe') 'FreeCAD Python runtime'
Assert-File (Join-Path $FreeCADRoot 'bin\pythonw.exe') 'FreeCAD windowed Python runtime'
Assert-File (Join-Path $FreeCADRoot 'bin\FreeCAD.exe') 'FreeCAD executable'
Assert-File $launcherSource 'Setup launcher source'
Assert-File $installerSource 'Installer UI source'
Assert-File $uninstallerSource 'Uninstaller script'
Assert-File $stagePayloadScript 'Payload staging script'
Assert-File $payloadConfigPath 'Payload configuration'
$compiler = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
Assert-File $compiler 'Windows C# compiler'

$runtimeVersion = (& (Join-Path $FreeCADRoot 'bin\python.exe') -c "import FreeCAD as App; print('.'.join(App.Version()[:3]))").Trim()
if ($LASTEXITCODE -ne 0 -or $runtimeVersion -ne '1.1.1') {
    throw "Expected FreeCAD 1.1.1, found '$runtimeVersion'."
}
Write-Host "  Application source: $SourceRoot"
Write-Host "  FreeCAD runtime:    $runtimeVersion"
Write-Host "  PDF source:         $PdfRoot"

Write-BuildStep 2 'Staging the application and approved PDF sources...'
Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $stageApp, $distRoot -Force | Out-Null
$stageResult = & $stagePayloadScript `
    -SourceRoot $SourceRoot `
    -PdfRoot $PdfRoot `
    -Destination $stageApp `
    -PayloadConfigPath $payloadConfigPath
Write-Host "  Staged application files: $($stageResult.ApplicationFiles)"
Write-Host "  Included PDF files:       $($stageResult.CatalogueFiles)"

Write-BuildStep 3 'Generating the application payload manifest...'
$manifestContents = Get-ChildItem -LiteralPath $stageApp -File -Recurse | Sort-Object FullName | ForEach-Object {
    [ordered]@{
        path = [IO.Path]::GetRelativePath($stageApp, $_.FullName).Replace('\', '/')
        bytes = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
[ordered]@{
    schema = 'aavds-self-extracting-installer-payload-v1'
    version = $ProductVersion
    generated_utc = [DateTime]::UtcNow.ToString('o')
    contents = @($manifestContents)
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $stageApp 'MANIFEST.json') -Encoding utf8
Write-Host "  Manifest entries: $($manifestContents.Count)"

Write-BuildStep 4 'Compiling the graphical setup launcher...'
& $compiler `
    /nologo `
    /target:winexe `
    /platform:anycpu `
    /optimize+ `
    "/out:$launcherPath" `
    /reference:System.Windows.Forms.dll `
    /reference:System.Drawing.dll `
    /reference:System.IO.Compression.dll `
    /reference:System.IO.Compression.FileSystem.dll `
    $launcherSource `
    $installerSource
if ($LASTEXITCODE -ne 0) {
    throw "Setup launcher compilation failed with exit code $LASTEXITCODE."
}
Assert-File $launcherPath 'Compiled setup launcher'

Write-BuildStep 5 'Compressing the application and bundled FreeCAD runtime...'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archiveItems = [Collections.Generic.List[object]]::new()
Get-ChildItem -LiteralPath $stageApp -File -Recurse | ForEach-Object {
    $archiveItems.Add((New-ArchiveItem -File $_ -Root $stageApp -Prefix 'app'))
}
Get-ChildItem -LiteralPath $FreeCADRoot -File -Recurse |
    Where-Object { $_.Name -notin @('install.log', 'Uninstall-FreeCAD.exe') } |
    ForEach-Object {
        $archiveItems.Add((New-ArchiveItem -File $_ -Root $FreeCADRoot -Prefix 'FreeCAD'))
    }
$archiveItems.Add([pscustomobject]@{
    Source = $uninstallerSource
    Entry = 'Uninstall-AAVDS.ps1'
    Bytes = (Get-Item -LiteralPath $uninstallerSource).Length
})

$totalBytes = [long](($archiveItems | Measure-Object -Property Bytes -Sum).Sum)
$processedBytes = 0L
$nextProgressMessage = 10
$longestEntry = $archiveItems.Entry | ForEach-Object Length | Measure-Object -Maximum | Select-Object -ExpandProperty Maximum
Write-Host ("  Compressing {0:N0} files ({1:N2} GiB before compression)..." -f $archiveItems.Count, ($totalBytes / 1GB))
Write-Host "  Longest payload path: $longestEntry characters"

$payloadStream = [IO.File]::Open($payloadPath, [IO.FileMode]::Create, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$archive = [IO.Compression.ZipArchive]::new($payloadStream, [IO.Compression.ZipArchiveMode]::Create, $false)
try {
    foreach ($item in $archiveItems) {
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $item.Source,
            $item.Entry,
            [IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
        $processedBytes += $item.Bytes
        $percent = [Math]::Min(100, [int][Math]::Floor(100.0 * $processedBytes / $totalBytes))
        Write-Progress -Activity 'Compressing installer payload' -Status $item.Entry -PercentComplete $percent
        if ($percent -ge $nextProgressMessage) {
            Write-Host ("  Compression progress: {0}% ({1:N2} of {2:N2} GiB processed)" -f $percent, ($processedBytes / 1GB), ($totalBytes / 1GB))
            $nextProgressMessage += 10
        }
    }
} finally {
    Write-Progress -Activity 'Compressing installer payload' -Completed
    $archive.Dispose()
    $payloadStream.Dispose()
}
Write-Host ("  Compressed payload: {0:N2} MiB" -f ((Get-Item -LiteralPath $payloadPath).Length / 1MB))

Write-BuildStep 6 'Creating and validating the single-file installer...'
Remove-Item -LiteralPath $installerPath, $checksumPath, $resultPath -Force -ErrorAction SilentlyContinue
Copy-Item -LiteralPath $launcherPath -Destination $installerPath
$payloadLength = (Get-Item -LiteralPath $payloadPath).Length
$installerStream = [IO.File]::Open($installerPath, [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::None)
$payloadReadStream = [IO.File]::OpenRead($payloadPath)
try {
    $payloadReadStream.CopyTo($installerStream, 1024 * 1024)
    $installerStream.Write($payloadMarker, 0, $payloadMarker.Length)
    $payloadLengthBytes = [BitConverter]::GetBytes([long]$payloadLength)
    $installerStream.Write($payloadLengthBytes, 0, $payloadLengthBytes.Length)
} finally {
    $payloadReadStream.Dispose()
    $installerStream.Dispose()
}

$verificationProcess = Start-Process -FilePath $installerPath -ArgumentList '--verify' -Wait -PassThru
if ($verificationProcess.ExitCode -ne 0) {
    throw "Self-check failed with exit code $($verificationProcess.ExitCode)."
}
Write-Host '  Embedded payload self-check passed.'

Write-BuildStep 7 'Calculating the checksum...'
$installerHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
"$installerHash  $installerName" | Set-Content -LiteralPath $checksumPath -Encoding ascii
$result = [ordered]@{
    productVersion = $ProductVersion
    signed = $false
    uploadExecutable = $installerPath
    uploadExecutableBytes = (Get-Item -LiteralPath $installerPath).Length
    uploadExecutableSha256 = $installerHash
    checksum = $checksumPath
    progressUi = 'determinate-file-extraction'
}
$result | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding utf8

Write-Host ''
Write-Host 'Build complete.' -ForegroundColor Green
Write-Host "  EXE:      $installerPath"
Write-Host "  Checksum: $checksumPath"
Write-Host "  SHA-256:  $installerHash"
Write-Host '  Status:   UNSIGNED - sign before distribution' -ForegroundColor Yellow
Write-Host ''
$result | ConvertTo-Json