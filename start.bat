@echo off
REM VHS Capture — Windows. Prérequis : Python 3.10+ et ffmpeg dans le PATH (winget install Gyan.FFmpeg Python.Python.3.12)
cd /d "%~dp0"
where ffmpeg >nul 2>nul || (echo ffmpeg introuvable. Installe-le : winget install Gyan.FFmpeg & pause & exit /b 1)
start "" http://localhost:8790
python app.py
pause
