# selfhost-music

Self-hosted music infrastructure — your own Spotify, without subscriptions.

Navidrome on Oracle Cloud Free Tier, offline cache on all devices, automatic metadata tagging, backups to Mail.ru cloud.

## Stack

| Component | Role |
|---|---|
| [Navidrome](https://www.navidrome.org/) | Music server (Subsonic API), lightweight Go app |
| [Caddy](https://caddyserver.com/) | HTTPS reverse proxy, auto Let's Encrypt certificates |
| [beets](https://beets.io/) | Metadata tagging, album art, folder structure |
| [Syncthing](https://syncthing.net/) | P2P file sync — laptop ↔ VPS (Mac, Windows, Linux) |
| [Supersonic](https://github.com/dweymouth/supersonic) | Desktop client with full offline cache (Mac/Win/Linux) |
| [Ultrasonic](https://gitlab.com/ultrasonic/ultrasonic) | Android client with offline cache |

## Hardware

Oracle Cloud Free Tier ARM VPS (4 OCPU, 24 GB RAM) — free within limits.
Account must be upgraded to PAYG to prevent automatic termination after 60 days.

## Quick start

```bash
# 1. Clone onto your VPS
git clone https://github.com/roman-redl/selfhost-music.git

# 2. Configure
cp .env.example .env
# Edit .env with your domain, credentials, paths

# 3. Start
docker compose up -d

# 4. Add music
# rsync your library into ./music/
# Or use Syncthing to sync ~/MusicInbox with /music-inbox/
```

## Repository layout

```
.
├── docker-compose.yml    # Navidrome + Caddy (+ optional Audiobookshelf)
├── config/
│   └── Caddyfile         # HTTPS, rate limiting
├── scripts/              # parse_filenames.py, watch-inbox.sh, backup-cron.sh
├── docs/
│   └── music-migration-plan.md  # Full plan, architecture, step-by-step
├── .env.example          # Environment template (copy to .env)
└── .gitignore
```

## Migration from VK/Kate Mobile

See [docs/music-migration-plan.md](docs/music-migration-plan.md) for the full step-by-step migration plan — from VPS setup through metadata normalization, playlist recovery, gap filling, and client configuration.

## License

[MIT](LICENSE)
