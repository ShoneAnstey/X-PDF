# XPDF

A simple, lightweight tabbed PDF reader for Windows and Linux that does more than
read: sign, fill, search, print, and reorganize pages — without the bloat,
subscriptions, or cloud uploads of commercial PDF software. Built to get away from
paid PDF suites for everyday reading, signing, and light editing.

### Read & navigate
- Open, page through, zoom, and fit-to-width
- **Multiple tabs** — open many PDFs at once; drag tabs to reorder
- **Continuous vertical scrolling** with crisp HiDPI rendering
- **Sidebar** with page **thumbnails** and the document **outline / bookmarks** —
  click to jump (toggle with `F9`)
- **Find** text in a document (`Ctrl+F`) with match highlighting
- **Print** (`Ctrl+P`)
- **Recent files** menu, and drag-and-drop one or more PDFs onto the window
- **Dark mode** for the app interface (View → Dark Mode)

### Sign
- Apply your signature: **Signature ▾ → Place signature on page**, drag to
  position, drag the corner to resize, **rotate** with `R` / `Shift+R`, then save
- **No transparent PNG needed** — sign a blank sheet of paper, photograph it, and
  open the photo; XPDF removes the paper background automatically (keeps the ink,
  even blue pen, and auto-crops)
- Remembers your signature image so you only pick it once

### Fill & edit
- **Typewriter / text tool** (`Ctrl+T`) — type directly onto a page (fill forms,
  add notes), then save
- **Page surgery** — right-click any page to **extract it to a new PDF** or
  **delete it** from the document

### Save
- Saving overwrites the original file (atomic temp-file replace), or use
  **Save As** (`Ctrl+Shift+S`) to write a copy

> This applies a **visual image** of your signature. It is not a cryptographic /
> digital signature.

## Run from source

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # Windows: .venv\Scripts\python
.venv/bin/python main.py
```

Run the tests with:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/
```

First use:
1. **Signature ▾ → Signature setup...** → pick your signature image (remembered
   after this). No signature file? Sign a blank sheet of paper, take a photo, and
   pick that — the paper background is removed for you.
2. **Open** a PDF (or drag one onto the window).
3. **Signature ▾ → Place signature on page**, position/resize/rotate it, then save.

### Shortcuts
- Open: `Ctrl+O`  •  Close tab: `Ctrl+W`  •  Save: `Ctrl+S`  •  Save As: `Ctrl+Shift+S`
- Find: `Ctrl+F`  •  Print: `Ctrl+P`  •  Add text: `Ctrl+T`  •  Toggle sidebar: `F9`
- Rotate signature: `R` / `Shift+R`
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
- `viewer.py` — main window: tab host, toolbar, menus, sidebar, dark mode, navigation
- `document_tab.py` — one open PDF per tab: render, navigate, zoom, sign, text, find, page surgery
- `pdf_document.py` — PyMuPDF wrapper: render pages, thumbnails, outline, stamp/save, extract/delete pages
- `sidebar.py` — page thumbnails + outline navigation panel
- `signature_item.py` — draggable / resizable / rotatable signature overlay
- `text_item.py` — draggable typewriter text overlay
- `signature_processing.py` — turns a paper photo into a transparent-background signature
- `config.py` — remembers signature path, last folder, recent files, window geometry, UI prefs
- `version.py` — version string + CI build provenance
- `security/` — self-contained pre-commit security gate
- `packaging/` — PyInstaller spec, AppImage + Windows build scripts, Inno Setup
  installer script, icons

## License

Released into the **public domain** under [The Unlicense](LICENSE) — free for
anyone to use, modify, and distribute, forever, with no restrictions.

