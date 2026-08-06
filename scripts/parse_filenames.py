#!/usr/bin/env python3
"""Parse Kate Mobile cache filenames and write ID3 tags.

Filename format: Artist_Title_<owner_id>_<track_id>.mp3
- Remove two trailing numeric segments (owner_id, track_id)
- Split remaining at FIRST underscore: artist | title
- Write artist and title as ID3v2 tags via mutagen

Unmatched files are logged to unmatched.txt for manual review.
"""

import os
import re
import sys
from pathlib import Path
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3

REPO = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO / "MusicRaw" / "kate_mobile"
UNMATCHED_LOG = REPO / "MusicRaw" / "unmatched.txt"


def parse_filename(filename: str) -> tuple[str, str] | None:
    """Parse artist and title from Kate Mobile cache filename.

    Returns (artist, title) or None if filename doesn't match expected pattern.
    """
    # Remove .mp3 extension
    name = filename.rsplit(".", 1)[0]

    # Split off last two underscore-separated numeric IDs
    # Pattern: ..._<digits>_<digits>
    m = re.match(r"^(.+)_(\d+)_(\d+)$", name)
    if not m:
        return None

    artist_title = m.group(1)

    # Split at FIRST underscore
    if "_" not in artist_title:
        return None

    parts = artist_title.split("_", 1)
    artist = parts[0].strip()
    title = parts[1].strip()

    if not artist or not title:
        return None

    return artist, title


def write_tags(filepath: Path, artist: str, title: str) -> bool:
    """Write artist and title ID3 tags to an MP3 file."""
    try:
        audio = EasyID3(str(filepath))
    except Exception:
        try:
            audio = EasyID3()
        except Exception:
            return False

    audio["artist"] = [artist]
    audio["title"] = [title]
    audio.save(str(filepath))
    return True


def main():
    mp3_files = sorted(CACHE_DIR.glob("*.mp3"))

    if not mp3_files:
        print(f"No MP3 files found in {CACHE_DIR}")
        sys.exit(1)

    print(f"Found {len(mp3_files)} MP3 files")

    unmatched = []
    matched = 0
    errors = 0

    for mp3 in mp3_files:
        result = parse_filename(mp3.name)
        if result is None:
            unmatched.append(mp3.name)
            continue

        artist, title = result
        if write_tags(mp3, artist, title):
            matched += 1
        else:
            errors += 1
            unmatched.append(mp3.name)

        if (matched + errors) % 100 == 0:
            print(f"  Processed {matched + errors}/{len(mp3_files)}...")

    # Write unmatched log
    with open(UNMATCHED_LOG, "w") as f:
        for name in unmatched:
            f.write(f"{name}\n")

    print(f"\nDone: {matched} matched, {len(unmatched)} unmatched, {errors} errors")
    if unmatched:
        print(f"Unmatched list → {UNMATCHED_LOG}")


if __name__ == "__main__":
    main()
