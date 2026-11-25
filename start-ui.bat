@echo off
rem Double-click to open the voice changer window.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Not set up yet. Run setup.bat first.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" live-vc-ui.py
