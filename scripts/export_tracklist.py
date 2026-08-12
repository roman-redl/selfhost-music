#!/usr/bin/env python3
"""
export_tracklist.py — Export full track inventory from Navidrome (Subsonic API) as CSV.

Usage:
  python3 export_tracklist.py [base_url] > tracklist.csv
  # base_url defaults to http://localhost:4533/rest (run on the VPS)
  # Remote: python3 export_tracklist.py https://$DOMAIN/rest

Credentials: NAVIDROME_USER / NAVIDROME_PASSWORD env vars, or .env next to the
script / in the repo root.

Output: CSV with header id, artist, title, album, year, duration_s, format, path.
Sorted by artist, title (case-insensitive). Opens as a table in Numbers/Excel
and renders as a table on GitHub. The file is versioned in git as a snapshot of
the collection — regenerate it after mass imports.
"""

import csv
import os
import sys
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4533/rest"
CLIENT = "export_tracklist"


def load_creds():
    """Read credentials from env vars, then from .env next to the script / repo root."""
    user = os.environ.get("NAVIDROME_USER", "")
    password = os.environ.get("NAVIDROME_PASSWORD", "") or os.environ.get("NAVIDROME_PASS", "")
    if not (user and password):
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
        ]
        for env_path in candidates:
            if os.path.exists(env_path):
                for line in open(env_path):
                    line = line.strip()
                    if line.startswith("NAVIDROME_USER="):
                        user = line.split("=", 1)[1]
                    elif line.startswith("NAVIDROME_PASSWORD="):
                        password = line.split("=", 1)[1]
                if user and password:
                    break
    return user, password


USER, PASS = load_creds()


def api_call(endpoint, params=None):
    if params is None:
        params = {}
    params.update({"u": USER, "p": PASS, "v": "1.16.1", "c": CLIENT})
    # Always urlencode: the password contains characters that break raw URLs
    url = f"{BASE_URL}/{endpoint}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return resp.read()
    except Exception as e:
        print(f"  ERROR API {endpoint}: {e}", file=sys.stderr)
        return b""


def parse_xml(data):
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        return None


def build_inventory():
    """Walk all artists/albums and collect every song with metadata."""
    ns = {"ns": "http://subsonic.org/restapi"}
    songs = {}

    root = parse_xml(api_call("getArtists"))
    if root is None:
        return songs
    for artist_el in root.findall(".//ns:artist", ns):
        artist_root = parse_xml(api_call("getArtist", {"id": artist_el.get("id")}))
        if artist_root is None:
            continue
        for album_el in artist_root.findall(".//ns:album", ns):
            album_root = parse_xml(api_call("getAlbum", {"id": album_el.get("id")}))
            if album_root is None:
                continue
            for song in album_root.findall(".//ns:song", ns):
                songs[song.get("id")] = {
                    "artist": song.get("artist", ""),
                    "title": song.get("title", ""),
                    "album": song.get("album", ""),
                    "year": song.get("year", ""),
                    "duration": song.get("duration", ""),
                    "suffix": song.get("suffix", ""),
                    "path": song.get("path", ""),
                }
    return songs


def clean(value):
    """Make a value CSV-safe (strip tabs/newlines)."""
    return str(value).replace("\t", " ").replace("\n", " ").strip()


def main():
    if not USER or not PASS:
        print("ERROR: set NAVIDROME_USER and NAVIDROME_PASSWORD (env or .env)", file=sys.stderr)
        sys.exit(1)

    songs = build_inventory()
    if not songs:
        print("ERROR: empty Navidrome index — check credentials/URL", file=sys.stderr)
        sys.exit(1)

    rows = [(sid, s) for sid, s in songs.items()]
    # Sort by artist, then title (case-insensitive, NFC-normalized)
    def sort_key(row):
        sid, s = row
        return (
            unicodedata.normalize("NFC", s["artist"].lower()),
            unicodedata.normalize("NFC", s["title"].lower()),
        )

    rows.sort(key=sort_key)

    writer = csv.writer(sys.stdout)
    writer.writerow(["id", "artist", "title", "album", "year", "duration_s", "format", "path"])
    for sid, s in rows:
        writer.writerow([
            sid,
            clean(s["artist"]),
            clean(s["title"]),
            clean(s["album"]),
            clean(s["year"]),
            clean(s["duration"]),
            clean(s["suffix"]),
            clean(s["path"]),
        ])

    print(f"# exported {len(rows)} tracks", file=sys.stderr)


if __name__ == "__main__":
    main()
