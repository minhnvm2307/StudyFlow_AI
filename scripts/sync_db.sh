#!/usr/bin/env bash
# Script to sync database schemas using Alembic
set -e

# Get the directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$DIR")"

# Load .env file if it exists
if [ -f "$ROOT_DIR/.env" ]; then
    echo "Loading environment variables from .env..."
    # Export all variables defined in .env, ignoring comments and empty lines
    export $(grep -v '^#' "$ROOT_DIR/.env" | grep -v '^$' | xargs)
else
    echo "Warning: .env file not found at $ROOT_DIR/.env"
fi

# Activate virtual environment if it exists
if [ -d "$ROOT_DIR/backend/.venv" ]; then
    echo "Activating Python virtual environment..."
    source "$ROOT_DIR/backend/.venv/bin/activate"
fi

# Determine target database
TARGET="local"
if [ "${1:-}" = "--cloud" ]; then
    TARGET="cloud"
fi

if [ "$TARGET" = "cloud" ]; then
    if [ -z "${CLOUD_SUPABASE_CONNECTION_STRING:-}" ]; then
        echo "Error: CLOUD_SUPABASE_CONNECTION_STRING is not set in .env"
        exit 1
    fi
    echo "Setting DATABASE_URL to Supabase Cloud connection string..."
    export DATABASE_URL="$CLOUD_SUPABASE_CONNECTION_STRING"
else
    if [ -z "${DATABASE_URL:-}" ]; then
        echo "Error: DATABASE_URL is not set in .env"
        exit 1
    fi
    echo "Using local DATABASE_URL..."
fi

echo "Running Alembic migrations on $TARGET database..."
cd "$ROOT_DIR/backend"
alembic upgrade head
echo "Migrations sync complete on $TARGET database!"
