# VHS Capture

Interface web pour numériser des cassettes : aperçu live, enregistrement MP4 (H.264 + AAC, désentrelacé, 4:3), lecture et téléchargement des rushs.
Prérequis partout : **Python 3.10+** et **ffmpeg**. Aucune dépendance pip.

## macOS
`./start.command` (ou double-clic) → http://localhost:8790
La vidéo passe par `magica` (pilote libusb em28xx, issu de [kode54/ManzanaMagica](https://github.com/kode54/ManzanaMagica) + ID `eb1a:5043` ajouté), car macOS n'a pas de pilote pour ces boîtiers.

## Windows
1. Installer le **pilote du boîtier** (CD/site du fabricant, ou pilote générique « EM2860 / USB 2.0 Video Capture »). Il doit apparaître dans le Gestionnaire de périphériques → *Contrôleurs son, vidéo et jeu* / *Périphériques d'imagerie*.
2. `winget install Python.Python.3.12 Gyan.FFmpeg`
3. Double-clic sur `start.bat`.

Le boîtier est détecté automatiquement (DirectShow). Sinon, voir les noms via http://localhost:8790/api/devices et forcer :
`set VHS_VIDEO_DEVICE=Nom exact` et `set VHS_AUDIO_DEVICE=Nom exact` avant `python app.py`.
Ne pas utiliser `magica` sous Windows (il faudrait remplacer le pilote par WinUSB via Zadig).

## Serveur Linux (boîtier branché sur le serveur)
Le noyau Linux gère nativement les em28xx (`/dev/video0` + carte ALSA).
```
echo VHS_PASSWORD=un-mot-de-passe > .env
docker compose up -d --build        # → http://IP-du-serveur:8790
```
Sans Docker : `VHS_HOST=0.0.0.0 VHS_PASSWORD=... python3 app.py`.
Carte son du boîtier : `arecord -l` → `VHS_AUDIO_DEVICE=hw:N`.

## Accès depuis un autre appareil
`VHS_HOST=0.0.0.0` ouvre l'app au réseau ; `VHS_PASSWORD` est alors obligatoire (auth HTTP Basic, utilisateur libre).
Pour Internet, passer derrière un reverse proxy HTTPS (Traefik/Caddy) ou un VPN — ne pas exposer en HTTP brut.

## Variables
| Variable | Défaut | Rôle |
|---|---|---|
| `VHS_HOST` | `127.0.0.1` | `0.0.0.0` pour le réseau |
| `VHS_PORT` | `8790` | |
| `VHS_PASSWORD` | — | requis hors localhost |
| `VHS_OUT_DIR` | `./rushs` | dossier des MP4 |
| `VHS_BACKEND` | auto | `macos` / `windows` / `linux` |
| `VHS_STD` | `pal` | `pal` ou `ntsc` |
| `VHS_INPUT` | `composite` | `svideo` (macOS) |
| `VHS_VIDEO_DEVICE` / `VHS_AUDIO_DEVICE` | auto | nom DirectShow, `/dev/videoN`, `hw:N` |

Le boîtier ne peut être utilisé que par un programme à la fois : l'aperçu se coupe ~1 s au début et à la fin d'un enregistrement.

## Recompiler magica (macOS)
`cd magica-src && swift build --product magica && cp .build/debug/magica ..`
Fork de [kode54/ManzanaMagica](https://github.com/kode54/ManzanaMagica) avec : ID `eb1a:5043` (Masster AVCap) ajouté, `HAVE_PIPE2` désactivé dans la libusb embarquée (absent sur macOS).

## Licence
GPL-2.0-only (comme ManzanaMagica et les pilotes Linux em28xx dont il est porté).
