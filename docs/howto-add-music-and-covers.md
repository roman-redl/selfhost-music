# Как добавлять музыку и работать с обложками

## Добавление новой музыки

### С ноутбука (основной способ)

1. Брось MP3/FLAC файл в папку `~/MusicInbox`
2. Через ~30 секунд трек появится в Navidrome на всех устройствах

**Важно для качества:**
- Файл должен называться `Артист - Название.mp3`
- Желательно чтобы ID3-теги (artist, title) были заполнены
- Если есть своя обложка — положи её рядом с тем же именем (см. ниже)

### Ручная обложка (без API)

Если хочешь свою обложку для трека — положи `.jpg` или `.png` **с тем же именем** рядом с MP3 в инбоксе:

```
~/MusicInbox/
├── Artist - Title.mp3
└── Artist - Title.jpg    ← обложка будет встроена в MP3 автоматически
```

Watcher сам найдёт картинку, встроит её в MP3/FLAC и удалит исходный файл — но только
после успешного встраивания. Если встраивание не удалось, картинка останется рядом
с треком в `/music/`.
Это **высший приоритет** — если есть ручная обложка, API-источники не опрашиваются.

### С телефона (Material Files)

1. Открой Material Files
2. Добавь SFTP-соединение: хост `redl-music.duckdns.org`, юзер `ubuntu`, ключ `~/.ssh/id_ed25519_oracle`
3. Перейди в `/opt/selfhost-music/music-inbox/`
4. Загрузи файл — автоимпорт сработает так же

---

## Обложки

### Как работает автообложка

`get_cover.py` пробует источники в порядке приоритета:

| # | Источник | Нужен ключ | Комментарий |
|---|----------|-----------|-------------|
| 1 | **Ручная** (`.jpg`/`.png` рядом) | Нет | Высший приоритет |
| 2 | **Deezer** API | Нет | Бесплатно, покрытие 76% |
| 3 | **iTunes** API | Нет | Бесплатно, +8% |
| 4 | **Cover Art Archive** (MusicBrainz) | Нет | Бесплатно, классика |
| 5 | **Discogs** API | Нет | Бесплатно, rate-limit 60/мин |
| 6 | **Bing Images** | Нет | Последний fallback, веб-поиск |

Поддерживаются MP3 и FLAC; остальные форматы проходят без автообложки.

Каждый следующий источник — fallback, если предыдущий не дал результата.

### Почему у некоторых треков странные обложки

Обложки скачивались автоматически через sacad (Deezer, iTunes, Discogs). Система не видит картинки — она ищет по названию артиста и трека. Ошибки случаются когда:
- Есть несколько артистов с одинаковым именем (например, Sandra — немецкая поп-певица vs другая Sandra)
- Трек редкий/андеграунд — API возвращает неподходящую картинку
- Сервис вернул generic-обложку («muzmoru бесплатная музыка»)

### Как заменить обложку у трека (новый способ)

Скрипт `scripts/get_cover.py` теперь поддерживает флаги для массового исправления:

```bash
# Перескачать обложку у одного трека (не трогает существующую)
python3 scripts/get_cover.py "MusicRaw/Library/Singletons/Fancy - Flames Of Love.mp3"

# Принудительно перезаписать существующую обложку
python3 scripts/get_cover.py --force "MusicRaw/Library/Singletons/Fancy - Flames Of Love.mp3"

# Массово перескачать обложки для всех треков артиста (без перезаписи)
python3 scripts/get_cover.py --artist "Sandra" MusicRaw/Library/Singletons/

# Массово перезаписать обложки для артиста (--force + --artist)
python3 scripts/get_cover.py --force --artist "Sandra" MusicRaw/Library/Singletons/

# После замены на Mac — синхронизировать на VPS:
rsync -avz -e "ssh -i ~/.ssh/id_ed25519_oracle" \
  MusicRaw/Library/Singletons/ \
  ubuntu@redl-music.duckdns.org:/opt/selfhost-music/music/Singletons/

# И триггернуть скан:
ssh -i ~/.ssh/id_ed25519_oracle ubuntu@redl-music.duckdns.org \
  "curl -s -X POST 'http://localhost:4533/rest/startScan?u=roman_zh1&p=...&v=1.16.1&c=test'"
```

**Флаги `get_cover.py`:**
- `--force` — перезаписывает существующую обложку (по умолчанию треки с обложкой пропускаются)
- `--artist "Имя"` — фильтр по артисту (case-insensitive, substring). Работает только для директории, не для одного файла

### Как вручную поставить обложку на VPS

Если трек уже на сервере, можно через SFTP положить `.jpg` рядом с `.mp3` и запустить `get_cover.py`:

```bash
ssh -i ~/.ssh/id_ed25519_oracle ubuntu@redl-music.duckdns.org \
  "cd /opt/selfhost-music/music/Singletons/ && python3 ../../scripts/get_cover.py 'Artist - Title.mp3'"
```

Или для массовой замены через ручную обложку — положи `.jpg` рядом с каждым MP3 в `~/MusicInbox/`,
они автоматически обработаются watcher'ом.

### Массовое обновление обложек

Для повторной загрузки обложек на всю библиотеку:
```bash
python3 scripts/cover_downloader_v2.py  # Перезапишет обложки у ВСЕХ треков
```

Или точечно через новый `get_cover.py`:
```bash
python3 scripts/get_cover.py --force /opt/selfhost-music/music/Singletons/
```

---

## Исправление тегов

### Если у трека нет или битые теги (artist/title/album)

```bash
# Один файл:
python3 scripts/fix_tags.py "MusicRaw/Library/Singletons/Artist - Title.mp3"

# Вся директория (просмотр без записи):
python3 scripts/fix_tags.py --dry-run MusicRaw/Library/Singletons/

# Вся директория (с записью):
python3 scripts/fix_tags.py MusicRaw/Library/Singletons/
```

`fix_tags.py` заполняет недостающие Artist/Title/Album из имени файла
(`Artist - Title.ext` → artist, title, album=artist) и убирает запрещённые значения
(`Неизвестен`, `[Unknown Album]` и т.п.). Поддерживает MP3 и FLAC.

**Для новых файлов это происходит автоматически** — watcher вызывает `fix_tags.py`
сразу после переноса трека из инбокса в `/music/`.

### Если нужно поправить конкретный трек

```bash
python3 -c "
from mutagen.id3 import ID3, TPE1, TIT2, TALB
audio = ID3('путь/к/файлу.mp3')
# Посмотреть текущие теги:
print(audio.pprint())
# Исправить:
audio.add(TPE1(encoding=3, text='Правильный Артист'))
audio.add(TIT2(encoding=3, text='Правильное Название'))
audio.save()
"
```

---

## Синхронизация после любых правок

```bash
rsync -avz -e "ssh -i ~/.ssh/id_ed25519_oracle" \
  MusicRaw/Library/Singletons/ \
  ubuntu@redl-music.duckdns.org:/opt/selfhost-music/music/Singletons/

ssh -i ~/.ssh/id_ed25519_oracle ubuntu@redl-music.duckdns.org \
  "curl -s -X POST 'http://localhost:4533/rest/startScan?u=roman_zh1&p=...&v=1.16.1&c=test'"
```
