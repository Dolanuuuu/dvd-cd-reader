#!/usr/bin/env python3
"""VHS Capture — interface web : aperçu live + enregistrement MP4 d'un boîtier de capture composite.

Config (variables d'environnement) :
  VHS_HOST      127.0.0.1 (local) ou 0.0.0.0 (accès réseau / serveur)
  VHS_PORT      8790
  VHS_PASSWORD  obligatoire si VHS_HOST n'est pas local (auth HTTP Basic, utilisateur libre)
  VHS_OUT_DIR   dossier des rushs (défaut ./rushs)
  VHS_BACKEND, VHS_STD, VHS_INPUT, VHS_VIDEO_DEVICE, VHS_AUDIO_DEVICE : voir capture.py / README
"""
import base64
import hmac
import json
import os
import re
import sys
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

from capture import Capture, list_dshow_devices

HERE = Path(__file__).resolve().parent
OUT_DIR = Path(os.environ.get("VHS_OUT_DIR", HERE / "rushs")).resolve()
OUT_DIR.mkdir(parents=True, exist_ok=True)
HOST = os.environ.get("VHS_HOST", "127.0.0.1")
PORT = int(os.environ.get("VHS_PORT", "8790"))
PASSWORD = os.environ.get("VHS_PASSWORD", "")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
SAFE_NAME = re.compile(r"[^\w\- ]", re.UNICODE)

cap = Capture()


def list_files():
    files = sorted(OUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    current = cap.recording[0] if cap.recording else None
    return [{"name": f.name, "size": f.stat().st_size, "mtime": f.stat().st_mtime,
             "recording": f == current} for f in files]


PAGE = (HERE / "index.html").read_text(encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _authorized(self):
        if not PASSWORD:
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                _, _, given = base64.b64decode(header[6:]).decode().partition(":")
            except ValueError:
                given = ""
            if hmac.compare_digest(given.encode(), PASSWORD.encode()):
                return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="VHS Capture"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._authorized():
            return
        url = urlparse(self.path)
        if url.path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/stream":
            self._stream()
        elif url.path == "/api/status":
            rec = cap.recording
            self._json({
                "live": cap.is_live(),
                "backend": cap.backend,
                "recording": rec[0].name if rec else None,
                "elapsed": time.time() - rec[1] if rec else 0,
                "error": cap.error,
                "files": list_files(),
            })
        elif url.path == "/api/devices" and cap.backend == "windows":
            videos, audios = list_dshow_devices()
            self._json({"video": videos, "audio": audios})
        elif url.path.startswith("/files/"):
            self._serve_file(unquote(url.path[len("/files/"):]))
        else:
            self.send_error(404)

    def do_POST(self):
        if not self._authorized():
            return
        url = urlparse(self.path)
        if url.path == "/api/record/start":
            raw = parse_qs(url.query).get("name", [""])[0]
            name = SAFE_NAME.sub("_", raw).strip() or time.strftime("rush_%Y%m%d_%H%M%S")
            path = OUT_DIR / f"{name}.mp4"
            n = 2
            while path.exists():
                path = OUT_DIR / f"{name}_{n}.mp4"
                n += 1
            cap.error = ""
            ok = cap.start(path)
            self._json({"ok": ok, "file": path.name, "error": cap.error})
        elif url.path == "/api/record/stop":
            cap.start(None)
            self._json({"ok": True})
        elif url.path == "/api/restart":
            cap.error = ""
            cap.start(None)
            self._json({"ok": True})
        else:
            self.send_error(404)

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        last = -1
        try:
            while True:
                with cap.lock:
                    fid, frame = cap.frame_id, cap.frame
                if fid != last and frame:
                    last = fid
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                time.sleep(0.04)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_file(self, name):
        path = (OUT_DIR / name).resolve()
        if path.parent != OUT_DIR.resolve() or not path.is_file():
            self.send_error(404)
            return
        size = path.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else 0
            end = int(b) if b else size - 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    if HOST not in LOCAL_HOSTS and not PASSWORD:
        sys.exit("Refusé : VHS_HOST expose l'app sur le réseau, définis VHS_PASSWORD.")
    server = ThreadingHTTPServer((HOST, PORT), Handler)  # bind avant de prendre le boîtier
    cap.start(None)
    shown = "localhost" if HOST in LOCAL_HOSTS else HOST
    print(f"VHS Capture [{cap.backend}] → http://{shown}:{PORT}  (rushs : {OUT_DIR})", flush=True)
    try:
        server.serve_forever()
    finally:
        cap.stop()
