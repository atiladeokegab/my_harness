#!/usr/bin/env bash
# Render every fixture page at the two judge sizes: <name>-desktop.png (1280x633), <name>-mobile.png (390x757).
#   ./capture.sh                      all fixture pages
#   ./capture.sh URL OUT_PREFIX       one live page, e.g. ./capture.sh https://example.com refs/example
# A fixed virtual-time budget makes motion land at the same frame every run.
set -euo pipefail
cd "$(dirname "$0")"
CHROME=${CHROME:-google-chrome}
PROFILE=$(mktemp -d); trap 'rm -rf "$PROFILE"' EXIT

chrome() { # seconds args...
  timeout "$1" "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run \
    --user-data-dir="$PROFILE" "${@:2}" >/dev/null 2>&1
}

shoot() { # url out-prefix
  for size in desktop:1280,633 mobile:390,757; do
    local args=(--window-size="${size#*:}" --screenshot="$2-${size%%:*}.png" "$1")
    # A live page that never goes idle hangs the virtual clock; then shoot at the load event, and say so.
    chrome 90 --virtual-time-budget=1500 "${args[@]}" ||
      { echo "$2-${size%%:*}: virtual time hung, shot at load" >&2; chrome 90 "${args[@]}"; }
  done
}

if [ $# -eq 2 ]; then shoot "$1" "$2"; exit; fi
for f in bad/*.html trio/*.html; do shoot "file://$PWD/$f" "${f%.html}"; done
