#!/bin/sh
# Nightly PostgreSQL backup with simple rotation. Run from cron on the host, e.g.
#   15 3 * * *  cd /srv/forevertracker && ./deploy/backup.sh >> /var/log/forevertracker-backup.log 2>&1
# Copy the backup directory off the host (object storage, another machine): a backup on the
# same disk is not a backup. Restore steps: docs/DEPLOYMENT.md, "Backups and restore".
set -eu

PROJECT="${COMPOSE_PROJECT:-forevertracker}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/forevertracker}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BACKUP_DIR"
docker compose -p "$PROJECT" -f docker-compose.prod.yml exec -T db \
  pg_dump -U forevertracker -d forevertracker --format=custom --compress=6 \
  > "$BACKUP_DIR/forevertracker-$STAMP.dump"

# Fail loudly if the dump is unusable.
docker compose -p "$PROJECT" -f docker-compose.prod.yml exec -T db pg_restore --list \
  < "$BACKUP_DIR/forevertracker-$STAMP.dump" > /dev/null

find "$BACKUP_DIR" -name 'forevertracker-*.dump' -mtime "+$KEEP_DAYS" -delete
echo "backup ok: $BACKUP_DIR/forevertracker-$STAMP.dump"
