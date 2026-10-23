#!/usr/bin/env bash
set -euo pipefail
# Run on the development computer. Changes only static UI files; radio keeps playing.
TARGET=${1:-defox@192.168.0.150}
SOURCE=$(cd "$(dirname "$0")/.." && pwd)
if [[ ! -f "$SOURCE/frontend/dist/index.html" ]]; then
  echo 'Nejprve spusťte npm --prefix frontend run build.' >&2
  exit 1
fi
STAGE=$(ssh "$TARGET" 'test -f /opt/piradio/frontend/dist/index.html && mktemp -d /tmp/piradio-web.XXXXXXXX')
if [[ ! "$STAGE" =~ ^/tmp/piradio-web\.[a-zA-Z0-9]+$ ]]; then
  echo 'Nelze připravit dočasný adresář na Raspberry Pi.' >&2
  exit 1
fi
rsync -a "$SOURCE/frontend/dist/" "$TARGET:$STAGE/"
# Keep old hashed assets for already-open phones; publish the new index last/atomically.
ssh -t "$TARGET" "set -e; sudo rsync -a --exclude=index.html '$STAGE/' /opt/piradio/frontend/dist/; sudo install -m 644 '$STAGE/index.html' /opt/piradio/frontend/dist/.index.html.new; sudo mv /opt/piradio/frontend/dist/.index.html.new /opt/piradio/frontend/dist/index.html; rm -rf -- '$STAGE'"
echo 'Webové rozhraní je aktualizované. Obnovte stránku v telefonu. Přehrávač nebyl restartován.'
