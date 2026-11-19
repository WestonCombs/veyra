@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
".venv\Scripts\python.exe" -m pip install -r requirements-sender.txt pyinstaller
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --name Veyra --icon assets\veyra.ico --collect-submodules pystray --workpath work\veyra-build desktop_app.py
