@echo off
REM VHS Capture — Windows. Prérequis : Python 3.10+ et ffmpeg (winget install Python.Python.3.12 Gyan.FFmpeg)
REM Pilote : WinUSB via Zadig sur l'interface vidéo du boîtier (voir README), ou pilote du fabricant.
cd /d "%~dp0"
where ffmpeg >nul 2>nul || (echo ffmpeg introuvable. Installe-le : winget install Gyan.FFmpeg & pause & exit /b 1)
where python >nul 2>nul || (echo Python introuvable. Installe-le : winget install Python.Python.3.12 & pause & exit /b 1)
start "" http://localhost:8790
python app.py
pause
