#!/usr/bin/env python3
"""
Minimal cover art downloader for a single track.
Uses Deezer API (free, no key needed) + iTunes API as fallback.
Usage: python3 get_cover.py /path/to/track.mp3
"""

import json, os, sys, urllib.request, urllib.parse
from mutagen.id3 import ID3, APIC


def deezer_search(artist, title):
    """Search Deezer for album art URL. Returns URL or None."""
    query = f"{artist} {title}"
    try:
        url = f"https://api.deezer.com/search?q={urllib.parse.quote(query)}&limit=3"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        for item in data.get("data", []):
            alb = item.get("album", {})
            cover = alb.get("cover_xl") or alb.get("cover_big") or alb.get("cover_medium")
            if cover:
                # Check artist match (loose)
                art_name = item.get("artist", {}).get("name", "").lower()
                if artist.lower() in art_name or art_name in artist.lower():
                    return cover
    except Exception:
        pass
    return None


def itunes_search(artist, title):
    """Search iTunes for artwork URL. Returns URL or None."""
    query = f"{artist} {title}"
    try:
        url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&limit=3&media=music"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        for item in data.get("results", []):
            cover = item.get("artworkUrl100", "").replace("100x100", "600x600")
            if cover:
                art_name = item.get("artistName", "").lower()
                if artist.lower() in art_name or art_name in artist.lower():
                    return cover
    except Exception:
        pass
    return None


def download_cover(url):
    """Download cover image bytes from URL."""
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.read()
    except Exception:
        return None


def embed_cover(filepath, image_data):
    """Embed JPEG cover art into MP3 file."""
    try:
        audio = ID3(filepath)
        # Remove existing covers
        for apic in audio.getall('APIC'):
            del audio[apic.HashKey]
        # Add new cover
        audio.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=image_data))
        audio.save()
        return True
    except Exception as e:
        print(f"  Error embedding: {e}", file=sys.stderr)
        return False


def parse_filename(filepath):
    """Parse 'Artist - Title.ext' from filename."""
    name = os.path.splitext(os.path.basename(filepath))[0]
    if ' - ' in name:
        return name.split(' - ', 1)
    return name, name


def get_track_tags(filepath):
    """Try to get artist/title from ID3 tags, fall back to filename."""
    try:
        audio = ID3(filepath)
        artist = title = None
        for tag in audio.getall('TPE1'):
            artist = str(tag)
        for tag in audio.getall('TIT2'):
            title = str(tag)
        if artist and title:
            return artist, title
    except Exception:
        pass
    return parse_filename(filepath)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 get_cover.py <track.mp3>")
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"ERROR: {filepath} not found")
        sys.exit(1)

    artist, title = get_track_tags(filepath)
    print(f"  Track: {artist} - {title}")

    # Try sources in order
    for name, func in [("Deezer", deezer_search), ("iTunes", itunes_search)]:
        url = func(artist, title)
        if url:
            data = download_cover(url)
            if data and len(data) > 1000:
                if embed_cover(filepath, data):
                    print(f"  COVER: {name} ({len(data)} bytes)")
                    return
        print(f"  No match: {name}")

    print("  No cover found")


if __name__ == '__main__':
    main()
