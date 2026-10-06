# Architecture & Operations — selfhost-music

Design decisions, library conventions, and operational lessons (what bit us and the
rules that came out of it).

## The system at a glance

```text
                                                         ┌────────────────┐
                                                         │v2rayN · v2rayNG│
                                                         └────────┬───────┘
                             ┌─ VPS (Oracle ARM) ─────────────────┼────────┐
┌────────────┐               │ ┌─────────────────┐                │        │
│ MusicInbox │──Syncthing───►│ │ /music-inbox/   │      ┌─────────┴────┐   │
│   (Mac)    │               │ │ music-watcher:  │      │  Xray VPN    │   │
└────────────┘               │ │ mv · fix_tags · │      │ VLESS+REALITY│   │
  ┌───────┐                  │ │ get_cover.py    │      │    :8443     │   │
  │ Phone │──SFTP───────────►│ │ (systemd)       │      └──────────────┘   │
  └───────┘                  │ └────────┬────────┘                         │
                             │          │                                  │
                             │     ┌─────────┐           ┌───────────────┐ │
                             │     │ /music/ │─read-only►│   Navidrome   │ │
                             │     └─────────┘           │     :4533     │ │
                             │  ┌──────────┐             │ (Subsonic API)│ │
                             │  │  /data/  │──owns──────►│               │ │
                             │  │ (SQLite) │             └───────┬───────┘ │
                             │  └──────────┘                     │ proxy   │
                             │                                   v         │
 ┌──────────┐                │                           ┌───────────────┐ │
 │  DuckDNS │───$DOMAIN──────├──────────────────────────►│  Caddy :443   │ │
 └──────────┘                │                           └───────┬───────┘ │
                             │                                   │         │
                             │ ┌──────────────┐ ┌──────────────┐ │         │
                             │ │ cron 04:37   │ │ cron 04:11   │ │         │
                             │ │ music backup │ │ git mirrors  │ │         │
                             │ └──────┬───────┘ └──────┬───────┘ │         │
                             └────────┼────────────────┼─────────┼─────────┘
                                      │ rsync (davfs2) │         │ HTTPS · Subsonic API
                             ┌───────────────────────────┐       │
                             │  Mail.ru WebDAV (davfs2)  │       │
                             │ backup/ (music + mirrors) │       │
                             └───────────────────────────┘       v
                                                      ┌───────────────────────┐
                                                      │ Psysonic (desktop)    │
                                                      │ Substreamer (Android) │
                                                      │ Supersonic (spare)    │
                                                      └───────────────────────┘

deploy:  Mac ──push──> GitHub ──pull──> /opt/selfhost-music (VPS)
```

## Components

| Component | Role |
|---|---|
| **Navidrome** (Docker) | Subsonic/OpenSubsonic server; reads `/music/` read-only, DB in `/data/` |
| **Caddy** (Docker) | TLS termination, automatic certs, reverse proxy to Navidrome |
| **music-watcher** (systemd) | Import pipeline for `/music-inbox/`: move → fix tags → fetch cover |
| **Syncthing** | Laptop `MusicInbox/` → VPS inbox |
| **SFTP** | Phone → VPS inbox (any SSH/SFTP file manager) |
| **DuckDNS** (cron `/opt/duckdns/duck.sh`) | Public name `$DOMAIN`; keeps the VPS IP current |
| **davfs2 → Mail.ru WebDAV** | Backup target mounted on the VPS; nightly rsync lands in `<mount>/backup/` |
| **GitHub** | Deploy source: the VPS checkout pulls `--ff-only`; nothing is edited on the VPS by hand |
| **cron** | Nightly WebDAV backups: music 04:37, GitHub repo mirrors 04:11 |
| **Xray VPN** (adjacent tenant) | Personal VPN on the same VPS: VLESS + REALITY on :8443, same `$DOMAIN`; clients v2rayN (Windows) / v2rayNG (Android); see the private `redl-vpn` repo |
| **Clients** | Psysonic (desktop, offline cache), Substreamer (Android, offline cache), any Subsonic client |

## Library conventions

### Filenames and tags

- `Artist - Title.ext`, single ` - ` separator, NFC-normalized Unicode.
- Tags must match the filename exactly (Artist TPE1, Title TIT2). Album (TALB) = the track
  title — since Navidrome stores one artwork per album and most clients display album art,
  this gives every track its own cover. Real compilations (multi-track albums) are the
  deliberate exception.
- One artist = one spelling/case (majority vote); stylized spellings are kept as-is.
- No junk in titles: year suffixes, `(Official Video)`, `Original Version`, etc. Intentional
  mix suffixes (Extended Mix…) may stay.

### Multiple artists

Navidrome splits the artist tag on `; ` and on `feat.` — and nothing else. `feat.` splits
into at most two parts (the rest is glued back together); **commas do not split at all**
(the whole string becomes one artist). Multi-frame TPE1 is not supported (only one frame
is read). Therefore:

- Multiple artists: `A; B; C` — in tags **and** filenames.
- Real duos/groups: a single name with `&` (`Al Bano & Romina Power`).
- Sort playlists by **first artist**, then title — not by the whole artist string.

## Import pipeline

`watch-inbox.sh` (systemd `music-watcher`) per file:

1. `mv` from `/music-inbox/` into `/music/`
2. `fix_tags.py` — fills missing/invalid Artist/Title/Album from the filename;
   valid tags are never overwritten
3. `get_cover.py` — embeds cover art: manual `Artist - Title.jpg|png` next to the file
   (highest priority) → Deezer → iTunes → Cover Art Archive → Discogs → Bing.
   A manual image is deleted only after successful embedding.
4. Navidrome picks the file up automatically.

## Subsonic API quirks (learned the hard way)

1. **Playlist indexes are 0-based**; `playlist_tracks.id` in the DB is 1-based.
   Removing by DB position without −1 silently removes the *next* track while the API
   returns `ok`.
2. **`songIdToAdd` accepts media file ids only** and does not validate them — passing
   anything else inserts garbage rows that `getPlaylist` silently hides (playlist looks
   empty for clients while the DB has rows). Rebuild playlists from `media_file.id` and
   verify via **API `getPlaylist`**, not just the DB.
3. `createPlaylist` takes exactly one `songId`; add the rest with `updatePlaylist`.
4. `search3` is unreliable with decomposed/Unicode text — match against a locally built
   NFC-normalized index of the whole library; never take the "first search result".
5. The Navidrome password may contain `#` — always URL-encode (`curl -G --data-urlencode`,
   `urllib.parse.urlencode`).
6. TIT3 (subtitle) is appended to titles in the API/clients though the DB title stays
   clean — strip TIT3 whenever you touch tags. A container restart does not fix it;
   only tag edit + rescan does.

## DB maintenance (rename/purge cycles)

Every on-disk rename or retag can leave dead rows in `media_file`. Periodically (and
always after bulk renames):

1. `docker stop` the Navidrome container; take a fresh DB backup first
   (SQLite backup API, not a file copy — the DB runs in WAL mode).
2. `DELETE FROM media_file WHERE missing=1`, then orphaned `annotation` rows, empty
   albums/artists, and dangling `album_artists`/`media_file_artists` links.
   **Careful:** "empty" artists may be secondary credited artists (no own tracks) —
   check the junction tables before deleting, or you will wipe them.
3. Start the container and run a **full scan**
   (`startScan?fullScan=true`) — it rebuilds artist entities from tags (ids are stable).
4. **A full scan duplicates artist links** in `album_artists`/`media_file_artists`
   (quick scans do not): after every full scan, deduplicate the junction tables
   (rows differing only by rowid). Rows with different `role` values are legitimate.
5. Cached `song_count` per album goes stale — recompute or ignore.

## ReplayGain

Gain tags are written into the files (computed with the ffmpeg `replaygain` audio filter,
embedded with mutagen as `TXXX:replaygain_track_gain/peak` for MP3 and Vorbis comments
for FLAC). Navidrome applies them per-user via its player settings; clients read the
standard tags directly. Note: the filter output prints positive gains like `+4.15` —
account for the sign when parsing.

## Backups

- Nightly cron → `backup-to-cloud.sh`: rsync `--delete` of `/music/` into
  `<mount>/backup/` (music files at the root, no extra nesting) plus
  `navidrome-data/` with a **consistent DB snapshot** (SQLite backup API).
  The live WAL database and the regenerable cache directory are excluded; rsync gets
  `--exclude navidrome-data` (and `--exclude git-backup` for the adjacent mirrors)
  so `--delete` on the music pass cannot remove them.
- Separate nightly cron 04:11 → `/usr/local/bin/git-backup-to-cloud` (VPS-local, not in
  this repo): `git fetch` in `/opt/git-backup/*.git` — `--mirror` clones of all personal
  GitHub repos (the notes vault among them) — then rsync into `<mount>/backup/git-backup/`.
  Adjacent tenant, not part of the music stack; shares only the VPS and the davfs mount.
  Restore: `git clone /opt/git-backup/<repo>.git` or the cloud copy.
- davfs2 quirks with Mail.ru WebDAV: needs `use_locks 0` and, on Linux ≥ 6.16,
  `buf_size 64` in `/etc/davfs2/davfs2.conf`, otherwise directory listing fails with
  `Invalid argument` while read/write still work. Renaming/moving cloud folders via
  `mv` on the mount fails with `Permission denied` — use a direct WebDAV `MOVE`
  (curl, creds from `/etc/davfs2/secrets`): returns 201, moves server-side
  without re-uploading (2026-10-05).
- Deleting thousands of files over WebDAV is extremely slow (one DELETE per request) —
  prefer removing whole folders from the cloud's web UI. A bulk `rm -rf` through the
  davfs mount can also *hang* with `Resource temporarily unavailable` — kill the rm,
  lazy-unmount + remount the davfs mount, retry (2026-10-03).

## Misc lessons

- `.env` is not exported by a plain `source` in zsh — use `set -a; source .env; set +a`.
- Reading a WAL-mode SQLite DB with `immutable=1` shows the pre-checkpoint state —
  useful for forensics ("what did the table look like before"), wrong for current state.
- macOS ships openrsync as `/usr/bin/rsync`: no `--info=progress2`. Use plain flags.
- macOS keyboards/zsh mangle quoting: pass scripts to remote hosts via stdin
  (`ssh host python3 - < file`) or base64 payloads; never inline heredocs with
  apostrophes in data.
- Renaming a file while keeping its tags preserves the Navidrome track id (playlists,
  play counts survive). Changing tags creates a new id — migrate `annotation` rows and
  playlist references explicitly.
