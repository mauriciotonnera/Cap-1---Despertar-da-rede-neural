$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

py -3 -m venv .build-venv
$python = Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt pyinstaller
& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name ImageDesk  viewer.py

if (-not (Test-Path 'dist\ImageDesk.exe')) {
    throw 'Windows build did not create dist\ImageDesk.exe'
}
Write-Host "Created $((Resolve-Path 'dist\ImageDesk.exe').Path)"
