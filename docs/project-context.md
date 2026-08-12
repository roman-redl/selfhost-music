# Контекст проекта и инциденты (selfhost-music)

> Живой справочник: правила, решения и грабли. Актуален на 2026-08-13.
> Операционный минимум — [CLAUDE.md](../CLAUDE.md) в корне репозитория.
> Хроника миграции — [music-migration-plan.md](music-migration-plan.md).

## История одной строкой

VK отключил публичное API → Kate Mobile перестал докачивать музыку → миграция на
self-hosted **Navidrome** (Oracle Cloud Free Tier + PAYG, Frankfurt, Ampere A1
4 OCPU / 24 GB RAM, Ubuntu 24.04, Docker). Этапы 1–8 выполнены 2026-08-06 … 08-10.
Библиотека перенесена на VPS, плейлисты восстановлены, домен из `.env`
(`DOMAIN`; DuckDNS + Caddy + Let's Encrypt).

## Архитектура

```
VPS (Oracle, PAYG):
  Caddy :443 (HTTPS, домен из env {$DOMAIN})
    └─ Navidrome :4533 (Subsonic API)
         читает /music/ (readonly), база /data/
  /music-inbox/ — входящие файлы (Syncthing с Mac ~/MusicInbox, SFTP с Android)
    └─ watcher (systemd, scripts/watch-inbox.sh):
         mv → /music/ → fix_tags.py (теги) → get_cover.py (обложка) → Navidrome подхватывает
  Бэкап: cron backup-to-cloud.sh → Mail.ru WebDAV (davfs2) — НЕ НАСТРОЕН
Клиенты: Supersonic (Mac/Win), Substreamer (Android) — полный офлайн-кеш.
```

## Правила (обязательные)

### Именование треков

- Единый стандарт: `Artist - Title.ext`
- Разделитель всегда ` - ` (пробел-дефис-пробел)
- Запрещены: `—` (em dash), `–` (en dash), `|`, `_` как разделитель
- `&amp;` → `&`
- Без leading-номеров треков (`1. `, `01. `, `(1x02) `)
- Без `[Source]`-префиксов в именах файлов (в списках — допустимо для контекста)

### ID3-теги

- **Artist (TPE1):** из имени файла. Запрещены: `Неизвестен`, `Unknown Artist`, пустое,
  полные классические атрибуции (`Бах - Сюита №2 - Капелла Истраполитана` → `Бах`).
- **Title (TIT2):** из имени файла. Запрещены: пустое, `Без названия`, имя артиста в поле названия.
- **Album (TALB):** реальный альбом, если известен; иначе **имя артиста**. Запрещены:
  `Unknown Album`, `[Unknown Album]`, пустое.
- Все три тега обязательны; при отсутствии/повреждении восстанавливаются из имени файла.
- m3u-файлы при исправлении тегов не трогать (переименования не допускаются).
- **Регистр:** один артист = один регистр (большинством голосов). Исключения — стилизованные (`a-ha`).
- Автоматизация: `scripts/fix_tags.py` (MP3 + FLAC), вызывается watcher'ом для каждого нового файла.

### Матчинг

- **Запрещён fuzzy-матчинг скриптами** — только агенты Claude Code в параллельном режиме.
- Агенты используют семантику: переводы, транслитерацию, жанровые знания.
- Никаких промежуточных скриптов-посредников.
- Для импорта плейлистов в Navidrome: NFC-нормализация + полный локальный индекс песен,
  никакого «вернуть первый результат» (см. инцидент 4).

### Запреты

| Запрещено | Причина |
|---|---|
| yt-dlp | Корпоративный запрет |
| rclone для Mail.ru | Не работает (проверено) — только WebDAV/davfs2 |
| Tailscale/сторонние VPN | Корпоративный Mac не позволяет |
| Хардкод кредов в коде | Всё в `.env` (gitignored); репозиторий публичный |
| Правки файлов на VPS вручную | Рассинхрон с git (инцидент 2026-08-13) |

## Ключевые решения (зафиксировано)

| Вопрос | Решение | Причина |
|---|---|---|
| Сервер-приложение | **Navidrome** (не Jellyfin) | Только музыка, легче (Go), больше Subsonic-клиентов |
| Хостинг | **Oracle Cloud Free Tier** (ARM, PAYG-апгрейд) | Бесплатно; PAYG защищает от удаления через 60 дней |
| Источник аудио | Кеш Kate Mobile из Mail.ru облака | Единый источник файлов |
| Облако-бэкап | Mail.ru (почтовое) через **WebDAV (davfs2)** | rclone не работает |
| Нормализация | Парсинг имён → ID3 → beets (позже отказ от beets: имена уже чистые) | 95% файлов уже содержали артиста и название |
| Докачка | **slskd (Soulseek)**, потом web + VK extension | yt-dlp запрещён; хитрейт slskd 8% — только первый проход |
| Загрузка файлов | Syncthing (ноутбук) + SFTP (телефон) | Navidrome не принимает файлы через API |
| Доступ | Публичный HTTPS (Caddy + DuckDNS) | Нельзя сторонние VPN |
| Десктоп-клиент | **Supersonic** (полный офлайн-кеш) | Feishin — кеш частичный; AIMP/Foobar — UI устарел |
| Android-клиент | **Substreamer** | Бесплатный, полный кеш, лучший UI |
| Аудиокниги | **Audiobookshelf** (отдельный контейнер, Этап 9) | Navidrome не подходит для аудиокниг |

Развилки (клиенты, способ бэкапа) решены — таблицы в хронике плана, «Открытые развилки».

## Инциденты и грабли

### Опыт эксплуатации (2026-08-12)

1. **m3u-автоимпорт Navidrome не работает** (баг «no admin users yet» при первом скане) —
   импорт плейлистов только через Subsonic API: `scripts/archive/import_playlists_api.py`.
2. **`createPlaylist` принимает ОДИН `songId`** — передача списка молча теряет первый трек.
   Создавать с первым треком, остальные — `updatePlaylist` по одному.
3. **Дубли плейлистов в Navidrome** — в `playlists_m3u/` (ныне `playlists/` в корне репо)
   жили пары `.m3u` с разным написанием имени. Держать ровно один файл на плейлист;
   после удаления дублей — rsync `--delete` + переимпорт.
4. **search3 плохо работает с юникодом** (Cyrillic, decomposed) и даёт ложные срабатывания —
   матчить по локально собранному индексу всех песен с NFC-нормализацией.
5. **Регистр артистов дробил их в Navidrome** (`Falco` vs `FALCO`) — правило каноничного регистра.
6. **Теги не совпадали с именами файлов** (artist в title, «Без названия») — строгое правило
   «теги = имя файла», чинит `scripts/fix_tags.py`.
7. **Обложки-muzmo** (generic-обложка «muzmo — бесплатная музыка») на десятках треков —
   находить по одинаковому md5-хэшу картинки и перескачивать через `get_cover.py`.
8. **Пароль Navidrome захардкожен в скрипте** — вынесен в `.env`
   (`NAVIDROME_USER`/`NAVIDROME_PASSWORD`), скрипт читает env или `.env`.
9. **Дубли строк внутри `.m3u`** — дедуп по содержимому.
10. **Бэкап в Mail.ru не настроен** — нет пароля приложения (задача человека, см. план).

### Свежие инциденты (2026-08-13)

11. **Exec-бит слетает при перезаписи `.sh`** (Write/перезапись файла) → systemd
    `203/EXEC`, watcher в crash-loop. Урок: после перезаписи shell-скрипта проверять
    `ls -l`; git фиксирует mode change.
12. **VPS-репозиторий разошёлся с GitHub** (старый расходящийся коммит, `scripts/` и часть
    конфигов untracked/рукоправленные). Лечение: бэкап рабочего дерева
    (`/opt/selfhost-music-backup-20260813/`) → `git reset --hard origin/main`.
    Урок: на VPS только `git pull`, никаких ручных правок.
13. **Пароль с `#` в URL-запросе ломает query-string** (Navidrome отдаёт «missing parameter:
    v»). Урок: всегда URL-кодировать — `curl -G --data-urlencode`, в Python — `urllib.parse.urlencode`.
14. **`{$DOMAIN}` в Caddyfile не резолвился бы без env** — в docker-compose у caddy-сервиса
    должен быть `environment: DOMAIN: ${DOMAIN}`. Рукоправленный Caddyfile на VPS заменён
    репозиторной версией с env.
15. **slskd отключён** (контейнер удалён, сервис закомментирован в compose). Для разовой
    докачки: раскомментировать → `docker compose up -d slskd` → SSH-туннель к `localhost:5030`
    → `scripts/archive/slskd_download.py`. Нужен свежий список missing (сейчас его нет —
    по итогам этапа 5.5 missing = 0).
16. **Клиентский кеш стареет** после обновлений сервера — выйти из аккаунта и зайти заново.
17. **Два формата `.m3u`** (EXTM3U+EXTINF vs простые пути) — разные партии файлов собирались
    разными агентами. Унифицировано: все `.m3u` только простые пути `Singletons/Artist - Title.ext`,
    без `#EXTM3U`/`#EXTINF` (импорт работает и так, но EXTINF-названия — мёртвый груз, могут
    расходиться с тегами).
18. **Читается только `*.m3u`** — и Navidrome, и `import_playlists_api.py` матчат строго по
    расширению `.m3u`. Файлы `.m3u.bak` (бэкапы от пересборки путей) нигде не читаются —
    мусор, удалены (2026-08-13). Никаких `.bak` в `playlists/` не хранить.

## Карта скриптов

| Скрипт | Назначение | Статус |
|---|---|---|
| `scripts/watch-inbox.sh` | Автоимпорт: mv из инбокса → теги → обложка → Navidrome (systemd `music-watcher`) | Активный |
| `scripts/get_cover.py` | Обложки MP3/FLAC: ручная → Deezer → iTunes → Cover Art Archive → Discogs → Bing; флаги `--force`, `--artist` | Активный |
| `scripts/fix_tags.py` | Чинит Artist/Title/Album по имени файла (MP3+FLAC), `--dry-run`, `--limit` | Активный |
| `scripts/export_tracklist.py` | Экспорт полного списка треков из Navidrome в TSV (`playlists/tracklist.tsv`) | Активный |
| `scripts/backup-to-cloud.sh` | Ночной бэкап `/music/` + `/data/` в Mail.ru WebDAV | Готов, **не активен** (нет пароля приложения) |
| `scripts/setup-vps.sh` | Развёртывание VPS с нуля (Oracle ARM) | Для DR |
| `scripts/duckdns.sh` | DDNS-обновление (на VPS работает сгенерированная копия `/opt/duckdns/duck.sh` по cron) | Справочный |
| `scripts/archive/*` | Одноразовые: `parse_filenames.py` (кеш Kate Mobile), `match_playlists.py` (fuzzy — запрещён к повторному использованию), `slskd_download.py`, `cover_downloader_v2.py` (массовые обложки, Mac-only), `import_playlists_api.py` (импорт плейлистов — единственный рабочий путь), `fix_missing_tags.py`/`fix_unknown_album.py` (заменены `fix_tags.py`) | Исторические |

## Текущее состояние

> Цифры (число треков, плейлистов, обложек) здесь намеренно не фиксируются — они меняются
> с каждым импортом. Проверить актуальные: число файлов —
> `find /opt/selfhost-music/music -type f | wc -l` на VPS; состав коллекции и плейлистов —
> в веб-интерфейсе Navidrome.

Статус-флаги (обновлять при изменении):

- **Бэкап:** НЕ НАСТРОЕН (см. инцидент 10). `davfs2` установлен, скрипт готов — нужен
  пароль приложения Mail.ru в `.env` (`MAILRU_EMAIL`, `MAILRU_APP_PASSWORD`).
- **slskd:** выключен (см. инцидент 15).
- **Этап 9 (аудиокниги):** отложен.
- **Пароль Navidrome:** в `.env` (`NAVIDROME_USER`/`NAVIDROME_PASSWORD`), содержит `#`
  (кодировать!). Старый утёкший пароль из git-истории недействителен.
- **Треки без обложек и на ручную замену:** список в `docs/manual-fix-list.txt`.

Точки входа:

- **VPS:** `ubuntu@$DOMAIN` (значение `DOMAIN` из `.env`), ключ `~/.ssh/id_ed25519_oracle`, sudo без пароля.
  Репозиторий `/opt/selfhost-music/`, стек: caddy + navidrome (docker compose).
- **Локальная копия библиотеки:** `MusicRaw/Library/Singletons/` на Mac — зеркало
  для массовых правок; после правок rsync на VPS + триггер скана.
- **Канонические m3u:** `playlists/` в корне репозитория (версионируются в git);
  снапшот коллекции — `playlists/tracklist.tsv` (обновлять через `export_tracklist.py`).
- **Логи:** watcher — `/var/log/music-import.log`; бэкапа — `/var/log/music-backup.log`.

## Disaster Recovery

Полная процедура — [disaster-recovery.md](disaster-recovery.md). Дополнения:
- `scripts/setup-vps.sh` ставит стек заново (slskd закомментирован — не поднимется).
- После восстановления вручную: mount WebDAV (fstab + davfs2/secrets), пароль Navidrome,
  Syncthing-папку, бэкап в cron.
- Данные для восстановления: `music/` (~12 GB) и `navidrome-data/` (~10–50 MB) в Mail.ru облаке
  (как только бэкап будет настроен).

## Ссылки

- [CLAUDE.md](../CLAUDE.md) — операционный минимум для агентов
- [music-migration-plan.md](music-migration-plan.md) — закрытая хроника + «Осталось на будущее»
- [howto-add-music-and-covers.md](howto-add-music-and-covers.md) — добавление музыки и обложек
- [disaster-recovery.md](disaster-recovery.md) — восстановление VPS
- [manual-fix-list.txt](manual-fix-list.txt) — треки для ручной правки обложек
