# Disaster Recovery — selfhost-music

## What is backed up

Nightly cron (`scripts/backup-to-cloud.sh`) syncs to WebDAV cloud storage:

| Data | VPS path | Cloud path | Size |
|---|---|---|---|
| Music library | `/opt/selfhost-music/music/` | `backup/` (files at the root) | your library size |
| Navidrome DB snapshot | SQLite backup API | `backup/navidrome-data/navidrome-snapshot.db` | ~10–50 MB |
| GitHub repo mirrors | `/opt/git-backup/*.git` | `backup/git-backup/` | ~330 MB |

The snapshot contains playlists, favorites, users, play counts. The live WAL database and
the regenerable cache are never copied. The repo mirrors (`--mirror` clones of all
personal GitHub repos, the notes vault among them) are an adjacent backup; their
authoritative source is GitHub itself.

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
   sudo rsync -a /mnt/mailru-backup/backup/ /opt/selfhost-music/music/
   sudo systemctl stop docker  # or: docker stop the navidrome container
   sudo cp /mnt/mailru-backup/backup/navidrome-data/navidrome-snapshot.db \
           /opt/selfhost-music/data/navidrome.db
   sudo systemctl start docker
   ```

4. **Verify**

   - `docker ps` — navidrome and caddy are up
   - `https://$DOMAIN` opens the web UI
   - Playlists / favorites / play counts are present (restored from the snapshot)

5. **(Optional) repo mirrors** — the adjacent git-backup tenant is lost with the VPS and
   is not re-created by the provisioning script. Re-create `/opt/git-backup` (`git clone
   --mirror` per repo), reinstall `/usr/local/bin/git-backup-to-cloud` + the 04:11 cron
   line if still wanted (see [architecture.md](architecture.md), "Backups"). If GitHub
   itself is unreachable, recover a repo with
   `git clone /mnt/mailru-backup/backup/git-backup/<repo>.git`.

**Expected time:** ~1 hour, dominated by downloading the library from the cloud.

## Backup verification

Once a month, check that the cloud mounts and reads:

```bash
sudo mount /mnt/mailru-backup
ls /mnt/mailru-backup/backup/ | head
ls -la /mnt/mailru-backup/backup/navidrome-data/
```

Also keep an occasional **local** copy of the library + snapshot on your own machine
before risky bulk operations (mass renames, DB maintenance) — a second copy outside the
VPS and the cloud has saved hours more than once.
