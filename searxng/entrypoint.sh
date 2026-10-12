#!/bin/sh
set -eu

TEMPLATE="/etc/searxng/settings.template.yml"
TARGET="/etc/searxng/settings.yml"

cp -f "$TEMPLATE" "$TARGET"

if [ -n "${SEARXNG_SECRET:-}" ]; then
  SECRET="$SEARXNG_SECRET"
else
  SECRET="$(head -c 24 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9')"
  echo "[searxng-entrypoint] SEARXNG_SECRET not set; generated a random" \
       "server.secret_key for this run"
fi

sed -i "s#ultrasecretkey#${SECRET}#g" "$TARGET"

MARGINALIA_API_KEY="${MARGINALIA_API_KEY:-public}"
sed -i "s#__MARGINALIA_API_KEY__#${MARGINALIA_API_KEY}#g" "$TARGET"
if [ -n "${MARGINALIA_API_KEY}" ] && [ "${MARGINALIA_API_KEY}" != "public" ]; then
  sed -i "s#__MARGINALIA_ENABLED__#false#g" "$TARGET"
else
  sed -i "s#__MARGINALIA_ENABLED__#true#g" "$TARGET"
fi

chown -R searxng:searxng /etc/searxng /var/cache/searxng 2>/dev/null || true
if [ "$(id -u)" -eq 0 ]; then
  update-ca-certificates >/dev/null 2>&1 || true
fi

export GRANIAN_PORT="${SEARXNG_PORT:-${GRANIAN_PORT:-8080}}"

exec /usr/local/searxng/.venv/bin/granian searx.webapp:app
