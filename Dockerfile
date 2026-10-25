# Serveur Linux avec le boîtier branché dessus (pilote noyau em28xx → /dev/video0 + ALSA)
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY app.py capture.py index.html ./
ENV VHS_HOST=0.0.0.0 VHS_PORT=8790 VHS_BACKEND=linux VHS_OUT_DIR=/rushs
EXPOSE 8790
CMD ["python", "app.py"]
