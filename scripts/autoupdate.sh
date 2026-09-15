#!/usr/bin/env bash
# Auto-update the locally built firecrawl images. Watchtower only covers
# registry images (searxng, redis, rabbitmq, foundationdb); this script
# handles the source-built ones: api, playwright-service, nuq-postgres.
# Policy: merge latest upstream tag; on conflict/failure abort and log.
set -u
export HUSKY=0
cd /opt/firecrawl || exit 1
LOG=/var/log/firecrawl-autoupdate.log
log() { echo "[$(date -Iseconds)] $*" >> "$LOG"; }

if ! git diff-index --quiet HEAD -- 2>/dev/null; then
  log "SKIP: tracked working tree not clean"
  exit 0
fi

git fetch --tags -q origin 2>>"$LOG" || { log "ERROR: git fetch failed"; exit 1; }
LATEST=$(git tag --list "v2.*" --sort=-v:refname | head -1)
[ -n "$LATEST" ] || { log "ERROR: no v2.* tag found"; exit 1; }
if git merge-base --is-ancestor "$LATEST" HEAD 2>/dev/null; then
  exit 0
fi

log "update: $(git describe --tags 2>/dev/null || git rev-parse --short HEAD) -> $LATEST"
if ! git merge "$LATEST" --no-edit >>"$LOG" 2>&1; then
  git merge --abort 2>/dev/null
  log "ERROR: conflicts merging $LATEST; MANUAL UPDATE REQUIRED"
  exit 1
fi

if ! docker run --rm -v /opt/firecrawl/apps/api:/app -w /app node:22-slim bash -c \
  "corepack enable && corepack prepare pnpm@11.4.0 --activate && pnpm install --lockfile-only --ignore-scripts" >>"$LOG" 2>&1; then
  git reset --hard ORIG_HEAD >>"$LOG" 2>&1
  log "ERROR: lockfile regen failed; rolled back source"
  exit 1
fi
if [ -n "$(git status --porcelain apps/api/pnpm-lock.yaml)" ]; then
  git add apps/api/pnpm-lock.yaml
  git commit -q -m "chore: regen pnpm-lock for $LATEST"
fi

rollback() {
  git reset --hard ORIG_HEAD >>"$LOG" 2>&1
  docker compose build api playwright-service nuq-postgres >>"$LOG" 2>&1
  docker compose up -d >>"$LOG" 2>&1
  log "ERROR: $1; rolled back to $(git describe --tags 2>/dev/null)"
}

if ! docker compose build api playwright-service nuq-postgres >>"$LOG" 2>&1; then
  rollback "build failed"; exit 1
fi
if ! docker compose up -d >>"$LOG" 2>&1; then
  rollback "up -d failed"; exit 1
fi
sleep 25
if ! curl -fsS -m 30 -X POST http://localhost:3003/v1/scrape \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://example.com\",\"formats\":[\"markdown\"]}" 2>>"$LOG" \
  | grep -q "\"success\":true"; then
  rollback "smoke test failed"; exit 1
fi
docker image prune -f >>"$LOG" 2>&1
log "OK: now on $(git describe --tags 2>/dev/null || git rev-parse --short HEAD)"
