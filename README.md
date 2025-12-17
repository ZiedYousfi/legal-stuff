# legal-stuff (Dokploy-only)

This repository is **Dokploy-first**: you deploy it by pointing Dokploy to this repo's `docker-compose.yml`.

- **No host machine steps** are required or assumed for this stack.
- **No host paths / bind mounts** are used by this stack.
- All persistence is handled via **Docker named volumes** managed by Dokploy/Docker.

If you're looking for "ssh to the server and create folders", that is intentionally **not** part of this setup.

---

## What this repo contains

- `legal-stuff/docker-compose.yml`: the complete Compose stack
- `legal-stuff/homepage/`: Homepage YAML config files (source of truth in git)
- `legal-stuff/homepage-config-gen`: an Alpine-based service that generates Homepage config with dynamic domain substitution

---

## Services

Defined in `docker-compose.yml`:

- `qbittorrent`
- `prowlarr`
- `sonarr`
- `radarr`
- `jellyfin`
- `jellyseerr`
- `homepage` (Next.js-based dashboard image)

---

## Persistence model (Dokploy-managed)

This stack uses **named volumes** for persistence. This ensures you do **not** re-download media on redeploy, and you do **not** rely on host bind mounts.

- App configs:
  - `qbittorrent_config`, `prowlarr_config`, `sonarr_config`, `radarr_config`, `jellyfin_config`, `jellyseerr_config`
- Homepage:
  - `homepage_config` mounted to `/app/config` (persistent)
  - `homepage_logs` mounted to `/app/config/logs` (persistent; prevents `ENOENT`)
- Media / downloads (persistent across redeploys):
  - `downloads` mounted to `/downloads`
  - `tv` mounted to `/tv`
  - `movies` mounted to `/movies`
  - `library` mounted to `/data` (Jellyfin)

Dokploy (and the Docker engine underneath it) is responsible for creating and persisting these volumes.

---

## Deploy on Dokploy

### 1) Create a Dokploy app from this repo

In Dokploy:

1. Create a new application (Docker Compose / Git-based).
2. Select this repository.
3. Set the Compose file path to:

- `legal-stuff/docker-compose.yml`

4. **Configure the `DOMAIN` environment variable** in Dokploy's environment settings:

```
DOMAIN=yourdomain.com
```
5. Deploy.

That's it. No host preparation.

### 2) Configure domains / routing (Dokploy)

How you expose services depends on your Dokploy reverse proxy setup.



This repo does not hardcode labels because Dokploy setups vary. Prefer configuring routing in Dokploy (or add labels once you confirm your proxy approach).

---

## Environment variables

### Required: DOMAIN

The `DOMAIN` environment variable is **required** and must be set in Dokploy's environment configuration.

Example:

```
DOMAIN=yourdomain.com
```

This domain will be used to generate all service URLs automatically:

- `https://${DOMAIN}` → Homepage dashboard
- `http://jellyfin.${DOMAIN}` → Jellyfin media player
- `http://jellyseer.${DOMAIN}` → Jellyseerr requests

**Default value:** `yourdomain.com` (if not specified)

### Optional: PUID/PGID

LinuxServer images commonly use `PUID`/`PGID`. This repo sets them to `1000/1000`.

In Dokploy you generally do one of the following:

- keep defaults, or
- override `PUID`/`PGID` in Dokploy environment configuration if needed.

Because volumes are managed by Docker/Dokploy, you typically won't need to manually fix permissions on the host.

---

## Homepage config management (important)

### Git is the source of truth (automated dynamic generation)

This repo is configured so that Homepage config is sourced from git **automatically at deploy/start time**, with dynamic domain substitution:

- `legal-stuff/homepage/*.yaml` is stored in git with `${DOMAIN}` placeholders
- the `homepage-config-gen` service runs first and:
  - replaces all `${DOMAIN}` occurrences with the actual domain value
  - copies the processed config into the persistent `homepage_config` named volume
- then `homepage` starts and reads config from `/app/config` (the volume)

This gives you:

- reproducible config from git on every deploy
- dynamic domain configuration (change `DOMAIN` env var to deploy on different domains)
- persistent volumes for logs and media (no re-downloads)

### How it works

The `homepage-config-gen` service uses Alpine Linux with `sed` to replace variables:

1. Reads `homepage/services.yaml` from the git repo
2. Replaces all `${DOMAIN}` with the actual domain (e.g., `yourdomain.com`)
3. Writes the processed config to the `homepage_config` volume
4. Copies other config files as-is

**Example:** If `DOMAIN=yourdomain.com`, then:

- `https://jellyfin.${DOMAIN}` → `https://jellyfin.yourdomain.com`
- `https://jellyseer.${DOMAIN}` → `https://jellyseer.yourdomain.com`

---

## Why this fixes `ENOENT: mkdir /app/config/logs`

That error happens when the app tries to create `/app/config/logs` and it’s not present/writable.

In this repo:

- `/app/config/logs` is a **dedicated named volume** (`homepage_logs`)
- it’s writable and persists across restarts
- so the app can always create/write logs there

---

## Updating / redeploying

In Dokploy:

- trigger a redeploy to pull newer images and recreate containers
- volumes remain intact unless you explicitly delete them

---

## Notes about setting up Dokploy (allowed host-level mention)

This repo assumes Dokploy is already installed and configured on a server. Installing Dokploy itself is a separate concern from this Compose stack.

If you need, share your Dokploy reverse proxy choice (Traefik/Nginx/Caddy) and desired domains, and I can add a ready-to-paste labels section for routing.
