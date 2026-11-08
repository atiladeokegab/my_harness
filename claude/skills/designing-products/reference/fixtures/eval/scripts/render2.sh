#!/usr/bin/env bash
# render2.sh R2_DIR OUT_DIR : every R2_DIR/<n>/index.html -> OUT_DIR/<n>-{desktop,mobile}.png
CAP=$HOME/.claude/skills/designing-products/reference/fixtures/capture.sh
mkdir -p "$2"
ls "$1"/*/index.html | xargs -P 6 -I{} bash -c 'f={}; n=$(basename $(dirname "$f")); '"$CAP"' "file://$f" "'"$2"'/$n"'
