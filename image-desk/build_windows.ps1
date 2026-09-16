$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

py -3 -m venv .build-venv
if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed' }
$python = Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }
& $python -m pip install -r requirements.txt pyinstaller==6.22.3
if ($LASTEXITCODE -ne 0) { throw 'Build dependencies could not be installed' }
& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name ImageDesk --add-data 'test_media.json:.' viewer.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }

if (-not (Test-Path 'dist\ImageDesk.exe')) {
    throw 'Windows build did not create dist\ImageDesk.exe'
}
Write-Host "Created $((Resolve-Path 'dist\ImageDesk.exe').Path)"
