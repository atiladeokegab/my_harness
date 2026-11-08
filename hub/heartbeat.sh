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
# `--event <Stop|PostToolUse|UserPromptSubmit>` overrides hook_event_name: some CLIs (agy) send payloads with no
# event name, so their hooks config passes Claude's name for each event.
agent="${HUB_AGENT:-${CLAUDE_CODE_SESSION_NAME:-}}" event=
while [ $# -ge 2 ]; do
  case $1 in --agent) agent=$2 ;; --event) event=$2 ;; esac
  shift 2
done
[ "$event" != PostToolUse ] || echo '{}'  # agy expects JSON back from a PostToolUse hook
# A launcher's throwaway probe (agy -p) runs the seat's global hooks too; it must not beat for the seat.
[ -z "${HUB_NO_HOOKS:-}" ] || exit 0
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
        "event": sys.argv[3] or hook.get("hook_event_name"), "tool": hook.get("tool_name")}
with tempfile.NamedTemporaryFile("w", dir=d, prefix=".beat.", delete=False) as f:
    json.dump(beat, f)
os.replace(f.name, os.path.join(d, sys.argv[2] + ".json"))
if beat["event"] == "Stop" and sys.argv[2].lower() != sys.argv[4].lower():
    kick = os.path.join(d, "dispatch.kick")
    open(kick, "a").close()
    os.utime(kick)
' "${HUB_DIR:-$HOME/hub}/state" "$agent" "$event" "${HUB_LEAD:-Zeus}" 2>/dev/null
exit 0
