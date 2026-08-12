#!/bin/bash
# Watcher: monitors /music-inbox/ → fixes tags → moves to /music/ → downloads cover → Navidrome picks up.
# Navidrome's built-in watcher (fsWatcherEnabled=true) handles the actual import.
#
# Manual cover support:
#   If Artist - Title.jpg (or .png) is placed alongside Artist - Title.mp3 in the inbox,
#   it will be used as the cover (highest priority, no API calls).
#   The image is deleted only after successful embedding; if embedding fails,
#   it stays next to the track in /music/.

set -e

INBOX="/opt/selfhost-music/music-inbox"
MUSIC="/opt/selfhost-music/music"
LOCKFILE="/var/lock/music-import.lock"
LOGFILE="/var/log/music-import.log"
COVER_SCRIPT="/opt/selfhost-music/scripts/get_cover.py"
TAGS_SCRIPT="/opt/selfhost-music/scripts/fix_tags.py"

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

    # Wait for Syncthing to finish writing
    sleep 2

    # Lock
    exec 200>"$LOCKFILE"
    flock -n 200 || { log "  Skipping (locked): $BASENAME"; continue; }

    # Check for manual cover in inbox (adjacent .jpg/.png with same basename)
    BASENAME_NOEXT="${BASENAME%.*}"
    MANUAL_COVER=""
    for EXT in jpg jpeg png; do
        CANDIDATE="$INBOX/${BASENAME_NOEXT}.${EXT}"
        if [[ -f "$CANDIDATE" ]]; then
            MANUAL_COVER="$CANDIDATE"
            log "  -> manual cover found: ${BASENAME_NOEXT}.${EXT}"
            break
        fi
    done

    # Move audio to music folder
    if mv "$FILEPATH" "$MUSIC/$BASENAME" 2>/dev/null; then
        log "  -> moved to music/"

        # Move manual cover alongside the audio (get_cover.py picks it up there)
        COVER_DEST=""
        if [[ -n "$MANUAL_COVER" ]]; then
            COVER_EXT="${MANUAL_COVER##*.}"
            COVER_DEST="$MUSIC/${BASENAME_NOEXT}.${COVER_EXT}"
            mv "$MANUAL_COVER" "$COVER_DEST" 2>/dev/null || \
                log "  WARN: failed to move manual cover"
        fi

        # Fix tags and covers for MP3/FLAC; other formats pass through as-is
        case "${BASENAME,,}" in
            *.mp3|*.flac)
                if [[ -f "$TAGS_SCRIPT" ]]; then
                    python3 "$TAGS_SCRIPT" "$MUSIC/$BASENAME" >> "$LOGFILE" 2>&1 || \
                        log "  WARN: tag fix failed"
                fi

                if [[ -f "$COVER_SCRIPT" ]]; then
                    if python3 "$COVER_SCRIPT" "$MUSIC/$BASENAME" >> "$LOGFILE" 2>&1; then
                        log "  -> cover embedded"
                        if [[ -n "$COVER_DEST" && -f "$COVER_DEST" ]]; then
                            rm -f "$COVER_DEST"
                            log "  -> manual cover cleaned up"
                        fi
                    else
                        log "  -> no cover embedded (manual image kept if present)"
                    fi
                fi
                ;;
            *)
                log "  -> auto-cover not supported for this format"
                ;;
        esac
    else
        log "  ERROR: failed to move $BASENAME"
    fi

    exec 200>&-
done
