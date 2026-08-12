#!/usr/bin/env python3
"""
Fix "[Unknown Album]" in Navidrome by setting album tag = artist name
for all tracks in MusicRaw/Library/Singletons/ that lack an album tag.

Usage: python3 scripts/fix_unknown_album.py [--dry-run] [--limit N]
"""

import os
import sys
import argparse
from mutagen import File
from mutagen.id3 import ID3, TALB

SINGLETONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "MusicRaw", "Library", "Singletons"
)


def get_artist(audio):
    """Extract artist from tags (ID3 TPE1 or Vorbis ARTIST)."""
    if audio is None or not hasattr(audio, 'tags') or audio.tags is None:
        return None
    if hasattr(audio.tags, 'getall'):
        frames = audio.tags.getall('TPE1')
        if frames:
            return str(frames[0])
    if hasattr(audio.tags, 'get'):
        artist = audio.tags.get('ARTIST') or audio.tags.get('artist')
        if artist:
            return str(artist[0]) if isinstance(artist, list) else str(artist)
    return None


def get_album(audio):
    """Extract album from tags (ID3 TALB or Vorbis ALBUM)."""
    if audio is None or not hasattr(audio, 'tags') or audio.tags is None:
        return None
    if hasattr(audio.tags, 'getall'):
        frames = audio.tags.getall('TALB')
        if frames:
            val = str(frames[0])
            if val and val != '[Unknown Album]':
                return val
    if hasattr(audio.tags, 'get'):
        album = audio.tags.get('ALBUM') or audio.tags.get('album')
        if album:
            return str(album[0]) if isinstance(album, list) else str(album)
    return None


def parse_artist_from_filename(fname):
    """Extract artist from filename pattern 'Artist - Title.ext'."""
    name = os.path.splitext(fname)[0]
    if ' - ' in name:
        return name.split(' - ', 1)[0].strip()
    return name.strip()


def set_album_tag(filepath, album_name):
    """Write album tag to file. Returns True on success."""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == '.mp3':
            audio = ID3(filepath)
            audio.add(TALB(encoding=3, text=album_name))
            audio.save()
            return True
        elif ext == '.flac':
            audio = File(filepath)
            if audio is not None and hasattr(audio, 'tags'):
                audio['ALBUM'] = album_name
                audio.save()
                return True
        else:
            audio = File(filepath)
            if audio is not None and hasattr(audio, 'tags'):
                try:
                    audio.tags.add(TALB(encoding=3, text=album_name))
                    audio.tags.save()
                except TypeError:
                    # Some formats need a different approach
                    pass
    except Exception as e:
        print(f"  ERROR writing tags for {os.path.basename(filepath)}: {e}", file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser(description='Fix "[Unknown Album]" by setting album=artist')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing')
    parser.add_argument('--limit', type=int, default=0, help='Process only N files (0 = all)')
    args = parser.parse_args()

    if not os.path.isdir(SINGLETONS_DIR):
        print(f"ERROR: Singletons dir not found: {SINGLETONS_DIR}")
        sys.exit(1)

    total = 0
    skipped_has_album = 0
    fixed = 0
    errors = 0

    files = sorted(os.listdir(SINGLETONS_DIR))
    if args.limit > 0:
        files = files[:args.limit]

    for fname in files:
        total += 1
        filepath = os.path.join(SINGLETONS_DIR, fname)
        if not os.path.isfile(filepath):
            continue

        # Check if album tag already exists
        try:
            audio = File(filepath)
        except Exception:
            errors += 1
            continue

        if audio is None:
            errors += 1
            continue

        existing_album = get_album(audio)
        if existing_album:
            skipped_has_album += 1
            continue

        # Get artist for new album value
        artist = get_artist(audio)
        if not artist:
            artist = parse_artist_from_filename(fname)

        if args.dry_run:
            if total <= 10:
                print(f"  WOULD SET: album='{artist}' for {fname}")
            fixed += 1
            continue

        if set_album_tag(filepath, artist):
            if fixed < 10:
                print(f"  SET: album='{artist}' for {fname}")
            fixed += 1
        else:
            errors += 1

    print(f"\n{'DRY RUN -- ' if args.dry_run else ''}Summary:")
    print(f"  Total files processed: {total}")
    print(f"  Already had album tag (skipped): {skipped_has_album}")
    print(f"  Fixed (album tag added): {fixed}")
    print(f"  Errors: {errors}")

    if args.dry_run:
        print("\n  Run without --dry-run to apply changes.")


if __name__ == '__main__':
    main()
