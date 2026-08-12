#!/usr/bin/env python3
"""
Stage 5: Search and download missing tracks via slskd (Soulseek).
Uses slskd REST API through SSH tunnel (localhost:5030).

Usage: python3 scripts/slskd_download.py [--dry-run] [--limit N]
"""
import json, time, uuid, re, sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

REPO = Path(__file__).resolve().parent.parent
MISSING_FILE = REPO / "MusicRaw" / "missing_tracks.txt"
SLSKD_URL = "http://localhost:5030"
LOG_FILE = REPO / "MusicRaw" / "slskd_download_log.txt"
STATE_FILE = REPO / "MusicRaw" / "slskd_state.json"

SEARCH_TIMEOUT = 15  # seconds to wait for search results


def parse_missing_track(line: str) -> tuple[str, str, str] | None:
    """Parse '[Source] Artist — Title' into (source, artist, title)."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    m = re.match(r"\[(.+?)\]\s+(.+)", line)
    if not m:
        return None
    source = m.group(1)
    rest = m.group(2)
    # Clean up common artifacts in artist names
    rest = rest.lstrip(".,;:!?… \t")  # remove leading junk like "...Sandra"
    # Try em-dash first, then regular dash
    for sep in [" — ", " – ", " - "]:
        if sep in rest:
            artist, title = rest.split(sep, 1)
            return (source, artist.strip(), title.strip())
    return (source, rest.strip(), "")


def slskd_search(artist: str, title: str) -> list[dict]:
    """Search Soulseek via slskd API. Returns list of file results."""
    search_id = str(uuid.uuid4())
    query = f"{artist} {title}"

    # Start search
    req = Request(
        f"{SLSKD_URL}/api/v0/searches",
        data=json.dumps({"id": search_id, "query": query, "searchText": query}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urlopen(req, timeout=5)
    except HTTPError as e:
        print(f"  Search error: {e.code}")
        return []

    # Poll for completion
    deadline = time.time() + SEARCH_TIMEOUT
    complete_states = {
        "Completed, Succeeded",
        "Completed, ResponseLimitReached",
        "Completed, NoResults",
        "Errored",
        "Cancelled",
    }

    while time.time() < deadline:
        time.sleep(1.5)
        try:
            resp = urlopen(f"{SLSKD_URL}/api/v0/searches/{search_id}", timeout=5)
            data = json.loads(resp.read())
        except (HTTPError, Exception):
            continue

        state = data.get("state", "")
        if state in ("Completed, NoResults", "Errored", "Cancelled"):
            return []
        if state in complete_states and data.get("fileCount", 0) > 0:
            break

    # Fetch files from responses endpoint
    try:
        resp = urlopen(f"{SLSKD_URL}/api/v0/searches/{search_id}/responses", timeout=10)
        responses = json.loads(resp.read())
    except (HTTPError, Exception):
        return []

    all_files = []
    for r in responses:
        for f in r.get("files", []):
            f["_username"] = r.get("username", "?")
            all_files.append(f)

    return all_files


def pick_best_file(files: list[dict]) -> dict | None:
    """Pick the best quality file from search results."""
    if not files:
        return None

    scored = []
    for f in files:
        filename = f.get("filename", "")
        size = f.get("size", 0)
        bitrate = f.get("bitRate", 0) or 0
        # Decode bitrate from attributes if needed
        attrs = f.get("attribute", [])
        for a in attrs:
            if a.get("type") == "BitRate" and a.get("value", 0) > bitrate:
                bitrate = a["value"]

        # Score: prefer FLAC, then high bitrate MP3
        is_flac = filename.lower().endswith(".flac")
        score = bitrate
        if is_flac:
            score = 999  # Always prefer FLAC

        # Penalize very small files (< 2 MB — likely not a full song)
        if size < 2_000_000:
            score -= 500

        scored.append((score, f))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else None


def download_file(file_info: dict) -> bool:
    """Download a single file via slskd API. Returns True on success."""
    username = file_info.get("_username", "")
    if not username:
        print(f"  No username in file info, cannot download")
        return False

    payload = [
        {
            "filename": file_info["filename"],
            "size": file_info["size"],
        }
    ]
    url = f"{SLSKD_URL}/api/v0/transfers/downloads/{username}"
    req = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urlopen(req, timeout=10)
        return True
    except HTTPError as e:
        print(f"  Download error: {e.code}")
        return False


def load_state() -> dict:
    """Load download state (already processed tracks)."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"downloaded": [], "not_found": [], "skipped": []}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def main():
    dry_run = "--dry-run" in sys.argv
    limit = None
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    lines = [l for l in MISSING_FILE.read_text(encoding="utf-8").splitlines() if l.startswith("[")]
    tracks = []
    for line in lines:
        parsed = parse_missing_track(line)
        if parsed:
            tracks.append(parsed)

    state = load_state()
    processed = set(state["downloaded"] + state["not_found"] + state["skipped"])

    # Filter: VK playlists first (higher priority), then Shazam, then Yandex, then YouTube
    def priority(source):
        if "VK:" in source:
            return 0
        if "Shazam" in source:
            return 1
        return 2

    tracks.sort(key=lambda t: (priority(t[0]), t[1]))

    pending = [(s, a, t) for s, a, t in tracks if f"{a} - {t}" not in processed]
    if limit:
        pending = pending[:limit]

    print(f"Missing tracks: {len(tracks)} total, {len(pending)} pending")
    if dry_run:
        print("DRY RUN — showing first 10 searches:")
        for source, artist, title in pending[:10]:
            print(f"  [{source}] {artist} — {title}")
        return

    print(f"{'='*60}")
    for i, (source, artist, title) in enumerate(pending):
        key = f"{artist} - {title}"
        print(f"\n[{i+1}/{len(pending)}] [{source}] {artist} — {title}")

        files = slskd_search(artist, title)
        if not files:
            print(f"  → NOT FOUND on Soulseek")
            state["not_found"].append(key)
            save_state(state)
            continue

        best = pick_best_file(files)
        if not best:
            print(f"  → No suitable file found")
            state["not_found"].append(key)
            save_state(state)
            continue

        fname = best.get("filename", "?")
        bitrate = best.get("bitRate", 0)
        size_mb = best.get("size", 0) / 1_000_000
        print(f"  → {fname} ({bitrate}kbps, {size_mb:.1f}MB)")

        if download_file(best):
            print(f"  ✓ DOWNLOADED → /music-inbox/")
            state["downloaded"].append(key)
        else:
            state["skipped"].append(key)
        save_state(state)

        # Rate limit: don't hammer Soulseek
        time.sleep(2)

    print(f"\n{'='*60}")
    print(f"Done. Downloaded: {len(state['downloaded'])}, "
          f"Not found: {len(state['not_found'])}, "
          f"Skipped: {len(state['skipped'])}")
    print(f"Log: {LOG_FILE}")


if __name__ == "__main__":
    main()
