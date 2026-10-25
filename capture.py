"""Pipeline de capture : une source par OS, un seul ffmpeg pour l'aperçu MJPEG + l'enregistrement MP4.

- macos   : magica (pilote libusb em28xx) → fifo → ffmpeg, son via AVFoundation
- windows : magica.exe (pilote WinUSB via Zadig) → TCP local → ffmpeg, son DirectShow ;
            sinon ffmpeg DirectShow avec le pilote du fabricant (VHS_WIN_MODE=dshow pour forcer)
- linux   : ffmpeg v4l2 (pilote noyau em28xx) + ALSA
"""
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
IS_WINDOWS = os.name == "nt"
STD = os.environ.get("VHS_STD", "pal").lower()           # pal | ntsc
SIZE = "720x576" if STD == "pal" else "720x480"
FPS = "25" if STD == "pal" else "30000/1001"
# Noms de périphériques probables pour un boîtier composite USB (auto-détection Windows)
CAPTURE_HINT = re.compile(r"avcap|em28|easycap|grabber|capture|cvbs|atv|video\s*grabber|usb\s*2\.0\s*video", re.I)


def detect_backend():
    forced = os.environ.get("VHS_BACKEND")
    if forced:
        return forced
    return {"Darwin": "macos", "Windows": "windows"}.get(platform.system(), "linux")


def _magica_path():
    exe = HERE / ("magica.exe" if IS_WINDOWS else "magica")
    return str(exe) if exe.exists() else shutil.which("magica")


def list_dshow_devices():
    """Retourne (vidéos, audios) DirectShow vus par ffmpeg."""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                         capture_output=True, text=True, errors="ignore").stderr
    videos, audios = [], []
    for line in out.splitlines():
        m = re.search(r'"([^"]+)"\s*\((video|audio)\)', line)
        if m:
            (videos if m.group(2) == "video" else audios).append(m.group(1))
    return videos, audios


def _pick(names, env_key):
    if os.environ.get(env_key):
        return os.environ[env_key]
    hits = [n for n in names if CAPTURE_HINT.search(n)]
    return hits[0] if hits else None


def _relay(proc, port):
    """Copie la sortie de magica vers le port TCP où ffmpeg écoute."""
    sock = None
    for _ in range(100):  # ffmpeg met un moment à ouvrir son port
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    if not sock:
        return
    try:
        with sock:
            while chunk := proc.stdout.read1(1 << 20):
                sock.sendall(chunk)
    except OSError:
        pass  # ffmpeg s'est arrêté


class Capture:
    """Le boîtier est exclusif : un seul pipeline à la fois, relancé à chaque début/fin d'enregistrement."""

    def __init__(self):
        self.backend = detect_backend()
        self.lock = threading.Lock()
        self.frame = b""
        self.frame_id = 0
        self.magica = None
        self.ffmpeg = None
        self.fifo = None
        self.recording = None  # (Path, start_time)
        self.error = ""

    # ---------- entrées ffmpeg par OS ----------
    def _inputs(self, with_audio):
        raw = ["-thread_queue_size", "1024"]
        if self.backend == "macos":
            magica = _magica_path()
            if not magica:
                raise RuntimeError("binaire magica introuvable à côté de app.py")
            self.fifo = tempfile.mktemp(prefix="vhs_", suffix=".fifo")
            os.mkfifo(self.fifo)
            self.magica = subprocess.Popen(
                [magica, "capture", "--input", os.environ.get("VHS_INPUT", "composite"),
                 "--std", STD, "--out", self.fifo],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            args = raw + ["-f", "rawvideo", "-pixel_format", "yuyv422", "-video_size", SIZE,
                          "-framerate", FPS, "-i", self.fifo]
            if with_audio:
                args += raw + ["-f", "avfoundation", "-i", ":" + os.environ.get("VHS_AUDIO_DEVICE", "Masster AVCap")]
            return args, "1:a"

        if self.backend == "windows" and _magica_path() and os.environ.get("VHS_WIN_MODE") != "dshow":
            return self._windows_magica_inputs(with_audio)

        if self.backend == "windows":
            videos, audios = list_dshow_devices()
            video = _pick(videos, "VHS_VIDEO_DEVICE")
            if not video:
                raise RuntimeError("Aucun boîtier de capture DirectShow trouvé. Vidéos vues : "
                                   + (", ".join(videos) or "aucune") + ". Définis VHS_VIDEO_DEVICE.")
            spec = f'video={video}'
            audio = _pick(audios, "VHS_AUDIO_DEVICE") if with_audio else None
            if audio:
                spec += f':audio={audio}'
            args = raw + ["-f", "dshow", "-rtbufsize", "256M", "-video_size", SIZE, "-framerate", FPS, "-i", spec]
            return args, ("0:a" if audio else None)

        # linux / serveur
        args = raw + ["-f", "v4l2", "-standard", STD.upper(), "-video_size", SIZE,
                      "-i", os.environ.get("VHS_VIDEO_DEVICE", "/dev/video0")]
        if with_audio:
            args += raw + ["-f", "alsa", "-i", os.environ.get("VHS_AUDIO_DEVICE", "hw:1")]
            return args, "1:a"
        return args, None

    def _windows_magica_inputs(self, with_audio):
        """Windows n'a pas de mkfifo : magica écrit sur stdout, on relaie vers ffmpeg en TCP local."""
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.magica = subprocess.Popen(
            [_magica_path(), "capture", "--input", os.environ.get("VHS_INPUT", "composite"),
             "--std", STD, "--out", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        threading.Thread(target=_relay, args=(self.magica, port), daemon=True).start()
        args = ["-thread_queue_size", "1024", "-f", "rawvideo", "-pixel_format", "yuyv422",
                "-video_size", SIZE, "-framerate", FPS, "-i", f"tcp://127.0.0.1:{port}?listen=1"]
        audio = None
        if with_audio:
            audio = _pick(list_dshow_devices()[1], "VHS_AUDIO_DEVICE")
            if audio:
                args += ["-thread_queue_size", "1024", "-f", "dshow", "-i", f"audio={audio}"]
        return args, ("1:a" if audio else None)

    def _build_cmd(self, record_path):
        inputs, audio_map = self._inputs(bool(record_path))
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", *inputs,
               "-map", "0:v", "-vf", "bwdif=0,scale=640:480", "-r", "12", "-q:v", "5", "-f", "mjpeg", "pipe:1"]
        if record_path:
            cmd += ["-map", "0:v"] + (["-map", audio_map] if audio_map else [])
            cmd += ["-vf", "bwdif=1,setdar=4/3", "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    str(record_path)]
        return cmd

    # ---------- cycle de vie ----------
    def start(self, record_path=None):
        self.stop()
        try:
            cmd = self._build_cmd(record_path)
        except RuntimeError as e:
            self.error = str(e)
            self._cleanup()
            return False
        self.ffmpeg = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.recording = (record_path, time.time()) if record_path else None
        threading.Thread(target=self._read_frames, args=(self.ffmpeg,), daemon=True).start()
        return True

    def _read_frames(self, proc):
        buf = b""
        while True:
            chunk = proc.stdout.read1(65536)
            if not chunk:
                err = proc.stderr.read().decode(errors="ignore").strip()
                if err and proc is self.ffmpeg:
                    self.error = err[-400:]
                return
            buf += chunk
            while True:
                start = buf.find(b"\xff\xd8")
                end = buf.find(b"\xff\xd9", start + 2)
                if start < 0 or end < 0:
                    break
                with self.lock:
                    self.frame = buf[start:end + 2]
                    self.frame_id += 1
                buf = buf[end + 2:]

    def stop(self):
        if self.ffmpeg and self.ffmpeg.poll() is None:
            try:
                self.ffmpeg.stdin.write(b"q")  # finalise proprement le MP4
                self.ffmpeg.stdin.flush()
            except OSError:
                pass
        if self.ffmpeg:
            try:
                self.ffmpeg.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.ffmpeg.kill()
                self.ffmpeg.wait()
        self._cleanup()

    def _cleanup(self):
        # magica peut rester bloqué sur la fifo et garder le boîtier : SIGINT puis SIGKILL
        if self.magica and self.magica.poll() is None:
            if IS_WINDOWS:
                self.magica.terminate()  # pas de SIGINT vers un process console ; l'OS libère l'USB
            else:
                self.magica.send_signal(signal.SIGINT)
            try:
                self.magica.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.magica.kill()
                self.magica.wait()
            time.sleep(0.5)  # laisse l'OS libérer l'interface USB
        if self.fifo and os.path.exists(self.fifo):
            os.remove(self.fifo)
        self.ffmpeg = self.magica = self.fifo = None
        self.recording = None

    def is_live(self):
        return bool(self.ffmpeg and self.ffmpeg.poll() is None)
