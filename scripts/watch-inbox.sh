#!/bin/bash
# Watcher: monitors /music-inbox/ → moves to /music/ → downloads cover → Navidrome picks up.
# Navidrome's built-in watcher (fsWatcherEnabled=true) handles the actual import.

set -e

INBOX="/opt/selfhost-music/music-inbox"
MUSIC="/opt/selfhost-music/music"
LOCKFILE="/var/lock/music-import.lock"
LOGFILE="/var/log/music-import.log"
COVER_SCRIPT="/opt/selfhost-music/scripts/get_cover.py"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" >> "$LOGFILE"; }
log "Watcher started, inbox=$INBOX, music=$MUSIC"

# Clean up stale temp files from Syncthing on startup
find "$INBOX" -name "*.tmp" -mmin +5 -delete 2>/dev/null || true
find "$INBOX" -name ".syncthing.*" -delete 2>/dev/null || true

inotifywait -m -r -e close_write -e moved_to --format '%w%f' "$INBOX" 2>/dev/null | while read -r FILEPATH; do
    BASENAME=$(basename "$FILEPATH")
    [[ -d "$FILEPATH" ]] && continue
    [[ "$BASENAME" == .* ]] && continue
    [[ "$BASENAME" == *.tmp ]] && continue

    case "${BASENAME,,}" in
        *.mp3|*.flac|*.m4a|*.ogg|*.wma|*.wav|*.aac|*.opus) ;;
        *) continue ;;
    esac

    log "New file: $BASENAME"

    # Wait for file to be fully written
    sleep 2

    # Lock
    exec 200>"$LOCKFILE"
    flock -n 200 || { log "  Skipping (locked): $BASENAME"; continue; }

    # Move to music folder
    if mv "$FILEPATH" "$MUSIC/$BASENAME" 2>/dev/null; then
        log "  -> moved to music/"

        # Auto-download cover art (only for MP3)
        if [[ "$BASENAME" == *.mp3 ]] && [[ -f "$COVER_SCRIPT" ]]; then
            python3 "$COVER_SCRIPT" "$MUSIC/$BASENAME" >> "$LOGFILE" 2>&1 && \
                log "  -> cover downloaded" || \
                log "  -> no cover found (OK)"
        fi
    else
        log "  ERROR: failed to move $BASENAME"
    fi

    exec 200>&-
done
