#!/usr/bin/env python3
"""
Import m3u playlists into Navidrome via Subsonic API.
Reads m3u files, matches each path against the Navidrome index, creates playlists.

Credentials: NAVIDROME_USER / NAVIDROME_PASSWORD env vars (or .env file).

Lessons learned (see docs/music-migration-plan.md «Проблемы и решения»):
- createPlaylist must be called with a SINGLE songId; the rest are added via
  updatePlaylist. Passing the whole list to createPlaylist silently loses
  the first track (urlencode mangles lists).
- Matching is done against a locally-built index of ALL Navidrome songs with
  Unicode NFC normalization — not search3, which fails on Cyrillic/decomposed
  Unicode and returns false positives.
- Never fall back to "first search result" — that creates wrong matches.
"""
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE_URL = "http://localhost:4533/rest"
CLIENT = "import_script"

M3U_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/selfhost-music/music/_Playlists"
DRY_RUN = "--dry-run" in sys.argv


def load_creds():
    """Read credentials from env vars, then from .env next to the script."""
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


def norm(s):
    """Unicode-safe normalization for matching (NFC + lowercase + strip punctuation)."""
    s = unicodedata.normalize("NFC", s.lower())
    return re.sub(r"[^\w\s]", "", s)


def api_call(endpoint: str, params: dict = None, method: str = "GET") -> bytes:
    if params is None:
        params = {}
    params["u"] = USER
    params["p"] = PASS
    params["v"] = "1.16.1"
    params["c"] = CLIENT
    qs = urllib.parse.urlencode(params)
    url = f"{BASE_URL}/{endpoint}?{qs}"
    try:
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except Exception as e:
        print(f"  ERROR API {endpoint}: {e}", file=sys.stderr)
        return b""


def build_index() -> dict:
    """Walk all artists/albums and build {song_id: {title, artist}}."""
    songs = {}
    xml_data = api_call("getArtists", {})
    if not xml_data:
        return songs
    root = ET.fromstring(xml_data)
    ns = {"ns": "http://subsonic.org/restapi"}
    for a in root.findall(".//ns:artist", ns):
        root2 = ET.fromstring(api_call("getArtist", {"id": a.get("id")}))
        for alb in root2.findall(".//ns:album", ns):
            root3 = ET.fromstring(api_call("getAlbum", {"id": alb.get("id")}))
            for s in root3.findall(".//ns:song", ns):
                songs[s.get("id")] = {"title": s.get("title", ""), "artist": s.get("artist", "")}
    return songs


def parse_m3u_path(path: str):
    """Parse 'Singletons/Artist - Title.ext' -> (artist, title)."""
    path = path.strip()
    for prefix in ["Singletons/", "../Singletons/"]:
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    if "." in path:
        path = path.rsplit(".", 1)[0]
    parts = path.split(" - ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return None


def create_playlist(name: str, song_ids: list) -> str | None:
    if not song_ids:
        return None
    if DRY_RUN:
        print(f"  [DRY RUN] Would create '{name}' with {len(song_ids)} tracks")
        return "dry-run-id"

    # CRITICAL: createPlaylist takes a single songId. Passing a list loses the
    # first track (urlencode serializes the list as its repr). Rest are added
    # one by one via updatePlaylist.
    xml_data = api_call("createPlaylist", {"name": name, "songId": song_ids[0]})
    if not xml_data:
        return None
    try:
        root = ET.fromstring(xml_data)
        ns = {"ns": "http://subsonic.org/restapi"}
        playlist = root.find(".//ns:playlist", ns)
        if playlist is not None:
            playlist_id = playlist.get("id")
            for sid in song_ids[1:]:
                api_call("updatePlaylist", {"playlistId": playlist_id, "songIdToAdd": sid})
                time.sleep(0.05)
            return playlist_id
    except ET.ParseError:
        pass
    return None


def main():
    if not USER or not PASS:
        print("ERROR: set NAVIDROME_USER and NAVIDROME_PASSWORD (or .env)", file=sys.stderr)
        sys.exit(1)

    print(f"Importing playlists from: {M3U_DIR}")
    print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")

    songs = build_index()
    if not songs:
        print("ERROR: empty Navidrome index — check credentials", file=sys.stderr)
        sys.exit(1)
    print(f"Navidrome index: {len(songs)} songs")

    # Exact-normalized lookups
    lookup = {}
    for sid, s in songs.items():
        lookup.setdefault(norm(s["artist"] + " " + s["title"]), sid)
    title_lookup = {}
    for sid, s in songs.items():
        title_lookup.setdefault(norm(s["title"]), sid)

    def find_song(artist, title):
        n_artist, n_title = norm(artist), norm(title)
        key = n_artist + " " + n_title
        if key in lookup:
            return lookup[key]
        if n_title in title_lookup:
            return title_lookup[n_title]
        return None

    total_tracks = total_found = total_missing = 0
    for f in sorted(os.listdir(M3U_DIR)):
        if not f.endswith(".m3u"):
            continue
        display_name = f[:-4].replace("VK_", "").replace("_", " ")
        filepath = os.path.join(M3U_DIR, f)
        paths = [l.strip() for l in open(filepath, encoding="utf-8") if l.strip() and not l.startswith("#")]

        found_ids, not_found = [], []
        for p in paths:
            parsed = parse_m3u_path(p)
            if not parsed:
                not_found.append(p)
                continue
            artist, title = parsed
            sid = find_song(artist, title)
            if sid:
                found_ids.append(sid)
            else:
                not_found.append(f"{artist} - {title}")

        playlist_id = create_playlist(display_name, found_ids)
        print(f"  {display_name}: {len(found_ids)}/{len(paths)}" + (f" (missing: {len(not_found)})" if not_found else ""))
        for nf in not_found[:5]:
            print(f"    MISSING: {nf}")
        if not DRY_RUN:
            time.sleep(0.3)

        total_tracks += len(paths)
        total_found += len(found_ids)
        total_missing += len(not_found)

    print(f"\nSUMMARY:")
    print(f"  Total tracks: {total_tracks}")
    print(f"  Found: {total_found}")
    print(f"  Missing: {total_missing}")


if __name__ == "__main__":
    main()
