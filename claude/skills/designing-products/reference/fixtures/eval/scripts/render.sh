#!/usr/bin/env bash
# render.sh SRC_DIR OUT_DIR : every SRC_DIR/*.html -> OUT_DIR/<name>-{desktop,mobile}.png
set -u
CAP=$HOME/.claude/skills/designing-products/reference/fixtures/capture.sh
mkdir -p "$2"
ls "$1"/*.html | xargs -P 6 -I{} bash -c 'f={}; n=$(basename "$f" .html); '"$CAP"' "file://$f" "'"$2"'/$n"'
ls "$2"/*-desktop.png | wc -l
