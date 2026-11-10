#!/bin/sh
set -eu
illona_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
illona_python=${ILLONA_PYTHON:-python3}
"$illona_python" -c 'import sys; assert sys.version_info >= (3, 11), "Illona requires Python 3.11 or newer"'
"$illona_python" -m venv "$illona_root/.venv"
"$illona_root/.venv/bin/python" -m pip install -r "$illona_root/requirements.lock"
chmod +x "$illona_root/run.sh"
echo "Illona is ready. Launch with: $illona_root/run.sh" >&2

