@echo off
setlocal
cd /d "%~dp0"
if exist "dist\Cancel Group Mics Sender.exe" (
  start "" "dist\Cancel Group Mics Sender.exe"
  exit /b 0
)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
".venv\Scripts\python.exe" -m pip install -r requirements-sender.txt
if errorlevel 1 goto failed
start "" ".venv\Scripts\pythonw.exe" tray_sender.py
exit /b 0
:failed
echo Could not install sender dependencies.
pause
