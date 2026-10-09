# CLAUDE.md — selfhost-music

Self-hosted music: Navidrome on an Oracle Cloud VPS + Caddy + automated import via
Syncthing/SFTP. This file is the operational entry point for AI coding agents.
Details: [docs/architecture.md](docs/architecture.md) (rules, decisions, lessons),
[docs/deployment.md](docs/deployment.md), [docs/disaster-recovery.md](docs/disaster-recovery.md).

## Hard rules (never break)

- **Edit files only with proper file tools** (Write/Edit), never `cat >` heredocs in Bash:
  diffs must be visible and confirmable in the CLI. Exception: programmatic transforms of
  large generated files — announce them and show a summary.
- **Filenames:** `Artist - Title.ext`, separator strictly ` - `, NFC Unicode. No em dashes,
  no `|`, no leading track numbers, no junk suffixes like `(Official Video)`/`(1985)`.
- **Tags:** Artist/Title/Album are mandatory; tags must equal the filename (NFC); one artist =
  one spelling/case. Album = track title (each track gets its own "album" and cover in
  Subsonic clients), except explicit real compilations.
- **Multiple artists only via `A; B`** — Navidrome splits artist tags on `; ` and `feat.`
  only (`feat.` splits into at most two parts). **Commas do not split** (verified
  experimentally). Real duos/groups stay as a single name with `&`.
- `scripts/fix_tags.py` never overwrites valid tags — set them explicitly (e.g. mutagen)
  when renaming/retagging on purpose. Always strip TIT3 (subtitle): Navidrome appends it
  to the title.
- **Fuzzy matching of tracks/playlists by scripts is forbidden** (~42% false positives in
  this project's history). Track matching is done by AI agents using semantics
  (translations, transliteration); everyday playlist edits happen in the Navidrome UI.
- **Subsonic API playlist indexes are 0-based** while `playlist_tracks.id` positions in the
  DB are 1-based: API index = DB position − 1. Remove tracks from the end; after every
  `updatePlaylist` call re-check the DB. `songIdToAdd` accepts *media file ids* — passing
  anything else (e.g. playlist row positions) silently corrupts `playlist_tracks`.
- **Deleting music:** Navidrome is read-only by design — remove the track from playlists
  first, then delete the file on disk, then rescan. Never edit the Navidrome DB by hand
  except via the documented maintenance procedure (see docs/architecture.md, "DB maintenance").
- **Forbidden:** yt-dlp, rclone for Mail.ru (broken — use WebDAV/davfs2), third-party VPNs
  on corporate machines, hardcoded credentials (everything lives in gitignored `.env`;
  the Navidrome password contains `#` — always URL-encode it).
- **The server domain comes from `DOMAIN` in `.env`** — never hardcode it.
- **Do not touch:** the `/music/` directory structure on the VPS (Navidrome has it
  indexed), `.env`, or the backup machinery unless explicitly asked.

## Adding music (summary)

1. Drop `Artist - Title.mp3|flac` into `MusicInbox/` (repo root, synced via Syncthing)
   or SFTP to `/opt/selfhost-music/music-inbox/` on the VPS.
2. The watcher does the rest: `fix_tags.py` → `get_cover.py` → Navidrome. ~30 seconds.
3. A manual cover: put `Artist - Title.jpg|png` with the same name next to the track —
   highest priority, embedded automatically.
4. Artist images come from Deezer by default; for a point fix run
   `python3 scripts/set_artist_images.py --artist "Name" --file pic.jpg` (webp/heic
   auto-converts; Psysonic's own upload button rejects them).
5. Details: [docs/adding-music.md](docs/adding-music.md).
6. After bulk imports, refresh the collection snapshot: on the VPS run
   `python3 scripts/export_tracklist.py > playlists/tracklist.csv` (path is local-only,
   gitignored).

## Playlists

- **Navidrome is the source of truth** (web UI and clients). Everyday edits happen there.
- Local `playlists/*.m3u` are snapshot backups taken from Navidrome (flow is strictly
  one-way: Navidrome → git). Importing an `.m3u` back is a disaster-recovery-only
  operation via the Subsonic API with NFC matching against the full index — never
  "first search result".

## Deploying changes

1. Locally: edit → `python3 -m py_compile scripts/*.py` / `bash -n scripts/*.sh` →
   smoke-test on copies in /tmp, never on the live library.
2. After rewriting a `.sh`, check `ls -l` — the exec bit is lost when a script file is
   replaced via some editors/deploy paths (caused a systemd 203/EXEC crash loop once).
3. Commit (short message) + push.
4. VPS: `ssh -i ~/.ssh/id_ed25519_oracle ubuntu@$DOMAIN` (`$DOMAIN` from `.env`):
   `cd /opt/selfhost-music && sudo git pull --ff-only`.
5. Restart services as needed: `sudo systemctl restart music-watcher`;
   `docker compose up -d caddy` if configs changed.
6. **Never edit files on the VPS by hand** — the VPS checkout diverged from git once;
   everything goes through git.

## Where to read

- System design, rules, operational lessons: `docs/architecture.md`
- Full deployment from scratch: `docs/deployment.md`
- Adding music and cover art: `docs/adding-music.md`
- Recovering from a lost VPS: `docs/disaster-recovery.md`
- **Machine-local private notes** (library specifics, incident journal — never published):
  `docs/private/` is gitignored; if it exists, read it first — it overrides/refines
  the generic rules above with operational context for this specific installation.
