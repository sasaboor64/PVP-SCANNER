#!/usr/bin/env bash
# Install or update PvP Scanner on a fresh Ubuntu server (AWS Lightsail).
#
# First install:   curl -fsSL https://raw.githubusercontent.com/sasaboor64/PVP-SCANNER/main/deploy/setup.sh | sudo DOMAIN=yourname.duckdns.org bash
# Update later:    sudo bash /opt/pvp-scanner/deploy/setup.sh
#
# Optional: BRANCH=<git branch> (default: main). DOMAIN and BRANCH are remembered for updates.
set -euo pipefail

REPO="https://github.com/sasaboor64/PVP-SCANNER.git"
APP_DIR=/opt/pvp-scanner
DATA_DIR=/var/lib/pvp-scanner
ENV_FILE=/etc/pvp-scanner.env
DOMAIN_FILE=/etc/pvp-scanner.domain
BRANCH_FILE=/etc/pvp-scanner.branch

if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo." >&2; exit 1; fi
if [ -z "${DOMAIN:-}" ] && [ -f "$DOMAIN_FILE" ]; then DOMAIN="$(cat "$DOMAIN_FILE")"; fi
if [ -z "${DOMAIN:-}" ]; then echo "Set DOMAIN, e.g. sudo DOMAIN=yourname.duckdns.org bash setup.sh" >&2; exit 1; fi
if ! [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]]; then echo "DOMAIN must be a plain host name like yourname.duckdns.org" >&2; exit 1; fi
echo "$DOMAIN" > "$DOMAIN_FILE"
if [ -z "${BRANCH:-}" ] && [ -f "$BRANCH_FILE" ]; then BRANCH="$(cat "$BRANCH_FILE")"; fi
BRANCH="${BRANCH:-main}"
echo "$BRANCH" > "$BRANCH_FILE"

echo "==> Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3-venv git curl gnupg debian-keyring debian-archive-keyring apt-transport-https
if ! command -v caddy >/dev/null; then
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q
  apt-get install -y -q caddy
fi

echo "==> Fetching code ($BRANCH)"
id pvp >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin pvp
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch -q origin "$BRANCH"
  git -C "$APP_DIR" checkout -q -B "$BRANCH" FETCH_HEAD
  git -C "$APP_DIR" reset -q --hard FETCH_HEAD
else
  git clone -q --branch "$BRANCH" "$REPO" "$APP_DIR"
fi

echo "==> Installing Python dependencies"
[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/backend/requirements.txt"

echo "==> Configuring services"
install -d -m 750 -o pvp -g pvp "$DATA_DIR"
if [ ! -f "$ENV_FILE" ]; then
  sed "s/{DOMAIN}/$DOMAIN/g" "$APP_DIR/deploy/pvp-scanner.env.example" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  NEW_ENV=1
fi
install -m 644 "$APP_DIR/deploy/pvp-scanner.service" /etc/systemd/system/pvp-scanner.service
sed "s/{DOMAIN}/$DOMAIN/g" "$APP_DIR/deploy/Caddyfile" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
systemctl daemon-reload
systemctl enable -q pvp-scanner caddy
systemctl restart pvp-scanner
systemctl reload caddy 2>/dev/null || systemctl restart caddy

sleep 2
if curl -fsS http://127.0.0.1:8000/api/health >/dev/null; then
  echo "==> API is running."
else
  echo "!! API did not start. See: sudo journalctl -u pvp-scanner -n 50" >&2
fi
echo
echo "Site: https://$DOMAIN"
if [ -n "${NEW_ENV:-}" ] || ! grep -q '^ANTHROPIC_API_KEY=.\+' "$ENV_FILE"; then
  echo "Next: add your Claude API key:"
  echo "  sudo nano $ENV_FILE        (fill in ANTHROPIC_API_KEY=...)"
  echo "  sudo systemctl restart pvp-scanner"
  echo "  sudo bash $APP_DIR/deploy/check.sh"
fi
