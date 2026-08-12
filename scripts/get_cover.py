#!/usr/bin/env python3
"""
Cover art downloader with multiple fallback sources.
Usage:
  python3 get_cover.py <track.mp3>                 # single file
  python3 get_cover.py --force <track.mp3>         # overwrite existing cover
  python3 get_cover.py --artist "Sandra" <dir>     # batch, filter by artist
  python3 get_cover.py --artist "Sandra" --force <dir>  # batch + overwrite

Sources (tried in priority order):
  1. Manual — adjacent .jpg/.png file next to the MP3
  2. Deezer API (free, no key)
  3. iTunes API (free, no key)
  4. Cover Art Archive via MusicBrainz (free, no key)
  5. Discogs API (free, no key)
  6. Bing Image Search (web scraping, no key)

Query sanitization: dirty ID3 tags are cleaned before searching
(e.g. "[muzmo.ru]", leading track numbers, OST prefixes).
"""

import argparse, json, os, re, sys, urllib.request, urllib.parse
from mutagen.id3 import ID3, APIC
from mutagen.flac import FLAC, Picture

USER_AGENT = "SelfhostMusic/1.0 (selfhost-music; roman-redl@github)"
MUSICBRAINZ_AGENT = "SelfhostMusic/1.0 (roman-redl@github)"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ============================================================
#  Query sanitization — clean dirty ID3 tags before API search
# ============================================================


def sanitize_query(artist, title):
    """Remove common garbage patterns from artist/title for better search results."""
    # Strip [site.ru] wrappers from both fields
    artist = re.sub(r"\[.*?\]", "", artist)
    title = re.sub(r"\[.*?\]", "", title)

    # Remove leading track numbers: "16. ", "01 - "
    artist = re.sub(r"^\d+[\.\-\)]\s*", "", artist)
    title = re.sub(r"^\d+[\.\-\)]\s*", "", title)

    # Remove "OST <show>" prefix — real artist is usually after a dash
    # "OST Shingeki no kyojin Attack On Titan - Sawano Hiroyuki [EMA ]"
    # -> keep "Sawano Hiroyuki"
    m = re.match(
        r"OST\s+.+?\s+-\s+(.+)", artist, re.IGNORECASE
    )
    if m:
        artist = m.group(1)

    # Collapse whitespace
    artist = re.sub(r"\s+", " ", artist).strip()
    title = re.sub(r"\s+", " ", title).strip()

    # Remove trailing empty after cleanup
    if not artist or not title:
        return None, None

    return artist, title


# ============================================================
#  Source functions — each returns a cover URL or None
# ============================================================


def manual_cover(filepath):
    """Read cover from adjacent .jpg/.png file. Returns raw bytes or None."""
    base = os.path.splitext(filepath)[0]
    for ext in (".jpg", ".jpeg", ".png"):
        cover_path = base + ext
        if os.path.exists(cover_path):
            try:
                with open(cover_path, "rb") as f:
                    data = f.read()
                if len(data) > 1000:
                    return data
            except Exception:
                pass
    return None


def deezer_search(artist, title):
    """Search Deezer for album art URL."""
    query = f"{artist} {title}"
    try:
        url = (
            "https://api.deezer.com/search?"
            f"q={urllib.parse.quote(query)}&limit=3"
        )
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        for item in data.get("data", []):
            alb = item.get("album", {})
            cover = (
                alb.get("cover_xl")
                or alb.get("cover_big")
                or alb.get("cover_medium")
            )
            if cover:
                art_name = item.get("artist", {}).get("name", "").lower()
                if artist.lower() in art_name or art_name in artist.lower():
                    return cover
    except Exception:
        pass
    return None


def itunes_search(artist, title):
    """Search iTunes for artwork URL."""
    query = f"{artist} {title}"
    try:
        url = (
            "https://itunes.apple.com/search?"
            f"term={urllib.parse.quote(query)}&limit=3&media=music"
        )
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as r:
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


def cover_art_archive_search(artist, title):
    """Search MusicBrainz -> get release MBID -> fetch cover from Cover Art Archive."""
    try:
        query = f'artist:"{artist}" AND recording:"{title}"'
        mb_url = (
            "https://musicbrainz.org/ws/2/recording/?"
            f"query={urllib.parse.quote(query)}&fmt=json&limit=3"
        )
        req = urllib.request.Request(mb_url, headers={"User-Agent": MUSICBRAINZ_AGENT})
        with urllib.request.urlopen(req, timeout=10) as r:
            mb_data = json.loads(r.read())

        mbids = []
        for rec in mb_data.get("recordings", []):
            for rel in rec.get("releases", []):
                mbid = rel.get("id")
                if mbid and mbid not in mbids:
                    mbids.append(mbid)
                    if len(mbids) >= 3:
                        break
            if len(mbids) >= 3:
                break

        for mbid in mbids:
            caa_url = f"https://coverartarchive.org/release/{mbid}/front"
            try:
                req = urllib.request.Request(
                    caa_url, headers={"User-Agent": MUSICBRAINZ_AGENT}
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    if r.status == 200 and r.headers.get(
                        "Content-Type", ""
                    ).startswith("image/"):
                        return caa_url
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue
                raise
    except Exception:
        pass
    return None


def discogs_search(artist, title):
    """Search Discogs for cover art URL."""
    token = os.environ.get("DISCOGS_TOKEN")
    query = f"{artist} {title}"
    try:
        url = (
            "https://api.discogs.com/database/search?"
            f"q={urllib.parse.quote(query)}&type=release&per_page=3"
        )
        headers = {"User-Agent": USER_AGENT}
        if token:
            headers["Authorization"] = f"Discogs token={token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        for item in data.get("results", []):
            cover = item.get("cover_image")
            if cover:
                return cover
    except Exception:
        pass
    return None


def bing_image_search(artist, title):
    """Search Bing Images for cover art. Returns direct image URL or None."""
    query = f"{artist} {title}"
    try:
        bing_url = (
            "https://www.bing.com/images/async?"
            f"q={urllib.parse.quote(query)}&first=1&count=3&mmasync=1"
        )
        referer = (
            "https://www.bing.com/images/search?q="
            + urllib.parse.quote(query)
        )
        req = urllib.request.Request(
            bing_url,
            headers={
                "User-Agent": BROWSER_UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.5",
                "Referer": referer,
            },
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")

        # Strategy 1: extract original image URLs from murl fields
        murls = re.findall(r"murl&quot;:&quot;([^&]+)", html)
        if murls:
            return urllib.parse.unquote(murls[0])

        # Strategy 2: construct full-size URL from Bing thumbnail ID
        thumb_ids = re.findall(r"th\?id=([A-Za-z0-9.~_%-]+)", html)
        if thumb_ids:
            return f"https://www.bing.com/th?id={thumb_ids[0]}&pid=ImgRaw"

    except Exception:
        pass
    return None


# ============================================================
#  Helpers
# ============================================================


def download_cover(url):
    """Download cover image bytes from URL. Returns bytes or None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
            if len(data) > 1000:
                return data
    except Exception:
        pass
    return None


def embed_cover(filepath, image_data):
    """Embed JPEG/PNG cover art into MP3 or FLAC. Removes existing covers first."""
    mime = "image/jpeg"
    if image_data[:4] == b"\x89PNG":
        mime = "image/png"

    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".flac":
            audio = FLAC(filepath)
            audio.clear_pictures()
            pic = Picture()
            pic.type = 3  # front cover
            pic.mime = mime
            pic.desc = "Cover"
            pic.data = image_data
            audio.add_picture(pic)
            audio.save()
            return True

        audio = ID3(filepath)
        for apic in audio.getall("APIC"):
            del audio[apic.HashKey]
        audio.add(
            APIC(encoding=3, mime=mime, type=3, desc="Cover", data=image_data)
        )
        audio.save()
        return True
    except Exception as e:
        print(f"  Error embedding: {e}", file=sys.stderr)
        return False


def has_cover(filepath):
    """Return True if file already has embedded cover art."""
    try:
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".flac":
            return len(FLAC(filepath).pictures) > 0
        audio = ID3(filepath)
        return len(audio.getall("APIC")) > 0
    except Exception:
        return False


def parse_filename(filepath):
    """Parse 'Artist - Title.ext' from filename."""
    name = os.path.splitext(os.path.basename(filepath))[0]
    if " - " in name:
        return name.split(" - ", 1)
    return name, name


def get_track_tags(filepath):
    """Get artist/title from tags (ID3 or FLAC Vorbis), fall back to filename parsing."""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".flac":
            audio = FLAC(filepath)
            artist = title = None
            if audio.get("artist"):
                artist = str(audio["artist"][0])
            if audio.get("title"):
                title = str(audio["title"][0])
            if artist and title:
                return artist, title
        else:
            audio = ID3(filepath)
            artist = title = None
            for tag in audio.getall("TPE1"):
                artist = str(tag)
            for tag in audio.getall("TIT2"):
                title = str(tag)
            if artist and title:
                return artist, title
    except Exception:
        pass
    return parse_filename(filepath)


# ============================================================
#  Core processing
# ============================================================


def process_file(filepath, force=False):
    """Download and embed cover for a single MP3/FLAC file.
    Returns True if cover was embedded, False otherwise.
    """
    # Manual cover (adjacent .jpg/.png) is an explicit user instruction —
    # it applies even when the file already has an embedded cover.
    manual_data = manual_cover(filepath)
    if manual_data:
        if embed_cover(filepath, manual_data):
            print(f"  COVER: manual ({len(manual_data)} bytes)")
            return True

    if not force and has_cover(filepath):
        print("  SKIP: already has cover (use --force to overwrite)")
        return False

    raw_artist, raw_title = get_track_tags(filepath)
    artist, title = sanitize_query(raw_artist, raw_title)

    if artist != raw_artist or title != raw_title:
        print(f"  Tags: {raw_artist} - {raw_title}")
        print(f"  Clean: {artist} - {title}")
    else:
        print(f"  Track: {artist} - {title}")

    if not artist or not title:
        print("  SKIP: cannot determine artist/title after sanitization")
        return False

    # 1. Manual cover — handled at the top of this function (highest priority)

    # 2–6. API + web sources in priority order
    sources = [
        ("Deezer", deezer_search),
        ("iTunes", itunes_search),
        ("Cover Art Archive", cover_art_archive_search),
        ("Discogs", discogs_search),
        ("Bing Images", bing_image_search),
    ]

    for name, func in sources:
        url = func(artist, title)
        if url:
            data = download_cover(url)
            if data:
                if embed_cover(filepath, data):
                    print(f"  COVER: {name} ({len(data)} bytes)")
                    return True
        print(f"  No match: {name}")

    # Retry with raw (unsanitized) query if sanitized query failed
    if (artist != raw_artist or title != raw_title) and raw_artist and raw_title:
        print(f"  Retrying with raw tags: {raw_artist} - {raw_title}")
        for name, func in sources:
            url = func(raw_artist, raw_title)
            if url:
                data = download_cover(url)
                if data:
                    if embed_cover(filepath, data):
                        print(f"  COVER: {name} [{len(data)} bytes] (raw tags)")
                        return True

    print("  No cover found (all sources exhausted)")
    return False


# ============================================================
#  Main
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="Download and embed cover art for MP3/FLAC files"
    )
    parser.add_argument("path", help="MP3/FLAC file or directory of files")
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing cover art"
    )
    parser.add_argument(
        "--artist",
        help="Only process tracks by this artist (batch mode, case-insensitive substring match)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.path):
        print(f"ERROR: {args.path} not found", file=sys.stderr)
        sys.exit(1)

    if os.path.isdir(args.path):
        tracks = []
        for root, _dirs, files in os.walk(args.path):
            for f in files:
                if f.lower().endswith((".mp3", ".flac")):
                    tracks.append(os.path.join(root, f))

        if not tracks:
            print(f"No MP3/FLAC files found in {args.path}")
            sys.exit(0)

        if args.artist:
            before = len(tracks)
            tracks = [
                fp
                for fp in tracks
                if args.artist.lower() in get_track_tags(fp)[0].lower()
            ]
            print(
                f"Artist filter '{args.artist}': {len(tracks)}/{before} tracks match"
            )

        print(f"Processing {len(tracks)} file(s)...")
        ok = 0
        for fp in tracks:
            print(f"\n{fp}")
            if process_file(fp, force=args.force):
                ok += 1
        print(f"\nDone: {ok}/{len(tracks)} covers embedded")
        sys.exit(0 if ok == len(tracks) else 1)
    else:
        sys.exit(0 if process_file(args.path, force=args.force) else 1)


if __name__ == "__main__":
    main()
