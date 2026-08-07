# План: личный VPN на Oracle Cloud VPS

> Связанный проект: [selfhost-music](https://github.com/roman-redl/selfhost-music) —
> этот же VPS (Oracle Cloud, Frankfurt, PAYG, 4 CPU / 24 GB RAM), домен
> `redl-music.duckdns.org`.

## Проблема

ChatGPT на Android блокирует запросы, несмотря на VPN (AdGuard). Браузерная версия
работает через тот же VPN. Причина — не геолокация по IP, а **IP-диапазоны
коммерческих VPN внесены в чёрные списки OpenAI.** Приложение агрессивнее браузера
в проверках.

Проверено и исключено:
- Play Store регион Молдова (не влияет)
- SIM-карта (режим самолёта + WiFi — не влияет)
- DNS/WebRTC утечки (браузер работает → IP чистый)

**Гипотеза:** личный IP на Oracle Cloud, отсутствующий в VPN-базах, пройдёт проверки
приложения. Плюс Xray + REALITY мимикрирует под HTTPS к легитимному сайту — DPI РФ/РБ
видит обычный веб-трафик.

## Решение

**Xray (VLESS) + REALITY** на существующем VPS.

### Почему Xray + REALITY, а не другое

| Протокол | Обход DPI | Скорость | Риск блокировки | Причина |
|----------|:---------:|:--------:|:---------------:|---------|
| **Xray VLESS + REALITY** | ✅ | Высокая | Минимальный | Притворяется HTTPS к реальному сайту (apple.com, microsoft.com) |
| Hysteria 2 (QUIC) | ⚠️ | Очень высокая | Средний | DPI учится блочить QUIC по паттернам |
| AmneziaWG | ⚠️ | Высокая | Средний | Маскировка под HTTPS, но менее стабильна |
| OpenVPN/WireGuard | ❌ | Высокая | Мгновенно | Легко детектится DPI |
| Outline/Shadowsocks | ❌ | Средняя | Высокий | Устарел, блочится пачками |

**Как работает REALITY:**
- Твой VPS перехватывает TLS-рукопожатие к чужому домену (например, `apple.com`)
- Если клиент без правильного ключа — соединение пробрасывается на реальный `apple.com`
- Если с правильным ключом — начинается туннель
- Для DPI это выглядит как обычный HTTPS к легитимному сайту
- Сертификат настоящий (от `apple.com`) — не самоподписанный

### Архитектура

```
┌─────────────────────────────────────────────────────────┐
│              VPS Oracle Cloud (Frankfurt)               │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ Xray     │  │ Navidrome│  │ Caddy (HTTPS)        │  │
│  │ :8443    │  │ :4533    │  │ :443                 │  │
│  │ (REALITY)│  │          │  │ redl-music.duckdns   │  │
│  └────┬─────┘  └──────────┘  └──────────────────────┘  │
│       │                                                 │
│       │  ufw: 8443/tcp (Xray)                          │
│       │  ufw: 443/tcp  (Caddy)                         │
│       │  ufw: 22/tcp   (SSH)                           │
└───────┼─────────────────────────────────────────────────┘
        │
        │  Порты не конфликтуют: Xray на 8443,
        │  Caddy на 443 — разные порты, одна VPS.
        │
   ┌────┴────┐       ┌──────────┐
   │ Android │       │   Mac    │
   │ v2rayNG │       │ Sing-box │
   └─────────┘       └──────────┘
```

### Клиенты

| Платформа | Клиент | Комментарий |
|-----------|--------|------------|
| Android | **v2rayNG** | Бесплатный, настраивается через QR/ссылку |
| Windows | **v2rayN** | Бесплатный клиент для Windows |
| iOS | **Shadowrocket** или **Sing-box** | Shadowrocket платный (~$3), лучший UI |
| Mac | ❌ нельзя | Клиент не устанавливается |

### Что с ChatGPT на Android?

После настройки:
1. Подключиться к своему Xray-серверу через v2rayNG
2. Открыть приложение ChatGPT
3. Если работает → проблема была в IP-пулах AdGuard ✅
4. Если не работает → приложение использует Google Play Integrity, нужен обходной путь
   (второй Google-аккаунт в Work Profile и т.д.)

### Ограничения

- **Пинг:** Frankfurt → РБ ~60-80 мс. Для чатов/браузера ок, для игр/видеозвонков —
  на грани.
- **Трафик:** Oracle Free Tier — 10 TB/мес. Для личного VPN с запасом.
- **Надёжность:** Oracle может в любой момент заблокировать Free Tier аккаунт.
  PAYG-апгрейд (уже сделан) снижает риск, но не исключает.
- **Один порт:** Xray на :8443, не конфликтует с Caddy на :443.

## Этапы

### Этап 1 — Установка Xray на VPS

1. SSH на VPS: `ssh -i ~/.ssh/id_ed25519_oracle ubuntu@redl-music.duckdns.org`
2. Установить Xray:
   ```bash
   bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
   ```
3. Сгенерировать ключи:
   ```bash
   xray x25519
   ```
   Записать Private key и Public key.

4. Настроить конфиг `/usr/local/etc/xray/config.json`:
   ```json
   {
     "inbounds": [{
       "port": 8443,
       "protocol": "vless",
       "settings": {
         "clients": [{
           "id": "<UUID>",
           "flow": "xtls-rprx-vision"
         }],
         "decryption": "none"
       },
       "streamSettings": {
         "network": "tcp",
         "security": "reality",
         "realitySettings": {
           "dest": "www.apple.com:443",
           "serverNames": ["www.apple.com", "apple.com"],
           "privateKey": "<PRIVATE_KEY>",
           "shortIds": ["<RANDOM_6_HEX>"]
         }
       }
     }],
     "outbounds": [{"protocol": "freedom"}]
   }
   ```
   - `dest`: сайт для мимикрии (apple.com, microsoft.com, youtube.com)
   - `UUID`: `uuidgen` на сервере
   - `shortIds`: 6 случайных HEX-символов

5. Открыть порт в ufw:
   ```bash
   ufw allow 8443/tcp
   ```
   И в Security List подсети Oracle Cloud.

6. Запустить: `systemctl enable --now xray`

### Этап 2 — Клиенты

**Android (v2rayNG):**
1. Установить из Google Play или F-Droid
2. Создать профиль VLESS + REALITY:
   - Адрес: `redl-music.duckdns.org`
   - Порт: 8443
   - UUID: из конфига сервера
   - Flow: `xtls-rprx-vision`
   - Security: `reality`
   - Public Key: из `xray x25519`
   - SNI: `www.apple.com`
   - Fingerprint: `chrome`
   - Short ID: из конфига

**Mac (Sing-box):**
1. `brew install sing-box`
2. Конфиг — аналогично

### Этап 3 — Тестирование

1. Подключиться с Android через v2rayNG
2. Проверить IP: `ping.eu` или `whatismyip.com` в браузере
3. Открыть ChatGPT на Android
4. Если работает → ✅
5. Если нет → копаем Play Integrity, пробуем Work Profile

### Этап 4 — Автоматизация и fallback

- Добавить `cron` для автообновления Xray
- Если ChatGPT через Xray не работает — пробовать:
  - Work Profile + новый Google-аккаунт
  - Альтернативные клиенты (через OpenAI API)
  - Shadowsocks как fallback (менее надёжен, но иногда работает для приложений)

## Связанные проекты

- **Музыкальный сервер:** тот же VPS, Docker, Caddy на :443, Navidrome на :4533
  ([план миграции](music-migration-plan.md))
- **SSH-ключ:** `~/.ssh/id_ed25519_oracle`
- **Oracle Cloud:** PAYG, Frankfurt, 4 OCPU / 24 GB / 200 GB
