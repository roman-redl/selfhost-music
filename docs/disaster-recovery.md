# Disaster Recovery — selfhost-music

## What is backed up

Nightly cron (`scripts/backup-to-cloud.sh`) syncs to WebDAV cloud storage:

| Data | VPS path | Cloud path | Size |
|---|---|---|---|
| Music library | `/opt/selfhost-music/music/` | `selfhost-music/` (files at the root) | your library size |
| Navidrome DB snapshot | SQLite backup API | `selfhost-music/navidrome-data/navidrome-snapshot.db` | ~10–50 MB |

The snapshot contains playlists, favorites, users, play counts. The live WAL database and
the regenerable cache are never copied.

## Recovery procedure

### Prerequisites

- A fresh Ubuntu 24.04 VPS, ports 22/80/443 open
- Your DuckDNS token + subdomain
- WebDAV credentials for the backup cloud (email + app password)

### Steps

1. **Re-provision and restore data**

   ```bash
   curl -sSL https://raw.githubusercontent.com/roman-redl/selfhost-music/main/scripts/setup-vps.sh | \
     bash -s -- <duckdns-token> <duckdns-subdomain>
   ```

2. **Mount the backup cloud**

   ```bash
   # /etc/davfs2/secrets: https://webdav.cloud.mail.ru <email> <app-password>
   # /etc/davfs2/davfs2.conf: use_locks 0 ; buf_size 64   (Linux >= 6.16)
   sudo mount /mnt/mailru-backup
   ```

3. **Restore the library and the database**

   ```bash
   sudo rsync -a /mnt/mailru-backup/selfhost-music/ /opt/selfhost-music/music/
   sudo systemctl stop docker  # or: docker stop the navidrome container
   sudo cp /mnt/mailru-backup/selfhost-music/navidrome-data/navidrome-snapshot.db \
           /opt/selfhost-music/data/navidrome.db
   sudo systemctl start docker
   ```

4. **Verify**

   - `docker ps` — navidrome and caddy are up
   - `https://$DOMAIN` opens the web UI
   - Playlists / favorites / play counts are present (restored from the snapshot)

**Expected time:** ~1 hour, dominated by downloading the library from the cloud.

## Backup verification

Once a month, check that the cloud mounts and reads:

```bash
sudo mount /mnt/mailru-backup
ls /mnt/mailru-backup/selfhost-music/ | head
ls -la /mnt/mailru-backup/selfhost-music/navidrome-data/
```

Also keep an occasional **local** copy of the library + snapshot on your own machine
before risky bulk operations (mass renames, DB maintenance) — a second copy outside the
VPS and the cloud has saved hours more than once.
