#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
COMPOSE=(docker compose --env-file backend/.env.production -f docker-compose.production.yml -f docker-compose.core.yml)

if [[ ! -f backend/.env.production ]]; then
  echo "Missing backend/.env.production. Create it from backend/.env.example and set production secrets." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Docker Engine and the Docker Compose plugin are required." >&2
  exit 1
fi

"${COMPOSE[@]}" config -q
"${COMPOSE[@]}" up -d --build
"${COMPOSE[@]}" ps
