#!/usr/bin/env bash
#
# Build a portable Linux AppImage for XPDF.
#
# Run on Linux (Debian/Ubuntu tested). Requires: python venv with the project deps,
# plus internet access on first run to download appimagetool. Output:
#   dist/XPDF-x86_64.AppImage
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"   # repo root: contains main.py and packaging/
PY="${PYTHON:-$ROOT/.venv/bin/python}"

cd "$ROOT"

echo ">> Installing build tooling (PyInstaller)…"
"$PY" -m pip install --quiet --upgrade pyinstaller

echo ">> Building one-dir bundle with PyInstaller…"
rm -rf build "dist/XPDF"
"$PY" -m PyInstaller --noconfirm "$ROOT/packaging/xpc_pdf.spec"

APPDIR="build/AppDir"
echo ">> Assembling AppDir at $APPDIR…"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -r "dist/XPDF/." "$APPDIR/usr/bin/"
cp "$ROOT/packaging/icon.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/xpdf.png"
cp "$ROOT/packaging/icon.png" "$APPDIR/xpdf.png"

cat > "$APPDIR/usr/share/applications/xpdf.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=XPDF
Exec=XPDF
Icon=xpdf
Categories=Office;Viewer;
MimeType=application/pdf;
DESKTOP
cp "$APPDIR/usr/share/applications/xpdf.desktop" "$APPDIR/xpdf.desktop"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "$HERE/usr/bin/XPDF" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

TOOL="build/appimagetool-x86_64.AppImage"
if [[ ! -x "$TOOL" ]]; then
    echo ">> Downloading appimagetool…"
    curl -L -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$TOOL"
fi

mkdir -p dist
echo ">> Building AppImage…"
# --appimage-extract-and-run avoids needing FUSE on the build host.
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "dist/XPDF-x86_64.AppImage"

echo ">> Done: dist/XPDF-x86_64.AppImage"
