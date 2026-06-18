#!/usr/bin/env bash
#
# Database backup helper for the NEPSE AI Trading platform (Phase 14).
#
# Creates a timestamped pg_dump in custom format and prunes old backups.
# Reads DATABASE_URL from the environment (falls back to .env if present).
#
# Usage:
#   ./scripts/backup_db.sh [BACKUP_DIR] [RETENTION]
#
#   BACKUP_DIR  Directory to write dumps to (default: ./backups)
#   RETENTION   Number of most recent dumps to keep (default: 14)

set -euo pipefail

BACKUP_DIR="${1:-./backups}"
RETENTION="${2:-14}"

# Load DATABASE_URL from .env if not already set.
if [[ -z "${DATABASE_URL:-}" && -f .env ]]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set." >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

TS="$(date +%Y%m%d_%H%M%S)"
OUTFILE="${BACKUP_DIR}/nepse_ai_${TS}.dump"

echo "Backing up database to ${OUTFILE}"
pg_dump "${DATABASE_URL}" --format=custom --file="${OUTFILE}"
echo "Backup complete: ${OUTFILE}"

# Prune all but the most recent ${RETENTION} dumps.
# shellcheck disable=SC2012
ls -1t "${BACKUP_DIR}"/nepse_ai_*.dump 2>/dev/null | tail -n "+$((RETENTION + 1))" | xargs -r rm -f
echo "Retention applied: keeping newest ${RETENTION} dumps."
