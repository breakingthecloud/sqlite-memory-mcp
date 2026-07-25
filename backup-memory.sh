#!/bin/bash
# backup-memory.sh — Backup memory.db to local timestamped copy
#
# Usage: ./backup-memory.sh
# Cron:  0 6 * * * /path/to/backup-memory.sh  (daily at 6AM)

DB_PATH="${MEMORY_DB_PATH:-$HOME/dev/breakingthecloud/.kiro/memory.db}"
BACKUP_DIR="$HOME/dev/breakingthecloud/.kiro/memory-backups"
KEEP_DAYS=30

mkdir -p "$BACKUP_DIR"

# Create timestamped backup
TIMESTAMP=$(date +%Y-%m-%d)
BACKUP_FILE="$BACKUP_DIR/memory-$TIMESTAMP.db"

if [ -f "$DB_PATH" ]; then
    cp "$DB_PATH" "$BACKUP_FILE"
    echo "✅ Backed up: $BACKUP_FILE ($(du -sh "$BACKUP_FILE" | cut -f1))"
else
    echo "❌ Source not found: $DB_PATH"
    exit 1
fi

# Rotate: delete backups older than N days
find "$BACKUP_DIR" -name "memory-*.db" -mtime +$KEEP_DAYS -delete
REMAINING=$(ls "$BACKUP_DIR"/memory-*.db 2>/dev/null | wc -l | tr -d ' ')
echo "   Retained $REMAINING backups (last $KEEP_DAYS days)"
