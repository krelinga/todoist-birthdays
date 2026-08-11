#!/usr/bin/env bash
# Named volumes (and fresh bind mounts) are created root-owned by the Docker
# daemon, but the app process runs as the unprivileged "app" user -- so on
# first run (or after a volume is recreated) it can't write state.json.
#
# This runs as root before the app starts: it chowns the directory holding
# STATE_PATH (default kept in sync with DEFAULT_STATE_PATH in main.py) to
# "app", then drops privileges via gosu to exec the real command. It's cheap
# and idempotent, so it's safe to run on every container start.
set -euo pipefail

state_path="${STATE_PATH:-/data/state.json}"
state_dir="$(dirname "$state_path")"

mkdir -p "$state_dir"
chown -R app:app "$state_dir"

exec gosu app "$@"
