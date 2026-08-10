# Как добавлять музыку и работать с обложками

## Добавление новой музыки

### С ноутбука (основной способ)

1. Брось MP3/FLAC файл в папку `~/MusicInbox`
2. Через ~30 секунд трек появится в Navidrome на всех устройствах

**Важно для качества:**
- Файл должен называться `Артист - Название.mp3`
- Желательно чтобы ID3-теги (artist, title) были заполнены
- Если есть обложка — встрой её в файл заранее (через Picard/Yate/beets)

### С телефона (Material Files)

1. Открой Material Files
2. Добавь SFTP-соединение: хост `redl-music.duckdns.org`, юзер `ubuntu`, ключ `~/.ssh/id_ed25519_oracle`
3. Перейди в `/opt/selfhost-music/music-inbox/`
4. Загрузи файл — автоимпорт сработает так же

---

## Обложки

### Почему у некоторых треков странные обложки

Обложки скачивались автоматически через sacad (Deezer, iTunes, Discogs). Система не видит картинки — она ищет по названию артиста и трека. Ошибки случаются когда:
- Есть несколько артистов с одинаковым именем (например, Sandra — немецкая поп-певица vs другая Sandra)
- Трек редкий/андеграунд — sacad возвращает неподходящую картинку
- Сервис вернул generic-обложку («muzmoru бесплатная музыка»)

### Как заменить обложку у трека

Скрипт `scripts/replace_cover.py` — замена обложки у конкретных треков:

```bash
# Заменить обложку у одного трека (скачать из Deezer/iTunes)
python3 scripts/replace_cover.py "MusicRaw/Library/Singletons/Fancy - Flames Of Love.mp3"

# Заменить обложки у всех треков указанного артиста
python3 scripts/replace_cover.py --artist "Sandra" MusicRaw/Library/Singletons/

# Dry-run: посмотреть что будет скачано без записи
python3 scripts/replace_cover.py --dry-run "путь/к/файлу.mp3"

# После замены — синхронизировать на VPS:
rsync -avz -e "ssh -i ~/.ssh/id_ed25519_oracle" \
  MusicRaw/Library/Singletons/ \
  ubuntu@redl-music.duckdns.org:/opt/selfhost-music/music/Singletons/

# И триггернуть скан:
ssh -i ~/.ssh/id_ed25519_oracle ubuntu@redl-music.duckdns.org \
  "curl -s -X POST 'http://localhost:4533/rest/startScan?u=roman_zh1&p=...&v=1.16.1&c=test'"
```

### Как вручную поставить обложку

Если хочешь свою обложку (скачанную из интернета):

1. Скачай картинку (JPEG, не больше 500×500)
2. Используй `mutagen`:
```bash
python3 -c "
from mutagen.id3 import ID3, APIC
audio = ID3('MusicRaw/Library/Singletons/Fancy - Flames Of Love.mp3')
with open('cover.jpg', 'rb') as f:
    audio.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=f.read()))
audio.save()
"
```

3. Синхронизируй на VPS (rsync + скан как выше)

### Массовое обновление обложек

Для повторной загрузки обложек на всю библиотеку:
```bash
python3 scripts/cover_downloader_v2.py  # Перезапишет обложки у ВСЕХ треков
```

---

## Исправление тегов

### Если у трека нет артиста (как было у Charli G)

```bash
# Пакетное исправление — парсит имя файла и пишет теги:
python3 scripts/fix_missing_tags.py
```

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
