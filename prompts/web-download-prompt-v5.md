# Prompt: ФИНАЛЬНЫЙ прогон — докачка ВСЕХ missing tracks

Это последний прогон, цель — добить всё что возможно.

---

## Контекст

Проект selfhost-music в `~/personal-projects/selfhost-music/`.

- Уже скачано: **234 трека (2.0 GB)** в `MusicRaw/web_downloads/`
- Осталось: **~127 треков** в `MusicRaw/missing_tracks.txt`
- Файл состояния: `MusicRaw/web_download_state.md`

## Стратегия: многоэтапный прогон

Для каждого трека из missing_tracks.txt (исключая уже скачанные) проходим этапы:

### Этап 1: hitmoz.org (покрывает ~85%)

```
WebFetch → https://ru.hitmoz.org/search?q=URL_ENCODED_ARTIST+TRACK
prompt: "Return ONLY first download path: get/music/...mp3"
Если нашлось → curl → СЛЕДУЮЩИЙ ТРЕК
Если "ничего не найдено" → Этап 2
```

### Этап 2: full_web_search (DuckDuckGo/Brave/Bing — находит drivemusic.club, sefon.pro, mp3uk.net)

```
mcp__generic_web-search__full_web_search:
  query: "АРТИСТ НАЗВАНИЕ скачать mp3"
  limit: 3
  includeContent: true
→ Извлечь прямую .mp3 ссылку из контента
→ Если нашлась → curl → СЛЕДУЮЩИЙ ТРЕК
→ Если нет → Этап 3
```

### Этап 3: Прямой WebFetch на альтернативные сайты

По очереди (до первого успеха):
```
a) WebFetch → https://rus.hitmotop.com/search?q=ARTIST+TRACK
   (редирект на ru.hitmoz.org — см. Этап 1)

b) WebFetch → https://sefon.pro/search?q=ARTIST+TRACK
   prompt: "Find mp3 download link"

c) WebFetch → https://drivemusic.club/search?q=ARTIST+TRACK
   prompt: "Find mp3 download link"

d) WebFetch → https://mp3uk.net/search?q=ARTIST+TRACK
   prompt: "Find mp3 download link"

e) WebFetch → https://mp3party.net/search?q=ARTIST+TRACK
   prompt: "Find mp3 download link"
```
Если нашлось → curl → СЛЕДУЮЩИЙ ТРЕК
Если нет → Этап 4

### Этап 4: WebSearch (последний шанс)

```
WebSearch: "АРТИСТ НАЗВАНИЕ скачать mp3 site:promodj.com OR site:drivemusic.club OR site:sefon.pro OR site:mp3uk.net"
→ Если нашлась ссылка → WebFetch страницу → найти .mp3 → curl
→ Если нет → ЗАПИСАТЬ В skipped.txt, идти дальше
```

## Правила

- **Параллелить по 2-3 операции** на каждом этапе для скорости
- Убирать из имён файлов: `/`, `:`, `*`, `?`, `"`, `<`, `>`, `|`
- Для треков с японскими названиями — пробовать и оригинал, и ромадзи
- Каждые 30 обработанных треков обновлять `MusicRaw/web_download_state.md`
- **Не пропускать «Зелёный слоник» и аниме OST** — hitmoz их находит!

## Как проверить, скачан ли трек

```bash
ls MusicRaw/web_downloads/ | grep -i "ключевое_слово"
```

## Итоговый отчёт

В конце вывести:
```
=== ФИНАЛЬНЫЙ ПРОГОН ===
Обработано треков: X
Скачано: Y (Z% от обработанных)
Из них:
  - Этап 1 (hitmoz): A
  - Этап 2 (full_web_search): B
  - Этап 3 (прямые сайты): C
  - Этап 4 (WebSearch): D
Пропущено (нигде нет): E
Всего в web_downloads: F треков, G GB
Осталось в missing_tracks.txt: H
```
