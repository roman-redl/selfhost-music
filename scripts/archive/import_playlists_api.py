#!/usr/bin/env python3
"""
Import m3u playlists into Navidrome via Subsonic API.
Reads m3u files, searches for each track, creates playlist with matched tracks.
"""
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE_URL = "http://localhost:4533/rest"
USER = os.environ.get("NAVIDROME_USER", "")
PASS = os.environ.get("NAVIDROME_PASSWORD", "") or os.environ.get("NAVIDROME_PASS", "")
CLIENT = "import_script"

M3U_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/selfhost-music/music/_Playlists"
DRY_RUN = "--dry-run" in sys.argv


def api_call(endpoint: str, params: dict = None, method: str = "GET") -> bytes:
    """Make a Subsonic API call"""
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception as e:
        print(f"  ERROR API {endpoint}: {e}", file=sys.stderr)
        return b""


def search_track(artist: str, title: str) -> str | None:
    """Search for a track, return song ID or None"""
    # Try exact search first
    query = f"{artist} {title}"
    xml_data = api_call("search3", {"query": query, "songCount": 5})
    if not xml_data:
        return None

    try:
        root = ET.fromstring(xml_data)
        ns = {"ns": "http://subsonic.org/restapi"}
        songs = root.findall(".//ns:song", ns)

        for song in songs:
            song_artist = song.get("artist", "").lower()
            song_title = song.get("title", "").lower()
            if artist.lower() in song_artist and title.lower() in song_title:
                return song.get("id")

        # If no exact match, return first result
        if songs:
            return songs[0].get("id")
    except ET.ParseError:
        pass

    return None


def parse_m3u_path(path: str) -> tuple[str, str] | None:
    """Parse 'Singletons/Artist - Title.ext' → (artist, title)"""
    path = path.strip()
    # Remove prefix
    for prefix in ["Singletons/", "../Singletons/"]:
        if path.startswith(prefix):
            path = path[len(prefix):]
            break

    # Remove extension
    if "." in path:
        path = path.rsplit(".", 1)[0]

    # Split artist - title
    parts = path.split(" - ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]

    return None


def read_m3u(filepath: str) -> list[str]:
    """Read track paths from m3u file"""
    paths = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                paths.append(line)
    return paths


def create_playlist(name: str, song_ids: list[str]) -> str | None:
    """Create a playlist via Subsonic API, return playlist ID"""
    if not song_ids:
        return None

    if DRY_RUN:
        print(f"  [DRY RUN] Would create '{name}' with {len(song_ids)} tracks")
        return "dry-run-id"

    # Create playlist with first song
    xml_data = api_call("createPlaylist", {"name": name, "songId": song_ids})
    if not xml_data:
        return None

    try:
        root = ET.fromstring(xml_data)
        ns = {"ns": "http://subsonic.org/restapi"}
        playlist = root.find(".//ns:playlist", ns)
        if playlist is not None:
            playlist_id = playlist.get("id")
            # Add remaining songs
            if len(song_ids) > 1:
                for sid in song_ids[1:]:
                    api_call("updatePlaylist", {
                        "playlistId": playlist_id,
                        "songIdToAdd": sid
                    })
                    time.sleep(0.1)  # Rate limit
            return playlist_id
    except ET.ParseError:
        pass

    return None


def import_playlist(filepath: str) -> dict:
    """Import one m3u file as a Navidrome playlist"""
    name = os.path.splitext(os.path.basename(filepath))[0]
    # Clean up name (remove VK_ prefix)
    display_name = name
    if name.startswith("VK_"):
        display_name = name[3:]
    display_name = display_name.replace("_", " ")

    paths = read_m3u(filepath)
    print(f"\n{'='*60}")
    print(f"Playlist: {display_name} ({len(paths)} tracks)")
    print(f"File: {filepath}")

    found_ids = []
    not_found = []

    for path in paths:
        parsed = parse_m3u_path(path)
        if not parsed:
            not_found.append(path)
            continue

        artist, title = parsed
        song_id = search_track(artist, title)

        if song_id:
            found_ids.append(song_id)
        else:
            not_found.append(f"{artist} - {title}")

    print(f"  Found: {len(found_ids)}, Not found: {len(not_found)}")

    if not_found and len(not_found) <= 10:
        for nf in not_found:
            print(f"    MISSING: {nf}")
    elif not_found:
        print(f"    (showing first 10 of {len(not_found)} missing)")
        for nf in not_found[:10]:
            print(f"    MISSING: {nf}")

    playlist_id = create_playlist(display_name, found_ids)
    if playlist_id:
        print(f"  Created playlist ID: {playlist_id}")

    return {
        "name": display_name,
        "total": len(paths),
        "found": len(found_ids),
        "missing": len(not_found),
        "id": playlist_id
    }


def main():
    if not USER or not PASS:
        print(
            "ERROR: set NAVIDROME_USER and NAVIDROME_PASS environment variables",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Importing playlists from: {M3U_DIR}")
    print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")

    results = []
    for f in sorted(os.listdir(M3U_DIR)):
        if f.endswith(".m3u") and not f.startswith("_test"):
            filepath = os.path.join(M3U_DIR, f)
            result = import_playlist(filepath)
            results.append(result)
            if not DRY_RUN:
                time.sleep(1)  # Be nice to the server

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY:")
    total_tracks = sum(r["total"] for r in results)
    total_found = sum(r["found"] for r in results)
    total_missing = sum(r["missing"] for r in results)
    created = sum(1 for r in results if r["id"])

    print(f"  Playlists: {len(results)}")
    print(f"  Created: {created}")
    print(f"  Total tracks: {total_tracks}")
    print(f"  Found: {total_found} ({100*total_found/max(1,total_tracks):.1f}%)")
    print(f"  Missing: {total_missing}")

    if DRY_RUN:
        print("\nRun without --dry-run to actually create playlists.")


if __name__ == "__main__":
    main()
