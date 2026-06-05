# PyInstaller spec for XPDF.
#
# Build (run on the TARGET OS — PyInstaller does not cross-compile):
#   pyinstaller pdf/packaging/xpc_pdf.spec
#
# Windows  -> dist/XPDF.exe   (portable, double-click to run)
# Linux    -> dist/XPDF/      (one-dir bundle, wrapped into an AppImage)
#
# On Windows the icon is icon.ico; on Linux PyInstaller ignores .ico so we pass None.

import sys
from pathlib import Path

spec_dir = Path(SPECPATH)
pdf_dir = spec_dir.parent

is_windows = sys.platform.startswith("win")
icon = str(spec_dir / "icon.ico") if is_windows else None

block_cipher = None

a = Analysis(
    [str(pdf_dir / "main.py")],
    pathex=[str(pdf_dir)],
    binaries=[],
    datas=[(str(spec_dir / "icon.png"), ".")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Trim unused (large) Qt modules to keep the bundle smaller.
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtMultimedia",
        "PySide6.Qt3DCore",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if is_windows:
    # One-file portable .exe on Windows.
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="XPDF",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        console=False,
        icon=icon,
    )
else:
    # One-dir bundle on Linux (gets wrapped into an AppImage).
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="XPDF",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        icon=icon,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        name="XPDF",
    )
