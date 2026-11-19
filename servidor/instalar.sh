#!/usr/bin/env bash
# Instala el motor de CLIPPER en un servidor Linux (Ubuntu/Debian) con UN comando:
#   curl -fsSL -H "Authorization: Bearer TOKEN" https://raw.githubusercontent.com/cloviz12/clipper/main/servidor/instalar.sh | sudo -E bash
# Pide las llaves una vez, deja el motor corriendo siempre y lo actualiza solo cada vez que cambie main.
set -euo pipefail
REPO="${CLIPPER_REPO:-cloviz12/clipper}"
DIR=/opt/clipper

if [ "$(id -u)" != 0 ]; then echo "Ejecutalo con sudo"; exit 1; fi
leer() { local v; read -r -p "$1: " v < /dev/tty; echo "$v"; }
leer_secreto() { local v; read -r -s -p "$1: " v < /dev/tty; echo >&2; echo "$v"; }

echo "== Docker =="
if ! command -v docker >/dev/null; then curl -fsSL https://get.docker.com | sh; fi
systemctl enable --now docker

echo "== Codigo =="
TOKEN="${GITHUB_TOKEN:-}"
[ -z "$TOKEN" ] && TOKEN=$(leer_secreto "Token de GitHub de solo lectura (el mismo de las actualizaciones)")
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull -q
else
  apt-get install -y -q git >/dev/null
  git clone -q "https://x-access-token:${TOKEN}@github.com/${REPO}.git" "$DIR"
fi

ENV="$DIR/worker/.env"
if [ ! -f "$ENV" ]; then
  echo "== Llaves (quedan solo en este servidor) =="
  {
    echo "SUPABASE_URL=$(leer 'URL de Supabase (https://xxxx.supabase.co)')"
    echo "SUPABASE_SERVICE_ROLE_KEY=$(leer_secreto 'Llave service_role de Supabase')"
    echo "ANTHROPIC_API_KEY=$(leer_secreto 'Llave de Claude (Enter si no hay)')"
    echo "GOOGLE_CLIENT_ID=$(leer 'Google Client ID (Enter si no hay)')"
    echo "GOOGLE_CLIENT_SECRET=$(leer_secreto 'Google Client secret (Enter si no hay)')"
    echo "TIKTOK_CLIENT_KEY=$(leer 'TikTok Client key (Enter si no hay)')"
    echo "TIKTOK_CLIENT_SECRET=$(leer_secreto 'TikTok Client secret (Enter si no hay)')"
  } > "$ENV"
  chmod 600 "$ENV"
fi

echo "== Encendiendo el motor (la primera vez tarda varios minutos) =="
cd "$DIR/servidor"
docker compose up -d --build

echo "== Actualizacion automatica cada 10 minutos =="
chmod +x "$DIR/servidor/actualizar.sh"
echo "*/10 * * * * root $DIR/servidor/actualizar.sh >> /var/log/clipper-actualizar.log 2>&1" > /etc/cron.d/clipper
echo
echo "LISTO. En la app, arriba a la derecha, debe aparecer 'servidor' como motor encendido."
echo "Ver lo que hace:  docker logs -f clipper-motor"
