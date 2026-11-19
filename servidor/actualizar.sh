#!/usr/bin/env bash
# Si main cambio en GitHub, baja el codigo nuevo y reconstruye el motor (lo llama cron cada 10 min).
set -euo pipefail
DIR=/opt/clipper
cd "$DIR"
git fetch -q origin main
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
  echo "$(date) actualizando a $(git rev-parse --short origin/main)"
  git reset -q --hard origin/main
  cd servidor && docker compose up -d --build
  docker image prune -f >/dev/null
fi
