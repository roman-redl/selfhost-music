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
log "Syncing music..."
rsync -a --delete --inplace --exclude 'navidrome-data' --exclude 'git-backup' --exclude 'Аудиокниги' \
    --exclude "$BAD_NAMES" \
    /opt/selfhost-music/music/ "$BACKUP_ROOT/" >> "$LOGFILE" 2>&1
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
rsync -a --delete --inplace --exclude 'cache' --exclude 'navidrome.db' --exclude 'navidrome.db-wal' --exclude 'navidrome.db-shm' \
    /opt/selfhost-music/data/ "$BACKUP_ROOT/navidrome-data/" >> "$LOGFILE" 2>&1
rsync -a --inplace /tmp/navidrome-snapshot.db "$BACKUP_ROOT/navidrome-data/navidrome-snapshot.db" >> "$LOGFILE" 2>&1
rm -f /tmp/navidrome-snapshot.db
log "Navidrome data sync done."

log "Backup completed successfully."
