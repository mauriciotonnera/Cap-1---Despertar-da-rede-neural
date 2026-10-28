"""Keep redistributable DLLs from the pinned old toolchain, not the CI host."""
import shutil
import sys
from pathlib import Path
import PySide2

root = Path(sys.argv[1]).resolve()
# API-set forwarders and ucrtbase from the build host are OS components, not
# portable runtime files. On Win7, KB2999226 supplies the matching UCRT. Copying
# Server 2022 forwarders would shadow the target OS's compatible implementation.
removed = []
for path in root.rglob("*.dll"):
    name = path.name.lower()
    if name.startswith(("api-ms-win-", "ext-ms-win-")) or name == "ucrtbase.dll":
        removed.append(str(path.relative_to(root)))
        path.unlink()
print("Removed host-specific Windows DLLs:", len(removed))
qt_root = Path(PySide2.__file__).parent
runtime_names = ("msvcp140*.dll", "vcruntime140*.dll", "concrt140.dll")
source_files = {}
for source in (qt_root, Path(sys.base_prefix)):
    for pattern in runtime_names:
        for path in source.glob(pattern):
            source_files[path.name.lower()] = path
if "msvcp140.dll" not in source_files or "vcruntime140.dll" not in source_files:
    raise RuntimeError("Pinned Python/Qt packages did not supply the required old MSVC runtime")
for path in root.rglob("*.dll"):
    if path.name.lower().startswith(("msvcp140", "vcruntime140", "concrt140")):
        source = source_files.get(path.name.lower())
        if source is None:
            raise RuntimeError("Unexpected host runtime in package: " + str(path))
        shutil.copy2(source, path)
for source in source_files.values():
    shutil.copy2(source, root / source.name)
print("Pinned MSVC runtime:", ", ".join(sorted(source_files)))
# Retain notices supplied by the installed Python distributions.
notice_root = root / "licenses"
notice_root.mkdir(exist_ok=True)
for package in ("PySide2", "shiboken2", "QtPy", "python_vlc", "packaging"):
    for dist in qt_root.parent.glob(package + "*.dist-info"):
        for source in dist.rglob("*"):
            if source.is_file() and any(word in source.name.lower() for word in ("license", "copying")):
                target = notice_root / package / source.relative_to(dist)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.exists():
    shutil.copy2(python_license, notice_root / "Python-LICENSE.txt")
