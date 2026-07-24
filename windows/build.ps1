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

# Optional Authenticode signing (reduces Smart App Control / SmartScreen blocks)
# Set SOUNDOBIT_SIGN_PFX + SOUNDOBIT_SIGN_PASSWORD, or SOUNDOBIT_SIGN_THUMBPRINT (store cert)
$pfx = $env:SOUNDOBIT_SIGN_PFX
$pwd = $env:SOUNDOBIT_SIGN_PASSWORD
$thumb = $env:SOUNDOBIT_SIGN_THUMBPRINT
$signtool = $null
foreach ($c in @(
  "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe",
  "${env:ProgramFiles}\Windows Kits\10\bin\*\x64\signtool.exe"
)) {
  $hit = Get-Item $c -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
  if ($hit) { $signtool = $hit.FullName; break }
}

if ($signtool -and ($pfx -or $thumb)) {
  Write-Host "==> Authenticode signing with $signtool" -ForegroundColor Cyan
  $ts = "http://timestamp.digicert.com"
  if ($pfx) {
    if ($pwd) {
      & $signtool sign /fd SHA256 /tr $ts /td SHA256 /f $pfx /p $pwd $exe
    } else {
      & $signtool sign /fd SHA256 /tr $ts /td SHA256 /f $pfx $exe
    }
  } else {
    & $signtool sign /fd SHA256 /tr $ts /td SHA256 /sha1 $thumb $exe
  }
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "signtool failed (exit $LASTEXITCODE). EXE left unsigned."
  } else {
    Write-Host "Signed OK." -ForegroundColor Green
    & $signtool verify /pa $exe
  }
} else {
  Write-Host ""
  Write-Host "Note: EXE is UNSIGNED. Smart App Control / SmartScreen may block it." -ForegroundColor Yellow
  Write-Host "  To sign: install Windows SDK (signtool), set SOUNDOBIT_SIGN_PFX + password, re-run build.ps1"
  Write-Host "  Or use Azure Trusted Signing. See windows/README.md"
}

Write-Host ""
Write-Host "Built: $exe" -ForegroundColor Green
Write-Host "Size:  $([math]::Round((Get-Item $exe).Length / 1MB, 1)) MB"
Write-Host ""
Write-Host "Run:   .\dist\SoundOrbit.exe"
Write-Host "Keys:  Esc quit | Space orbit | F11 fullscreen"
Write-Host "Audio: uses WASAPI loopback of default playback device"
