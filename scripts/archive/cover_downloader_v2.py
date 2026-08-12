#!/usr/bin/env python3
"""
Cover Art Downloader v2 — Uses beets metadata + smart filename parsing.
Primary: sacad (Deezer, Discogs, iTunes, Last.fm)
Fallback: Direct Deezer API, iTunes API
"""
import subprocess
import sys
import os
import re
import json
import time
import hashlib
from pathlib import Path
from io import BytesIO

import mutagen
from mutagen.id3 import ID3, APIC
from mutagen.flac import FLAC, Picture
from mutagen.mp3 import MP3
from PIL import Image
import requests

# ===== CONFIGURATION =====
MUSIC_DIR = Path("/Users/r.zhikharev/personal-projects/selfhost-music/MusicRaw/Library/Singletons")
TMP_DIR = Path("/Users/r.zhikharev/personal-projects/selfhost-music/tmp_covers")
LOG_FILE = TMP_DIR / "cover_log_v2.json"
BEETS_META_FILE = TMP_DIR / "beets_metadata.txt"
SACAD_BIN = "/Users/r.zhikharev/personal-projects/selfhost-music/venv/bin/sacad"
TARGET_SIZE = 600
RATE_LIMIT_DELAY = 1.0
REQUEST_TIMEOUT = 20

TMP_DIR.mkdir(parents=True, exist_ok=True)

_last_request_time = 0

def rate_limit():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < RATE_LIMIT_DELAY:
        time.sleep(RATE_LIMIT_DELAY - elapsed)
    _last_request_time = time.time()

# ===== BEETS METADATA LOADING =====
def load_beets_metadata() -> dict[str, tuple[str, str]]:
    """Load artist/title from beets metadata export. Returns dict[filename] = (artist, title)."""
    meta = {}
    if not BEETS_META_FILE.exists():
        print(f"Warning: {BEETS_META_FILE} not found, using filename parsing only")
        return meta
    
    for line in BEETS_META_FILE.read_text().splitlines():
        line = line.strip()
        if not line or ' ||| ' not in line:
            continue
        parts = line.split(' ||| ', 2)
        if len(parts) != 3:
            continue
        path_str, artist, title = parts
        filename = Path(path_str).name
        if filename and (artist.strip() or title.strip()):
            meta[filename] = (artist.strip(), title.strip())
    return meta

# ===== FILENAME PARSING (fallback for files not in beets) =====
def parse_filename(filepath: Path) -> tuple[str, str]:
    """Parse 'Artist - Title.ext' from filename, with improved heuristics."""
    name = filepath.stem
    
    # Strip bracketed prefixes like [Bleach]
    name = re.sub(r'^\[.*?\]\s*', '', name)
    
    # Handle "AC-DC - AC-DC - Song" -> "AC-DC - Song"
    if ' - ' in name:
        parts = name.split(' - ')
        if len(parts) > 2 and parts[0].strip() == parts[1].strip():
            name = f"{parts[0]} - {' - '.join(parts[2:])}"
    
    if ' - ' in name:
        parts = name.split(' - ', 1)
        artist = parts[0].strip()
        title = parts[1].strip()
        
        # Clean up number prefix like "05." or "12." but only if it's clearly a track number
        # (number followed by dot and the result still has a clear artist name)
        m = re.match(r'^(\d{1,3})\.\s+(.+)$', artist)
        if m and len(m.group(2)) > 3:
            artist = m.group(2)
    else:
        artist = name.strip()
        title = name.strip()
    
    return artist, title

# ===== GET ARTIST/TITLE (beets preferred, filename fallback) =====
def get_artist_title(filepath: Path, beets_meta: dict[str, tuple[str, str]]) -> tuple[str, str]:
    """Get artist/title from beets metadata, falling back to filename parsing."""
    filename = filepath.name
    
    # Try exact filename match first
    if filename in beets_meta:
        artist, title = beets_meta[filename]
        if artist and title:
            return artist, title
    
    # Try with different unicode normalizations
    normalized_name = filename
    for key in beets_meta:
        if key == filename or key.encode('utf-8') == filename.encode('utf-8'):
            artist, title = beets_meta[key]
            if artist and title:
                return artist, title
    
    # Fallback to filename parsing
    return parse_filename(filepath)

# ===== COVER CHECK =====
def has_embedded_cover(filepath: Path) -> bool:
    """Check if audio file already has embedded cover art."""
    try:
        audio = mutagen.File(str(filepath))
        if audio is None:
            return False
        ext = filepath.suffix.lower()
        if ext == '.mp3':
            if hasattr(audio, 'tags') and audio.tags:
                for tag in audio.tags.values():
                    if hasattr(tag, 'FrameID') and tag.FrameID == 'APIC':
                        return True
        elif ext == '.flac':
            if audio.pictures:
                return True
    except Exception:
        pass
    return False

# ===== SACAD DOWNLOAD =====
def download_via_sacad(artist: str, title: str, output_path: Path) -> bool:
    """Use sacad to download cover art from Deezer, Discogs, iTunes, Last.fm."""
    rate_limit()
    
    # Clean artist/title for sacad (some characters may cause issues)
    clean_artist = artist.replace('"', '').replace("'", "").replace("\\", "")
    clean_title = title.replace('"', '').replace("'", "").replace("\\", "")
    
    # Skip if artist or title is empty after cleaning
    if not clean_artist.strip() or not clean_title.strip():
        return False
    
    try:
        result = subprocess.run(
            [SACAD_BIN, clean_artist, clean_title, str(TARGET_SIZE), str(output_path)],
            capture_output=True, text=True, timeout=25,
            env={**os.environ, 'PATH': os.environ.get('PATH', '')}
        )
        if result.returncode == 0 and output_path.exists():
            size = output_path.stat().st_size
            if size > 1000:
                return True
            # Clean up small/invalid files
            output_path.unlink()
        
        # Try alternative: search without title (artist only)
        if not output_path.exists():
            alt_output = Path(str(output_path).replace('.jpg', '_alt.jpg'))
            result = subprocess.run(
                [SACAD_BIN, clean_artist, clean_artist, str(TARGET_SIZE), str(alt_output)],
                capture_output=True, text=True, timeout=25,
                env={**os.environ, 'PATH': os.environ.get('PATH', '')}
            )
            if result.returncode == 0 and alt_output.exists() and alt_output.stat().st_size > 1000:
                output_path.unlink(missing_ok=True)
                alt_output.rename(output_path)
                return True
            alt_output.unlink(missing_ok=True)
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    
    output_path.unlink(missing_ok=True)
    return False

# ===== DEEZER API =====
def download_via_deezer_api(artist: str, title: str, output_path: Path) -> bool:
    """Search Deezer API for track/album/artist cover art."""
    rate_limit()
    try:
        # Search by track
        params = {'q': f'{artist} {title}', 'limit': 10}
        resp = requests.get('https://api.deezer.com/search', params=params, timeout=10)
        data = resp.json()
        
        for item in data.get('data', []):
            album = item.get('album', {})
            cover_url = album.get('cover_big') or album.get('cover_xl')
            if cover_url:
                try:
                    cover_resp = requests.get(cover_url, timeout=15)
                    if cover_resp.status_code == 200 and len(cover_resp.content) > 2000:
                        output_path.write_bytes(cover_resp.content)
                        return True
                except Exception:
                    continue
        
        # Search by artist
        if not output_path.exists():
            params = {'q': artist, 'limit': 5}
            resp = requests.get('https://api.deezer.com/search/artist', params=params, timeout=10)
            data = resp.json()
            for artist_item in data.get('data', []):
                for size_key in ['picture_big', 'picture_xl', 'picture_medium']:
                    pic_url = artist_item.get(size_key)
                    if pic_url:
                        try:
                            cover_resp = requests.get(pic_url, timeout=15)
                            if cover_resp.status_code == 200 and len(cover_resp.content) > 2000:
                                output_path.write_bytes(cover_resp.content)
                                return True
                        except Exception:
                            continue
    except Exception:
        pass
    return False

# ===== ITUNES API =====
def download_via_itunes_api(artist: str, title: str, output_path: Path) -> bool:
    """Search iTunes/Apple Music API for artwork."""
    rate_limit()
    try:
        # Search by artist + track
        params = {'term': f'{artist} {title}', 'entity': 'song', 'limit': 10}
        resp = requests.get('https://itunes.apple.com/search', params=params, timeout=10)
        data = resp.json()
        
        for item in data.get('results', []):
            art_url = item.get('artworkUrl100', '')
            if art_url:
                art_url = art_url.replace('100x100bb', '600x600bb')
                try:
                    cover_resp = requests.get(art_url, timeout=15)
                    if cover_resp.status_code == 200 and len(cover_resp.content) > 2000:
                        output_path.write_bytes(cover_resp.content)
                        return True
                except Exception:
                    continue
        
        # Search by artist only
        if not output_path.exists():
            params = {'term': artist, 'entity': 'musicArtist', 'limit': 5}
            resp = requests.get('https://itunes.apple.com/search', params=params, timeout=10)
            data = resp.json()
            for item in data.get('results', []):
                artist_id = item.get('artistId')
                if artist_id:
                    lookup_resp = requests.get('https://itunes.apple.com/lookup', 
                                                params={'id': artist_id, 'entity': 'album'}, timeout=10)
                    lookup_data = lookup_resp.json()
                    for result in lookup_data.get('results', []):
                        art_url = result.get('artworkUrl100', '')
                        if art_url:
                            art_url = art_url.replace('100x100bb', '600x600bb')
                            try:
                                cover_resp = requests.get(art_url, timeout=15)
                                if cover_resp.status_code == 200 and len(cover_resp.content) > 2000:
                                    output_path.write_bytes(cover_resp.content)
                                    return True
                            except Exception:
                                continue
    except Exception:
        pass
    return False

# ===== EMBEDDING =====
def embed_cover(filepath: Path, image_path: Path) -> bool:
    """Embed cover art into audio file using mutagen."""
    try:
        ext = filepath.suffix.lower()
        img_data = image_path.read_bytes()
        
        # Determine mime type from image
        try:
            img = Image.open(BytesIO(img_data))
            img_format = img.format
            if img_format == 'JPEG':
                mime = 'image/jpeg'
            elif img_format == 'PNG':
                mime = 'image/png'
            else:
                mime = 'image/jpeg'
            
            img_width = img.width
            img_height = img.height
        except Exception:
            mime = 'image/jpeg'
            img_width = 0
            img_height = 0
        
        if ext == '.mp3':
            audio = MP3(str(filepath), ID3=ID3)
            if audio.tags is None:
                audio.add_tags()
            audio.tags.delall('APIC')
            audio.tags.add(
                APIC(
                    encoding=3,
                    mime=mime,
                    type=3,  # Cover (front)
                    desc='Cover',
                    data=img_data
                )
            )
            audio.save()
            return True
            
        elif ext == '.flac':
            audio = FLAC(str(filepath))
            audio.clear_pictures()
            picture = Picture()
            picture.type = 3
            picture.mime = mime
            picture.desc = 'Cover'
            picture.data = img_data
            picture.width = img_width
            picture.height = img_height
            picture.depth = 24
            audio.add_picture(picture)
            audio.save()
            return True
            
    except Exception as e:
        print(f"  Embed error: {e}")
        return False

# ===== MAIN PROCESSING =====
def load_log() -> dict:
    """Load processing log."""
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text())
        except Exception:
            pass
    return {"processed": {}, "stats": {"success": 0, "failed_sacad": 0, "failed_api": 0, "failed_no_cover": 0, "skipped": 0}}

def save_log(log: dict):
    """Save processing log."""
    LOG_FILE.write_text(json.dumps(log, indent=2, ensure_ascii=False))

def clean_artist_for_search(artist: str) -> list[str]:
    """Generate alternative artist names to try for better search results."""
    variants = [artist]
    
    # Strip leading number prefix like "05 " or "12. "
    m = re.match(r'^(\d{1,3})[\.\s]+\s*(.+)$', artist)
    if m:
        variants.append(m.group(2))
    
    # Strip leading dash from "-Usher-" style names
    if artist.startswith('-') and artist.endswith('-'):
        variants.append(artist.strip('-'))
    
    return variants

def process_file(filepath: Path, log: dict, beets_meta: dict) -> str:
    """Process a single file. Returns 'success', 'failed', or 'skipped'."""
    key = filepath.name
    
    # Skip already processed
    if key in log["processed"]:
        prev = log["processed"][key]
        if prev.get("status") == "success":
            return 'skipped'
    
    # Check for existing cover
    if has_embedded_cover(filepath):
        log["processed"][key] = {"status": "skipped", "reason": "already_had_cover"}
        log["stats"]["skipped"] = log["stats"].get("skipped", 0) + 1
        return 'skipped'
    
    # Get artist/title
    artist, title = get_artist_title(filepath, beets_meta)
    if not artist or not title:
        log["processed"][key] = {"status": "failed", "reason": "no_metadata", "source": None}
        log["stats"]["failed_no_cover"] = log["stats"].get("failed_no_cover", 0) + 1
        return 'failed'
    
    total_done = sum(v for k, v in log["stats"].items())
    print(f"\n[{total_done + 1}] {artist} - {title}")
    
    safe_name = hashlib.md5(filepath.name.encode()).hexdigest()[:12]
    cover_path = TMP_DIR / f"cover_{safe_name}.jpg"
    cover_path.unlink(missing_ok=True)
    
    # Try approaches
    success = False
    source = None
    
    # Try sacad with original artist/title and cleaned variants
    artist_variants = clean_artist_for_search(artist)
    for variant_artist in artist_variants:
        if download_via_sacad(variant_artist, title, cover_path):
            success = True
            source = "sacad"
            print(f"  [OK] sacad (artist='{variant_artist}')")
            break
    
    # Fallback to Deezer API
    if not success:
        cover_path.unlink(missing_ok=True)
        for variant_artist in artist_variants:
            if download_via_deezer_api(variant_artist, title, cover_path):
                success = True
                source = "deezer_api"
                print(f"  [OK] Deezer API")
                break
    
    # Fallback to iTunes API
    if not success:
        cover_path.unlink(missing_ok=True)
        for variant_artist in artist_variants:
            if download_via_itunes_api(variant_artist, title, cover_path):
                success = True
                source = "itunes_api"
                print(f"  [OK] iTunes API")
                break
    
    if success and cover_path.exists():
        if embed_cover(filepath, cover_path):
            log["processed"][key] = {"status": "success", "source": source, "artist_searched": artist}
            log["stats"]["success"] = log["stats"].get("success", 0) + 1
            cover_path.unlink()
            return 'success'
        else:
            log["processed"][key] = {"status": "failed", "reason": "embed_error", "source": source}
            log["stats"]["failed_sacad"] = log["stats"].get("failed_sacad", 0) + 1
            cover_path.unlink(missing_ok=True)
            return 'failed'
    else:
        log["processed"][key] = {"status": "failed", "reason": "no_cover_found", "artist_searched": artist}
        log["stats"]["failed_no_cover"] = log["stats"].get("failed_no_cover", 0) + 1
        print(f"  [FAIL] No cover from any source")
        cover_path.unlink(missing_ok=True)
        return 'failed'

def main():
    print("=" * 70)
    print("Cover Art Downloader v2 — Selfhost-Music Library")
    print("=" * 70)
    
    # Load beets metadata
    beets_meta = load_beets_metadata()
    print(f"Loaded {len(beets_meta)} tracks from beets metadata")
    
    # Load files
    files = sorted([f for f in MUSIC_DIR.iterdir() if f.suffix.lower() in ('.mp3', '.flac')])
    total_files = len(files)
    print(f"Found {total_files} audio files")
    
    # Load log
    log = load_log()
    already_processed = len(log["processed"])
    print(f"Previously processed: {already_processed}")
    stats = log.get("stats", {})
    print(f"Success: {stats.get('success', 0)} | Failed: {sum(v for k, v in stats.items() if k.startswith('failed'))} | Skipped: {stats.get('skipped', 0)}")
    
    remaining = [f for f in files if f.name not in log["processed"] or log["processed"][f.name].get("status") != "success"]
    print(f"Remaining: {len(remaining)}")
    
    # Count how many use beets meta vs filename parsing
    with_beets = sum(1 for f in remaining if f.name in beets_meta)
    print(f"With beets metadata: {with_beets} | Filename parsing: {len(remaining) - with_beets}")
    print("-" * 70)
    
    # Process
    for i, filepath in enumerate(remaining):
        process_file(filepath, log, beets_meta)
        
        if (i + 1) % 25 == 0:
            save_log(log)
            s = log["stats"]
            total_failed = sum(v for k, v in s.items() if k.startswith("failed"))
            print(f"\n--- Progress: {i+1}/{len(remaining)} | OK: {s.get('success', 0)} | Failed: {total_failed} | Skip: {s.get('skipped', 0)} ---")
    
    save_log(log)
    
    # Final summary
    s = log["stats"]
    total_failed = sum(v for k, v in s.items() if k.startswith("failed"))
    total_success = s.get("success", 0)
    total_attempted = total_success + total_failed
    
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"Total files: {total_files}")
    print(f"Successfully added covers: {total_success}")
    print(f"Failed (no cover found): {total_failed}")
    print(f"Skipped (already had cover): {s.get('skipped', 0)}")
    if total_attempted > 0:
        print(f"Success rate: {total_success / total_attempted * 100:.1f}%")
    
    # Source breakdown
    sources = {}
    for k, v in log["processed"].items():
        if v.get("status") == "success":
            src = v.get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1
    print(f"\nCover sources: {sources}")
    print(f"Log saved to: {LOG_FILE}")

if __name__ == '__main__':
    main()
