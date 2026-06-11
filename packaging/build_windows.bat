@echo off
REM Build a portable Windows .exe for Inkstone.
REM
REM Run on Windows in a terminal (cmd). Requires Python 3.10+ on PATH.
REM Output: dist\XPDF.exe  (portable, double-click to run)

setlocal
set HERE=%~dp0
set ROOT=%HERE%..

cd /d "%ROOT%"

echo ^>^> Creating build venv...
if not exist .build_venv (
    python -m venv .build_venv
)
call .build_venv\Scripts\activate.bat

echo ^>^> Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r "%ROOT%\requirements.txt" pyinstaller

echo ^>^> Building with PyInstaller...
rmdir /s /q build 2>nul
python -m PyInstaller --noconfirm "%ROOT%\packaging\inkstone.spec"

echo.
echo ^>^> Done: dist\XPDF.exe
endlocal
