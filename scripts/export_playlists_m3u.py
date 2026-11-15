#!/usr/bin/env python3
"""Export every Navidrome playlist to <out_dir>/<name>.m3u (run on the VPS).

Used by the nightly backup-to-cloud.sh. Same format as handoff/export_playlists.py:
plain paths relative to the music folder, one per line, no EXTM3U/EXTINF, track
order = playlist_tracks.id, "/" in a playlist name becomes "_". Reads the DB
read-only. The output must stay outside the music folder, otherwise Navidrome
could import the files as playlists.

Usage: python3 scripts/export_playlists_m3u.py <out_dir> [db_path]
"""
import sqlite3
import sys
import unicodedata
from pathlib import Path

DB = sys.argv[2] if len(sys.argv) > 2 else "/opt/selfhost-music/data/navidrome.db"

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
for old in out.glob("*.m3u"):
    old.unlink()

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
count = 0
for pid, name in con.execute("SELECT id, name FROM playlist ORDER BY name"):
    paths = [
        unicodedata.normalize("NFC", path)
        for (path,) in con.execute(
            "SELECT mf.path FROM playlist_tracks pt"
            " JOIN media_file mf ON mf.id = pt.media_file_id"
            " WHERE pt.playlist_id = ? ORDER BY pt.id",
            (pid,),
        )
    ]
    body = "\n".join(paths)
    (out / (name.replace("/", "_") + ".m3u")).write_text(body + ("\n" if body else ""), encoding="utf-8")
    count += 1
print(count)
