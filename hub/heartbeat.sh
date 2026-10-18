#!/usr/bin/env bash
# UserPromptSubmit, PostToolUse and Stop hook (T-501, agent OS §5.5): writes
# $HUB_DIR/state/<agent>.json {at, event, tool} so `dispatch.py watch` can tell a quiet agent from a working
# one, and hubwaked can tell a mid-turn agent (last event UserPromptSubmit/PostToolUse) from an idle
# one (Stop). Sessions without HUB_AGENT (ad hoc, not a hub agent) write nothing. Never fails or
# slows the hook: every error is swallowed.
# On Stop the agent just went idle, so it also touches state/dispatch.kick (T-527); the lead
# ($HUB_LEAD) is excluded so its many short turns with you do not storm the dispatcher.
# `--agent <Name>` overrides the env: Codex hooks run in a shared app-server daemon whose env is
# whoever started it, so ~/.codex/hooks.json passes the name and HUB_DIR explicitly (spike T1).
agent="${HUB_AGENT:-${CLAUDE_CODE_SESSION_NAME:-}}"
[ "${1:-}" != --agent ] || agent="${2:-}"
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
if beat["event"] == "Stop" and sys.argv[2].lower() != sys.argv[3].lower():
    kick = os.path.join(d, "dispatch.kick")
    open(kick, "a").close()
    os.utime(kick)
' "${HUB_DIR:-$HOME/hub}/state" "$agent" "${HUB_LEAD:-Zeus}" 2>/dev/null
exit 0
