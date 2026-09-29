#!/bin/bash
# selfhost-music VPS setup script
# Run as root on fresh Ubuntu 24.04 ARM instance
# Usage: curl -sSL https://raw.githubusercontent.com/roman-redl/selfhost-music/main/scripts/setup-vps.sh | bash -s -- <duckdns-token> <duckdns-subdomain>

set -euo pipefail

DUCKDNS_TOKEN="${1:-}"
DUCKDNS_SUBDOMAIN="${2:-}"

if [ -z "$DUCKDNS_TOKEN" ] || [ -z "$DUCKDNS_SUBDOMAIN" ]; then
    echo "Usage: $0 <duckdns-token> <duckdns-subdomain>"
    echo "  Example: $0 abc123 myserver"
    echo "  Result:  myserver.duckdns.org"
    exit 1
fi

DOMAIN="${DUCKDNS_SUBDOMAIN}.duckdns.org"
GIT_REPO="https://github.com/roman-redl/selfhost-music.git"
APP_DIR="/opt/selfhost-music"

echo "=== [1/8] System update ==="
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq curl wget git ufw inotify-tools davfs2

echo "=== [2/8] Configure firewall (UFW) ==="
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
ufw status verbose

echo "=== [3/8] SSH hardening ==="
sed -i 's/^#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#PermitRootLogin yes/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
# Ubuntu 24.04: SSH service is "ssh" (socket-activated), not "sshd"
systemctl restart ssh

echo "=== [4/8] Install Docker ==="
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker ubuntu
    systemctl enable docker
fi

echo "=== [5/8] DuckDNS dynamic DNS ==="
DUCKDNS_DIR="/opt/duckdns"
mkdir -p "$DUCKDNS_DIR"
cat > "$DUCKDNS_DIR/duck.sh" << EOF
#!/bin/bash
curl -s "https://www.duckdns.org/update?domains=${DUCKDNS_SUBDOMAIN}&token=${DUCKDNS_TOKEN}&ip=" -o /dev/null
echo "DuckDNS updated: \$(date)"
EOF
chmod +x "$DUCKDNS_DIR/duck.sh"

# Run once now
bash "$DUCKDNS_DIR/duck.sh"

# Cron: every 5 minutes
(crontab -l 2>/dev/null || true; echo "*/5 * * * * bash $DUCKDNS_DIR/duck.sh >> $DUCKDNS_DIR/duck.log 2>&1") | crontab -

echo "=== [6/8] Clone repo ==="
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR" && git pull
else
    git clone "$GIT_REPO" "$APP_DIR"
fi

echo "=== [7/8] Setup .env ==="
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    sed -i "s/music.yourdomain.duckdns.org/$DOMAIN/" "$APP_DIR/.env"
fi

echo "=== [8/8] Start services ==="
cd "$APP_DIR"
docker compose up -d

echo ""
echo "=============================================="
echo " Setup complete!"
echo "=============================================="
echo ""
echo " Domain:  https://$DOMAIN"
echo " App dir: $APP_DIR"
echo ""
echo " Check status:  cd $APP_DIR && docker compose ps"
echo " Check logs:    cd $APP_DIR && docker compose logs -f"
echo ""
echo " Next steps:"
echo "  1. Wait ~1 min for Let's Encrypt certificate"
echo "  2. Open https://$DOMAIN in browser"
echo "  3. Create admin user in Navidrome web UI"
echo "=============================================="
