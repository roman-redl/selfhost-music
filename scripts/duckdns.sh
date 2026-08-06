#!/bin/bash
# DuckDNS dynamic DNS updater
# Run: ./scripts/duckdns.sh
# Cron: */5 * * * * /opt/duckdns/duck.sh
#
# Usage: DUCKDNS_TOKEN=xxx DUCKDNS_SUBDOMAIN=myserver ./scripts/duckdns.sh

set -euo pipefail

TOKEN="${DUCKDNS_TOKEN:-}"
SUBDOMAIN="${DUCKDNS_SUBDOMAIN:-}"

if [ -z "$TOKEN" ] || [ -z "$SUBDOMAIN" ]; then
    echo "Usage: DUCKDNS_TOKEN=xxx DUCKDNS_SUBDOMAIN=myserver ./scripts/duckdns.sh"
    exit 1
fi

RESPONSE=$(curl -s "https://www.duckdns.org/update?domains=${SUBDOMAIN}&token=${TOKEN}&ip=")
echo "[$(date -Iseconds)] DuckDNS update: $RESPONSE"
