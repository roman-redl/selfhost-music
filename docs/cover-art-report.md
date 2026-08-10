# Cover Art Download Report — Selfhost-Music Library

**Date:** 2026-08-10
**Library location:** `/Users/r.zhikharev/personal-projects/selfhost-music/MusicRaw/Library/Singletons/`

---

## Executive Summary

Successfully downloaded and embedded cover art for **1,079 out of 1,142** tracks that lacked covers (94.5% success rate among tracks needing covers). The library went from **15.7%** coverage (213/1,355) to **95.4%** coverage (1,292/1,355). Only 63 tracks remain without covers — predominantly obscure Russian meme music, mashups, and poorly tagged classical recordings.

| Metric | Before | After |
|--------|--------|-------|
| Total tracks | 1,355 | 1,355 |
| Tracks with embedded covers | 213 (15.7%) | **1,292 (95.4%)** |
| Tracks without covers | 1,142 (84.3%) | 63 (4.6%) |
| Net new covers added | — | **+1,079** |

---

## Library Overview

- **Total tracks:** 1,355
- **Format:** 1,259 MP3 + 96 FLAC files (includes both `.mp3` and `.mp3"` extensions from filenames with embedded quotes)
- **Naming convention:** `Artist - Title.ext` (singletons, no album organization)
- **beets library:** 1,033 tracks imported, 322 outside beets database
- **Existing cover art before run:** 213 tracks (15.7%)

---

## Approaches Investigated

### 1. beets + fetchart Plugin

**Verdict: NOT APPLICABLE for this library structure.**

- **Tool:** beets v2.13.1 with fetchart plugin
- **Status:** Installed and configured at `~/.config/beets/config.yaml`
- **Why it failed:** The `fetchart` plugin operates on beets *albums*, not individual singleton tracks. The library has **0 albums** and 1,033 singleton tracks. Running `beet fetchart` produced no output because there were no album-level items to process.
- **Conclusion:** fetchart is designed for album-oriented libraries. A singleton-only library cannot use this plugin without restructuring tracks into pseudo-albums.

### 2. sacad (Smart Automatic Cover Art Downloader)

**Verdict: PRIMARY APPROACH — works excellently as the main engine.**

- **Tool:** sacad v2.8.3, installed via pip in project venv
- **Sources used:** Deezer, Discogs, iTunes, Last.fm
- **How it works:** sacad expects `artist album size output.jpg`. We pass the track title as the "album" name. For most mainstream artists, this returns relevant album covers.
- **Throughput:** ~2-5 seconds per successful lookup; ~10 seconds for misses that cascade through fallbacks
- **Contribution to final result:** 742 covers via sacad (71.3% of all successful downloads)
- **Rate limiting:** sacad makes multiple source calls per invocation (Deezer, Discogs, iTunes, Last.fm). We limited to 1-second cooldown between calls to avoid API throttling.

**Quality assessment:**
- Excellent for mainstream Western music (pop, rock, electronic)
- Good for Japanese/anime music (Bleach OST, Shiro Sagisu, etc.)
- Moderate for Russian popular music (MORGENSHTERN, Элджей — found via Deezer, not sacad)
- Poor for underground/meme music and classical with complex artist names

### 3. Custom Python Script with Direct API Calls

**Verdict: ESSENTIAL FALLBACK — covered tracks that sacad missed.**

**Script:** `/Users/r.zhikharev/personal-projects/selfhost-music/scripts/cover_downloader_v2.py`

**Architecture (Tiered approach):**

```
Tier 1: sacad (Deezer + Discogs + iTunes + Last.fm)
   |
   v (if failed)
Tier 2: Deezer REST API (direct search + artist lookup)
   |
   v (if failed)
Tier 3: iTunes/Apple Music API (song search + artist lookup)
```

**APIs used directly:**
- **Deezer API** (`api.deezer.com`): No auth required. Search by artist+track, then fall back to artist-only search. Downloads album `cover_big` or artist `picture_big`.
- **iTunes API** (`itunes.apple.com`): No auth required. Search by artist+track, fall back to artist lookup with album artwork.

**Key features:**
- Uses beets database metadata for 1,033 tracks (most accurate artist/title parsing)
- Falls back to filename parsing for 322 tracks outside beets
- Handles complex filenames: leading numbers/track numbers, bracketed prefixes, duplicate artist patterns ("AC-DC - AC-DC - Thunderstruck")
- Embeds covers directly into audio files using mutagen (MP3: ID3 APIC frames, FLAC: Picture blocks)
- Resume capability via JSON log file
- Rate limiting (1-second cooldown between API calls)
- Progress saved every 25 files

**Contribution to final result:**
- Deezer API: 270 covers (25.9%)
- iTunes API: 29 covers (2.8%)
- Total API fallback: 299 covers (28.7%)

### 4. Navidrome Built-in Artwork

**Verdict: NOT APPLICABLE locally.**

- **Status:** Navidrome is configured in `docker-compose.yml` but not running locally
- **Capability:** Navidrome can fetch artwork from Deezer, Last.fm, and Spotify via its built-in scanner
- **API endpoint:** No dedicated "refresh all artwork" endpoint exists. Artwork is fetched during library scans or on-demand per-album.
- **Limitation:** Like beets, Navidrome operates on albums. Singleton tracks would need album grouping to benefit from Navidrome's artwork fetching.
- **Conclusion:** Could be used if the library were restructured into albums and deployed to the VPS, but does not help with the current local singleton structure.

### 5. MusicBrainz Picard

**Verdict: NOT PRACTICAL for batch processing.**

- GUI-based tagger, not scriptable via CLI
- Can look up covers from Cover Art Archive, but requires manual interaction per track/album
- Would require significant manual effort for 1,355 tracks
- **Conclusion:** Mentioned for completeness but not a viable approach for batch cover art retrieval.

---

## Implementation

### Script: `scripts/cover_downloader_v2.py`

Full source at: `/Users/r.zhikharev/personal-projects/selfhost-music/scripts/cover_downloader_v2.py`

**Dependencies (installed in project venv):**
- `sacad` — cover art search and download
- `mutagen` — MP3/FLAC tag manipulation
- `Pillow` — image format detection
- `requests` — HTTP API calls

**Metadata sources:**
- `beets_metadata.txt` — exported from beets database (`beet ls -f '$path ||| $artist ||| $title'`)
- Filename parsing with regex for tracks outside beets

**Filename parsing heuristics:**
- Strips bracketed prefixes `[Bleach]`
- Handles duplicate artist names (`AC-DC - AC-DC - Song`)
- Strips track number prefixes (`05.`, `12. ` etc.) when they are clearly not part of artist name
- Handles Cyrillic filenames and Unicode

**Cover embedding:**
- MP3: ID3v2 APIC frame (type 3 = front cover), JPEG/PNG mime detection via Pillow
- FLAC: Picture block in Vorbis comments
- Existing APIC frames are replaced (not duplicated)

**Execution time:** ~115 minutes total (two runs with resume)
- Rate limited to avoid API throttling
- sacad calls ~2-5 seconds each
- API fallback calls ~1-2 seconds each

---

## Results

### Overall Statistics

| Metric | Count | Percentage |
|--------|-------|------------|
| Total files processed | 1,355 | 100% |
| Covers successfully added | 1,079 | 94.5% of needed |
| Already had covers (skipped) | 213 | 15.7% |
| Failed (no cover found) | 63 | 5.5% of needed |
| **Final coverage** | **1,292** | **95.4%** |

### Cover Sources Breakdown

| Source | Covers Downloaded | % of Downloads |
|--------|-------------------|----------------|
| sacad (multi-source) | 742 | 71.3% |
| Deezer API (direct) | 270 | 25.9% |
| iTunes API (direct) | 29 | 2.8% |
| **Total** | **1,041** | **100%** |

*Note: 1,041 successful downloads per script stats vs. 1,079 net new covers per final scan. The difference of 38 covers came from test runs and manual embeds during development.*

### Edge Cases Handled

- **Leading numbers:** "05 Борис Моисеев" -> searched as "Борис Моисеев" (fallback after original failed)
- **Bracket prefixes:** "[Bleach] Shiro Sagisu" -> "Shiro Sagisu"
- **Duplicate artist names:** "AC-DC - AC-DC - Thunderstruck" -> "AC-DC - Thunderstruck"
- **Cyrillic titles:** Successfully matched via Deezer API for popular Russian tracks (MORGENSHTERN, Элджей, etc.)
- **Classical music:** Widely known pieces (Vivaldi, Mozart) matched; obscure recordings with conductor names as "artist" failed
- **Japanese:** Anime OSTs mostly found (Bleach, Shiro Sagisu, Sagisu Shiro)
- **Chinese:** One track found via Deezer API (小小狐)

---

## Analysis of Failures (63 tracks)

### Categories of Failed Tracks

| Category | Count | Examples |
|----------|-------|----------|
| Russian underground/meme | ~20 | TheAlexunder7772008 variants, Зеленый Слоник, Пахом, SuperGhostBastard |
| Classical with complex artist names | ~5 | Beethoven, Mozart, Bach with conductor/orchestra as artist |
| Mashups / remixes | ~5 | Snoop Dogg x Игорь Вихорьков, I MONSTER x Mareux, GONE.Fludd x FLESH |
| Chinese obscure | ~3 | Инь Гуан, Мао Цзэ Дун, OST 天官赐福 |
| Poor metadata (artist=track, etc.) | ~5 | "Dj Sergey Placid (Summer Session 2013) - track 9", ХОВАНГРЕБЕНЬ |
| Niche electronic/phonk | ~5 | MOONDEITY X INTERWORLD, mc orsen Austrian Painter, trapademic |
| Russian pop parodies | ~5 | Элджей&Федук - Розовое вино, пародия, Школа танцев хардбаса |
| Game/movie OST | ~5 | Разрушители Легенд-Мифов, Сокровище Монтесумы, Пингвины Мадагаскара |
| Other obscure one-offs | ~10 | Various |

### Root Causes

1. **Artist not in databases:** Underground/meme/niche artists with no presence on Deezer, Discogs, iTunes, or Last.fm.
2. **Complex artist names:** Classical tracks where the "artist" field contains conductor + orchestra + soloist names rather than just the composer.
3. **Mashups:** Tracks combining multiple artists (e.g., "Rammstein & Katy Perry") don't match any real release.
4. **Poor tagging:** Tracks imported into beets with empty or nonsensical artist/title fields.
5. **Title format mismatch:** Tracks with "[ID ...]" suffixes, year suffixes like "(12-) - 1986", or other non-standard formatting.

### Recommendations for Remaining 63 Tracks

1. **Manual cover assignment:** For the 63 remaining tracks, manual cover search and embedding is the most reliable approach.
2. **Retry with Google Images / Bing:** A custom scraper could find covers for some of the meme/niche tracks.
3. **Artist name cleanup:** Re-tag tracks like "Dj Sergey Placid (Summer Session 2013)" with cleaner artist names, then re-run the downloader.
4. **Classical re-tagging:** Use composer name as artist (e.g., "Людвиг ван Бетховен" instead of conductor+orchestra).
5. **yandex-music / VK search:** For Russian tracks that failed on Western services, Russian streaming APIs (Yandex Music, VK) could potentially find covers.

---

## Tool Summary

| Tool | Viability | Quality | Speed | Automation | Notes |
|------|-----------|---------|-------|------------|-------|
| beets + fetchart | NO | N/A | N/A | N/A | Requires albums, not singletons |
| sacad | YES (primary) | High | Fast | Full | Best for mainstream music |
| Custom Python + APIs | YES (fallback) | High | Fast | Full | Catches what sacad misses |
| Navidrome | NO (locally) | Medium | Medium | Partial | Requires deployment, album-based |
| MusicBrainz Picard | NO | High | Slow | None | GUI only, manual per-track |

---

## Scripts Produced

| Script | Path | Purpose |
|--------|------|---------|
| Cover Downloader v2 | `scripts/cover_downloader_v2.py` | Main production script |
| beets metadata export | `tmp_covers/beets_metadata.txt` | Artist/title data for 1,033 tracks |
| Processing log | `tmp_covers/cover_log_v2.json` | Resume-capable JSON log |
| Files needing covers | `tmp_covers/needs_cover.txt` | Pre-run inventory |
| Files with covers | `tmp_covers/has_cover.txt` | Post-run inventory |

---

*Report generated automatically by cover download pipeline.*
