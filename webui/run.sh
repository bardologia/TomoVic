#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PORT="${1:-8765}"

CANDIDATES=("$HOME/miniconda3/envs/Dune/bin/python" "$HOME/miniconda3/bin/python" "$(command -v python3 || true)")

PY=""
for candidate in "${CANDIDATES[@]}"; do
  if [ -x "$candidate" ]; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "No usable python interpreter found. Tried, in order:" >&2
  for candidate in "${CANDIDATES[@]}"; do
    echo "  ${candidate:-<python3 not on PATH>}" >&2
  done
  echo "Create the Dune env (see README section 1) or put python3 on PATH." >&2
  exit 1
fi

echo "Starting TomoVic control console with: $PY"
exec "$PY" "$HERE/serve.py" --port "$PORT"
