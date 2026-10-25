#!/bin/zsh
# VHS Capture — macOS / Linux (double-clic sur Mac). Prérequis : python3 + ffmpeg.
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || { echo "ffmpeg introuvable (brew install ffmpeg)"; exit 1; }
( sleep 2; open "http://localhost:${VHS_PORT:-8790}" 2>/dev/null || xdg-open "http://localhost:${VHS_PORT:-8790}" ) &
exec python3 app.py
