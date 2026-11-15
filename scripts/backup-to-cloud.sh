#!/bin/bash
# Backup script: sync music + Navidrome data to Mail.ru cloud via WebDAV
# Run daily via cron. Mount WebDAV first: mount /mnt/mailru-backup

set -e

WEBDAV_MOUNT="/mnt/mailru-backup"
BACKUP_ROOT="$WEBDAV_MOUNT/backup"             # единая папка всех бэкапов; личные папки облака не трогаем
LOCKFILE="/var/lock/music-backup.lock"
LOGFILE="/var/log/music-backup.log"

exec 200>"$LOCKFILE"
flock -n 200 || { echo "$(date): Backup already running, exiting." >> "$LOGFILE"; exit 0; }

log() { echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" >> "$LOGFILE"; }

log "Starting backup..."

# Ensure WebDAV is mounted
# 200>&-: the mount.davfs daemon must not inherit the lock descriptor,
# otherwise it holds the lock forever and every later run exits as "already running".
if ! mountpoint -q "$WEBDAV_MOUNT"; then
    mount "$WEBDAV_MOUNT" 200>&- || { log "ERROR: Failed to mount WebDAV"; exit 1; }
fi
mkdir -p "$BACKUP_ROOT"

# Backup music files (directly into backup/ root — no extra nesting)
# --inplace: davfs2 (Mail.ru WebDAV) fails rsync's temp-file + rename dance
# with I/O error 5; in-place writes avoid the rename entirely.
# --exclude git-backup: рядом в backup/ лежат зеркала репозиториев (крон 04:11),
# их --delete музыкального прохода касаться не должен.
# Mail.ru отклоняет имена с " * : < > ? \ | — davfs молча оставляет такие файлы
# в своём кеше и копит их каждую ночь. Такие файлы исключаются и пишутся в лог.
BAD_NAMES='*[?"*:<>|\\]*'
find /opt/selfhost-music/music -name "$BAD_NAMES" -printf '%P\n' | while read -r f; do
    log "WARN: not backed up, name rejected by cloud: $f"
done
# davfs sometimes fails a single delete/write with "Resource temporarily unavailable"
# (rsync code 23): log it and go on with the remaining steps instead of aborting.
FAILED=0
sync_step() {
    rsync "$@" >> "$LOGFILE" 2>&1 || { log "WARN: rsync rc=$? (see errors above), continuing"; FAILED=1; }
}

log "Syncing music..."
sync_step -a --delete --inplace --exclude 'navidrome-data' --exclude 'git-backup' \
    --exclude "$BAD_NAMES" \
    /opt/selfhost-music/music/ "$BACKUP_ROOT/"
log "Music sync done."

# Backup Navidrome data (playlists, favourites, users, progress)
# The live WAL database is inconsistent if copied directly: take a snapshot via
# the SQLite backup API instead. The transcode/artwork cache is regenerable
# and is excluded from the backup.
log "Snapshotting Navidrome DB..."
python3 -c "import sqlite3; src = sqlite3.connect('/opt/selfhost-music/data/navidrome.db'); dst = sqlite3.connect('/tmp/navidrome-snapshot.db'); src.backup(dst); dst.close(); src.close()" \
    || { log "ERROR: DB snapshot failed"; exit 1; }
log "Syncing Navidrome data..."
# --inplace — same davfs2 rename failure as above (seen on playlists/*.m3u).
# --exclude playlists-export: written below, not present in data/.
sync_step -a --delete --inplace --exclude 'cache' --exclude 'navidrome.db' --exclude 'navidrome.db-wal' --exclude 'navidrome.db-shm' \
    --exclude 'playlists-export' \
    /opt/selfhost-music/data/ "$BACKUP_ROOT/navidrome-data/"
sync_step -a --inplace /tmp/navidrome-snapshot.db "$BACKUP_ROOT/navidrome-data/navidrome-snapshot.db"
log "Navidrome data sync done."

# Playlists as .m3u from the same snapshot — readable without Navidrome.
# Kept outside the music folder so Navidrome never imports them.
log "Exporting playlists..."
rm -rf /tmp/playlists-export
n=$(python3 /opt/selfhost-music/scripts/export_playlists_m3u.py /tmp/playlists-export /tmp/navidrome-snapshot.db) \
    || { log "ERROR: playlist export failed"; exit 1; }
sync_step -a --delete --inplace /tmp/playlists-export/ "$BACKUP_ROOT/navidrome-data/playlists-export/"
rm -rf /tmp/playlists-export /tmp/navidrome-snapshot.db
log "Exported $n playlists."

if [ "$FAILED" -ne 0 ]; then
    log "ERROR: backup completed with rsync errors (see WARN above)."
    exit 1
fi
log "Backup completed successfully."
