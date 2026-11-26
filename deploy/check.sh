#!/usr/bin/env bash
# Verify a deployment: service status, public HTTPS endpoint, and one tiny Claude request.
set -uo pipefail
APP_DIR=/opt/pvp-scanner
ENV_FILE=/etc/pvp-scanner.env
DOMAIN="$(cat /etc/pvp-scanner.domain 2>/dev/null || true)"

if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo." >&2; exit 1; fi

echo "== Service"
systemctl is-active pvp-scanner caddy

echo "== Public endpoint"
curl -fsS "https://$DOMAIN/api/health" && echo || echo "!! https://$DOMAIN is not reachable yet (DNS, firewall port 443, or certificate still pending)"

echo "== Claude"
set -a
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a
cd "$APP_DIR/backend" && runuser -u pvp -- env PVP_SCANNER_HOME=/var/lib/pvp-scanner \
  ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" PVP_AI_MODEL="${PVP_AI_MODEL:-claude-opus-5-5}" \
  "$APP_DIR/.venv/bin/python" -m app.ai_check
