#!/usr/bin/env bash
# Controlled update on the VPS: backup -> build -> start -> health check -> automatic rollback on failure.
#   ./deploy.sh              # deploy origin/main
#   ./deploy.sh v1.2.0       # deploy a tag or commit (also used for manual rollback)
# Database migrations in EventPass only ever ADD columns, so the previous version
# still runs on a migrated database — that is what makes the rollback safe.
set -euo pipefail

# Wrapped in a function: bash reads it completely before running it, so checking out
# a newer version of this very file mid-run cannot change what is executed.
main() {
  cd "$(dirname "$0")/../.."
  REF="${1:-origin/main}"
  DIR=infrastructure/deployment

  [ -f .env ] || { echo ".env missing — copy .env.example and fill it in first."; exit 1; }

  PREVIOUS=$(git rev-parse HEAD)
  "$DIR/backup.sh"

  git fetch --quiet --tags origin
  git checkout --quiet --detach "$REF"
  export CMGI_VERSION=$(git rev-parse --short HEAD)
  echo "Deploying $CMGI_VERSION (previous: ${PREVIOUS:0:7})"

  # Ready-made images (Body of Christ, PostgreSQL) are downloaded; our own apps are built here.
  docker compose pull --ignore-buildable --quiet
  docker compose build
  docker compose up -d --remove-orphans

  if ! "$DIR/healthcheck.sh"; then
    echo "Deployment failed — rolling back to ${PREVIOUS:0:7}"
    docker compose logs --tail 50 eventpass-api || true
    git checkout --quiet --detach "$PREVIOUS"
    export CMGI_VERSION=$(git rev-parse --short HEAD)
    docker compose up -d --build --remove-orphans
    "$DIR/healthcheck.sh" || echo "Rollback is unhealthy too — check 'docker compose logs'."
    exit 1
  fi

  git rev-parse HEAD > .deployed-version
  docker image prune -f --filter "until=168h" > /dev/null
  echo "Deployed $CMGI_VERSION."
}

main "$@"
