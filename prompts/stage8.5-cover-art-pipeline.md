# Stage 8.5 — Улучшенный пайплайн обложек

Ты — агент. Прочитай `docs/music-migration-plan.md` для контекста, затем выполни задачу.

## Текущее состояние

Обложки скачиваются для новых треков через `scripts/get_cover.py` (Deezer API + iTunes API).
Покрытие библиотеки: 95.4% (1292/1355). Watcher: `scripts/watch-inbox.sh` (systemd).
VPS: `ubuntu@redl-music.duckdns.org`, ключ `~/.ssh/id_ed25519_oracle`, путь `/opt/selfhost-music/`.

## Задача

### 1. Добавить источники обложек в `get_cover.py`

Текущие: Deezer API, iTunes API. Добавить:

- **Cover Art Archive** (MusicBrainz) — `https://coverartarchive.org/release/{mbid}/front`
- **Last.fm** — `https://www.last.fm/music/{artist}/+images`
- **Spotify** — через public API поиска: `https://api.spotify.com/v1/search?q=...&type=track` (нужен client credentials token, бесплатный)
- **Discogs** — `https://api.discogs.com/database/search?q=...&type=release`

Приоритет: Deezer → iTunes → Cover Art Archive → Spotify → Last.fm → Discogs.
Каждый следующий источник — fallback если предыдущий не дал результат.

### 2. Ручная обложка через соседнюю папку

Добавить в watcher: если рядом с `трек.mp3` в инбоксе лежит `трек.jpg` (или `трек.png`) —
взять её как обложку, не ходить в API.

```
~/MusicInbox/
├── Artist - Title.mp3
└── Artist - Title.jpg    ← обложка будет встроена в MP3
```

### 3. Массовое перескачивание плохих обложек

Добавить в `get_cover.py` флаг `--force` — перезаписывает существующую обложку.
Добавить `--artist "Sandra"` — фильтр по артисту для точечного исправления.

### 4. Обновить watcher

`scripts/watch-inbox.sh` должен:
- Проверять наличие `.jpg`/`.png` рядом с аудиофайлом
- Вызывать `get_cover.py` с поддержкой новых флагов
- После встраивания обложки — удалять `.jpg`/`.png` из инбокса

## Ограничения

- **Не менять** структуру файлов в `/music/` — Navidrome уже всё проиндексировал
- **Не трогать** существующие обложки без `--force`
- **Не использовать** yt-dlp
- Все API-ключи должны быть опциональны (работать без них, просто с меньшим покрытием)
- Деплоить через scp + перезапуск systemd сервиса

## Ожидаемый результат

- `scripts/get_cover.py` с 6 источниками + флагами `--force`, `--artist`
- `scripts/watch-inbox.sh` с поддержкой ручных обложек
- Обновлённая документация в `docs/howto-add-music-and-covers.md`
- Задеплоено на VPS, сервис перезапущен
