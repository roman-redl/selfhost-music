#!/usr/bin/env python3
"""Set Navidrome artist images from the artists' own track covers.

Every artist gets the embedded cover of their alphabetically-first album's
first track, uploaded through the native API (POST /api/artist/{id}/image).
An uploaded image overrides the external lookups (Deezer / last.fm), so all
clients show the artist's own artwork instead of a possibly wrong internet
match.

Run on the machine that can reach the Navidrome port (the VPS itself or over
SSH); credentials come from .env (NAVIDROME_USER / NAVIDROME_PASSWORD,
optionally NAVIDROME_URL, default http://127.0.0.1:4533).

Usage:
    python3 scripts/set_artist_images.py --dry-run          # plan only
    python3 scripts/set_artist_images.py --artist "ABBA"    # selected artists
    python3 scripts/set_artist_images.py --all              # every artist
"""
import argparse
import hashlib
import json
import secrets
import sys
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

    def upload_artist_image(self, artist_id, image: bytes):
        if self.bearer is None:
            self.login()
        boundary = uuid_hex()
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
            f"filename=\"artist.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n"
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
                    help="artist name (repeatable); default: all artists")
    ap.add_argument("--all", action="store_true", help="process every artist")
    ap.add_argument("--dry-run", action="store_true",
                    help="show the chosen source track, upload nothing")
    ap.add_argument("--sleep", type=float, default=0.1,
                    help="pause between uploads, seconds (default 0.1)")
    args = ap.parse_args()

    env = load_env()
    user = env.get("NAVIDROME_USER")
    password = env.get("NAVIDROME_PASSWORD")
    if not user or not password:
        sys.exit("NAVIDROME_USER / NAVIDROME_PASSWORD not found in .env")
    client = Client(env.get("NAVIDROME_URL", "http://127.0.0.1:4533"), user, password)

    wanted = {unicodedata.normalize("NFC", a).casefold() for a in args.artist}
    if wanted and not args.all:
        pass  # selected artists only
    elif not args.all and not wanted:
        sys.exit("nothing to do: pass --artist NAME and/or --all")

    index = client.subsonic("getArtists")["artists"]["index"]
    artists = [a for letter in index for a in letter.get("artist", [])]
    if wanted:
        artists = [a for a in artists
                   if unicodedata.normalize("NFC", a["name"]).casefold() in wanted]
        missing = wanted - {unicodedata.normalize("NFC", a["name"]).casefold()
                            for a in artists}
        if missing:
            sys.exit(f"artists not found on the server: {sorted(missing)}")

    print(f"artists to process: {len(artists)}")
    done = failed = 0
    for artist in artists:
        picked = pick_track_cover(client, artist["id"])
        if picked is None:
            print(f"SKIP {artist['name']!r}: no track cover found")
            failed += 1
            continue
        album, title, data = picked
        if args.dry_run:
            print(f"would set {artist['name']!r} <- [{album}] {title} "
                  f"({len(data)} bytes)")
            continue
        try:
            client.upload_artist_image(artist["id"], data)
            done += 1
            print(f"OK {artist['name']!r} <- [{album}] {title}")
        except Exception as exc:  # noqa: BLE001 — one artist must not kill the run
            failed += 1
            print(f"FAIL {artist['name']!r}: {exc}")
        time.sleep(args.sleep)
    if not args.dry_run:
        print(f"done: {done}, failed/skipped: {failed}")


if __name__ == "__main__":
    main()
