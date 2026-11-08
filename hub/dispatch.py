#!/usr/bin/env python3
"""The factory's timed loops (T-501). Stdlib only, so systemd runs it with /usr/bin/python3.

  dispatch.py tick [--dry-run]    every 2 min (hub-dispatch.timer): wake each idle agent once per task
  dispatch.py watch [--dry-run]   every minute (hub-watch.timer): classify each live pane, log and alert
  dispatch.py weekly [--dry-run]  Monday mornings (hub-weekly.timer): cleanup and rule-promotion tasks
  dispatch.py agents              agent names from factory.json, for scripts
  dispatch.py check-config        exit 1, one line each, if a factory.json agent setting is mistyped

--dry-run reads the real panes, board and state and only prints. Agent list: factory.json, else the
roster in HUB_CODEX_AGENTS / HUB_CLAUDE_AGENTS / HUB_LEAD (the lead is never dispatched).
State lives in $HUB_DIR/state: dispatch.json (wakes sent, last GitHub poll), watch.json (each
agent's last cause, pane fingerprint, rate-limit breaker), config.json (the factory.json problems
Zeus has been told of), <agent>.json (heartbeat.sh).
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
import autonomy  # noqa: E402
import board as hb  # noqa: E402

HUB = Path(hb.HUB_DIR)
STATE = HUB / "state"
NAME_RE = hb.AGENT_RE
LEAD = hb.LEAD_AGENT
REVIEWER = os.environ.get("HUB_REVIEWER") or "Hermes"
# The roster when factory.json gives none (HUB_CODEX_AGENTS / HUB_CLAUDE_AGENTS): watch still sees
# every pane, dispatch wakes nobody.
DEFAULT_AGENTS = [*({"name": n, "kind": "codex", "dispatch": False}
                    for n in os.environ.get("HUB_CODEX_AGENTS", "Prometheus").split()),
                  *({"name": n, "kind": "claude", "dispatch": False}
                    for n in os.environ.get("HUB_CLAUDE_AGENTS", "Zeus Apollo Hermes Athena").split())]

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
# "N. No" or "Esc to cancel" line, so a numbered list in a reply is not one (T-508). Case-sensitive
# Esc: agy's lowercase "esc to cancel" is its busy footer, under any reply, not a dialog's.
DIALOG_YES = re.compile(CHROME + r"1\.\s+Yes\b", re.I)
DIALOG_NO = re.compile(CHROME + r"(?:\d\.\s+No\b|(?-i:Esc to cancel))", re.I)
CAUSES = (
    # Codex's trust and command-center screens swallow typed text.
    ("permission prompt", re.compile(CHROME + r"(?:Do you trust|Trust this folder|Agent command center)", re.I)),
    # Not Codex's "5h limit: only 5% left" warning: that agent still works.
    ("rate limited", re.compile(ERROR_CHROME + r"(?:API Error: 429|Claude (?:AI )?usage limit reached|"
                                r"You[’']ve (?:hit|reached) your (?:usage )?limit|\d+-hour limit reached|"
                                r"Weekly limit reached|Rate limit reached|Request rejected \(429\)|"
                                r"You have exhausted your quota|individual quota reached)", re.I)),
    ("logged out", re.compile(ERROR_CHROME + r"(?:API Error: 401|Invalid API key|OAuth token (?:has )?expired|"
                              r"Not logged in|Please run /login|Your access token could not be refreshed|"
                              r"Authentication expired|You are not logged into Antigravity)",
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


# Every key a factory.json agent may carry: (accepts, what is allowed, what a bad value falls back to).
# A bad value is dropped, so the agent gets the safe default: never a wake or a reset nobody asked for.
AGENT_KEYS = {
    "name": (lambda v: isinstance(v, str) and NAME_RE.fullmatch(v), f"a name matching {NAME_RE.pattern}",
             "agent skipped"),
    "kind": (lambda v: v in ("claude", "codex", "agy"), '"claude", "codex" or "agy"', "no per-task reset"),
    "session": (lambda v: isinstance(v, str), "a tmux session name", "hub-<name> used"),
    "reset": (lambda v: v is False or v == "per-task", 'false or "per-task"', "treated as off"),
    "dispatch": (lambda v: isinstance(v, bool), "true or false", "treated as off"),
    "reads": (lambda v: isinstance(v, bool), "true or false", "treated as off"),
    "phase": (lambda v: isinstance(v, str), "a phase name from autonomy.phases", "phase off"),
}


def settings():
    """factory.json's agents with every bad setting dropped, its intervals, and one line per problem.
    With an autonomy block, each agent's phase gives its dispatch, reset and budget (living spec §4)."""
    try:
        cfg = json.loads((HUB / "factory.json").read_text())
    except (OSError, ValueError) as e:
        cfg, bad = {}, [f"factory.json: unreadable ({e}); watching the default agents, dispatching none"]
    else:
        bad = []
    cfg = cfg if isinstance(cfg, dict) else {}
    auto, auto_bad = autonomy.table(cfg)
    bad += auto_bad
    agents = []
    for a in cfg.get("agents") or []:
        if not isinstance(a, dict):
            bad.append(f"factory.json: agent entry {json.dumps(a)} is not an object; skipped")
            continue
        who = a.get("name") if isinstance(a.get("name"), str) else json.dumps(a.get("name"))
        for k, v in a.items():
            if k not in AGENT_KEYS:
                bad.append(f"factory.json: agent {who}: unknown key {json.dumps(k)}; ignored "
                           f"(known: {', '.join(AGENT_KEYS)})")
            elif not AGENT_KEYS[k][0](v):
                bad.append(f"factory.json: agent {who}: {k}={json.dumps(v)} is not allowed "
                           f"(allowed: {AGENT_KEYS[k][1]}); {AGENT_KEYS[k][2]}")
        ok = {k: v for k, v in a.items() if k in AGENT_KEYS and AGENT_KEYS[k][0](v)}
        if "name" not in a:
            bad.append(f"factory.json: agent entry {json.dumps(a)} has no name; skipped")
        if "name" not in ok:  # names reach shell commands, so only plain names pass
            continue
        if "dispatch" in a:
            ok.setdefault("dispatch", False)
        if auto is not None:
            if "phase" in a and isinstance(a["phase"], str) and a["phase"] not in auto["phases"]:
                bad.append(f"factory.json: agent {who}: phase={json.dumps(a['phase'])} is not in autonomy.phases; "
                           f"phase off")
            elif "phase" not in a and a.get("kind") not in auto["known_kinds"]:
                bad.append(f"factory.json: agent {who}: unknown kind {a.get('kind')}, phase off")
            p = autonomy.phase_name(a, auto)
            spec = auto["phases"][p]
            derived = {"phase": p, "dispatch": spec["dispatch"], "reset": spec["reset"],
                       "budget_minutes": spec["budget_minutes"]}
            # A phase wins over hand-set keys; without one they still work, for the migration.
            ok = {**ok, **derived} if "phase" in a else {**derived, **ok}
        agents.append(ok)
    agents = [{"session": f"hub-{a['name'].lower()}", "dispatch": True, **a} for a in agents or DEFAULT_AGENTS]
    return agents, cfg.get("intervals") or {}, bad


def config(notify=False):
    """Agents and intervals. Mistyped settings go to stderr every time, and to the lead once each."""
    agents, intervals, bad = settings()
    for line in bad:
        print(line, file=sys.stderr)
    if notify:
        told = load("config.json").get("told", [])
        new = [line for line in bad if line not in told]
        text = "[dispatch] factory.json has mistyped settings, each replaced by its safe default:\n" + "\n".join(new)
        try:
            sent = not new or not subprocess.run(
                [sys.executable, str(HERE / "board.py"), "notify", LEAD, text], capture_output=True,
                text=True, timeout=30, env={**os.environ, "HUB_AGENT": "Dispatch"}).returncode
        except (OSError, subprocess.TimeoutExpired):
            sent = False
        # Only what is still wrong stays told, so a problem fixed and made again is reported again.
        if sent and told != bad:
            save("config.json", {"told": bad})
    return agents, intervals


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


def blocked_by(all_tasks, name):
    return [t["id"] for t in all_tasks
            if t["status"] == "blocked" and (hb.actor(t) or "").lower() == name.lower()]


def resettable(a, all_tasks):
    """Agent OS §1: a fresh session per task only for an opted-in agent holding nothing, standing
    and blocked tasks included (their context is still worth keeping), that just stopped a turn."""
    name = a["name"]
    held = [t for t in all_tasks if t["status"] == "claimed" and (hb.actor(t) or "").lower() == name.lower()]
    return (a.get("reset") == "per-task" and name.lower() != LEAD.lower() and a.get("kind") in ("claude", "codex", "agy")
            and not held and not blocked_by(all_tasks, name) and load(f"{name}.json").get("event") == "Stop")


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
    return any("esc to interrupt" in line or line.startswith("esc to cancel") for line in tail(pane))  # agy


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


FLASH = "gemini-3.8-flash-medium"  # shell.sh's agy default


def quota_out(name, now, model=None):
    """(reset epoch, line) when agy's statusLine file (agy-status.sh) shows a quota bucket of the running
    model's (or `model`'s) family used up and not yet reset, else None: every gemini-* for Argon, only
    gemini-5h and gemini-weekly for other Gemini models (gemini-argon-wtu-weekly is Argon's alone), 3p-*
    for the rest (Claude), either when the model is unknown. Several used up: the later reset is real."""
    st = load(f"{name}.agy.json")
    if model is None:
        model = st.get("model") if isinstance(st.get("model"), str) else ""
    m = model.lower()
    family = (("gemini-",) if "argon" in m else ("gemini-5h", "gemini-weekly") if m.startswith("gemini")
              else ("3p-",) if m else ("gemini-", "3p-"))
    out = []
    for bucket, q in (st.get("quota") or {}).items():
        try:
            if bucket.startswith(family) and q["remaining_fraction"] <= 0:
                at = datetime.fromisoformat(q["reset_time"].replace("Z", "+00:00")).timestamp()
                if at > now:
                    out.append((at, f"{bucket} quota used up"))
        except (TypeError, KeyError, ValueError, AttributeError):
            continue
    return max(out, default=None)


def flash_fallback(name, since, now):
    """True when the agy seat should be relaunched on Flash: its model is not Flash and that model's bucket
    is used up, while Flash's have room (gemini-weekly among them). A statusLine older than `since` (the
    last relaunch) is the previous session's, so it never counts: no kill loop before the new one reports."""
    st = load(f"{name}.agy.json")
    model = st.get("model") if isinstance(st.get("model"), str) else ""
    try:
        fresh = datetime.fromisoformat(st["at"]).timestamp() > since
        room = st["quota"]["gemini-weekly"]["remaining_fraction"] > 0
    except (KeyError, TypeError, ValueError):
        return False
    return (fresh and room and model != "" and "flash" not in model.lower()
            and bool(quota_out(name, now)) and not quota_out(name, now, FLASH))


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
    next's first pick, so a skipped task (untrusted, run-locked, offered) falls through.
    `read` tasks belong to the reader (factory.json "reads": true), the only tasks it is offered, and held back
    from everyone else until open longer than offer_minutes, in case the reader is down or limited."""
    out = []
    for project in projects or [None]:
        # next_candidates ends with the agent's work in other projects; that is not this project's.
        out += [t for t in hb.next_candidates(all_tasks, name, project)
                if project is None or (t.get("project") or "") == project]
    agents, intervals = config()
    readers = {a["name"].lower() for a in agents if a.get("reads") is True and a.get("dispatch")}
    is_read = lambda t: "read" in (t.get("tags") or [])  # noqa: E731
    if name.lower() in readers:
        return [t for t in out if is_read(t)]  # the reader is research only (lead, 2026-10-23)
    if readers:
        cutoff = time.time() - intervals.get("offer_minutes", 30) * 60
        out = [t for t in out if not is_read(t) or datetime.fromisoformat(t["created"]).timestamp() < cutoff]
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


def fetch(t):
    """hub claim builds the worktree from $HUB_CODE_DIR/<project>'s origin refs, and Prometheus's sandbox has no DNS to
    fetch them: fetch here, outside any sandbox, so they are fresh. On failure they stay as they were."""
    clone = Path(os.environ.get("HUB_CODE_DIR") or Path.home() / "code") / (t.get("project") or "")
    if (clone / ".git").exists():
        try:
            subprocess.run(["git", "-C", str(clone), "fetch", "-q", "--prune", "origin"], capture_output=True,
                           timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"  git fetch failed: {e!r}", file=sys.stderr)


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


def reset_wake(name, t, kind):
    """Inbox message, then the v2 request hubwaked turns into /clear or /new plus the receive line."""
    mid = f"{time.time_ns()}-{os.getpid()}"
    text = (f"[dispatch] Fresh session. Your task: {t['id']} {t['title']}. Run: hub claim {t['id']} && "
            f"hub show {t['id']}, then work in the workspace path hub claim prints.")
    try:
        r = subprocess.run([sys.executable, str(HERE / "board.py"), "notify", name, text, "--task", t["id"],
                            "--message-id", mid], capture_output=True, text=True, timeout=30,
                           env={**os.environ, "HUB_AGENT": "Dispatch"})
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"  hub notify failed: {e!r}", file=sys.stderr)
        return False
    if r.returncode:
        print(f"  hub notify failed: {r.stderr.strip()}", file=sys.stderr)
        return False
    wake_dir = HUB / "wake"
    wake_dir.mkdir(exist_ok=True)
    # Overwrites any pending request: the relay's receive --pending reveals every unreceived message anyway.
    with tempfile.NamedTemporaryFile("w", dir=wake_dir, prefix=f".{name}.", delete=False) as f:
        f.write(f"version=2\nagent={name}\nids={mid}\nreset=1\nkind={kind}\ncreated={int(time.time())}\n")
    os.replace(f.name, wake_dir / f"{name}.wake")
    print(f"  queued -> {name} inbox; reset request wake/{name}.wake")
    return True


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
    agents, intervals = config(notify=not dry)
    state = load("dispatch.json")
    delay = min(state.get("last_tick", 0) + 5 - time.time(), 5)  # a future last_tick waits 5 s, not forever
    if delay > 0:
        print(f"debounced {delay:.1f}s")
        time.sleep(delay)
    kick = STATE / "dispatch.kick"
    for _ in range(3):  # initial pass plus at most two re-runs
        started = kick.stat().st_mtime_ns if kick.exists() else 0
        now = time.time()
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
                        else "stale" if "stale" in (c.get("tags") or [])
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
            how = ("run" if "headless" in (t.get("tags") or [])
                   else "reset" if resettable(a, all_tasks) else "wake")
            verb = {"run": "start hub run for", "reset": "reset for", "wake": "wake for"}[how]
            if dry:
                print(f"{name}: idle, would {verb} {t['id']} {t['title']}{note}")
                continue
            print(f"{name}: idle, {verb} {t['id']} {t['title']}{note}")
            if how != "run":
                fetch(t)
            if (start_headless(name, t) if how == "run" else reset_wake(name, t, a["kind"]) if how == "reset"
                    else wake(name, t)):
                woken[t["id"]] = {**woken.get(t["id"], {}), "agent": name, "at": hb.now(), "how": how}
        if not dry:
            state["last_tick"] = now
            save("dispatch.json", state)
        if (kick.stat().st_mtime_ns if kick.exists() else 0) <= started:
            break
    return 0


def heartbeat(name):
    try:
        beat = json.loads((STATE / f"{name}.json").read_text())
        return datetime.fromisoformat(beat["at"]).timestamp()
    except (OSError, ValueError, KeyError, TypeError):
        return None


def report(name, before, cause, line, dry, lead, key=None):
    msg = f"{name}: {before} -> {cause}" + (f" ({line})" if line else "")
    alert = cause != "healthy"
    key = key or f"watchdog:{name}"  # one current alert per agent in Zeus's inbox, each replacing the last
    if dry:
        print(f"  would log '{msg}'" + (f", notify {LEAD}" if alert else "") + (", alert the lead" if lead else ""))
        return
    with open(HUB / "watchdog.log", "a") as f:
        f.write(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} {msg}\n")
    if not alert:  # recovered or relaunched: its stale alert leaves Zeus's inbox
        hb.deliver(LEAD, None, key=key)
        return
    text = (f"[watchdog] {msg}. The watchdog never relaunches a live session; "
            f"look at tmux hub-{name.lower()}.")
    r = subprocess.run([sys.executable, str(HERE / "board.py"), "notify", LEAD, text, "--key", key],
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
    agents, intervals = config(notify=not dry)
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
        quota = quota_out(name, now)  # agy stops by itself at its quota, with no dialog to answer
        if cause is None and quota:
            cause, line = "rate limited", quota[1]
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
            until = quota[0] if quota else prev["until"] if prev.get("line") == line and prev.get("until") else None
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
    budgets(agents, all_tasks, state, now, dry)
    if not dry:
        save("watch.json", state)
    return 0


def budgets(agents, all_tasks, state, now, dry):
    """Living spec §4: a claimed task past its budget (its own, else its claimer's phase's) tells Zeus once and
    gets a note; past twice its budget, the lead too, once. Nothing is killed or released: work is never lost."""
    names = {a["name"].lower(): a for a in agents}
    over = state.setdefault("over_budget", {})
    for tid in [tid for tid in over if not any(t["id"] == tid and t["status"] == "claimed" for t in all_tasks)]:
        del over[tid]  # released or done: the next claim starts a new budget
        if not dry:
            hb.deliver(LEAD, None, key=f"watchdog:budget:{tid}")
    claims = None
    for t in all_tasks:
        who = hb.canon(hb.actor(t) or "")
        a = names.get(who.lower(), {})
        budget = t.get("budget_minutes") or a.get("budget_minutes")
        if t["status"] != "claimed" or "standing" in (t.get("tags") or []) or not budget:
            continue
        if limited(state.get(a.get("name"), {}), now):
            continue  # parked by the rate-limit breaker: waiting out a limit is not overrunning
        at = t.get("claimed_at")
        if not at:  # claimed before claimed_at existed: the ledger's latest claim, else skipped
            if claims is None:
                claims = {e["task"]: e["at"] for e in hb.ledger() if e["event"] == "claimed"}
            at = claims.get(t["id"])
        if not at:
            continue
        minutes = int((now - datetime.fromisoformat(at).timestamp()) // 60)
        level = 2 if minutes >= 2 * budget else 1 if minutes >= budget else 0
        if level <= over.get(t["id"], 0):
            continue
        cause = f"over {'2x ' if level == 2 else ''}budget"
        line = f"{t['id']} {cause}: claimed {minutes} min ago, budget {budget} min"
        print(f"{who}: {line}")
        report(who, "on time", cause, line, dry, lead=level == 2, key=f"watchdog:budget:{t['id']}")
        if dry:
            continue
        with hb.board(write=True) as (data, events):
            x = next((x for x in data["tasks"] if x["id"] == t["id"]), None)
            if x is not None:
                x["notes"].append({"at": hb.now(), "by": "Watchdog",
                                   "text": f"{line}. Nothing is stopped: finish it, hub block it, or ask Zeus."})
                x["updated"] = hb.now()
            hb.log(events, "Watchdog", "over_budget", t["id"], agent=who, level=level, minutes=minutes, budget=budget)
        over[t["id"]] = level


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
    autonomy.weekly(dry)
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("tick", "watch", "weekly", "agents", "check-config", "flash-fallback"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("name", nargs="?", help="flash-fallback: the agy agent")
    p.add_argument("--since", type=float, default=0, help="flash-fallback: ignore statusLines older than this epoch")
    a = p.parse_args()
    if a.command == "agents":
        print(" ".join(x["name"] for x in config()[0]))
        return 0
    if a.command == "flash-fallback":  # exit 0: relaunch it on Flash (an agy seat)
        return 0 if a.name and flash_fallback(a.name, a.since, time.time()) else 1
    if a.command == "check-config":
        bad = settings()[2]
        for line in bad:
            print(line, file=sys.stderr)
        return 1 if bad else 0
    return {"tick": tick, "watch": watch, "weekly": weekly}[a.command](a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
