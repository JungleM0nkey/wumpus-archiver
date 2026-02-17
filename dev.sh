#!/usr/bin/env bash
# Start the wumpus-archiver dev environment (backend + frontend with hot-reload).
# Usage: ./dev.sh [database] [attachments_dir]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Defaults — override with args or env vars
DB="${1:-${DB:-data/archive.db}}"
ATT_DIR="${2:-${ATT_DIR:-data/attachments}}"
PORT="${PORT:-8000}"
VITE_PORT="${VITE_PORT:-5173}"
PG_URL="${POSTGRES_URL:-}"

# Fall back to root-level archive.db if data/ copy doesn't exist
if [[ ! -f "$DB" && -f "archive.db" ]]; then
    DB="archive.db"
fi

if [[ ! -f "$DB" ]]; then
    echo "Error: Database not found at '$DB'"
    echo "Usage: ./dev.sh [path/to/archive.db] [path/to/attachments]"
    exit 1
fi

if [[ -n "$PG_URL" ]]; then
    exec wumpus-archiver dev "$DB" --port "$PORT" --frontend-port "$VITE_PORT" -a "$ATT_DIR" --postgres-url "$PG_URL"
else
    exec wumpus-archiver dev "$DB" --port "$PORT" --frontend-port "$VITE_PORT" -a "$ATT_DIR"
fi
