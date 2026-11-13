#!/usr/bin/env bash
# One-time setup of the Social Uploader agent on an Ubuntu/Debian server (for example Oracle Cloud).
# Run it as your normal user (not root):   bash ~/social-uploader/server/setup_server.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="$(id -un)"
say() { printf '\n==> %s\n' "$*"; }

command -v apt-get >/dev/null || { echo "This script is for Ubuntu/Debian (it needs apt-get)."; exit 1; }
[ "$(id -u)" -ne 0 ] || { echo "Run this as your normal user (for example ubuntu), not as root. It uses sudo when needed."; exit 1; }
[ -f "$DIR/agent.py" ] || { echo "agent.py was not found in $DIR. Upload the project files first (see the guide, Part D)."; exit 1; }

say "1/6  Installing system packages"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip ffmpeg curl ca-certificates rclone

say "2/6  Installing cloudflared (the free tunnel Instagram needs)"
ARCH="$(dpkg --print-architecture)"   # amd64 or arm64
if ! command -v cloudflared >/dev/null; then
  curl -fsSL -o /tmp/cloudflared.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb"
  sudo dpkg -i /tmp/cloudflared.deb
  rm -f /tmp/cloudflared.deb
fi
cloudflared --version

say "3/6  Swap space (helps small servers)"
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$MEM_MB" -lt 2000 ] && ! swapon --show | grep -q .; then
  sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
else
  echo "Not needed."
fi

say "4/6  Python environment"
cd "$DIR"
python3 -m venv venv
./venv/bin/pip install --upgrade pip >/dev/null
./venv/bin/pip install -r requirements.txt
mkdir -p inbox scheduled done skipped

say "5/6  Installing the background service"
sudo sed -e "s|__USER__|$RUN_USER|g" -e "s|__DIR__|$DIR|g" "$DIR/server/social-uploader.service" \
  | sudo tee /etc/systemd/system/social-uploader.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable social-uploader >/dev/null

say "6/6  Checking your setup"
chmod 600 "$DIR/.env" "$DIR/token.json" 2>/dev/null || true
MISSING=0
for f in .env settings.json; do
  [ -f "$DIR/$f" ] || { echo "MISSING: $f  (upload it from your PC, see the guide)"; MISSING=1; }
done
[ -f "$DIR/token.json" ] || echo "NOTE: token.json is missing. YouTube will not work until you upload it."
./venv/bin/python agent.py --check || true

if rclone listremotes 2>/dev/null | grep -q '^gdrive:'; then
  ( crontab -l 2>/dev/null | grep -v 'sync_inbox.sh' || true; echo "* * * * * /bin/bash $DIR/server/sync_inbox.sh" ) | crontab -
  echo "Google Drive sync is ON: videos saved in the Drive folder 'social-inbox' move to the agent's inbox every minute."
else
  echo "Google Drive sync is not set up yet (guide, Part G). Run this script again afterwards."
fi

if [ "$MISSING" -eq 0 ]; then
  sudo systemctl restart social-uploader
  sleep 4
  systemctl --no-pager --lines=6 status social-uploader || true
  echo
  echo "Done. Send /status to your Telegram bot. (Make sure the agent on your Windows PC is stopped.)"
else
  echo
  echo "Upload the missing files, then run:  sudo systemctl restart social-uploader"
fi
