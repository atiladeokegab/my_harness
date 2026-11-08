# Every agent dies at once on a Linux host, with no reboot

**Repo:** any; the hub host itself. **First cost:** about 45 minutes of a three-builder round.

## Symptom

All tmux sessions (`hub-zeus`, `hub-hermes`, ...) vanish together, along with every
background sub-agent. `uptime -s` shows the machine did NOT reboot. Work stops mid-edit and
nothing restarts it.

## Confirm it

```bash
grep Start-Date /var/log/apt/history.log | tail             # unattended-upgrades ran just before
journalctl --since "<time>" | grep -E 'logind|tmux-spawn'   # logind restarted, then "Stopping tmux-spawn-..."
loginctl show-user "$USER" -p Linger                        # Linger=no is the cause
```

## Cause

unattended-upgrades restarted `systemd-logind`. The new logind lost the user's login sessions
and, with linger off, stopped `user@<uid>.service`. tmux panes run in that user manager's
scopes, so every agent died with it.

## Fix

```bash
sudo loginctl enable-linger "$USER"
```

The user manager then outlives login sessions and logind restarts, and user timers (the
factory loops in `install-factory-timers.md`) keep running and start at boot. Agents that
already died still need relaunching by hand: re-enter each one and tell it to run `hub brief`.

## Traps while fixing it

Linger needs sudo once. On a host where you cannot get it, expect this to recur on every
logind upgrade, and consider holding the `systemd` packages out of unattended-upgrades.
