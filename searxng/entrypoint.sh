#!/bin/sh
# Renders /etc/searxng/settings.yml from the tracked template, injecting the
# server.secret_key from the SEARXNG_SECRET env var (random fallback). This
# keeps the real secret out of the git-tracked template while still letting
# every other line of settings.yml be version-controlled.
#
# Replaces the stock image entrypoint for the config-rendering step; the CA
# refresh and ownership fix are replicated so HTTPS engines and granian still
# behave as stock.
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

# Use '#' as the sed delimiter: the generated value is base64 [A-Za-z0-9],
# and an operator-supplied secret is unlikely to contain '#'.
sed -i "s#ultrasecretkey#${SECRET}#g" "$TARGET"

# Match the stock entrypoint: fix ownership and refresh the CA bundle, since
# the engines reach upstream search services over HTTPS.
chown -R searxng:searxng /etc/searxng /var/cache/searxng 2>/dev/null || true
if [ "$(id -u)" -eq 0 ]; then
  update-ca-certificates >/dev/null 2>&1 || true
fi

# granian reads its host/port/worker config from the GRANIAN_* env already set
# on the container; mirror the stock port override for parity.
export GRANIAN_PORT="${SEARXNG_PORT:-${GRANIAN_PORT:-8080}}"

exec /usr/local/searxng/.venv/bin/granian searx.webapp:app
