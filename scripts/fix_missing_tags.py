#!/usr/bin/env python3
"""
Fix missing ID3 tags by parsing Artist - Title from filename.
Only touches files that are MISSING the tag — skips files that already have it.
"""

import os, sys
from mutagen.id3 import ID3, TPE1, TIT2, TALB

SINGLETONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "MusicRaw", "Library", "Singletons")

def main():
    fixed_artist = 0
    fixed_title = 0
    fixed_album = 0
    checked = 0

    for fname in sorted(os.listdir(SINGLETONS)):
        if not fname.endswith(('.mp3', '.flac')):
            continue
        fp = os.path.join(SINGLETONS, fname)
        checked += 1

        try:
            audio = ID3(fp)
        except Exception:
            continue

        # Parse from filename
        name = os.path.splitext(fname)[0]
        if ' - ' in name:
            f_artist, f_title = name.split(' - ', 1)
        else:
            f_artist, f_title = name, name

        artist_frames = audio.getall('TPE1')
        if not artist_frames or not str(artist_frames[0]).strip():
            audio.add(TPE1(encoding=3, text=f_artist.strip()))
            fixed_artist += 1
            print(f"  +ARTIST: {fname} -> '{f_artist.strip()}'")

        title_frames = audio.getall('TIT2')
        if not title_frames or not str(title_frames[0]).strip():
            audio.add(TIT2(encoding=3, text=f_title.strip()))
            fixed_title += 1
            print(f"  +TITLE: {fname} -> '{f_title.strip()}'")

        album_frames = audio.getall('TALB')
        if not album_frames or not str(album_frames[0]).strip():
            audio.add(TALB(encoding=3, text=f_artist.strip()))
            fixed_album += 1

        audio.save()

    print(f"\nChecked: {checked} files")
    print(f"Artist fixed: {fixed_artist}")
    print(f"Title fixed: {fixed_title}")
    print(f"Album fixed: {fixed_album}")

if __name__ == '__main__':
    main()
