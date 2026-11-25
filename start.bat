@echo off
rem Double-click to start the voice changer.
rem   start.bat --devices   list microphones and outputs
rem   start.bat --voices    list the ElevenLabs voices your key can use
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Not set up yet. Run setup.bat first.
    pause
    exit /b 1
)
if not exist ".env" (
    echo .env is missing. Run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" live-vc.py %*
pause
