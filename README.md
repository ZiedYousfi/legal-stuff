# Media Stack

A local Docker Compose stack for Jellyfin, qBittorrent, Prowlarr, Sonarr, Radarr, and Recyclarr.

Every media-aware container sees the same `/media` path. This avoids remote path mappings and allows hardlinks between downloads and libraries.

The setup supports Windows with Docker Desktop and native Linux.

## What it installs

| Service | Purpose | Address |
| --- | --- | --- |
| Jellyfin | Media server | `http://localhost:8096` |
| qBittorrent | Download client | `http://localhost:8080` |
| Prowlarr | Indexer manager | `http://localhost:9696` |
| Sonarr | Series manager | `http://localhost:8989` |
| Radarr | Movie manager | `http://localhost:7878` |
| Recyclarr | Quality profile synchronization | No web interface |

Only Jellyfin is exposed to the local network. The administration interfaces listen on `127.0.0.1`.

The qBittorrent traffic port `6881` remains exposed for incoming torrent connections.

## Media layout

The setup asks for one media directory and creates this structure:

```text
Media/
|-- Downloads/
|-- Movies/
`-- Series/
```

Every container uses the following paths:

```text
/media/Downloads
/media/Movies
/media/Series
```

Application state is stored in the repository's local `config/` directory. The directory is excluded from Git.

## Requirements

Install these tools before running the setup:

- Docker Engine with Docker Compose on Linux
- Docker Desktop using Linux containers on Windows
- Python 3.10 or newer

Docker must be running before setup begins.

On Windows, Docker Desktop must have access to the selected media drive.

## Download

Download the repository ZIP:

https://github.com/inayayousfi/legal-stuff/archive/refs/heads/mommy.zip

Extract the archive to its permanent location. The automatic startup configuration uses that absolute path, so moving the directory later will break startup.

## First setup

Open a terminal inside the extracted directory.

On Windows:

```powershell
py media_stack.py setup
```

On Linux:

```bash
python3 media_stack.py setup
```

The script performs these checks and actions:

1. Verifies that Docker and Docker Compose are available.
2. Asks for the media directory.
3. Presents a `Y/n` confirmation for the qBittorrent legal notice.
4. Creates the media and configuration directories.
5. Writes the local `.env`.
6. Starts Jellyfin, qBittorrent, Prowlarr, Sonarr, and Radarr.
7. Displays the complete manual configuration checklist.
8. Stores the chosen local administration credentials in `.env`.
9. Requests the Sonarr and Radarr API keys.
10. Applies the Recyclarr profiles.
11. Installs automatic startup.

A completed setup overwrites `.env`. Existing application configuration under `config/` remains available.

An interrupted setup restores the previous `.env`.

## Manual application setup

The Python script prints these instructions during setup.

### qBittorrent

Open this link:

```text
http://localhost:8080
```

The script reads the generated temporary password from the container logs and displays it with the `admin` username.

After signing in:

1. Open `Tools > Options > Web UI`.
2. Find the `Authentication` section.
3. Set the username from `QBIT_USER` in `.env`.
4. Set the password from `QBIT_PASS` in `.env`.
5. Open the `Downloads` section.
6. Set `Saving Management > Default Save Path` to `/media/Downloads`.
7. Click `Apply`, then `OK`.

### Sonarr

Open:

```text
http://localhost:8989
```

1. Complete first-run authentication with `SONARR_USER` and `SONARR_PASS` from `.env`.
2. Open `Settings > Media Management`.
3. Under `Root Folders`, click `Add Root Folder`.
4. Select `/media/Series` and save it.
5. Open `Settings > Download Clients`.
6. Click `Add`, then select qBittorrent.
7. Set `Host` to `qbittorrent` and `Port` to `8080`.
8. Use `QBIT_USER` and `QBIT_PASS` from `.env`.
9. Set `Category` to `sonarr`.
10. Click `Test`, then `Save`.

Use `qbittorrent`, not `localhost`. Inside the Sonarr container, `localhost` means Sonarr itself.

Copy the API key for the next terminal prompt:

```text
Settings > General > Security > API Key
```

### Radarr

Open:

```text
http://localhost:7878
```

1. Complete first-run authentication with `RADARR_USER` and `RADARR_PASS` from `.env`.
2. Open `Settings > Media Management`.
3. Under `Root Folders`, click `Add Root Folder`.
4. Select `/media/Movies` and save it.
5. Open `Settings > Download Clients`.
6. Click `Add`, then select qBittorrent.
7. Set `Host` to `qbittorrent` and `Port` to `8080`.
8. Use `QBIT_USER` and `QBIT_PASS` from `.env`.
9. Set `Category` to `radarr`.
10. Click `Test`, then `Save`.

Copy the API key from:

```text
Settings > General > Security > API Key
```

### Prowlarr

Open:

```text
http://localhost:9696
```

1. Complete first-run authentication with `PROWLARR_USER` and `PROWLARR_PASS` from `.env`.
2. Open `Settings > Apps`.
3. Add Sonarr with `Full Sync`.
4. Set `Prowlarr Server` to `http://prowlarr:9696`.
5. Set `Sonarr Server` to `http://sonarr:8989`.
6. Use `SONARR_API_KEY` from `.env`, then test and save.
7. Add Radarr with `Full Sync`.
8. Set `Prowlarr Server` to `http://prowlarr:9696`.
9. Set `Radarr Server` to `http://radarr:7878`.
10. Use `RADARR_API_KEY` from `.env`, then test and save.
11. Open `Indexers`, add your indexers, then test each one.

### Jellyfin

Open:

```text
http://localhost:8096
```

1. Select the display language.
2. Create the Jellyfin administrator account.
3. Do not reuse credentials from `.env` for Jellyfin.
4. Add a Movies library using `/media/Movies`.
5. Add a Shows library using `/media/Series`.
6. Complete the remaining setup wizard pages.

## Recyclarr profiles

Recyclarr creates one profile named `4K Progressive` in Sonarr and Radarr.

The Sonarr profile uses the TRaSH Guides WEB 2160p combined profile. It accepts a lower available quality and upgrades to 4K later.

The Radarr profile uses the TRaSH Guides UHD Bluray and WEB rules. It prefers these qualities in order:

```text
Bluray 2160p
WEB 2160p
Bluray 1080p
WEB 1080p
HDTV 1080p
Bluray 720p
WEB 720p
HDTV 720p
DVD
SDTV
```

The profile upgrades downloaded movies until Bluray 2160p is available.

Both profiles favor HDR10+ while retaining HDR10 compatibility. Dolby Vision releases without an HDR fallback are rejected.

Anime uses the same progressive profiles.

The stack expects subtitles to be embedded in the media files. It does not install Bazarr or download missing subtitles.

Recyclarr runs after setup and after every `media_stack.py start`. Running `docker compose up -d` directly skips that synchronization.

## Daily commands

Show every command with a short description:

```bash
python3 media_stack.py help
```

`-h` prints the same general help. Add `-h` after any command for its detailed help:

```bash
python3 media_stack.py setup -h
python3 media_stack.py start -h
python3 media_stack.py stop -h
python3 media_stack.py status -h
```

Start the stack and synchronize Recyclarr:

```bash
python3 media_stack.py start
```

On Windows, replace `python3` with `py`.

Show container status:

```bash
python3 media_stack.py status
```

Stop the stack:

```bash
python3 media_stack.py stop
```

## Automatic startup

### Linux user service

The setup can install:

```text
~/.config/systemd/user/media-stack.service
```

It starts with the user's systemd session.

Inspect it with:

```bash
systemctl --user status media-stack.service
```

Disable and remove it with:

```bash
systemctl --user disable --now media-stack.service
rm ~/.config/systemd/user/media-stack.service
systemctl --user daemon-reload
```

### Linux system service

The setup can instead install:

```text
/etc/systemd/system/media-stack.service
```

This option requires `sudo` and starts the stack during system boot.

Inspect it with:

```bash
sudo systemctl status media-stack.service
```

Disable and remove it with:

```bash
sudo systemctl disable --now media-stack.service
sudo rm /etc/systemd/system/media-stack.service
sudo systemctl daemon-reload
```

### Windows

The setup creates a hidden launcher named `media-stack.vbs` in the current user's Startup folder.

The launcher waits up to five minutes for Docker Desktop. Startup output is written to:

```text
config/startup.log
```

Remove the launcher from:

```text
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```

## Updating

Container images are pinned by multi-platform digest. A new installation therefore uses the same image builds until `compose.yaml` is updated.

After updating the digests, pull and restart the stack:

```bash
docker compose pull
python3 media_stack.py start
```

Application data remains under `config/`.

## Backups

Back up these items:

```text
.env
config/
Media/
```

The `.env` file contains the qBittorrent, Sonarr, Radarr, and Prowlarr credentials, plus the Sonarr and Radarr API keys. These stored credentials are a local reference; the containers do not use them to configure application authentication. Do not commit or share this file.

The `recyclarr/recyclarr.yml` file contains no secrets and remains tracked by Git.

## Previous stack

This repository previously used Docker named volumes. The new setup does not migrate them.

Existing named volumes remain untouched, but the new containers do not mount them. Recover or migrate their contents manually before deleting those volumes.

An older `.env` also remains accessible in the public Git history. Credentials from the previous stack must be treated as exposed and replaced. The new setup generates fresh application configuration and collects the new Sonarr and Radarr keys.

## Security notes

qBittorrent is not routed through a VPN.

Jellyfin is available to the local network. Protect its administrator account with a strong password.

Sonarr, Radarr, Prowlarr, and qBittorrent are accessible only from the Docker host.

Jellyfin does not officially support Docker on Windows or macOS. This does not mean it cannot work, so the setup remains worth trying. Some features, particularly hardware-accelerated transcoding, may still fail on those hosts.
