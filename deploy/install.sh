#!/usr/bin/env bash
set -euo pipefail
# Spouštějte až na Raspberry Pi, z kořene kompletního projektu.
if [[ "$(uname -s)" != Linux || "$(uname -m)" != aarch64 ]]; then
  echo 'Instalátor je určen pro Raspberry Pi OS 64-bit (aarch64).' >&2; exit 1
fi
if [[ ${EUID} -ne 0 ]]; then echo 'Spusťte přes sudo bash deploy/install.sh.' >&2; exit 1; fi
if ! command -v node >/dev/null || ! node -e 'if(Number(process.versions.node.split(".")[0]) < 22) process.exit(1)'; then
  echo 'Nejdříve nainstalujte Node.js 22+ ze zdroje pro vaši verzi Raspberry Pi OS; yt-dlp ho potřebuje pro YouTube.' >&2; exit 1
fi
SOURCE=$(cd "$(dirname "$0")/.." && pwd)
if [[ ! -f "$SOURCE/frontend/dist/index.html" ]]; then echo 'Nejdříve sestavte frontend: npm ci && npm run build ve frontend/.' >&2; exit 1; fi
apt-get update
apt-get install -y python3 python3-venv mpv alsa-utils rsync
id piradio &>/dev/null || useradd --system --user-group --home-dir /var/lib/piradio --shell /usr/sbin/nologin piradio
usermod -aG audio piradio
install -d -m 755 /opt/piradio /opt/piradio/frontend/dist
install -d -m 700 -o piradio -g piradio /var/lib/piradio
# Data a tajemství nejsou součástí synchronizace. Existující nastavení zachováme.
rsync -a --exclude='.venv' --exclude='node_modules' --exclude='.env*' --exclude='data' --exclude='.git' "$SOURCE/backend/" /opt/piradio/backend/
rsync -a "$SOURCE/frontend/dist/" /opt/piradio/frontend/dist/
python3 -m venv /opt/piradio/.venv
/opt/piradio/.venv/bin/pip install -r /opt/piradio/backend/requirements.txt
if [[ ! -f /etc/piradio.env ]]; then
  umask 077
  TOKEN=$(/opt/piradio/.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')
  printf 'PIRADIO_TOKEN=%s\nPIRADIO_DATA=/var/lib/piradio\nPIRADIO_DEMO=0\n' "$TOKEN" > /etc/piradio.env
fi
chmod 600 /etc/piradio.env
install -m 644 "$SOURCE/deploy/piradio.service" /etc/systemd/system/piradio.service
systemctl daemon-reload
systemctl enable piradio.service
systemctl restart piradio.service
echo 'Hotovo. Stav: systemctl status piradio. Token je v /etc/piradio.env; nesdílejte jej.'
