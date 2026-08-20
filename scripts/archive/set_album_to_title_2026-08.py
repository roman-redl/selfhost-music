#!/usr/bin/env python3
"""set_album_to_title_2026-08.py — one-off migration: Album tag = Title for every track.

Decision 2026-08-21 (see docs/handover-2026-08-20.md): the library has no real albums —
the Album field held the artist name for almost all multi-track albums. Navidrome keeps
ONE artwork per album and Psysonic/Substreamer show the album artwork for all album
tracks, so every track gets its own album (album = title) and thus its own cover.

Only the Album tag is touched; files are not renamed and playlists are unaffected.
Every change is appended to a TSV log (status, path, old_album, new_album) so the run
can be rolled back exactly:

    python3 set_album_to_title_2026-08.py --rollback LOG.tsv

Usage:
    python3 set_album_to_title_2026-08.py <dir> [--dry-run] [--limit N] [--log PATH]
"""

import argparse
import csv
import os
import sys
import unicodedata

from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError, TALB

AUDIO_EXTS = (".mp3", ".flac")


def nfc(s):
    return unicodedata.normalize("NFC", str(s).strip())


def open_tags(filepath):
    """Open audio and read (title, album). Returns (audio, is_mp3, title, album, error)."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".mp3":
        try:
            audio = ID3(filepath)
        except ID3NoHeaderError:
            return None, True, "", "", "no ID3 header"
        except Exception as e:
            return None, True, "", "", f"open error: {e}"
        title = nfc(audio.getall("TIT2")[0]) if audio.getall("TIT2") else ""
        album = nfc(audio.getall("TALB")[0]) if audio.getall("TALB") else ""
        return audio, True, title, album, None
    if ext == ".flac":
        try:
            audio = FLAC(filepath)
        except Exception as e:
            return None, False, "", "", f"open error: {e}"
        title = nfc(audio.get("title", [""])[0])
        album = nfc(audio.get("album", [""])[0])
        return audio, False, title, album, None
    return None, False, "", "", "unsupported format"


def set_album(audio, value, is_mp3):
    if is_mp3:
        audio.add(TALB(encoding=3, text=value))
    else:
        audio["album"] = value


def collect_files(root):
    files = []
    for dirpath, _dirs, fnames in os.walk(root):
        for f in sorted(fnames):
            if f.lower().endswith(AUDIO_EXTS):
                files.append(os.path.join(dirpath, f))
    return files


def migrate(root, dry_run, limit, logfile):
    files = collect_files(root)
    if limit > 0:
        files = files[:limit]
    writer = None
    logf = None
    if logfile and not dry_run:
        logf = open(logfile, "a", encoding="utf-8")
        writer = csv.writer(logf, delimiter="\t", lineterminator="\n")
        if logf.tell() == 0:
            writer.writerow(["status", "path", "old_album", "new_album"])
    stats = {"checked": 0, "changed": 0, "unchanged": 0, "errors": 0}
    try:
        for fp in files:
            audio, is_mp3, title, album, err = open_tags(fp)
            if audio is None or err:
                stats["errors"] += 1
                print(f"  ERROR {fp}: {err}", file=sys.stderr)
                if writer:
                    writer.writerow(["error", fp, album, ""])
                continue
            stats["checked"] += 1
            if not title:
                stats["errors"] += 1
                print(f"  ERROR {fp}: no title tag", file=sys.stderr)
                if writer:
                    writer.writerow(["no_title", fp, album, ""])
                continue
            if album == title:
                stats["unchanged"] += 1
                continue
            if dry_run:
                stats["changed"] += 1
                print(f"  would change: {os.path.basename(fp)}: '{album}' -> '{title}'")
                continue
            set_album(audio, title, is_mp3)
            try:
                audio.save(fp)
            except Exception as e:
                stats["errors"] += 1
                print(f"  ERROR saving {fp}: {e}", file=sys.stderr)
                if writer:
                    writer.writerow(["save_error", fp, album, title])
                continue
            stats["changed"] += 1
            if writer:
                writer.writerow(["changed", fp, album, title])
    finally:
        if logf:
            logf.close()
    return stats


def rollback(logfile):
    """Restore album tags from a migration log (rows with status=changed)."""
    with open(logfile, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    changed = [r for r in rows if r.get("status") == "changed"]
    ok = skipped = errs = 0
    for r in changed:
        fp = r["path"]
        old = r["old_album"]
        audio, is_mp3, _title, album, err = open_tags(fp)
        if audio is None or err:
            print(f"  ERROR {fp}: {err}", file=sys.stderr)
            errs += 1
            continue
        if album != r["new_album"]:
            print(f"  SKIP {fp}: current album '{album}' != logged '{r['new_album']}' (changed after migration)")
            skipped += 1
            continue
        set_album(audio, old, is_mp3)
        try:
            audio.save(fp)
        except Exception as e:
            print(f"  ERROR saving {fp}: {e}", file=sys.stderr)
            errs += 1
            continue
        ok += 1
    print(f"Rollback done: restored {ok}, skipped {skipped}, errors {errs} (of {len(changed)} logged changes)")


def main():
    parser = argparse.ArgumentParser(
        description="Set Album tag = Title for every MP3/FLAC (one-off migration, 2026-08)"
    )
    parser.add_argument("path", nargs="?", help="Directory with music files")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--limit", type=int, default=0, help="Process only N files (0 = all)")
    parser.add_argument("--log", default="", help="TSV log path (required for real runs, used by --rollback)")
    parser.add_argument("--rollback", metavar="LOG", help="Restore album tags from a migration log")
    args = parser.parse_args()

    if args.rollback:
        rollback(args.rollback)
        sys.exit(0)

    if not args.path or not os.path.isdir(args.path):
        print("ERROR: path required (directory)", file=sys.stderr)
        sys.exit(1)

    if not args.dry_run and not args.log:
        print("ERROR: real run requires --log (needed for rollback)", file=sys.stderr)
        sys.exit(1)

    stats = migrate(args.path, args.dry_run, args.limit, args.log)
    print(f"\n{'DRY RUN -- ' if args.dry_run else ''}Summary:")
    print(f"  Files checked: {stats['checked']}")
    print(f"  Album changed: {stats['changed']}")
    print(f"  Already album==title: {stats['unchanged']}")
    print(f"  Errors/skipped: {stats['errors']}")


if __name__ == "__main__":
    main()
