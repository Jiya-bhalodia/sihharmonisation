#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"
COMPOSE_ENV_FILE="${COMPOSE_ENV_FILE:-$REPO_ROOT/backend/.env.production}"
if [[ "$COMPOSE_ENV_FILE" != /* ]]; then
  COMPOSE_ENV_FILE="$REPO_ROOT/$COMPOSE_ENV_FILE"
fi
COMPOSE=(docker compose --env-file "$COMPOSE_ENV_FILE" -f docker-compose.production.yml -f docker-compose.core.yml)

usage() {
  echo "Usage: $0 BACKUP_DIRECTORY --confirm" >&2
  echo "Restore applies the archived database objects and overlays MinIO/DATA_DIR files; a rollback backup is made first." >&2
  exit 2
}

[[ $# -eq 2 && "$2" == "--confirm" ]] || usage
if [[ "$1" = /* ]]; then
  SOURCE="$(cd "$1" && pwd)"
else
  SOURCE="$(cd "$REPO_ROOT/$1" && pwd)"
fi
[[ -s "$SOURCE/database.dump" ]] || { echo "Missing database.dump in $SOURCE" >&2; exit 1; }
[[ -s "$SOURCE/data-state.tar.gz" ]] || { echo "Missing data-state.tar.gz in $SOURCE" >&2; exit 1; }
[[ -s "$SOURCE/minio-data.tar.gz" ]] || { echo "Missing minio-data.tar.gz in $SOURCE" >&2; exit 1; }
[[ -f "$COMPOSE_ENV_FILE" ]] || { echo "Missing Compose environment file: $COMPOSE_ENV_FILE" >&2; exit 1; }

# Always make a rollback copy before stopping application writers or restoring data.
"$REPO_ROOT/backup.sh"
restart_on_exit=1
resume_services() {
  if [[ "$restart_on_exit" == "1" ]]; then
    "${COMPOSE[@]}" up -d minio backend worker || true
  fi
}
trap resume_services EXIT
"${COMPOSE[@]}" stop backend worker minio

# PGPASSWORD is supplied to the backup service by Compose. --clean replaces
# objects represented in the dump; newer objects absent from it may remain.
"${COMPOSE[@]}" run --rm --no-deps -v "$SOURCE:/restore:ro" --entrypoint /bin/sh backup -c \
  'pg_restore --clean --if-exists --no-owner --no-privileges -h db -U bhumix -d bhumix /restore/database.dump'

# Restore MinIO's raw volume while its server is stopped. Extraction overlays
# archived files and preserves version metadata; it does not prune newer files.
"${COMPOSE[@]}" run --rm --no-deps --user 0:0 -v "$SOURCE:/restore:ro" --entrypoint tar backup \
  -xzf /restore/minio-data.tar.gz -C /minio

# Restore the shared DATA_DIR snapshot archive as an overlay.
"${COMPOSE[@]}" run --rm --no-deps --user 0:0 -v "$SOURCE:/restore:ro" --entrypoint tar backup \
  -xzf /restore/data-state.tar.gz -C /data

"${COMPOSE[@]}" up -d minio backend worker
restart_on_exit=0
trap - EXIT
printf 'Restore completed from %s\n' "$SOURCE"
