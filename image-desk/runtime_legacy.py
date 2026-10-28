"""Select the bundled Qt 5 binding before QtPy imports it."""
import os
os.environ["QT_API"] = "pyside2"
os.environ.setdefault("QT_OPENGL", "software")
