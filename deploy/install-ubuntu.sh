#!/usr/bin/env bash
# One-shot installer for a 24/7 Ubuntu/Debian VM.
# Run as root (or with sudo). Idempotent.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/jaafarsadeq/Mytest.git}"
BRANCH="${BRANCH:-claude/whatsapp-mcp-notifications-5syJ9}"
APP_DIR="/opt/whatsapp-mcp"
APP_USER="whatsapp"

echo "==> Installing system packages"
apt-get update
apt-get install -y --no-install-recommends \
  curl ca-certificates git chromium \
  fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 libcairo2 \
  libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 libnspr4 libnss3 \
  libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 \
  libxfixes3 libxkbcommon0 libxrandr2 \
  python3 make g++

if ! command -v node >/dev/null || [ "$(node -v | cut -d. -f1 | tr -d v)" -lt 18 ]; then
  echo "==> Installing Node.js 20 LTS"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

echo "==> Creating service user '$APP_USER'"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"

echo "==> Cloning repo to $APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
git -C "$APP_DIR" fetch origin "$BRANCH"
git -C "$APP_DIR" checkout "$BRANCH"
git -C "$APP_DIR" pull --ff-only origin "$BRANCH"

echo "==> Installing npm deps"
sudo -u "$APP_USER" -H bash -c "cd '$APP_DIR' && npm install --omit=dev"

if [ ! -f "$APP_DIR/.env" ]; then
  echo "==> Copying .env.example -> .env (edit it before starting!)"
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
fi

mkdir -p "$APP_DIR/data"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Installing systemd unit"
install -m 0644 "$APP_DIR/deploy/whatsapp-bridge.service" /etc/systemd/system/whatsapp-bridge.service
systemctl daemon-reload
systemctl enable whatsapp-bridge.service

cat <<EOF

================================================================
Almost done.

1. Edit /opt/whatsapp-mcp/.env and set:
     NTFY_TOPIC=<your hard-to-guess topic>
     PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

2. Start the service:
     sudo systemctl start whatsapp-bridge

3. Watch the logs and scan the QR with WhatsApp on your phone:
     sudo journalctl -u whatsapp-bridge -f

   (WhatsApp -> Settings -> Linked Devices -> Link a Device)

4. After "[wa] client ready." messages will be forwarded to your
   phone via ntfy.sh. The service auto-restarts on crash and on
   reboot.
================================================================
EOF
