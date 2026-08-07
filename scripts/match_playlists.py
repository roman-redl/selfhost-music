#!/usr/bin/env python3
"""
Stage 4: Fuzzy-match playlists against the normalized library and create .m3u files.

Inputs:
  - MusicRaw/Library/Singletons/          — 1010 MP3 files (artist - title.mp3)
  - MusicRaw/playlists/*.txt              — 41 VK playlists
  - MusicRaw/yandex/яндекс музыка.txt     — Yandex favorites
  - MusicRaw/youtube/ютуб топ.txt         — YouTube top
  - MusicRaw/shazam/shazam.txt            — Shazam history

Outputs:
  - MusicRaw/playlists_m3u/               — .m3u files for Navidrome
  - MusicRaw/missing_tracks.txt           — tracks not found in library (→ Stage 5)
  - MusicRaw/stage4_report.txt            — detailed matching report
"""

import os
import re
from pathlib import Path
from rapidfuzz import fuzz

# --- Config ---
REPO = Path(__file__).resolve().parent.parent
LIBRARY_DIR = REPO / "MusicRaw" / "Library" / "Singletons"
PLAYLISTS_DIR = REPO / "MusicRaw" / "playlists"
YANDEX_FILE = REPO / "MusicRaw" / "yandex" / "яндекс музыка.txt"
YOUTUBE_FILE = REPO / "MusicRaw" / "youtube" / "ютуб топ.txt"
SHAZAM_FILE = REPO / "MusicRaw" / "shazam" / "shazam.txt"
M3U_OUTPUT = REPO / "MusicRaw" / "playlists_m3u"
MISSING_OUTPUT = REPO / "MusicRaw" / "missing_tracks.txt"
REPORT_OUTPUT = REPO / "MusicRaw" / "stage4_report.txt"

# Matching thresholds
THRESHOLD_HIGH = 90    # confident match
THRESHOLD_LOW = 80     # uncertain — include but flag for review

# --- Helpers ---

def normalize(s: str) -> str:
    """Normalize a string for fuzzy comparison."""
    s = s.lower()
    # Normalize dashes: em-dash, en-dash, horizontal bar → ASCII hyphen
    s = s.replace("—", "-").replace("–", "-").replace("―", "-")
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # Remove trailing punctuation on whole string (e.g., "Boney M." → "Boney M")
    s = re.sub(r"[.,;:!?]+$", "", s)
    return s


def strip_track_number(line: str) -> str:
    """Remove leading track numbers like '16. ' or '2. ' or '05 '."""
    return re.sub(r"^\d+[\.\s]\s*", "", line).strip()


def parse_library(library_dir: Path) -> dict[str, tuple[str, str]]:
    """
    Parse library filenames into a lookup dict.

    Returns: {normalized_key: (display_name, filename)}
      normalized_key = "artist - title" (lowercase, normalized)
      display_name   = "Artist - Title" (from filename, without .mp3)
      filename       = "Artist - Title.mp3" (actual filename)
    """
    library = {}
    for f in sorted(library_dir.glob("*.mp3")):
        stem = f.stem  # filename without .mp3
        key = normalize(strip_track_number(stem))  # also strip track numbers from library keys
        library[key] = (stem, f.name)
    return library


def parse_playlist_line(line: str) -> tuple[str, str] | None:
    """
    Parse a single playlist line into (artist, title).

    Handles separators: " - " (ASCII), " — " (em-dash), " – " (en-dash).
    Returns None for empty/comment lines.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Try to split on common separators
    for sep in [" — ", " – ", " - ", "\t"]:
        if sep in line:
            parts = line.split(sep, 1)
            artist = strip_track_number(parts[0]).strip()
            title = parts[1].strip()
            if artist and title:
                return (artist, title)

    # No separator found — treat whole line as title, no artist
    return ("", line)


def match_track(artist: str, title: str, library: dict, threshold: int = THRESHOLD_LOW) -> tuple[str | None, str | None, int, str]:
    """
    Fuzzy-match a playlist track against the library.

    Returns: (matched_filename, matched_display_name, score, method)
      method: "exact", "token_sort", "partial", "none"
    """
    full_query = normalize(f"{artist} - {title}")

    # Stage 1: exact match (fast path)
    if full_query in library:
        display, fname = library[full_query]
        return (fname, display, 100, "exact")

    # Stage 2: token_sort_ratio — best for word-order differences
    best_score = 0
    best_key = None
    for lib_key in library:
        score = fuzz.token_sort_ratio(full_query, lib_key)
        if score > best_score:
            best_score = score
            best_key = lib_key

    if best_score >= threshold and best_key is not None:
        display, fname = library[best_key]
        return (fname, display, int(best_score), "token_sort")

    # Stage 3: partial_ratio for substring matches (lower precision)
    # Require token_sort_ratio ≥ 50 as a guard — prevents artist-only false matches
    # (e.g., "Fancy - Burnin' Out The Light" → "Fancy - Bolero" scores high on partial
    #  because "fancy - " is a substring, but token_sort catches the title mismatch)
    best_score = 0
    best_key = None
    for lib_key in library:
        score = fuzz.partial_ratio(full_query, lib_key)
        if score > best_score:
            # Secondary check: token_sort must also be reasonable
            ts_score = fuzz.token_sort_ratio(full_query, lib_key)
            if ts_score >= 50:
                best_score = score
                best_key = lib_key

    if best_score >= threshold and best_key is not None:
        display, fname = library[best_key]
        return (fname, display, int(best_score), "partial")

    return (None, None, 0, "none")


def build_m3u_content(matches: list[tuple[str, str, int, str, str, str]]) -> str:
    """
    Build .m3u file content from matched tracks.

    Each match: (filename, display_name, score, method, artist, title)

    Uses relative paths: Singletons/<filename>
    Navidrome resolves these relative to its music folder root.
    """
    lines = ["#EXTM3U"]
    for fname, display, score, method, artist, title in matches:
        display_text = f"{artist} - {title}" if artist else title
        lines.append(f"#EXTINF:0,{display_text}")
        lines.append(f"Singletons/{fname}")
    lines.append("")  # trailing newline
    return "\n".join(lines)


# --- Main ---

def main():
    print("=" * 60)
    print("Stage 4: Playlist → Library Fuzzy Matching")
    print("=" * 60)

    # 1. Parse library
    print(f"\n[1/4] Parsing library: {LIBRARY_DIR}")
    library = parse_library(LIBRARY_DIR)
    print(f"  → {len(library)} tracks indexed")

    # 2. Collect all playlist sources
    sources: list[tuple[str, Path]] = []

    # VK playlists
    vk_files = sorted(PLAYLISTS_DIR.glob("*.txt"))
    for f in vk_files:
        sources.append((f"VK: {f.stem}", f))

    # Yandex
    if YANDEX_FILE.exists():
        sources.append(("Яндекс Музыка", YANDEX_FILE))

    # YouTube
    if YOUTUBE_FILE.exists():
        sources.append(("YouTube Топ", YOUTUBE_FILE))

    # Shazam
    if SHAZAM_FILE.exists():
        sources.append(("Shazam", SHAZAM_FILE))

    print(f"\n[2/4] Playlist sources: {len(sources)}")
    for name, path in sources:
        line_count = len([l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()])
        print(f"  • {name}: {line_count} tracks ({path.name})")

    # 3. Match each source
    print(f"\n[3/4] Fuzzy-matching (threshold: {THRESHOLD_LOW})...")

    M3U_OUTPUT.mkdir(parents=True, exist_ok=True)

    all_missing: list[str] = []          # tracks for Stage 5 download
    all_uncertain: list[str] = []        # matches < THRESHOLD_HIGH
    stats = {"total": 0, "matched": 0, "missing": 0, "uncertain": 0}

    for source_name, source_path in sources:
        lines = source_path.read_text(encoding="utf-8").splitlines()

        matches = []
        missing = []

        for line in lines:
            parsed = parse_playlist_line(line)
            if parsed is None:
                continue
            artist, title = parsed
            stats["total"] += 1

            fname, display, score, method = match_track(artist, title, library)

            if fname:
                matches.append((fname, display, score, method, artist, title))
                stats["matched"] += 1
                if score < THRESHOLD_HIGH:
                    stats["uncertain"] += 1
                    all_uncertain.append(
                        f"[{source_name}] score={score} ({method}): \"{artist} - {title}\"\n"
                        f"  → library: \"{display}\""
                    )
            else:
                missing.append((artist, title, line.strip()))
                stats["missing"] += 1
                all_missing.append(f"[{source_name}] {artist} - {title}")

        # Write .m3u
        m3u_name = source_name.replace(": ", "_").replace(" ", "_") + ".m3u"
        m3u_path = M3U_OUTPUT / m3u_name
        m3u_content = build_m3u_content(matches)
        m3u_path.write_text(m3u_content, encoding="utf-8")

        matched_pct = len(matches) / (len(matches) + len(missing)) * 100 if (matches or missing) else 0
        print(f"  {source_name}: {len(matches)} matched ({matched_pct:.0f}%), {len(missing)} missing → {m3u_name}")

    # 4. Write reports
    print(f"\n[4/4] Writing reports...")

    # Missing tracks
    with open(MISSING_OUTPUT, "w", encoding="utf-8") as f:
        f.write("# Missing Tracks — for Stage 5 download (slskd)\n")
        f.write(f"# Total: {len(all_missing)} tracks across all sources\n\n")
        for m in all_missing:
            f.write(m + "\n")
    print(f"  → {MISSING_OUTPUT} ({len(all_missing)} tracks)")

    # Detailed report
    with open(REPORT_OUTPUT, "w", encoding="utf-8") as f:
        f.write("# Stage 4 — Matching Report\n\n")
        f.write(f"## Summary\n\n")
        f.write(f"- Library: {len(library)} tracks\n")
        f.write(f"- Playlist tracks total: {stats['total']}\n")
        f.write(f"- Matched: {stats['matched']} ({stats['matched']/max(stats['total'],1)*100:.1f}%)\n")
        f.write(f"- Missing: {stats['missing']} ({stats['missing']/max(stats['total'],1)*100:.1f}%)\n")
        f.write(f"- Uncertain (score < {THRESHOLD_HIGH}): {stats['uncertain']}\n")
        f.write(f"\n## Uncertain Matches (need manual review)\n\n")
        if all_uncertain:
            for u in all_uncertain:
                f.write(u + "\n\n")
        else:
            f.write("(none — all matches are confident)\n")
        f.write(f"\n## Missing Tracks\n\n")
        if all_missing:
            for m in all_missing:
                f.write(f"- {m}\n")
        else:
            f.write("(none — all tracks matched!)\n")
    print(f"  → {REPORT_OUTPUT}")

    # Final summary
    print(f"\n{'=' * 60}")
    print(f"RESULTS")
    print(f"{'=' * 60}")
    print(f"  Total playlist tracks:  {stats['total']}")
    print(f"  Matched:               {stats['matched']} ({stats['matched']/max(stats['total'],1)*100:.1f}%)")
    print(f"  Missing (→ Stage 5):   {stats['missing']}")
    print(f"  Uncertain (review):    {stats['uncertain']}")
    print(f"  .m3u files created:    {len(list(M3U_OUTPUT.glob('*.m3u')))}")
    print(f"\nNext: review {REPORT_OUTPUT.name} for uncertain matches,")
    print(f"      then Stage 5 downloads {MISSING_OUTPUT.name}")


if __name__ == "__main__":
    main()
