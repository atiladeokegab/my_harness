#!/usr/bin/env bash
# agy's statusLine command (Hephaestus, T-559). agy pipes one snake_case JSON object on every agent
# state change; this keeps $HUB_DIR/state/<agent>.agy.json {at, agent_state,
# tool_confirmation_pending, model (model.id, which picks the quota family), quota: {bucket:
# {remaining_fraction, reset_time}}} for the relay and dispatch.py, and prints a tiny line for agy's footer. Only those fields reach disk: the payload
# carries the account email. Never fails or writes to stderr; garbage input leaves the file alone.
# `--agent <Name>` overrides HUB_AGENT.
agent="${HUB_AGENT:-}"
[ "${1:-}" != --agent ] || agent="${2:-}"
[[ "$agent" =~ ^[A-Za-z][A-Za-z0-9_-]{0,31}$ ]] || agent=
timeout 5 python3 -c '
import json, os, sys, tempfile
from datetime import datetime, timezone
d, agent = sys.argv[1], sys.argv[2]
try:
    s = json.load(sys.stdin)
    state = s["agent_state"]
except (ValueError, TypeError, KeyError):
    print(agent)
    sys.exit()
print(f"{agent} {state}".strip())
if not agent:
    sys.exit()
quota = {k: {"remaining_fraction": q.get("remaining_fraction"), "reset_time": q.get("reset_time")}
         for k, q in (s.get("quota") or {}).items() if isinstance(q, dict)}
model = s.get("model") if isinstance(s.get("model"), dict) else {}
out = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "agent_state": state,
       "tool_confirmation_pending": bool(s.get("tool_confirmation_pending")),
       "model": model.get("id") if isinstance(model.get("id"), str) else None, "quota": quota}
os.makedirs(d, exist_ok=True)
with tempfile.NamedTemporaryFile("w", dir=d, prefix=".agy.", delete=False) as f:
    json.dump(out, f)
os.replace(f.name, os.path.join(d, agent + ".agy.json"))
' "${HUB_DIR:-$HOME/hub}/state" "$agent" 2>/dev/null
exit 0
