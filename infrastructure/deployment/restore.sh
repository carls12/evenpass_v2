#!/usr/bin/env bash
# Restore EventPass data into the running stack.
#   ./restore.sh /var/backups/cmgi-apps/eventpass-20260101-031500-manual.tar.gz   # a backup from backup.sh
#   ./restore.sh ./eventpass.sqlite3                                              # import a database file
# The current state is always saved first (…-pre-restore inside the volume).
set -euo pipefail
cd "$(dirname "$0")/../.."
SRC="${1:?usage: restore.sh <backup.tar.gz | database.sqlite3>}"
[ -f "$SRC" ] || { echo "Not found: $SRC"; exit 1; }

docker compose exec -T eventpass-api sh -c 'rm -rf /data/restore && mkdir -p /data/restore'
case "$SRC" in
  *.tar.gz)
    docker compose exec -T eventpass-api tar -C /data/restore -xzf - < "$SRC"
    TARGET=$(docker compose exec -T eventpass-api sh -c 'ls -1d /data/restore/*/ | head -n 1' | tr -d '\r') ;;
  *)
    docker compose exec -T eventpass-api sh -c 'cat > /data/restore/import.sqlite3' < "$SRC"
    TARGET=/data/restore/import.sqlite3 ;;
esac

read -r -p "Replace the live EventPass data with $SRC? Type 'yes': " answer
[ "$answer" = "yes" ] || { echo "Aborted — nothing changed."; exit 1; }

docker compose exec -T eventpass-api python backup.py --restore "$TARGET"
docker compose restart eventpass-api
docker compose exec -T eventpass-api sh -c 'rm -rf /data/restore'
echo "Restore finished."
