#!/usr/bin/env bash
# Claude Code PostToolUse and Stop hook (T-501): writes $HUB_DIR/state/<agent>.json {at, event, tool}
# so `dispatch.py watch` can tell a quiet agent from a working one. Sessions without HUB_AGENT (ad hoc,
# not a hub agent) write nothing. Never fails or slows the hook: every error is swallowed.
agent="${HUB_AGENT:-${CLAUDE_CODE_SESSION_NAME:-}}"
[[ "$agent" =~ ^[A-Za-z][A-Za-z0-9_-]{0,31}$ ]] || exit 0
timeout 5 python3 -c '
import json, os, sys, tempfile
from datetime import datetime, timezone
try:
    hook = json.load(sys.stdin)
except ValueError:
    hook = {}
d = sys.argv[1]
os.makedirs(d, exist_ok=True)
beat = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": hook.get("hook_event_name"), "tool": hook.get("tool_name")}
with tempfile.NamedTemporaryFile("w", dir=d, prefix=".beat.", delete=False) as f:
    json.dump(beat, f)
os.replace(f.name, os.path.join(d, sys.argv[2] + ".json"))
' "${HUB_DIR:-$HOME/hub}/state" "$agent" 2>/dev/null
exit 0
