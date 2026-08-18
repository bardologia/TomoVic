#!/usr/bin/env bash
# Remove Python bytecode caches and the pytest cache from the repo.
# These are gitignored and regenerated automatically, so a git pull never
# removes them on other machines. Run this locally on each machine instead.
set -euo pipefail

cd "$(dirname "$0")"

find . -path ./.git -prune -o -type d -name "__pycache__" -exec rm -rf {} +
rm -rf .pytest_cache

echo "Cleaned __pycache__ directories and .pytest_cache."
