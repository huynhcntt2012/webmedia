#!/usr/bin/env bash
# Uses the same tested Windows/Linux Docker backup code.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
exec python3 scripts/local_ops.py backup --profile production --directory "${1:?Supply initialized backup directory}"
