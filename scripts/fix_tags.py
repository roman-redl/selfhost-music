#!/usr/bin/env python3
"""
fix_tags.py — Ensure Artist/Title/Album tags are present and valid.

Implements the project's ID3 rules (docs/music-migration-plan.md):
  - Artist: from filename; forbidden: empty, "Неизвестен", "Unknown Artist"
  - Title:  from filename; forbidden: empty, "Без названия", artist name in title field
  - Album:  = artist when unknown; forbidden: empty, "[Unknown Album]", "Unknown Album"

Existing valid values are never overwritten. Only missing/invalid tags are fixed.
Supports MP3 (ID3v2) and FLAC (Vorbis comments); other formats are skipped.

Usage:
  python3 fix_tags.py <file-or-dir> [--dry-run] [--limit N]

Called automatically by watch-inbox.sh for every new MP3/FLAC in the inbox.
"""

import argparse
import os
import sys

from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError, TPE1, TIT2, TALB

FORBIDDEN_ARTIST = ("неизвестен", "unknown artist", "unknown")
FORBIDDEN_TITLE = ("без названия", "untitled")
FORBIDDEN_ALBUM = ("[unknown album]", "unknown album")

AUDIO_EXTS = (".mp3", ".flac")


def parse_filename(filepath):
    """Parse 'Artist - Title.ext' from filename."""
    name = os.path.splitext(os.path.basename(filepath))[0]
    if " - " in name:
        artist, title = name.split(" - ", 1)
        return artist.strip(), title.strip()
    return name.strip(), name.strip()


def open_audio(filepath):
    """Open audio file for tag editing. Returns (audio, is_mp3) or None if unsupported."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".mp3":
        try:
            return ID3(filepath), True
        except ID3NoHeaderError:
            return ID3(), True
        except Exception:
            return None, False
    if ext == ".flac":
        try:
            return FLAC(filepath), False
        except Exception:
            return None, False
    return None, False


def get_tag(audio, kind, is_mp3):
    """Read artist/title/album tag value ("" if missing)."""
    if is_mp3:
        frame = {"artist": "TPE1", "title": "TIT2", "album": "TALB"}[kind]
        vals = audio.getall(frame)
        return str(vals[0]).strip() if vals else ""
    vals = audio.get(kind)
    if vals:
        return str(vals[0]).strip()
    return ""


def set_tag(audio, kind, value, is_mp3):
    """Write artist/title/album tag value (overwrites the frame/key)."""
    if is_mp3:
        frame = {
            "artist": TPE1(encoding=3, text=value),
            "title": TIT2(encoding=3, text=value),
            "album": TALB(encoding=3, text=value),
        }[kind]
        audio.add(frame)
    else:
        audio[kind] = value


def is_valid(kind, value, filename_artist):
    """Check tag value against the project's ID3 rules."""
    if not value:
        return False
    v = value.strip().lower()
    if kind == "artist":
        return v not in FORBIDDEN_ARTIST
    if kind == "title":
        if v in FORBIDDEN_TITLE:
            return False
        if value.strip() == filename_artist.strip():
            return False  # artist name in the title field
        return True
    return v not in FORBIDDEN_ALBUM


def process_file(filepath, dry_run=False):
    """Fix tags for one file. Returns list of (kind, old, new) changes, or None on error."""
    audio, is_mp3 = open_audio(filepath)
    if audio is None:
        return None

    f_artist, f_title = parse_filename(filepath)
    changes = []

    artist = get_tag(audio, "artist", is_mp3)
    if not is_valid("artist", artist, f_artist):
        changes.append(("artist", artist, f_artist))
        if not dry_run:
            set_tag(audio, "artist", f_artist, is_mp3)

    title = get_tag(audio, "title", is_mp3)
    if not is_valid("title", title, f_artist):
        changes.append(("title", title, f_title))
        if not dry_run:
            set_tag(audio, "title", f_title, is_mp3)

    album = get_tag(audio, "album", is_mp3)
    if not is_valid("album", album, f_artist):
        changes.append(("album", album, f_artist))
        if not dry_run:
            set_tag(audio, "album", f_artist, is_mp3)

    if changes and not dry_run:
        try:
            audio.save(filepath)
        except Exception as e:
            print(f"  ERROR saving {os.path.basename(filepath)}: {e}", file=sys.stderr)
            return None

    return changes


def main():
    parser = argparse.ArgumentParser(
        description="Fix missing/invalid Artist/Title/Album tags (MP3 + FLAC)"
    )
    parser.add_argument("path", help="Audio file or directory")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--limit", type=int, default=0, help="Process only N files (0 = all)")
    args = parser.parse_args()

    if not os.path.exists(args.path):
        print(f"ERROR: {args.path} not found", file=sys.stderr)
        sys.exit(1)

    if os.path.isfile(args.path):
        files = [args.path]
    else:
        files = []
        for root, _dirs, fnames in os.walk(args.path):
            for f in sorted(fnames):
                if f.lower().endswith(AUDIO_EXTS):
                    files.append(os.path.join(root, f))
        if not files:
            print(f"No MP3/FLAC files found in {args.path}")
            sys.exit(0)

    if args.limit > 0:
        files = files[:args.limit]

    checked = 0
    fixed = 0
    for fp in files:
        changes = process_file(fp, dry_run=args.dry_run)
        if changes is None:
            continue  # unsupported format or error
        checked += 1
        if changes:
            fixed += 1
            for kind, old, new in changes:
                print(f"  +{kind.upper()}: {os.path.basename(fp)}: '{old}' -> '{new}'")

    print(f"\n{'DRY RUN -- ' if args.dry_run else ''}Summary:")
    print(f"  Files checked: {checked}")
    print(f"  Files fixed: {fixed}")


if __name__ == "__main__":
    main()
