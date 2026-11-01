#!/usr/bin/env bash
# Consistent EventPass backup (database + uploaded images) copied out of the Docker volume.
# Run daily via cron and automatically before every deployment:
#   15 3 * * *  /opt/cmgi-apps/infrastructure/deployment/backup.sh >> /var/log/cmgi-backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -f .env ] && set -a && . ./.env && set +a

DEST="${BACKUP_DEST:-/var/backups/cmgi-apps}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"

if [ -z "$(docker compose ps -q --status running eventpass-api 2>/dev/null)" ]; then
  echo "$(date -Is) eventpass-api is not running — nothing to back up."
  exit 0
fi

# 1. Snapshot inside the container (SQLite online backup API + integrity and row-count check).
docker compose exec -T eventpass-api python backup.py --keep 14
NAME=$(docker compose exec -T eventpass-api sh -c 'ls -1 /data/backups | tail -n 1' | tr -d '\r')

# 2. Copy the snapshot to the host so it survives even if the volume is lost.
mkdir -p "$DEST"
docker compose exec -T eventpass-api tar -C /data/backups -czf - "$NAME" > "$DEST/eventpass-$NAME.tar.gz"
find "$DEST" -name 'eventpass-*.tar.gz' -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) backup stored: $DEST/eventpass-$NAME.tar.gz"

# 3. Sermon Intelligence (database + recordings).
if [ -n "$(docker compose ps -q --status running sermon-api 2>/dev/null)" ]; then
  docker compose exec -T sermon-api python backup.py --keep 7
  SNAME=$(docker compose exec -T sermon-api sh -c 'ls -1 /data/backups | tail -n 1' | tr -d '\r')
  docker compose exec -T sermon-api tar -C /data/backups -czf - "$SNAME" > "$DEST/sermon-$SNAME.tar.gz"
  find "$DEST" -name 'sermon-*.tar.gz' -mtime +"$KEEP_DAYS" -delete
  echo "$(date -Is) backup stored: $DEST/sermon-$SNAME.tar.gz"
fi
# Off-site copy (recommended), e.g. to a Hetzner Storage Box with rclone:
#   rclone copy "$DEST" storagebox:cmgi-apps-backups
