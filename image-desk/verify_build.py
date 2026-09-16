"""Run the actual executable's decoder checks on its native build runner."""

import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
if sys.platform == "win32":
    executable = root / "dist/ImageDesk.exe"
elif sys.platform == "darwin":
    executable = root / "dist/ImageDesk.app/Contents/MacOS/ImageDesk"
else:
    executable = root / "dist/ImageDesk/ImageDesk"
report = root / "dist/playback-check.json"
env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_MEDIA_BACKEND="ffmpeg")
result = subprocess.run([str(executable), "--self-test", str(report)],
                        env=env, capture_output=True, text=True, timeout=90)
if not report.exists():
    raise RuntimeError(f"Executable exited {result.returncode} without a report.\n{result.stderr}")
data = json.loads(report.read_text())
print(json.dumps(data, indent=2))
if result.returncode or not data.get("success"):
    raise SystemExit(1)
