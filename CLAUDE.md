# CLAUDE.md — selfhost-music

Self-hosted музыка: Navidrome на Oracle Cloud VPS + Caddy + автоимпорт через Syncthing/SFTP.
Миграция с VK/Kate Mobile завершена (этапы 1–8). Этот файл — операционная точка входа для
агентов. Детали: [docs/project-context.md](docs/project-context.md) (правила, решения,
инциденты), [docs/music-migration-plan.md](docs/music-migration-plan.md) (закрытая хроника
миграции + «Осталось на будущее»).

## Правила (нарушать нельзя)

- **Имена файлов:** `Artist - Title.ext`, разделитель строго ` - `. Без `—`, `|`, `_`-разделителей, без leading-номеров.
- **Теги:** Artist/Title/Album обязательны. Album неизвестен → имя артиста. Теги = имя файла (NFC-нормализация). Один артист = один регистр. Чинит `scripts/fix_tags.py` (MP3+FLAC).
- **Матчинг** плейлистов/треков — только агенты (семантика: переводы, транслитерация). Fuzzy-скрипты запрещены (~42% ложных срабатываний).
- **Запрещено:** yt-dlp (корпоративный запрет), rclone для Mail.ru (не работает — только WebDAV/davfs2), Tailscale/сторонние VPN (корпоративный Mac), хардкод кредов (всё в `.env`).
- **Домен сервера — только через `DOMAIN` из `.env`**, в командах `$DOMAIN`. Не хардкодить `redl-music.duckdns.org`.
- **Не трогать:** структуру `/music/` на VPS (Navidrome проиндексировал), `.env` (gitignored, содержит секреты), бэкап-механику без явной задачи.

## Как добавить музыку

1. Файл `Artist - Title.mp3`/`.flac` в `~/MusicInbox` (Syncthing) или по SFTP в `/opt/selfhost-music/music-inbox/` на VPS.
2. Watcher всё делает сам: `fix_tags.py` (теги) → `get_cover.py` (обложка) → Navidrome. ~30 секунд.
3. Ручная обложка: положить `Artist - Title.jpg`/`.png` тем же именем рядом в инбокс — высший приоритет. Удаляется только после успешного встраивания, иначе остаётся рядом с треком.
4. Детали и флаги: `docs/howto-add-music-and-covers.md`.
5. После массовых заливок обнови снапшот коллекции: на VPS `python3 scripts/export_tracklist.py > playlists/tracklist.csv`, файл закоммить.

## Как добавить или обновить плейлист

- Канонические `.m3u` живут в `playlists/` в корне репозитория (версионируются в git). Один файл = один плейлист.
- Формат `.m3u`: строки `Singletons/Artist - Title.ext`, без дублей внутри файла, без `#EXTM3U`/`#EXTINF`.
- **Автоимпорт m3u в Navidrome сломан** (баг «no admin users yet») — импортировать через Subsonic API: `scripts/archive/import_playlists_api.py` (NFC-матчинг по полному индексу, креды из env или `.env`). Не использовать «первый результат поиска».
- Подробности: project-context.md, инциденты 1–4.

## Как деплоить изменения

1. Локально: правки → `python3 -m py_compile scripts/*.py` / `bash -n scripts/*.sh` → smoke-тест на **копиях** в /tmp, не на библиотеке.
2. После перезаписи `.sh` проверить `ls -l` — exec-бит слетает при перезаписи файла (инцидент 2026-08-13: systemd 203/EXEC).
3. Коммит (короткое сообщение) + push (remote на SSH: `git@github.com:roman-redl/selfhost-music.git`).
4. VPS: `ssh -i ~/.ssh/id_ed25519_oracle ubuntu@$DOMAIN` (sudo без пароля; `$DOMAIN` из `.env`):
   `cd /opt/selfhost-music && sudo git pull --ff-only`.
5. Перезапуск: `sudo systemctl restart music-watcher`; если менялись Caddyfile/docker-compose — `docker compose up -d caddy`.
6. **Правки на VPS руками не делать** — репозиторий там расходился с GitHub (инцидент 2026-08-13). Всё через git.
7. Navidrome-базу руками не править; чистка мёртвых записей — только по процедуре из project-context.md (инцидент 3).

## Карта файлов

| Путь | Что это |
|---|---|
| `scripts/` | Операционные: `watch-inbox.sh` (watcher, systemd), `get_cover.py` (обложки MP3/FLAC), `fix_tags.py` (теги), `export_tracklist.py` (снапшот коллекции в TSV), `backup-to-cloud.sh` (бэкап, пока не активен), `setup-vps.sh` (развёртывание с нуля), `duckdns.sh` (справочный) |
| `playlists/` | Канонические `.m3u` плейлистов + `tracklist.csv` — снапшот коллекции из Navidrome, читаемый таблицей (обновлять через `export_tracklist.py`) |
| `scripts/archive/` | Одноразовые миграционные (этапы 3–6). Не использовать без понимания контекста |
| `config/` | `Caddyfile` (домен через env `{$DOMAIN}`), `slskd.yml`, `music-watcher.service` |
| `docs/` | `project-context.md` (правила/инциденты), `music-migration-plan.md` (хроника + будущее), `howto-add-music-and-covers.md`, `disaster-recovery.md`, `manual-fix-list.txt` |
| `.env` | Секреты (gitignored): `DOMAIN`, `NAVIDROME_USER`/`NAVIDROME_PASSWORD` (пароль содержит `#` — всегда URL-кодировать!), `SLSKD_*`, `MAILRU_*` |

## Где что читать

- Состояние системы и открытые задачи: `docs/project-context.md` («Текущее состояние») и «Осталось на будущее» в плане
- Правила, решения, инциденты с датами: `docs/project-context.md`
- Хроника миграции и «Осталось на будущее»: `docs/music-migration-plan.md`
- Добавление музыки/обложек: `docs/howto-add-music-and-covers.md`
- Восстановление после потери VPS: `docs/disaster-recovery.md`
