[CmdletBinding()]
param(
    [string]$BasePython = "C:\Users\johan\AppData\Local\Programs\Python\Python314\python.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentPath = Join-Path $projectRoot ".venv"
$environmentPython = Join-Path $environmentPath "Scripts\python.exe"
$requirementsPath = Join-Path $projectRoot "requirements-airkan.txt"

if (-not (Test-Path -LiteralPath $BasePython -PathType Leaf)) {
    throw "Python was not found at: $BasePython"
}

if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf)) {
    throw "Requirements file was not found at: $requirementsPath"
}

if (-not (Test-Path -LiteralPath $environmentPython -PathType Leaf)) {
    Write-Host "Creating project environment at $environmentPath"
    & $BasePython -m venv $environmentPath
}

Write-Host "Updating pip"
& $environmentPython -m pip install --upgrade pip

Write-Host "Installing AIRKAN PDF tools"
& $environmentPython -m pip install --requirement $requirementsPath

Write-Host "Verifying imports and an in-memory PDF render"
$verification = @'
from importlib.metadata import version

import cv2
import fitz
import numpy
import pdfplumber
import PIL
import reportlab
import svgwrite

document = fitz.open()
page = document.new_page(width=100, height=100)
page.insert_text((10, 50), "AIRKAN PDF tools")
pixels = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
assert pixels.width == 200 and pixels.height == 200
assert len(pixels.samples) > 0

packages = (
    "pymupdf",
    "pdfplumber",
    "pillow",
    "numpy",
    "opencv-python-headless",
    "svgwrite",
    "reportlab",
)
for package in packages:
    print(f"{package}={version(package)}")
print(f"render={pixels.width}x{pixels.height} OK")
'@
& $environmentPython -c $verification

Write-Host "PDF tool environment is ready: $environmentPython"