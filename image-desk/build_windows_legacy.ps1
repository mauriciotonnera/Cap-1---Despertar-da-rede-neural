param([ValidateSet('x86', 'x64')][string]$Architecture = 'x64')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

python -c "import sys, struct; assert sys.version_info[:3] == (3,8,10), 'Use Python 3.8.10'; assert struct.calcsize('P')*8 == (32 if '$Architecture' == 'x86' else 64), 'Wrong Python architecture'"
if ($LASTEXITCODE -ne 0) { throw 'Legacy Python requirements were not met' }
python -m venv .legacy-venv
if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed' }
$python = Join-Path $PSScriptRoot '.legacy-venv\Scripts\python.exe'
& $python -m pip install pip==25.0.1 setuptools==68.2.2 wheel==0.45.1
if ($LASTEXITCODE -ne 0) { throw 'Build environment installation failed' }
& $python -m pip install -r requirements-windows-legacy.txt pyinstaller==5.13.2 pyinstaller-hooks-contrib==2023.8 altgraph==0.17.4 pefile==2023.2.7 pywin32-ctypes==0.2.3
if ($LASTEXITCODE -ne 0) { throw 'Legacy dependency installation failed' }

$vlcArch = if ($Architecture -eq 'x64') { 'win64' } else { 'win32' }
$expected = if ($Architecture -eq 'x64') { 'eb4fd8a28291da73608c733786a09610fea865fbe94113bcb60b91c1ebb8404a' } else { 'f148ff49cdac6c0b6b7018ad7c4e6cd24c99bc6c2dea8258d82684261a639017' }
New-Item -ItemType Directory -Force -Path '.legacy-downloads' | Out-Null
$archive = Join-Path $PSScriptRoot ".legacy-downloads\vlc-3.0.23-$vlcArch.7z"
Invoke-WebRequest "https://download.videolan.org/pub/videolan/vlc/3.0.23/$vlcArch/vlc-3.0.23-$vlcArch.7z" -OutFile $archive
if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'VLC checksum did not match VideoLAN release' }
& 7z x $archive '-o.legacy-downloads' -y | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'VLC extraction failed' }
$vlc = Join-Path $PSScriptRoot '.legacy-downloads\vlc-3.0.23'
if (-not (Test-Path "$vlc\libvlc.dll")) { throw 'VLC package is incomplete' }

$env:QT_API = 'pyside2'
& $python -m PyInstaller --noconfirm --clean --onedir --windowed --noupx --name ImageDesk-Legacy --runtime-hook runtime_legacy.py --exclude-module PySide6 --exclude-module PyQt5 --exclude-module PyQt6 --add-data 'test_media.json;.' viewer.py
if ($LASTEXITCODE -ne 0) { throw 'Legacy executable build failed' }
$target = Join-Path $PSScriptRoot 'dist\ImageDesk-Legacy'
New-Item -ItemType Directory -Force -Path "$target\vlc" | Out-Null
Copy-Item "$vlc\libvlc.dll", "$vlc\libvlccore.dll" "$target\vlc\"
Copy-Item "$vlc\plugins" "$target\vlc\" -Recurse -Force
# VideoLAN ships codecs together with their license notices.
Get-ChildItem $vlc -File | Where-Object { $_.Name -match '^(COPYING|AUTHORS|THANKS|README)' } | Copy-Item -Destination "$target\vlc\"

# Never accidentally ship the newer runner's MSVC runtime. The Python 3.8 and
# PySide2 wheels carry their original redistributable DLLs, compatible with Win7.
& $python prepare_legacy_package.py $target
if ($LASTEXITCODE -ne 0) { throw 'Legacy runtime staging failed' }
& $python audit_windows_legacy.py $target
if ($LASTEXITCODE -ne 0) { throw 'Legacy compatibility audit failed' }
Copy-Item 'WINDOWS-LEGACY.md' "$target\READ-ME.txt"
Copy-Item 'check_legacy.cmd' "$target\Check-compatibility.cmd"
Copy-Item 'THIRD-PARTY-LEGACY.md' "$target\THIRD-PARTY.txt"
Write-Host "Created $target\ImageDesk-Legacy.exe"
