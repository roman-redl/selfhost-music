# selfhost-music

A self-hosted music streaming system: your library, your server, your rules.

[Navidrome](https://navidrome.org) behind [Caddy](https://caddyserver.com) (automatic HTTPS),
an automated import pipeline (tag fix → cover art → library), and incremental cloud backups —
all on a single free-tier VPS.

## What it does

- **Stream your library** via the Subsonic/OpenSubsonic API from any client
  (desktop, Android, iOS, web). Works with Psysonic, Substreamer, Symfonium, Feishin, etc.
- **Drop-in import:** put `Artist - Title.mp3` into an inbox folder → within ~30 s the track
  is tagged, gets embedded cover art, and appears on every device.
- **Automatic cover art:** manual image > Deezer > iTunes > Cover Art Archive > Discogs > Bing.
- **Tag hygiene:** a fixer derives Artist/Title/Album from filenames and removes junk values.
- **Nightly incremental backups** of the library and a consistent Navidrome DB snapshot
  to Mail.ru Cloud over WebDAV (any WebDAV endpoint works with minor tweaks).
- **Disaster recovery in ~1 hour:** one script re-provisions the VPS, backups restore
  the library and the database (playlists, favorites, play counts).

## Architecture

```
VPS (Oracle Cloud free tier / any Ubuntu box):
  Caddy :443 (HTTPS, domain from {$DOMAIN})
    └─ Navidrome :4533 (Subsonic API)
         reads /music/ (read-only), DB in /data/
  /music-inbox/ — incoming files (Syncthing from laptop, SFTP from phone)
    └─ watcher (systemd, scripts/watch-inbox.sh):
         mv → /music/ → fix_tags.py → get_cover.py → Navidrome picks it up
  Backup cron 04:37 → scripts/backup-to-cloud.sh → WebDAV (Mail.ru Cloud)
  Git mirrors cron 04:11 → git-backup-to-cloud (VPS-local) → WebDAV /git-backup/ —
    adjacent tenant: --mirror clones of all personal GitHub repos, not part of the stack
```

## Quick start

```bash
# 1. Provision a fresh Ubuntu 24.04 VPS (2+ GB RAM, 20+ GB disk)
curl -sSL https://raw.githubusercontent.com/roman-redl/selfhost-music/main/scripts/setup-vps.sh | \
  bash -s -- <duckdns-token> <duckdns-subdomain>

# 2. Configure secrets
cp .env.example .env   # fill in DOMAIN, Navidrome user/password, backup creds

# 3. Bring the stack up
docker compose up -d
```

Then open `https://your-domain`, create the admin user, and drop your first track
into `MusicInbox/` (see [docs/adding-music.md](docs/adding-music.md)).

## Repository layout

| Path | Purpose |
|---|---|
| `scripts/watch-inbox.sh` | Import watcher: inbox → tags → cover → library (systemd unit in `config/`) |
| `scripts/fix_tags.py` | Repairs Artist/Title/Album tags from filenames (MP3 + FLAC) |
| `scripts/get_cover.py` | Cover art: manual image → Deezer → iTunes → CAA → Discogs → Bing |
| `scripts/export_tracklist.py` | Exports the collection as CSV from Navidrome |
| `scripts/backup-to-cloud.sh` | Incremental WebDAV backup + consistent DB snapshot |
| `scripts/setup-vps.sh` | One-shot VPS provisioning |
| `config/` | Caddyfile, systemd unit, optional slskd config |
| `docs/` | [Architecture](docs/architecture.md), [deployment](docs/deployment.md), [adding music](docs/adding-music.md), [disaster recovery](docs/disaster-recovery.md) |

## Library conventions

- Filenames: `Artist - Title.ext` (single ` - ` separator, NFC-normalized Unicode).
- Tags must match the filename; Album = track title by default (each track gets its own
  "album" and therefore its own cover in Subsonic clients), except real compilations.
- Multiple artists in one tag: `A; B` — Navidrome only splits on `; ` (and `feat.`),
  **commas do not split**.
- Full rules and operational lessons: [docs/architecture.md](docs/architecture.md).

## Backups

`backup-to-cloud.sh` runs from cron (04:37 by default):

```
<webdav-mount>/selfhost-music/
├── <all music files>            # rsync --delete from /music/
└── navidrome-data/
    └── navidrome-snapshot.db    # consistent snapshot via the SQLite backup API
```

The live `navidrome.db` is never copied directly (WAL makes a naive copy inconsistent);
the cache directory is excluded as it is regenerable.

An adjacent nightly job (04:11, `git-backup-to-cloud`, lives on the VPS rather than in
this repo) mirrors all personal GitHub repos — the notes vault included — into
`<webdav-mount>/git-backup/`; see [docs/architecture.md](docs/architecture.md).

## License

MIT — see [LICENSE](LICENSE).
