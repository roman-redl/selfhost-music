#!/usr/bin/env python3
"""Set Navidrome artist images: from a local picture file or from the artist's
own track cover.

The default source for artist images is the server's external lookup (Deezer),
which Psysonic and other clients display — usually good, occasionally the
wrong artist. Use this script for point fixes:

    # a specific picture (JPEG/PNG as-is; webp/heic/avif auto-converted):
    python3 scripts/set_artist_images.py --artist "ABBA" --file pic.jpg
    # from the artist's own track cover (their alphabetically-first album):
    python3 scripts/set_artist_images.py --artist "Boston" --from-track

Runs from the repo root on the Mac (uploads over https://$DOMAIN) or on the
VPS (localhost). Credentials come from .env (NAVIDROME_USER /
NAVIDROME_PASSWORD; NAVIDROME_URL overrides, DOMAIN is used otherwise).

Notes: the server accepts JPEG/PNG only — anything else is converted with
ffmpeg or sips (macOS). Psysonic's own "set artist image" button hits the
same endpoint but does not convert, so a webp/heic upload fails there with
"Uploaded file is not a valid image".
"""
import argparse
import hashlib
import json
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def load_env():
    env = {}
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


class Client:
    def __init__(self, base, user, password):
        self.base = base.rstrip("/")
        self.user = user
        self.password = password
        self.bearer = None

    # --- Subsonic API (documented, read-only here) ---
    def subsonic(self, endpoint, **params):
        salt = secrets.token_hex(8)
        query = urllib.parse.urlencode({
            "u": self.user,
            "t": hashlib.md5((self.password + salt).encode()).hexdigest(),
            "s": salt, "v": "1.16.1", "c": "artist-img", "f": "json", **params})
        resp = json.load(urllib.request.urlopen(
            f"{self.base}/rest/{endpoint}?{query}"))["subsonic-response"]
        if resp["status"] != "ok":
            raise RuntimeError(f"{endpoint}: {resp}")
        return resp

    def cover_bytes(self, cover_id):
        salt = secrets.token_hex(8)
        query = urllib.parse.urlencode({
            "u": self.user,
            "t": hashlib.md5((self.password + salt).encode()).hexdigest(),
            "s": salt, "v": "1.16.1", "c": "artist-img",
            "id": cover_id})
        return urllib.request.urlopen(
            f"{self.base}/rest/getCoverArt?{query}").read()

    # --- native API (upload) ---
    def login(self):
        resp = json.load(urllib.request.urlopen(urllib.request.Request(
            f"{self.base}/auth/login",
            data=json.dumps({"username": self.user,
                             "password": self.password}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")))
        self.bearer = resp["token"]

    def upload_artist_image(self, artist_id, image: bytes, mime="image/jpeg"):
        if self.bearer is None:
            self.login()
        boundary = uuid_hex()
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
            f"filename=\"artist.{mime.split('/')[-1]}\"\r\nContent-Type: {mime}\r\n\r\n"
        ).encode() + image + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            f"{self.base}/api/artist/{artist_id}/image", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                     "X-ND-Authorization": f"Bearer {self.bearer}"}, method="POST")
        result = json.load(urllib.request.urlopen(req))
        if result.get("status") != "ok":
            raise RuntimeError(f"upload {artist_id}: {result}")


def uuid_hex():
    return secrets.token_hex(16)


def read_image(path):
    """Read an image file, converting to JPEG when the server cannot take it.

    Navidrome accepts JPEG/PNG; webp/heic/avif and friends are converted via
    ffmpeg (Linux/VPS) or sips (macOS).
    """
    data = Path(path).expanduser().read_bytes()
    if data[:3] == b"\xff\xd8\xff":
        return data, "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return data, "image/png"
    out = Path(tempfile.mkstemp(suffix=".jpg")[1])
    try:
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
                            "-frames:v", "1", str(out)], check=True)
        elif shutil.which("sips"):
            subprocess.run(["sips", "-s", "format", "jpeg", str(path),
                            "--out", str(out)], check=True, capture_output=True)
        else:
            sys.exit(f"{path}: not a JPEG/PNG and no ffmpeg/sips found to convert")
        return out.read_bytes(), "image/jpeg"
    finally:
        out.unlink(missing_ok=True)


def pick_track_cover(client, artist_id):
    """The cover of the artist's alphabetically-first album's first track."""
    albums = client.subsonic("getArtist", id=artist_id)["artist"].get("album", [])
    for album in sorted(albums, key=lambda a: unicodedata.normalize("NFC", a["name"]).casefold()):
        songs = client.subsonic("getAlbum", id=album["id"])["album"].get("song", [])
        for song in songs:
            try:
                data = client.cover_bytes(song["id"])
                if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n":
                    return album["name"], song["title"], data
            except urllib.error.HTTPError:
                continue  # no art on this song — try the next
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--artist", action="append", default=[],
                    help="artist name (repeatable)")
    source = ap.add_mutually_exclusive_group()
    source.add_argument("--file", metavar="PATH",
                        help="set the image from this local file (one artist)")
    source.add_argument("--from-track", action="store_true",
                        help="set the image from the artist's own track cover")
    source.add_argument("--all", action="store_true",
                        help="with --from-track: process every artist")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be done, upload nothing")
    ap.add_argument("--sleep", type=float, default=0.1,
                    help="pause between uploads, seconds (default 0.1)")
    args = ap.parse_args()

    env = load_env()
    user = env.get("NAVIDROME_USER")
    password = env.get("NAVIDROME_PASSWORD")
    if not user or not password:
        sys.exit("NAVIDROME_USER / NAVIDROME_PASSWORD not found in .env")
    base = (env.get("NAVIDROME_URL")
            or (f"https://{env['DOMAIN']}" if env.get("DOMAIN") else None)
            or "http://127.0.0.1:4533")
    client = Client(base, user, password)

    wanted = {unicodedata.normalize("NFC", a).casefold() for a in args.artist}
    if args.file and not wanted:
        sys.exit("--file needs exactly one --artist")
    if not args.file and not args.from_track and not args.all:
        sys.exit("pick a source: --file PATH or --from-track (--artist NAME / --all)")

    index = client.subsonic("getArtists")["artists"]["index"]
    artists = [a for letter in index for a in letter.get("artist", [])]
    if wanted:
        artists = [a for a in artists
                   if unicodedata.normalize("NFC", a["name"]).casefold() in wanted]
        missing = wanted - {unicodedata.normalize("NFC", a["name"]).casefold()
                            for a in artists}
        if missing:
            sys.exit(f"artists not found on the server: {sorted(missing)}")

    print(f"artists to process: {len(artists)} ({base})")
    done = failed = 0
    for artist in artists:
        name = artist["name"]
        if args.file:
            try:
                data, mime = read_image(args.file)
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {name!r}: {exc}"); failed += 1; continue
            if args.dry_run:
                print(f"would set {name!r} <- {args.file} "
                      f"({len(data)} bytes, {mime})")
                continue
            try:
                client.upload_artist_image(artist["id"], data, mime)
                done += 1
                print(f"OK {name!r} <- {args.file}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name!r}: {exc}")
            time.sleep(args.sleep)
            continue

        picked = pick_track_cover(client, artist["id"])
        if picked is None:
            print(f"SKIP {name!r}: no track cover found")
            failed += 1
            continue
        album, title, data = picked
        if args.dry_run:
            print(f"would set {name!r} <- [{album}] {title} ({len(data)} bytes)")
            continue
        try:
            client.upload_artist_image(artist["id"], data)
            done += 1
            print(f"OK {name!r} <- [{album}] {title}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name!r}: {exc}")
        time.sleep(args.sleep)
    if not args.dry_run:
        print(f"done: {done}, failed/skipped: {failed}")


if __name__ == "__main__":
    main()
