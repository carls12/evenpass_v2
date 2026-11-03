#!/usr/bin/env bash
# Waits until all CMGI Apps containers report "healthy" (max. ~2 minutes).
set -uo pipefail
cd "$(dirname "$0")/../.."
# All services of the active profiles (Body of Christ only counts once it is enabled).
SERVICES=$(docker compose config --services)
for _ in $(seq 1 40); do
  unhealthy=0
  for service in $SERVICES; do
    id=$(docker compose ps -aq "$service")
    # Long-running services must be "healthy"; one-shot jobs (db-setup) must have finished with exit code 0.
    status=$([ -n "$id" ] && docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}:{{.State.ExitCode}}{{end}}' "$id" 2>/dev/null || echo missing)
    case "$status" in healthy|exited:0) ;; *) unhealthy=1 ;; esac
  done
  [ "$unhealthy" = 0 ] && { echo "All services healthy."; exit 0; }
  sleep 3
done
docker compose ps
echo "Services did not become healthy."
exit 1
