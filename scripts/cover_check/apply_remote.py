#!/usr/bin/env python3
"""
Embeds an image into the mp3/flac file(s) with the matching stem under /music on the VPS.
Run on the VPS: python3 apply_remote.py <image> <base_name>
Prints EMBEDDED <n> / NOT_FOUND / FAIL ...
"""
import os, sys, unicodedata

def norm(s):
    return unicodedata.normalize("NFC", s)

def main():
    img, base = sys.argv[1], sys.argv[2]
    root = "/opt/selfhost-music/music"  # covers both subfolders and files at the /music/ root
    exts = (".mp3", ".flac")
    found = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith(exts) and norm(os.path.splitext(f)[0]) == norm(base):
                found.append(os.path.join(dirpath, f))
    if not found:
        print("NOT_FOUND")
        sys.exit(2)

    with open(img, "rb") as fh:
        data = fh.read()
    mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"

    ok, fail = [], []
    for fp in found:
        try:
            ext = os.path.splitext(fp)[1].lower()
            if ext == ".flac":
                from mutagen.flac import FLAC, Picture
                audio = FLAC(fp)
                audio.clear_pictures()
                pic = Picture()
                pic.type = 3  # front cover
                pic.mime = mime
                pic.desc = "Cover"
                pic.data = data
                audio.add_picture(pic)
                audio.save()
            else:
                from mutagen.id3 import ID3, APIC
                audio = ID3(fp)
                for apic in audio.getall("APIC"):
                    del audio[apic.HashKey]
                audio.add(APIC(encoding=3, mime=mime, type=3,
                               desc="Cover", data=data))
                audio.save()
            ok.append(fp)
        except Exception as e:
            fail.append(f"{fp}: {e}")
    print("EMBEDDED", len(ok))
    for fp in ok:
        print("OK", fp)
    for x in fail:
        print("FAIL", x)


if __name__ == "__main__":
    main()
