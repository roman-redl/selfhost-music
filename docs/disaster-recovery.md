# Disaster Recovery — Selfhost Music

## Что бэкапится

| Данные | Путь на VPS | Путь в облаке | Размер |
|--------|------------|---------------|--------|
| Музыка | `/opt/selfhost-music/music/` | `music/` | ~12 GB |
| База Navidrome | `/opt/selfhost-music/data/` | `navidrome-data/` | ~10-50 MB |

Бэкап запускается ежедневно через cron (`scripts/backup-to-cloud.sh`).

## Процедура восстановления

### Предпосылки

- Новый VPS (Oracle Cloud, Ubuntu 24.04, 4 CPU / 24 GB RAM, ≥200 GB диск)
- Docker и Docker Compose установлены
- DuckDNS домен настроен
- Доступ к Mail.ru облаку через WebDAV (пароль приложения)

### Шаги

1. **Установить зависимости:**
   ```bash
   apt update && apt install -y docker.io docker-compose-v2 davfs2
   ```

2. **Настроить WebDAV-доступ к облаку:**
   ```bash
   # /etc/fstab
   https://webdav.cloud.mail.ru /mnt/mailru-backup davfs user,noauto,uid=0,gid=0 0 0
   
   # /etc/davfs2/secrets
   /mnt/mailru-backup <email> <app-password>
   
   mount /mnt/mailru-backup
   ```

3. **Скачать данные из облака:**
   ```bash
   mkdir -p /opt/selfhost-music/music /opt/selfhost-music/data
   rsync -avz /mnt/mailru-backup/music/ /opt/selfhost-music/music/
   rsync -avz /mnt/mailru-backup/navidrome-data/ /opt/selfhost-music/data/
   ```

4. **Клонировать репозиторий и запустить:**
   ```bash
   git clone https://github.com/roman-redl/selfhost-music.git /opt/selfhost-music
   cd /opt/selfhost-music
   docker compose up -d
   ```

5. **Проверить:**
   - `docker ps` — navidrome и caddy должны быть up
   - `https://redl-music.duckdns.org` — должен открываться веб-интерфейс
   - Плейлисты, избранное, пользователи — всё должно быть на месте (база восстановлена)

**Расчётное время:** ~1 час (в основном скачивание 12 GB из облака).

## Проверка бэкапа

Раз в месяц проверять, что облако монтируется и файлы читаются:
```bash
mount /mnt/mailru-backup
ls /mnt/mailru-backup/music/Singletons/ | head -20
ls /mnt/mailru-backup/navidrome-data/
```
