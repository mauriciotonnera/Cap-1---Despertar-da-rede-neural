"""Catch known newer-Windows dependencies; not a substitute for a Win7 run."""
import json
import struct
import sys
from pathlib import Path
import pefile

root = Path(sys.argv[1]).resolve()
machine = 0x8664 if struct.calcsize("P") == 8 else 0x14c
# Imports which would make the main application fail before it can start on 7.
newer_apis = {"GetSystemTimePreciseAsFileTime", "GetCurrentThreadStackLimits",
              "GetDpiForWindow", "GetDpiForSystem", "SetProcessDpiAwarenessContext",
              "GetOverlappedResultEx", "CreateFile2", "SetThreadDescription"}
failures, checked = [], []
for path in root.rglob("*"):
    if path.suffix.lower() not in (".exe", ".dll", ".pyd"):
        continue
    relative = str(path.relative_to(root))
    if path.name.lower().startswith(("api-ms-win-", "ext-ms-win-")) or path.name.lower() == "ucrtbase.dll":
        failures.append(relative + ": host OS DLL must not be bundled")
    # VLC includes optional Windows-8/10 display/audio plugins, selected only
    # on those OSes. Its Win7 paths use memory video output and DirectSound.
    optional = "plugins" in path.parts and "vlc" in path.parts
    pe = pefile.PE(str(path), fast_load=True)
    try:
        if pe.FILE_HEADER.Machine != machine:
            failures.append(relative + ": wrong CPU architecture")
        subsystem = (pe.OPTIONAL_HEADER.MajorSubsystemVersion, pe.OPTIONAL_HEADER.MinorSubsystemVersion)
        if subsystem > (6, 1) and not optional:
            failures.append(relative + ": subsystem newer than Windows 7")
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                                               pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        if not optional:
            for module in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
                for imported in module.imports:
                    name = imported.name.decode("ascii", "replace") if imported.name else ""
                    if name in newer_apis:
                        failures.append(relative + ": imports " + name)
        if path.name.lower().startswith(("msvcp140", "vcruntime140", "concrt140")):
            fixed = getattr(pe, "VS_FIXEDFILEINFO", [])
            if not fixed:
                failures.append(relative + ": runtime version is unknown")
            else:
                version = (fixed[0].FileVersionMS >> 16, fixed[0].FileVersionMS & 65535)
                if version > (14, 29):
                    failures.append(relative + ": MSVC runtime is newer than the pinned Win7 toolchain")
        checked.append(relative)
    finally:
        pe.close()
for name in ("ImageDesk-Legacy.exe", "python38.dll", "PySide2/Qt5Core.dll", "vlc/libvlc.dll", "vlc/libvlccore.dll"):
    if not (root / name).exists():
        failures.append("Missing required file: " + name)
report = {"success": not failures, "target": "Windows 7 SP1 (updated), 8/8.1, 10, 11",
          "bits": struct.calcsize("P") * 8, "binary_count": len(checked),
          "limitations": "Static checks for known incompatibilities only; target-OS testing is still required.",
          "failures": failures}
(root / "dependency-audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
if failures:
    raise SystemExit(1)
