@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install -r requirements-sender.txt pyinstaller
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name "Cancel Group Mics Sender" --collect-submodules pystray --workpath work\sender-build tray_sender.py
