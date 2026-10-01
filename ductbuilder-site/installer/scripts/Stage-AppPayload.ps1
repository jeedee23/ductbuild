[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$SourceRoot,
    [Parameter(Mandatory)]
    [string]$PdfRoot,
    [Parameter(Mandatory)]
    [string]$Destination,
    [Parameter(Mandatory)]
    [string]$PayloadConfigPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

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

function Copy-PayloadEntry([string]$RelativePath) {
    if ([IO.Path]::IsPathRooted($RelativePath) -or $RelativePath -match '(^|[\\/])\.\.([\\/]|$)') {
        throw "Unsafe payload path: $RelativePath"
    }
    $sourcePath = Join-Path $SourceRoot $RelativePath
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        throw "Configured payload entry not found: $sourcePath"
    }
    $destinationPath = Join-Path $Destination $RelativePath
    New-Item -ItemType Directory -Path (Split-Path -Parent $destinationPath) -Force | Out-Null
    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Recurse -Force
}

Assert-Directory $SourceRoot 'Application source directory'
Assert-Directory $PdfRoot 'Approved PDF directory'
Assert-File $PayloadConfigPath 'Payload configuration'
Assert-File (Join-Path $SourceRoot 'airkan_builder\catalogue_rules_v3.json') 'Catalogue rules'

$config = Get-Content -LiteralPath $PayloadConfigPath -Raw | ConvertFrom-Json
if ($config.schema -ne 'aavds-installer-payload-config-v1') {
    throw "Unsupported payload configuration schema: $($config.schema)"
}
$entries = @($config.include)
if (-not $entries.Count) {
    throw 'The payload configuration contains no entries.'
}

New-Item -ItemType Directory -Path $Destination -Force | Out-Null
foreach ($entry in $entries) {
    Copy-PayloadEntry ([string]$entry)
}
Get-ChildItem -LiteralPath $Destination -Directory -Recurse -Force |
    Where-Object Name -eq '__pycache__' |
    Remove-Item -Recurse -Force

$rules = Get-Content -LiteralPath (Join-Path $SourceRoot 'airkan_builder\catalogue_rules_v3.json') -Raw | ConvertFrom-Json
$availablePdfs = @(
    Get-ChildItem -LiteralPath $PdfRoot -File -Filter '*.pdf' | ForEach-Object {
        [pscustomobject]@{
            Path = $_.FullName
            Sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
)
$requiredSources = @($rules.sources.PSObject.Properties | ForEach-Object { $_.Value }) |
    Sort-Object sha256 -Unique
$sourcesDestination = Join-Path $Destination 'sources'
New-Item -ItemType Directory -Path $sourcesDestination -Force | Out-Null
foreach ($source in $requiredSources) {
    $expectedSha256 = ([string]$source.sha256).ToLowerInvariant()
    $candidatePdfs = @($availablePdfs | Where-Object Sha256 -eq $expectedSha256)
    if ($candidatePdfs.Count -ne 1) {
        throw "Expected exactly one approved PDF with SHA-256 $($source.sha256) for $($source.filename); found $($candidatePdfs.Count)."
    }
    Copy-Item -LiteralPath $candidatePdfs[0].Path -Destination (Join-Path $sourcesDestination $source.filename) -Force
}

[pscustomobject]@{
    ApplicationFiles = @(Get-ChildItem -LiteralPath $Destination -File -Recurse).Count
    CatalogueFiles = @(Get-ChildItem -LiteralPath $sourcesDestination -File -Filter '*.pdf').Count
}
