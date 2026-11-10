#!/bin/sh
set -eu
illona_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$illona_root"
if [ ! -x "$illona_root/.venv/bin/python" ]; then
    echo "Illona is not installed. Run setup.sh with Python 3.11 or newer." >&2
    exit 1
fi
exec "$illona_root/.venv/bin/python" -m illona_mcp.server

