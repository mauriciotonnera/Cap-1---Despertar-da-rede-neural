#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .build-venv
.build-venv/bin/python -m pip install --upgrade pip
.build-venv/bin/python -m pip install -r requirements.txt pyinstaller==6.22.3
.build-venv/bin/python -m PyInstaller --noconfirm --clean --onedir --windowed --name ImageDesk \
  --osx-bundle-identifier com.mauricio.imagedesk --add-data 'test_media.json:.' viewer.py

test -d dist/ImageDesk.app
echo "Created $(pwd)/dist/ImageDesk.app"
