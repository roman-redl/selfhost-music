#!/bin/bash
# Backup script: sync music + Navidrome data to Mail.ru cloud via WebDAV
# Run daily via cron. Mount WebDAV first: mount /mnt/mailru-backup

set -e

WEBDAV_MOUNT="/mnt/mailru-backup"
LOCKFILE="/var/lock/music-backup.lock"
LOGFILE="/var/log/music-backup.log"

exec 200>"$LOCKFILE"
flock -n 200 || { echo "$(date): Backup already running, exiting." >> "$LOGFILE"; exit 0; }

log() { echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" >> "$LOGFILE"; }

log "Starting backup..."

# Ensure WebDAV is mounted
if ! mountpoint -q "$WEBDAV_MOUNT"; then
    mount "$WEBDAV_MOUNT" || { log "ERROR: Failed to mount WebDAV"; exit 1; }
fi

# Backup music files
log "Syncing music..."
rsync -avz --delete /opt/selfhost-music/music/ "$WEBDAV_MOUNT/music/" >> "$LOGFILE" 2>&1
log "Music sync done."

# Backup Navidrome data (playlists, favourites, users, progress)
log "Syncing Navidrome data..."
rsync -avz --delete /opt/selfhost-music/data/ "$WEBDAV_MOUNT/navidrome-data/" >> "$LOGFILE" 2>&1
log "Navidrome data sync done."

log "Backup completed successfully."
