# XPDF

A simple, lightweight tabbed PDF reader for Windows and Linux with one feature
beyond reading: stamping your saved signature image onto a page and saving. Built
to get away from Adobe for everyday reading and the occasional document signing.

- Read PDFs (open, page through, zoom, fit-to-width)
- **Multiple tabs** — open many PDFs at once; drag tabs to reorder
- Apply a transparent PNG signature: click **Add Signature**, drag to position,
  drag the bottom-right corner to resize, then **Sign & Save**
- Remembers your signature image so you only pick it once
- Saving overwrites the original file (atomic temp-file replace)
- Drag-and-drop one or more PDFs onto the window to open them in tabs

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
- Open: `Ctrl+O`  •  Close tab: `Ctrl+W`  •  Sign & Save: `Ctrl+S`
- Next / Previous page: `PageDown` / `PageUp`
- Zoom in / out: `Ctrl++` / `Ctrl+-`, or **Ctrl + mouse wheel**

## Downloads (GitHub Actions)

PyInstaller cannot cross-compile, so each binary is built on its own OS via the
bundled workflow (`.github/workflows/build-pdf.yml`). Run it from the **Actions**
tab (or push a `v*` tag) and download the artifacts:

| Artifact | Contents |
|----------|----------|
| `XPDF-windows-installer` | `XPDF-Setup.exe` — installer with Desktop + Start Menu shortcuts |
| `XPDF-windows-portable` | `XPDF.exe` — portable, no install |
| `XPDF-linux` | `XPDF-x86_64.AppImage` — portable |

## Building locally

### Linux AppImage
```bash
bash packaging/build_appimage.sh
# -> dist/XPDF-x86_64.AppImage   (chmod +x, then double-click)
```
Needs internet on first run (downloads `appimagetool`).

### Windows portable .exe (build on Windows)
```bat
packaging\build_windows.bat
REM -> dist\XPDF.exe   (portable, double-click)
```

### Windows installer (build on Windows)
Build the `.exe` first, then compile the installer with Inno Setup:
```bat
iscc packaging\xpdf_installer.iss
REM -> dist\XPDF-Setup.exe   (creates Desktop + Start Menu shortcuts)
```
The unsigned binaries may trigger a SmartScreen warning on first launch
(choose *More info → Run anyway*).

## Files
- `main.py` — entry point, app icon
- `viewer.py` — main window: tab host, toolbar, navigation, zoom, signature actions
- `document_tab.py` — one open PDF per tab: render, navigate, zoom, sign
- `pdf_document.py` — PyMuPDF wrapper: render pages, stamp + overwrite-save
- `signature_item.py` — draggable / resizable signature overlay
- `config.py` — remembers signature path, last folder, window geometry
- `packaging/` — PyInstaller spec, AppImage + Windows build scripts, Inno Setup
  installer script, icons
