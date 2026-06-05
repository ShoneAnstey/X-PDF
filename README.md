# XPC PDF

A simple, lightweight PDF reader for Windows and Linux with one feature beyond
reading: stamping your saved signature image onto a page and saving. Built to get
away from Adobe for everyday reading and the occasional document signing.

- Read PDFs (open, page through, zoom, fit-to-width)
- Apply a transparent PNG signature: click **Add Signature**, drag to position,
  drag the bottom-right corner to resize, then **Sign & Save**
- Remembers your signature image so you only pick it once
- Saving overwrites the original file (atomic temp-file replace)
- Drag-and-drop a PDF onto the window to open it

> This applies a **visual image** of your signature. It is not a cryptographic /
> digital signature.

## Run from source

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # Windows: .venv\Scripts\python
.venv/bin/python main.py
```

First use:
1. **Set Signature** → pick your transparent PNG (remembered after this).
2. **Open** a PDF (or drag one onto the window).
3. **Add Signature**, position/resize it, then **Sign & Save**.

### Shortcuts
- Open: `Ctrl+O`  •  Sign & Save: `Ctrl+S`
- Next / Previous page: `PageDown` / `PageUp`
- Zoom in / out: `Ctrl++` / `Ctrl+-`

## Building installers

PyInstaller cannot cross-compile, so each binary is built on its own OS.
The easiest path is the bundled GitHub Actions workflow
(`.github/workflows/build-pdf.yml`): run it from the Actions tab (or push a `v*`
tag) and download the `XPC-PDF-windows` and `XPC-PDF-linux` artifacts.

### Linux AppImage (build locally)
```bash
bash packaging/build_appimage.sh
# -> dist/XPC_PDF-x86_64.AppImage   (chmod +x, then double-click)
```
Needs internet on first run (downloads `appimagetool`).

### Windows portable .exe (build on Windows)
```bat
packaging\build_windows.bat
REM -> dist\XPC PDF.exe   (portable, double-click)
```
The unsigned .exe may trigger a SmartScreen warning on first launch
(choose *More info → Run anyway*).

## Files
- `main.py` — entry point
- `viewer.py` — main window, toolbar, navigation, zoom, signature actions
- `pdf_document.py` — PyMuPDF wrapper: render pages, stamp + overwrite-save
- `signature_item.py` — draggable / resizable signature overlay
- `config.py` — remembers signature path, last folder, window geometry
- `packaging/` — PyInstaller spec, AppImage + Windows build scripts, icons
