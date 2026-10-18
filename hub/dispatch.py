#!/usr/bin/env python3
"""The factory's timed loops (T-501). Stdlib only, so systemd runs it with /usr/bin/python3.

  dispatch.py tick [--dry-run]    every 2 min (hub-dispatch.timer): wake each idle agent once per task
  dispatch.py watch [--dry-run]   every minute (hub-watch.timer): classify each live pane, log and alert
  dispatch.py weekly [--dry-run]  Monday mornings (hub-weekly.timer): cleanup and rule-promotion tasks
  dispatch.py agents              agent names from factory.json, for scripts

--dry-run reads the real panes, board and state and only prints. Agent list: factory.json, else the
roster in HUB_CODEX_AGENTS / HUB_CLAUDE_AGENTS / HUB_LEAD (the lead is never dispatched).
State lives in $HUB_DIR/state: dispatch.json (wakes sent, last GitHub poll), watch.json (each
agent's last cause, pane fingerprint, rate-limit breaker), <agent>.json (heartbeat.sh).
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board as hb  # noqa: E402

HUB = Path(hb.HUB_DIR)
STATE = HUB / "state"
NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}")
LEAD = hb.LEAD_AGENT
REVIEWER = os.environ.get("HUB_REVIEWER") or "Hermes"
DEFAULT_AGENTS = [*({"name": n} for n in os.environ.get("HUB_CODEX_AGENTS", "Prometheus").split()),
                  *({"name": n} for n in os.environ.get("HUB_CLAUDE_AGENTS", "Zeus Apollo Hermes Athena").split()
                    if n != LEAD),
                  {"name": LEAD, "dispatch": False}]

# Only the bottom of a pane counts: older scrollback may quote these words in conversation.
TAIL = 15
# Match the CLIs' own chrome, never prose: an agent's reply or a grep's output often contains the
# same words (Hermes, T-501 review). A cause counts only when a line STARTS with the CLI's message,
# after an optional chrome prefix: a dialog border, the prompt arrow, Claude's error/tool gutter (⎿)
# or Codex's banner (■). Prose starts with ● / ⏺ / • or plain text, and a grep line with a path.
# hubwaked keeps its own wider dialog check before it types anything, so a miss here stays safe.
CHROME = r"^(?:[│╭╰❯›>⎿■✗⚠]\s*)*"
# Errors only print in the error gutter or banner: a quote (>), the prompt (❯ ›) or a table cell (│)
# is someone talking about the error (T-508).
ERROR_CHROME = r"^(?:[⎿■✗⚠]\s*)*"
# Both CLIs' permission dialogs list numbered options: a dialog needs a "1. Yes" line AND a
# "N. No" or "Esc to cancel" line, so a numbered list in a reply is not one (T-508).
DIALOG_YES = re.compile(CHROME + r"1\.\s+Yes\b", re.I)
DIALOG_NO = re.compile(CHROME + r"(?:\d\.\s+No\b|Esc to cancel)", re.I)
CAUSES = (
    # Codex's trust and command-center screens swallow typed text.
    ("permission prompt", re.compile(CHROME + r"(?:Do you trust|Trust this folder|Agent command center)", re.I)),
    # Not Codex's "5h limit: only 5% left" warning: that agent still works.
    ("rate limited", re.compile(ERROR_CHROME + r"(?:API Error: 429|Claude (?:AI )?usage limit reached|"
                                r"You[’']ve (?:hit|reached) your (?:usage )?limit|\d+-hour limit reached|"
                                r"Weekly limit reached|Rate limit reached|Request rejected \(429\))", re.I)),
    ("logged out", re.compile(ERROR_CHROME + r"(?:API Error: 401|Invalid API key|OAuth token (?:has )?expired|"
                              r"Not logged in|Please run /login|Your access token could not be refreshed)",
                              re.I)),
)
CLOCK = re.compile(r"(?:resets?|try again)(?: at)? (\d{1,2})(?::(\d{2}))?\s*([ap]m)?"
                   r"(?:\s*\(([\w+-]+/[\w/+-]+)\))?", re.I)
WAIT = re.compile(r"try again in ((?:\d+\s*(?:days?|hours?|minutes?|mins?)[\s,and]*)+)", re.I)

WEEKLY = (
    ("Weekly cleanup",
     "Weekly (hub-weekly.timer). Close or re-scope stale open and blocked tasks, prune merged branches "
     "and worktrees, read watchdog.log for causes that repeat and fix the cause, check the snapshot "
     "bucket holds last night's tarball. Done when the board's open list is current."),
    ("Promote rule candidates",
     "Weekly (hub-weekly.timer). Collect this week's `rule candidate:` lines from " + REVIEWER + " (grep "
     "events.jsonl, task notes and inboxes). Promote the ones that would have prevented a real defect "
     "into AGENTS.md, CLAUDE.md, a skill or a runbook; drop the rest with one line why."),
)


def config():
    try:
        cfg = json.loads((HUB / "factory.json").read_text())
    except (OSError, ValueError):
        cfg = {}
    # Names reach tmux targets and shell scripts, so only plain names pass.
    agents = [a for a in cfg.get("agents") or []
              if isinstance(a, dict) and NAME_RE.fullmatch(str(a.get("name", "")))] or DEFAULT_AGENTS
    agents = [{"session": f"hub-{a['name'].lower()}", "dispatch": True, **a} for a in agents]
    return agents, cfg.get("intervals") or {}


def lead_alert():
    """factory.json "lead_alert": argv of a command that reaches the human lead (a chat bot, a pager);
    the message is appended as the last argument. Missing means Zeus's inbox is the only alert."""
    try:
        argv = json.loads((HUB / "factory.json").read_text()).get("lead_alert")
    except (OSError, ValueError, AttributeError):
        return None
    return argv if isinstance(argv, list) and argv and all(isinstance(x, str) for x in argv) else None


def load(name):
    try:
        return json.loads((STATE / name).read_text())
    except (OSError, ValueError):
        return {}


def save(name, data):
    STATE.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=STATE, prefix=f".{name}.", delete=False) as f:
        json.dump(data, f, indent=1)
    os.replace(f.name, STATE / name)


def tasks():
    with hb.board() as (data, _):
        return data["tasks"]


def claimed(all_tasks, name):
    """Claimed tasks that keep this agent busy. A `standing` duty (watching a repo, reviewing) is
    held indefinitely and never means busy, for the wake or for the stuck check."""
    return [t["id"] for t in all_tasks
            if t["status"] == "claimed" and (hb.actor(t) or "").lower() == name.lower()
            and "standing" not in (t.get("tags") or [])]


def capture(session):
    try:
        r = subprocess.run(["tmux", "capture-pane", "-p", "-t", session],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def tail(pane):
    return [line.strip() for line in pane.splitlines() if line.strip()][-TAIL:]


def classify(pane):
    """(cause, the line that shows it); cause None means nothing wrong is on screen."""
    lines = tail(pane)
    yes = next((line for line in lines if DIALOG_YES.search(line)), None)
    if yes and any(DIALOG_NO.search(line) for line in lines):
        return "permission prompt", yes
    for cause, pattern in CAUSES:
        for line in lines:
            if pattern.search(line):
                return cause, line
    return None, ""


def busy(pane):
    return any("esc to interrupt" in line for line in tail(pane))


def reset_at(lines, now):
    """Epoch seconds when a shown rate limit lifts, or None if no time is shown. Lines are joined
    because panes wrap the message mid-sentence ("or try" / "again at 7:28 PM")."""
    text = " ".join(lines)
    waits = list(WAIT.finditer(text))
    if waits:
        parts = {unit: int(n) for n, unit in re.findall(r"(\d+)\s*([dhm])", waits[-1].group(1))}
        return now + timedelta(days=parts.get("d", 0), hours=parts.get("h", 0),
                               minutes=parts.get("m", 0)).total_seconds()
    for m in reversed(list(CLOCK.finditer(text))):
        hour, minute, half, zone = int(m[1]), int(m[2] or 0), (m[3] or "").lower(), m[4]
        if half:
            hour = hour % 12 + (12 if half == "pm" else 0)
        if hour > 23 or minute > 59:
            continue
        try:
            tz = ZoneInfo(zone) if zone else None
        except (ZoneInfoNotFoundError, ValueError):
            tz = None
        local = datetime.fromtimestamp(now, tz).astimezone(tz)
        at = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if at <= local:
            at += timedelta(days=1)
        return at.timestamp()
    return None


def limited(entry, now):
    lim = entry.get("limited")
    return bool(lim) and (lim.get("until") is None or lim["until"] > now)


def run_locked(tid, dry):
    """True while hub run (run.py) holds ~/hub/run/<id>.lock. A dead pid's lock is not held, but it is left
    for run.py to reclaim under its own O_EXCL guard: two removers would race."""
    lock = HUB / "run" / f"{tid}.lock"
    try:
        text = lock.read_text().strip()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        pid = int(text)
        if pid < 1:
            raise ValueError
        os.kill(pid, 0)
    except ProcessLookupError:
        print(f"  {tid}: run lock pid {pid} is gone; stale, run.py reclaims it")
        return False
    except (ValueError, PermissionError):
        pass  # being written, or another user's pid: treat as held, as run.py does
    return True


def dispatch_projects():
    """factory.json "projects": the only projects the dispatcher offers work from. Missing means
    every project; the board holds old tasks from paused projects that no agent should be woken for."""
    try:
        return json.loads((HUB / "factory.json").read_text()).get("projects")
    except (OSError, ValueError):
        return None


def candidates(name, all_tasks, projects):
    """Open tasks this agent may take, in hub next's order (board.next_candidates) within each
    factory project in turn; projects None means every project. The whole list rather than hub
    next's first pick, so a skipped task (untrusted, run-locked, offered) falls through."""
    out = []
    for project in projects or [None]:
        # next_candidates ends with the agent's work in other projects; that is not this project's.
        out += [t for t in hb.next_candidates(all_tasks, name, project)
                if project is None or (t.get("project") or "") == project]
    return out


def expire_offers(woken, all_tasks, offer_minutes, now):
    """Forget offers for tasks no longer open. An unanswered wake expires after offer_minutes and
    the task may go to another agent, never back to the one that ignored it. A headless run's offer
    never expires: the task stays open after the run until someone decides on its result."""
    still_open = {t["id"] for t in all_tasks if t["status"] == "open"}
    for tid in [tid for tid in woken if tid not in still_open]:
        del woken[tid]
    for offer in woken.values():
        if offer.get("agent") and offer.get("how") != "run" and \
                now - datetime.fromisoformat(offer["at"]).timestamp() >= offer_minutes * 60:
            offer.setdefault("ignored", []).append(offer.pop("agent"))
            offer.pop("at", None)


def wake(name, t):
    text = (f"[dispatch] You look idle and hub next offers {t['id']}: {t['title']}. Run hub show "
            f"{t['id']}, claim it and do it. If it is not yours to do, tell {LEAD} why with hub notify.")
    try:
        r = subprocess.run(["hubmsg", name, text, "--task", t["id"]], capture_output=True, text=True,
                           timeout=90, env={**os.environ, "HUB_AGENT": "Dispatch"})
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"  hubmsg failed: {e!r}", file=sys.stderr)
        return False
    print("  " + (r.stdout.strip() or r.stderr.strip()).replace("\n", "\n  "))
    return "queued" in r.stdout  # the durable half landed; hubwaked retries the keystroke


def start_headless(name, t):
    # Its own transient unit: a child of this oneshot service would die when the tick exits.
    env = [f"--setenv={k}={os.environ[k]}" for k in ("PATH", "HUB_DIR", "HUB_CODE_DIR", "HUB_LEAD",
                                                       "HUB_CLAUDE_AGENTS", "HUB_CODEX_AGENTS") if k in os.environ]
    cmd = ["systemd-run", "--user", "--quiet", "--collect", f"--unit=hub-run-{t['id']}",
           f"--setenv=HUB_AGENT={name}", *env, "--", sys.executable, str(HERE / "run.py"), t["id"]]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"  systemd-run failed: {e!r}", file=sys.stderr)
        return False
    print(f"  started hub run {t['id']} as unit hub-run-{t['id']}" if r.returncode == 0
          else f"  systemd-run failed: {r.stderr.strip()}")
    return r.returncode == 0


def poll_github(state, intervals, now, dry):
    if now - state.get("polled", 0) < intervals.get("poll_seconds", 300):
        return
    try:
        import gh_sync
        poll = getattr(gh_sync, "poll_factory_repos", None)
        if poll:
            poll(dry_run=dry)
        else:
            print("gh_sync has no poll_factory_repos; not polling GitHub")
    except (Exception, SystemExit) as e:  # a failed poll must never stop the wakes
        print(f"factory poll failed: {e!r}", file=sys.stderr)
    if not dry:
        state["polled"] = now


def not_idle(a, held, watched, now):
    """Why this agent must not be woken now, or None when it sits idle at a prompt."""
    if not a["dispatch"]:
        return "dispatch off in factory.json"
    if held:
        return f"busy (claimed {', '.join(held)})"
    try:  # run.py records a limit it hit here; heartbeat.sh owns <name>.json and would overwrite it
        ran = json.loads((HUB / "state" / f"{a['name']}.limit.json").read_text()).get("until") or 0
    except (OSError, ValueError, AttributeError):
        ran = 0
    if ran > now:
        return f"rate limited (hub run) until {datetime.fromtimestamp(ran, timezone.utc):%H:%MZ}"
    if limited(watched, now):
        until = watched["limited"].get("until")
        return f"rate limited until {datetime.fromtimestamp(until, timezone.utc):%H:%MZ}" if until \
            else "rate limited until the message clears"
    pane = capture(a["session"])
    if pane is None:
        return "no tmux session"
    cause = classify(pane)[0]
    lifted = (watched.get("limited") or {}).get("until")
    if cause == "rate limited" and lifted and lifted <= now:
        cause = None  # the shown reset time has passed; the message just has not scrolled away
    if cause:
        return f"pane shows {cause}"
    if busy(pane):
        return "working (esc to interrupt on screen)"
    return None


def tick(dry):
    reason = hb.paused()
    if reason:
        print(f"hub is paused ({reason}); dispatching nothing")
        return 0
    agents, intervals = config()
    state, now = load("dispatch.json"), time.time()
    poll_github(state, intervals, now, dry)
    all_tasks, watch, woken = tasks(), load("watch.json"), state.setdefault("woken", {})
    expire_offers(woken, all_tasks, intervals.get("offer_minutes", 30), now)
    projects = dispatch_projects()
    for a in agents:
        name = a["name"]
        why = not_idle(a, claimed(all_tasks, name), watch.get(name, {}), now)
        pending = next((tid for tid, o in woken.items() if o.get("agent") == name and o.get("how") != "run"), None)
        if why or pending:
            print(f"{name}: {why or f'idle, offer of {pending} pending'}")
            continue
        t, skipped = None, []
        for c in candidates(name, all_tasks, projects):
            offer = woken.get(c["id"], {})
            skip = ("untrusted" if "untrusted" in (c.get("tags") or [])
                    else f"offered to {offer['agent']}" if offer.get("agent")
                    else "ignored before" if name in offer.get("ignored", [])
                    else "run lock held" if run_locked(c["id"], dry) else None)
            if not skip:
                t = c
                break
            skipped.append(f"{c['id']} {skip}")
        note = f" (skipped {'; '.join(skipped)})" if skipped else ""
        if t is None:
            print(f"{name}: idle, nothing available{note}")
            continue
        headless = "headless" in (t.get("tags") or [])
        verb = "start hub run for" if headless else "wake for"
        if dry:
            print(f"{name}: idle, would {verb} {t['id']} {t['title']}{note}")
            continue
        print(f"{name}: idle, {verb} {t['id']} {t['title']}{note}")
        if (start_headless if headless else wake)(name, t):
            woken[t["id"]] = {**woken.get(t["id"], {}), "agent": name, "at": hb.now(),
                              "how": "run" if headless else "wake"}
    if not dry:
        save("dispatch.json", state)
    return 0


def heartbeat(name):
    try:
        beat = json.loads((STATE / f"{name}.json").read_text())
        return datetime.fromisoformat(beat["at"]).timestamp()
    except (OSError, ValueError, KeyError, TypeError):
        return None


def report(name, before, cause, line, dry, lead):
    msg = f"{name}: {before} -> {cause}" + (f" ({line})" if line else "")
    alert = cause != "healthy"
    if dry:
        print(f"  would log '{msg}'" + (f", notify {LEAD}" if alert else "") + (", alert the lead" if lead else ""))
        return
    with open(HUB / "watchdog.log", "a") as f:
        f.write(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} {msg}\n")
    if not alert:
        return
    text = (f"[watchdog] {msg}. The watchdog never relaunches a live session; "
            f"look at tmux hub-{name.lower()}.")
    r = subprocess.run([sys.executable, str(HERE / "board.py"), "notify", LEAD, text],
                       env={**os.environ, "HUB_AGENT": "Watchdog"}, capture_output=True, text=True, timeout=30)
    if r.returncode:
        print(f"  notify failed: {r.stderr.strip()}", file=sys.stderr)
    argv = lead_alert() if lead else None
    if argv:
        try:  # best effort: the lead's channel may be down or rate limited
            subprocess.run([*argv, text], capture_output=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired):
            pass


def watch(dry):
    agents, intervals = config()
    stuck_after = intervals.get("stuck_minutes", 30) * 60
    all_tasks, state, now = tasks(), load("watch.json"), time.time()
    for a in agents:
        name = a["name"]
        pane = capture(a["session"])
        if pane is None:
            print(f"{name}: no session (the relaunch loop handles that)")
            continue
        cur = state.setdefault(name, {})
        cause, line = classify(pane)
        digest = hashlib.sha1(pane.encode()).hexdigest()
        if cur.get("pane") != digest:
            cur["pane"], cur["pane_since"] = digest, now
        held = claimed(all_tasks, name)
        if cause is None and held:
            beat = heartbeat(name)  # heartbeat first; pane change only for agents without the hook
            quiet = now - (beat if beat is not None else cur["pane_since"])
            if quiet >= stuck_after:
                cause = "stuck"
                line = (f"{'no heartbeat' if beat is not None else 'pane unchanged'} for "
                        f"{int(quiet // 60)} min while holding {', '.join(held)}")
        if cause == "rate limited":
            prev = cur.get("limited") or {}
            # The same message still on screen keeps its first reading: re-reading "try again at 7:28 PM"
            # after 7:28 PM would push the breaker to tomorrow (T-506 run 2).
            until = prev["until"] if prev.get("line") == line and prev.get("until") else None
            cur["limited"] = {"until": until or reset_at(tail(pane), now) or prev.get("until"), "line": line,
                              "told": prev.get("told", False)}
        elif cur.get("limited") and (cur["limited"].get("until") or 0) <= now:  # no time shown: lifts with the message
            del cur["limited"]
        cause = cause or "healthy"
        until = (cur.get("limited") or {}).get("until")
        print(f"{name}: {cause}" + (f": {line}" if line else "")
              + (f" [breaker on until {datetime.fromtimestamp(until, timezone.utc):%Y-%m-%d %H:%MZ}]" if until else ""))
        before = cur.get("cause", "healthy")
        if cause != before:
            # The lead hears of a limit once per reset window (the breaker's life), and of the lead agent's trouble.
            lead = (not cur["limited"]["told"]) if cause == "rate limited" else (cause != "healthy" and name == LEAD)
            report(name, before, cause, line, dry, lead)
            if cause == "rate limited" and not dry:
                cur["limited"]["told"] = True
        cur["cause"] = cause
    if not dry:
        save("watch.json", state)
    return 0


def weekly(dry):
    reason = hb.paused()
    if reason:
        print(f"hub is paused ({reason}); opening nothing")
        return 0
    live = {t["title"] for t in tasks() if t["status"] != "done"}
    for title, detail in WEEKLY:
        if title in live:
            print(f"{title}: last one is not done yet, not opening another")
        elif dry:
            print(f"would open '{title}' for {LEAD}")
        else:
            subprocess.run([sys.executable, str(HERE / "board.py"), "new", title, "--owner", LEAD,
                            "--project", "hub", "--detail", detail], check=True, timeout=30,
                           env={**os.environ, "HUB_AGENT": "Dispatch"})
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("tick", "watch", "weekly", "agents"))
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    if a.command == "agents":
        print(" ".join(x["name"] for x in config()[0]))
        return 0
    return {"tick": tick, "watch": watch, "weekly": weekly}[a.command](a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
