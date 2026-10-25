# VHS Capture

Interface web pour numériser des cassettes : aperçu live, enregistrement MP4 (H.264 + AAC, désentrelacé, 4:3), lecture et téléchargement des rushs.
Prérequis partout : **Python 3.10+** et **ffmpeg**. Aucune dépendance pip.

## macOS
`./start.command` (ou double-clic) → http://localhost:8790
La vidéo passe par `magica` (pilote libusb em28xx, issu de [kode54/ManzanaMagica](https://github.com/kode54/ManzanaMagica) + ID `eb1a:5043` ajouté), car macOS n'a pas de pilote pour ces boîtiers.

## Windows
Deux modes, choisis automatiquement : **magica** si `magica.exe` est présent (par défaut), sinon le pilote du fabricant.

### Mode magica (recommandé, même procédé que sur Mac)
1. `winget install Python.Python.3.12 Gyan.FFmpeg`
2. **Zadig** (https://zadig.akeo.ie), une seule fois :
   - *Options → List All Devices*
   - choisir **Masster AVCap (Interface 0)** — surtout pas le périphérique entier, sinon le son du boîtier disparaît
   - pilote cible **WinUSB** → *Replace Driver*
3. Double-clic sur `start.bat` → http://localhost:8790

La vidéo passe par `magica.exe` (relayée à ffmpeg en TCP local), le son par le périphérique audio USB du boîtier (DirectShow).
Si le son n'est pas trouvé : `/api/devices` liste les noms, puis `set VHS_AUDIO_DEVICE=Nom exact`.
Pour revenir en arrière : Gestionnaire de périphériques → le boîtier → *Désinstaller le pilote*, puis débrancher/rebrancher.

### Mode pilote du fabricant
Si le boîtier a un pilote Windows qui fonctionne (il apparaît comme caméra / périphérique de capture) : `set VHS_WIN_MODE=dshow` avant `python app.py`.
Détection automatique du nom ; sinon `set VHS_VIDEO_DEVICE=Nom exact`.

`magica.exe` est compilé par mingw-w64 (workflow GitHub `magica-windows.yml`, ou `make -f Makefile.win` dans `magica-src/`).

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
| `VHS_WIN_MODE` | `magica` | `dshow` = pilote du fabricant |
| `VHS_STD` | `pal` | `pal` ou `ntsc` |
| `VHS_INPUT` | `composite` | `svideo` (macOS) |
| `VHS_VIDEO_DEVICE` / `VHS_AUDIO_DEVICE` | auto | nom DirectShow, `/dev/videoN`, `hw:N` |

Le boîtier ne peut être utilisé que par un programme à la fois : l'aperçu se coupe ~1 s au début et à la fin d'un enregistrement.

## Recompiler magica (macOS)
`cd magica-src && swift build --product magica && cp .build/debug/magica ..`
Fork de [kode54/ManzanaMagica](https://github.com/kode54/ManzanaMagica) avec : ID `eb1a:5043` (Masster AVCap) ajouté, `HAVE_PIPE2` désactivé dans la libusb embarquée (absent sur macOS), `--out -` (stdout) et portage Windows (horloge, nom de thread).

## Licence
GPL-2.0-only (comme ManzanaMagica et les pilotes Linux em28xx dont il est porté).
