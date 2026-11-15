#!/bin/bash
# Backup script: sync music + Navidrome data (+ parley dumps) to Mail.ru cloud via WebDAV
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
# их --delete музыкального прохода касаться не должен. То же для parley/ (дампы
# MongoDB и файлы LibreChat, пишутся ниже).
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
sync_step -a --delete --inplace --exclude 'navidrome-data' --exclude 'git-backup' --exclude '/parley' \
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

# parley (LibreChat, /opt/parley): dump of MongoDB database LibreChat + archive of
# uploaded/generated files (images, uploads; logs are not backed up). Dated files,
# last PARLEY_KEEP copies kept. A failure here only marks the run as failed (WARN +
# FAILED=1 -> exit 1 at the end); the music backup above is already done.
# The container is addressed via compose (project parley), not by container name.
# `if ! parley_backup` disables `set -e` inside the function, so every step is checked
# explicitly.
PARLEY_DIR="/opt/parley"
PARLEY_COMPOSE="$PARLEY_DIR/docker-compose.yml"
PARLEY_KEEP=3

parley_prune() {
    local dir="$1" pattern="$2" f rc=0
    # dated names sort lexicographically: newest first, skip the PARLEY_KEEP newest;
    # only names of the expected pattern count as copies
    while read -r f; do
        rm -f "$dir/$f" || { log "WARN: parley: could not delete old copy $dir/$f"; rc=1; }
    done < <(ls -1 "$dir" | grep -E "$pattern" | sort -r | tail -n +$((PARLEY_KEEP + 1)))
    return $rc
}

parley_backup() {
    local day dest stage rc=0
    day=$(date +%F)
    dest="$BACKUP_ROOT/parley"
    stage=$(mktemp -d /tmp/parley-backup.XXXXXX) || { log "WARN: parley: no staging dir"; return 1; }

    log "Dumping parley MongoDB..."
    # timeout runs inside the container: killing only the docker client would leave mongodump running
    docker compose -f "$PARLEY_COMPOSE" exec -T mongodb \
        timeout 900 mongodump --db LibreChat --archive --gzip > "$stage/mongo-LibreChat-$day.archive.gz" 2>> "$LOGFILE" \
        || { log "WARN: parley: mongodump failed"; rm -rf "$stage"; return 1; }
    # -s: a dump of an existing database is never empty; gzip -t catches a truncated stream
    if [ ! -s "$stage/mongo-LibreChat-$day.archive.gz" ] || ! gzip -t "$stage/mongo-LibreChat-$day.archive.gz"; then
        log "WARN: parley: mongodump produced an empty or broken archive"
        rm -rf "$stage"; return 1
    fi

    log "Archiving parley files..."
    # GNU tar exits with 1 when a file changed while being read (an upload during the backup):
    # the archive is still usable, so only 2 and above is a failure
    local trc=0
    tar -czf "$stage/files-$day.tar.gz" -C "$PARLEY_DIR/data/librechat" images uploads 2>> "$LOGFILE" || trc=$?
    if [ "$trc" -gt 1 ]; then
        log "WARN: parley: tar of images/uploads failed (rc=$trc)"; rm -rf "$stage"; return 1
    fi

    mkdir -p "$dest/mongo" "$dest/files" || { log "WARN: parley: cannot create $dest"; rm -rf "$stage"; return 1; }
    # --inplace — same davfs2 rename failure as above
    rsync -a --inplace "$stage/mongo-LibreChat-$day.archive.gz" "$dest/mongo/" >> "$LOGFILE" 2>&1 \
        || { log "WARN: parley: upload of mongo dump failed (rc=$?)"; rc=1; rm -f "$dest/mongo/mongo-LibreChat-$day.archive.gz"; }
    rsync -a --inplace "$stage/files-$day.tar.gz" "$dest/files/" >> "$LOGFILE" 2>&1 \
        || { log "WARN: parley: upload of files archive failed (rc=$?)"; rc=1; rm -f "$dest/files/files-$day.tar.gz"; }
    rm -rf "$stage"

    # Prune old copies only after a successful upload of both files
    if [ "$rc" -eq 0 ]; then
        parley_prune "$dest/mongo" '^mongo-LibreChat-[0-9]{4}-[0-9]{2}-[0-9]{2}\.archive\.gz$' || rc=1
        parley_prune "$dest/files" '^files-[0-9]{4}-[0-9]{2}-[0-9]{2}\.tar\.gz$' || rc=1
    fi
    return $rc
}

if ! parley_backup; then
    FAILED=1
else
    log "Parley backup done."
fi

if [ "$FAILED" -ne 0 ]; then
    log "ERROR: backup completed with errors (see WARN above)."
    exit 1
fi
log "Backup completed successfully."
