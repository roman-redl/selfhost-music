# Adding Music & Cover Art

## Adding a track

### From your computer (primary path)

1. Drop an MP3/FLAC into `MusicInbox/` (repo root — Syncthing carries it to the server).
2. In ~30 seconds the track is tagged, gets cover art, and shows up on every client.

Quality notes:
- Name the file `Artist - Title.ext` (single ` - `, NFC).
- Prefer files with sane ID3 tags (the fixer only repairs missing/invalid values).
- Want a specific cover? Put `Artist - Title.jpg|png` next to the audio file — see below.

### From your phone (SFTP)

Any SFTP file manager works (e.g. Material Files on Android):

- Host: your `DOMAIN`, port 22, key-based auth
- Upload to `/opt/selfhost-music/music-inbox/`

The watcher handles the rest exactly like the Syncthing path.

## Manual cover (highest priority)

Put a `.jpg`/`.png` **with the same name** next to the audio file in the inbox:

```
music-inbox/
├── Artist - Title.mp3
└── Artist - Title.jpg    ← embedded automatically
```

The watcher embeds the image and deletes it only after success (on failure the image
stays next to the track in `/music/` for a retry). If a manual image exists, online
sources are not queried.

Requirements: JPEG (preferred) or PNG, roughly square, ≥ 500×500 (~1000×1000 ideal),
under ~1 MB. WebP/GIF are not supported.

## Automatic cover art

`get_cover.py` tries sources in order:

| # | Source | Key needed | Notes |
|---|---|---|---|
| 1 | Manual image next to the file | — | Highest priority |
| 2 | Deezer API | — | ~76% hit rate |
| 3 | iTunes API | — | +8% |
| 4 | Cover Art Archive (MusicBrainz) | — | Good for classical |
| 5 | Discogs API | — | 60 req/min limit |
| 6 | Bing Images | — | Last-resort web search |

MP3 and FLAC are supported; other formats import without auto-covers.

### Why some covers are wrong

The script searches by artist/title text — it cannot "see" images. Failures happen with
same-named artists, underground tracks, or generic filler art returned by a source.
Replacements: re-run with `--force`, or drop a manual image.

```bash
python3 scripts/get_cover.py --force "path/to/Artist - Title.mp3"   # one track
python3 scripts/get_cover.py --force --artist "Artist Name" /music/ # whole artist
```

Flags: `--force` overwrites an existing cover (otherwise covered tracks are skipped);
`--artist "Name"` filters by artist (case-insensitive substring, directory mode only).

## Tag repair

```bash
python3 scripts/fix_tags.py --dry-run <file-or-dir>   # preview
python3 scripts/fix_tags.py <file-or-dir>             # write
```

Derives Artist/Title/Album from the filename and removes junk values (`Unknown Artist`,
`[Unknown Album]`, …). Valid tags are never overwritten. Runs automatically for every
inbox file.

For one-off corrections use mutagen directly:

```python
from mutagen.id3 import ID3, TPE1, TIT2
a = ID3("path/to/track.mp3")
a.add(TPE1(encoding=3, text="Correct Artist"))
a.add(TIT2(encoding=3, text="Correct Title"))
a.save()
```

## After manual edits on the server

Trigger a scan:

```bash
curl -s -X POST "http://localhost:4533/rest/startScan?u=$NAVIDROME_USER& \
p=$(python3 -c 'import urllib.parse,os;print(urllib.parse.quote(os.environ["NAVIDROME_PASSWORD"],safe=""))')&v=1.16.1&c=maint"
```
