#!/bin/bash
# The hub VM's startup script (instance metadata: runs as root at every boot), and its idle check.
#   startup.sh                      install the idle timer only with metadata hub-idle-stop=on
#   startup.sh check [--dry-run]    stop the VM if nobody has used the hub for 3 hours
# The VM is always on by default. Set instance metadata hub-idle-stop=on to opt in.
# Idle is all of: up 3 hours, nobody logged in over SSH, 15-minute load under 1, and no file
# changed for 3 hours under ~/hub (hub live logs every 5 minutes) or in the agents' transcripts.
# A shutdown from inside stops a Compute Engine VM: only its disk is billed after that.
set -u
H="${HUB_IDLE_HOME:-~}"
idle_setting=$(curl -fsS --max-time 2 -H 'Metadata-Flavor: Google' \
    http://metadata.google.internal/computeMetadata/v1/instance/attributes/hub-idle-stop 2>/dev/null || true)
if [ "$idle_setting" != on ]; then
    if [ "${1:-}" != check ] && [ -e /etc/systemd/system/hub-idle-stop.timer ]; then
        systemctl disable --now hub-idle-stop.timer
    fi
    echo 'idle stop disabled (set hub-idle-stop=on to enable)'
    exit 0
fi

if [ "${1:-}" != check ]; then
    install -m 0755 "$0" /usr/local/sbin/hub-idle-stop
    cat > /etc/systemd/system/hub-idle-stop.service <<'EOF'
[Unit]
Description=Stop the hub VM after 3 idle hours

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/hub-idle-stop check
EOF
    cat > /etc/systemd/system/hub-idle-stop.timer <<'EOF'
[Unit]
Description=Check every 15 minutes whether the hub VM is idle

[Timer]
OnBootSec=15min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
EOF
    systemctl daemon-reload
    systemctl enable --now hub-idle-stop.timer
    exit 0
fi

busy() { echo "busy: $1"; exit 0; }
up=$(cut -d. -f1 /proc/uptime)
[ "$up" -lt 10800 ] && busy "up ${up}s"
[ -n "$(who)" ] && busy "someone is logged in"
load=$(cut -d' ' -f3 /proc/loadavg)
[ "${load%%.*}" -ge 1 ] && busy "15-minute load $load"
dirs=("$H/hub" "$H"/.claude*/projects "$H/.codex/sessions")
[ -d "$H/.gemini/antigravity-cli/brain" ] && dirs+=("$H/.gemini/antigravity-cli/brain")
recent=$(find "${dirs[@]}" -path "$H/hub/.uv-cache" -prune \
         -o -type f -mmin -180 -print -quit 2>/dev/null)
[ -n "$recent" ] && busy "changed in the last 3 hours: $recent"
[ "${2:-}" = --dry-run ] && { echo "idle: would stop the VM"; exit 0; }
logger -t hub-idle-stop "idle for 3 hours: stopping the VM"
systemctl poweroff
