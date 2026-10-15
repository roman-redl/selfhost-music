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
- **Authenticated forward proxy on :443** (same Caddy): personal API traffic
  (e.g. Claude Code → Anthropic) exits from the VPS through an HTTPS CONNECT
  tunnel — probe-resistant, ACL-limited, credentials in `.env`.

## Architecture

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
 ┌──────────┐                │                           ┌───────────────┐ │      ┌────────────────────┐
 │  DuckDNS │───$DOMAIN──────├──────────────────────────►│  Caddy :443   │──tunnel──►│ api.anthropic.com  │
 └──────────┘                │                           │ rev·fwd proxy │ │      └────────────────────┘
 ┌────────────────────────┐  │                           │ CONNECT :443  │ │
 │ claude-api: Mac + Win  │──┼─────────HTTPS CONNECT────►│  (auth·ACL)   │ │
 └────────────────────────┘  │                           └───────┬───────┘ │
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
tunnel:  HTTPS CONNECT (basic auth, probe-resistant, ACL anthropic-only);
         end-to-end TLS inside — Anthropic only ever sees the VPS address
```

Details, rules and operational lessons: [docs/architecture.md](docs/architecture.md).

## Quick start

```bash
# 1. Provision a fresh Ubuntu 24.04 VPS (2+ GB RAM, 20+ GB disk)
curl -sSL https://raw.githubusercontent.com/roman-redl/selfhost-music/main/scripts/setup-vps.sh | \
  bash -s -- <duckdns-token> <duckdns-subdomain>

# 2. Configure secrets
cp .env.example .env   # fill in DOMAIN, Navidrome user/password, proxy auth, backup creds

# 3. Bring the stack up (first run builds the Caddy image with the forwardproxy plugin)
docker compose up -d --build
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

`backup-to-cloud.sh` runs from cron (04:37 by default). Everything backup-related
lives in one cloud folder — personal cloud folders are never touched:

```
<webdav-mount>/backup/
├── <all music files>            # rsync --delete from /music/
├── navidrome-data/
│   └── navidrome-snapshot.db    # consistent snapshot via the SQLite backup API
└── git-backup/                  # mirrors of personal GitHub repos (adjacent 04:11 job)
```

The live `navidrome.db` is never copied directly (WAL makes a naive copy inconsistent);
the cache directory is excluded as it is regenerable.

An adjacent nightly job (04:11, `git-backup-to-cloud`, lives on the VPS rather than in
this repo) mirrors all personal GitHub repos — the notes vault included — into
`<webdav-mount>/backup/git-backup/`; see [docs/architecture.md](docs/architecture.md).

## License

MIT — see [LICENSE](LICENSE).
