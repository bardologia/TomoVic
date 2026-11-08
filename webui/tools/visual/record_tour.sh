#!/usr/bin/env bash
# Record the console tour video against this machine's TomoVic console.
# Usage: record_tour.sh [record_tour.js flags and scenes...]
# Env:   PORT (default 8765), OUT (default /tmp/tomovic-tour), NAME (default tour), TOUR_FFMPEG (an ffmpeg with libx264)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEBUI="$(cd "$HERE/../.." && pwd)"

PORT="${PORT:-8765}"
OUT="${OUT:-/tmp/tomovic-tour}"
NAME="${NAME:-tour}"
LOG="/tmp/tomovic-webui-${PORT}.log"
FFDIR="$HERE/.ffmpeg"

if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
  echo "PORT must be a number, got '$PORT'" >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "node is not on PATH; the recorder needs node 18 or newer (conda: 'conda install -c conda-forge nodejs', or nvm)" >&2
  exit 1
fi
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$NODE_MAJOR" -lt 18 ]; then
  echo "node $(node --version) is too old for playwright-core; install node 18 or newer" >&2
  exit 1
fi

if [ ! -d "$HERE/node_modules/playwright-core" ]; then
  echo "installing playwright-core into $HERE/node_modules"
  (cd "$HERE" && npm ci --no-audit --no-fund)
fi

if ! (cd "$HERE" && node -e 'const { ChromiumResolver } = require("./chromium"); new ChromiumResolver().resolve()' >/dev/null 2>&1); then
  echo "fetching the chromium build that matches playwright-core"
  (cd "$HERE" && npx playwright-core install chromium)
fi

has_x264() {
  [ -n "$1" ] && [ -x "$1" ] && "$1" -hide_banner -encoders 2>/dev/null | grep libx264 >/dev/null
}

FFMPEG="${TOUR_FFMPEG:-}"
if ! has_x264 "$FFMPEG"; then
  FFMPEG="$(command -v ffmpeg || true)"
fi
if ! has_x264 "$FFMPEG"; then
  FFMPEG="$(ls "$FFDIR"/imageio_ffmpeg/binaries/ffmpeg-* 2>/dev/null | head -1 || true)"
fi
if ! has_x264 "$FFMPEG"; then
  PY="$(ls "$HOME/miniconda3/envs/Dune/bin/python" 2>/dev/null || command -v python3)"
  echo "no ffmpeg with libx264 found; fetching the imageio-ffmpeg static build into $FFDIR"
  "$PY" -m pip install --quiet --target "$FFDIR" imageio-ffmpeg
  FFMPEG="$(ls "$FFDIR"/imageio_ffmpeg/binaries/ffmpeg-* | head -1)"
  chmod +x "$FFMPEG"
fi
if ! has_x264 "$FFMPEG"; then
  echo "could not find or fetch an ffmpeg with libx264; set TOUR_FFMPEG" >&2
  exit 1
fi

if ! curl -fsS "http://127.0.0.1:$PORT/api/project" -o /dev/null 2>/dev/null; then
  echo "no console answers on port $PORT; starting one (log: $LOG)"
  nohup "$WEBUI/run.sh" "$PORT" > "$LOG" 2>&1 &
  for i in $(seq 1 120); do
    curl -fsS "http://127.0.0.1:$PORT/api/project" -o /dev/null 2>/dev/null && break
    if [ "$i" -eq 120 ]; then
      echo "the console did not come up on port $PORT; log tail:" >&2
      tail -20 "$LOG" >&2
      exit 1
    fi
    sleep 0.5
  done
  sleep 8
fi

mkdir -p "$OUT"
cd "$HERE" && exec node record_tour.js --port "$PORT" --out "$OUT" --name "$NAME" --ffmpeg "$FFMPEG" "$@"
