#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CONFIG_BASE=${XDG_CONFIG_HOME:-"$HOME/.config"}
CACHE_BASE=${XDG_CACHE_HOME:-"$HOME/.cache"}
CONFIG_DIR="$CONFIG_BASE/tokenscope"
CACHE_DIR="$CACHE_BASE/tokenscope"

mkdir -p "$CONFIG_DIR" "$CACHE_DIR"
if [ ! -f "$CONFIG_DIR/config.ini" ]; then
  cp "$APP_DIR/config.example.ini" "$CONFIG_DIR/config.ini"
fi

exec "$APP_DIR/TokenScopeServer/TokenScopeServer" \
  --host 0.0.0.0 --port 8765 --interval 300 \
  --config "$CONFIG_DIR/config.ini" --cache "$CACHE_DIR/web.json" --open-browser
