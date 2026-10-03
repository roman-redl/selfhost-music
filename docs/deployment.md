# Deployment — selfhost-music

From zero to a running server. Two paths: the one-shot script, or manual steps.

## Prerequisites

- A VPS: Ubuntu 24.04, 2+ GB RAM, 20+ GB disk (Oracle Cloud free tier works fine)
- A DuckDNS subdomain (or edit the scripts for any other Dynamic DNS / real domain)
- Ports 22, 80, 443 open (Oracle Cloud: also configure the VCN security list)

## One-shot provisioning

```bash
curl -sSL https://raw.githubusercontent.com/roman-redl/selfhost-music/main/scripts/setup-vps.sh | \
  bash -s -- <duckdns-token> <duckdns-subdomain>
# Result: stack running at https://<subdomain>.duckdns.org
```

The script installs Docker, clones this repo, writes `.env` (edit it to set the
Navidrome credentials!), starts Caddy + Navidrome, installs the import watcher as a
systemd service, and sets up the DuckDNS update cron.

## Manual steps (what the script does)

1. **Packages**

   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-v2 \
        python3-pip davfs2 ffmpeg bs1770gain
   sudo pip3 install --break-system-packages mutagen pillow
   ```

2. **Repo and secrets**

   ```bash
   sudo git clone https://github.com/roman-redl/selfhost-music.git /opt/selfhost-music
   cd /opt/selfhost-music
   cp .env.example .env && nano .env   # DOMAIN, NAVIDROME_USER/PASSWORD, backup creds
   ```

3. **Start the stack**

   ```bash
   sudo docker compose up -d
   ```

4. **Import watcher**

   ```bash
   sudo cp config/music-watcher.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now music-watcher
   tail -f /var/log/music-import.log
   ```

5. **Backup job (WebDAV)**

   ```bash
   # /etc/davfs2/secrets (chmod 600):
   https://webdav.cloud.mail.ru <email> <app-password>
   # /etc/davfs2/davfs2.conf:
   use_locks 0
   buf_size 64          # required on Linux >= 6.16, else readdir fails

   # /etc/fstab:
   https://webdav.cloud.mail.ru /mnt/mailru-backup davfs noauto,_netdev 0 0

   sudo mkdir -p /mnt/mailru-backup
   sudo mount /mnt/mailru-backup && ls /mnt/mailru-backup   # smoke test

   # root crontab:
   37 4 * * * bash /opt/selfhost-music/scripts/backup-to-cloud.sh
   ```

   The VPS also runs an unrelated adjacent job at 04:11 (`/usr/local/bin/git-backup-to-cloud`,
   mirrors of personal GitHub repos into the same WebDAV mount) — see
   [architecture.md](architecture.md), "Backups". It is not installed by this repo.

6. **First login** — open `https://$DOMAIN`, create the admin account, drop your first
   track into the inbox.

## Clients

| Platform | Recommended | Notes |
|---|---|---|
| macOS/Windows/Linux | **Psysonic** | Offline cache of pinned playlists with auto-sync |
| Android | **Substreamer** / Symfonium | Full offline cache |
| Any | Navidrome web UI | Streaming, playlist editing, admin |

## Updating

```bash
cd /opt/selfhost-music && sudo git pull --ff-only
sudo systemctl restart music-watcher        # if scripts changed
sudo docker compose up -d                   # if compose/Caddyfile changed
```

Never edit files on the VPS directly — the checkout must stay identical to git.
