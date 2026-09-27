#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"
COMPOSE_ENV_FILE="${COMPOSE_ENV_FILE:-$REPO_ROOT/backend/.env.production}"
if [[ "$COMPOSE_ENV_FILE" != /* ]]; then
  COMPOSE_ENV_FILE="$REPO_ROOT/$COMPOSE_ENV_FILE"
fi
COMPOSE=(docker compose --env-file "$COMPOSE_ENV_FILE" -f docker-compose.production.yml -f docker-compose.core.yml)
BACKUP_ROOT="${BACKUP_DIR:-$REPO_ROOT/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_ROOT/$STAMP"

if [[ ! -f "$COMPOSE_ENV_FILE" ]]; then
  echo "Missing Compose environment file: $COMPOSE_ENV_FILE" >&2
  exit 1
fi
mkdir -p "$DEST"

# Quiesce writers and stop the single-node MinIO server before archiving its
# data volume. This creates a brief service outage but preserves object versions.
restart_on_exit=1
resume_services() {
  if [[ "$restart_on_exit" == "1" ]]; then
    "${COMPOSE[@]}" up -d minio backend worker || true
  fi
}
trap resume_services EXIT
"${COMPOSE[@]}" stop backend worker minio

# PGPASSWORD is supplied to the backup service through Compose from the
# production environment file; pg_dump streams a custom-format archive to host.
"${COMPOSE[@]}" exec -T backup pg_dump -h db -U bhumix -d bhumix -Fc > "$DEST/database.dump"

# These tar archives read the named volumes while the writers are stopped.
"${COMPOSE[@]}" run --rm --no-deps --user 0:0 -v "$DEST:/backup" --entrypoint tar backup \
  -czf /backup/data-state.tar.gz -C /data .
"${COMPOSE[@]}" run --rm --no-deps --user 0:0 -v "$DEST:/backup" --entrypoint tar backup \
  -czf /backup/minio-data.tar.gz -C /minio .

"${COMPOSE[@]}" up -d minio backend worker
restart_on_exit=0
trap - EXIT
printf 'Backup created at %s\n' "$DEST"
