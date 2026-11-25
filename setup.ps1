# One-time setup for eleven labs vc (Windows).
# Installs uv if needed, a private Python 3.13 inside this folder, the Python
# packages, and creates .env from .env.example. Safe to run again.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root

function Write-Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

# Keep Python and the package cache inside the project folder, so the setup
# does not depend on (or clash with) any Python already on the machine.
$env:UV_PYTHON_INSTALL_DIR = Join-Path $root '.python'
$env:UV_CACHE_DIR = Join-Path $root '.uv-cache'

Write-Step 'Looking for uv'
$uv = $null
if (Get-Command uv -ErrorAction SilentlyContinue) {
    $uv = @('uv')
} elseif ((Get-Command py -ErrorAction SilentlyContinue) -and (& py -m uv --version 2>$null)) {
    $uv = @('py', '-m', 'uv')
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    Write-Host 'Installing uv with pip...'
    & py -m pip install --user --quiet uv
    $uv = @('py', '-m', 'uv')
} elseif (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host 'Installing uv with winget...'
    winget install --id astral-sh.uv -e --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + $env:Path
    $uv = @('uv')
} else {
    Write-Host 'Could not install uv automatically.' -ForegroundColor Red
    Write-Host 'Install it from https://docs.astral.sh/uv/ and run setup.bat again.'
    exit 1
}
function Invoke-Uv { & $uv[0] @($uv | Select-Object -Skip 1) @args; if ($LASTEXITCODE) { throw "uv $args failed" } }
Invoke-Uv --version

Write-Step 'Installing Python 3.13 into .python'
Invoke-Uv python install 3.13 --no-bin
$python = Invoke-Uv python find 3.13 --managed-python

Write-Step 'Installing packages into .venv'
Invoke-Uv sync --python $python

Write-Step 'Checking tools'
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host 'FFmpeg not found. Most setups work without it; if audio fails, install it with:' -ForegroundColor Yellow
    Write-Host '  winget install Gyan.FFmpeg'
}
$cable = & .\.venv\Scripts\python.exe -c "import sounddevice as sd; print(any('CABLE Input' in d['name'] for d in sd.query_devices()))"
if ($cable -ne 'True') {
    Write-Host 'VB-Cable is not installed. You need it to use the voice in Discord/Zoom/etc.' -ForegroundColor Yellow
    Write-Host '  1. Download it from https://vb-audio.com/Cable/'
    Write-Host '  2. Unzip, right-click VBCABLE_Setup_x64.exe > Run as administrator > Install Driver'
    Write-Host '  3. Reboot. Until then the voice plays through your speakers.'
} else {
    Write-Host 'VB-Cable found.' -ForegroundColor Green
}

Write-Step 'Settings'
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host 'Created .env. Opening it: paste your API_KEY and VOICE_ID, then save.' -ForegroundColor Green
    Start-Process notepad.exe -ArgumentList (Join-Path $root '.env')
} else {
    Write-Host '.env already exists, leaving it as is.'
}

Write-Host "`nSetup finished. Double-click start.bat to run the voice changer." -ForegroundColor Green
