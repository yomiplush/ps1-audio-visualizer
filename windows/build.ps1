# Build SoundOrbit.exe on Windows 11 (PowerShell)
# Usage:  powershell -ExecutionPolicy Bypass -File .\build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> SoundOrbit Windows build" -ForegroundColor Cyan

# Prefer py launcher
$py = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
  $py = "py -3"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $py = "python"
} else {
  Write-Error "Python 3.11+ not found. Install from https://www.python.org/downloads/ (check 'Add to PATH')."
}

Write-Host "Python: $($py)"
Invoke-Expression "$py --version"

Write-Host "==> Creating venv .venv-win"
if (-not (Test-Path ".venv-win")) {
  Invoke-Expression "$py -m venv .venv-win"
}
$pip = ".\.venv-win\Scripts\pip.exe"
$python = ".\.venv-win\Scripts\python.exe"
$pyi = ".\.venv-win\Scripts\pyinstaller.exe"

& $python -m pip install --upgrade pip wheel
& $pip install -r requirements.txt

Write-Host "==> PyInstaller one-file"
if (Test-Path "dist") { Remove-Item -Recurse -Force dist }
if (Test-Path "build") { Remove-Item -Recurse -Force build }

& $pyi --noconfirm --clean SoundOrbitWin.spec

$exe = Join-Path $PSScriptRoot "dist\SoundOrbit.exe"
if (-not (Test-Path $exe)) {
  Write-Error "Build failed: dist\SoundOrbit.exe not found"
}

Write-Host ""
Write-Host "Built: $exe" -ForegroundColor Green
Write-Host "Size:  $([math]::Round((Get-Item $exe).Length / 1MB, 1)) MB"
Write-Host ""
Write-Host "Run:   .\dist\SoundOrbit.exe"
Write-Host "Keys:  Esc quit | Space orbit | F11 fullscreen"
Write-Host "Audio: uses WASAPI loopback of default playback device"
