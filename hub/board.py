#!/usr/bin/env python3
"""Shared task board for the agent hub. Safe for concurrent access by multiple agents.

State lives in board.json (current snapshot) and events.jsonl (append-only ledger).
The ledger is the audit trail: every transition is recorded there even if a later write
to the snapshot is lost, so it's the place to look when debugging a race.
"""

import argparse
import difflib
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone

# Normally the directory this script lives in. Overridable so the suite can run against a
# throwaway board -- without this, testing concurrency or crash behaviour would mean
# mutating the live board five agents are using.
HUB_DIR = os.environ.get("HUB_DIR") or os.path.dirname(os.path.realpath(__file__))
BOARD = os.path.join(HUB_DIR, "board.json")
EVENTS = os.path.join(HUB_DIR, "events.jsonl")
LOCK = os.path.join(HUB_DIR, ".board.lock")
WAL = os.path.join(HUB_DIR, ".board.wal")
INBOX_DIR = os.path.join(HUB_DIR, "inbox")
PAUSE = os.path.join(HUB_DIR, "PAUSE")

STATUSES = ("open", "claimed", "done", "blocked")

# Legal transitions, in one place rather than scattered through cmd_*. The board's whole
# premise is that a stranger agent can pick up work safely; without this, any agent could
# finish another's task, re-finish a done one, or block something nobody claimed.
# Each verb has exactly one destination; what varies is which states you may leave from.
FROM_STATES = {
    "claim":   ("open", "blocked", "claimed"),   # re-claiming your own is a no-op, not an error
    "release": ("claimed", "blocked"),
    "done":    ("claimed",),                     # so a second `hub done` is refused, not silently re-run
    "block":   ("claimed",),                     # you must hold a task to declare it stuck
}
TO_STATE = {"claim": "claimed", "release": "open", "done": "done", "block": "blocked"}

# Which verbs require you to be the task's owner. Notes are deliberately absent: they are
# additive, attributed and non-destructive, and cross-agent commentary on a task (a review
# finding, a heads-up) is a thing the hub should encourage, not refuse.
OWNED_VERBS = ("release", "done", "block")
ACTIVE = ("open", "claimed", "blocked")
LOCK_TIMEOUT = 10.0

# hub done's verify gate. A failed verify is an attempt; this many and the task blocks.
MAX_ATTEMPTS = 2
VERIFY_TIMEOUT = 1800   # seconds; HUB_VERIFY_TIMEOUT overrides it
VERIFY_TAIL = 30        # lines of verify output kept on the task
SH_LOGS = os.path.join(HUB_DIR, "logs", "sh")   # hub sh and verify output; inbox_gc prunes after 7 days
SHOW_NOTES, NOTE_CUT = 5, 600                   # hub show without --full

# Bumped when board.json's shape changes; migrate() upgrades older boards in place.
# A board written before versioning existed has no field at all, which is version 1.
SCHEMA_VERSION = 1

IDENTITY_VARS = ("HUB_AGENT", "CLAUDE_CODE_SESSION_NAME")

# Events that can make work claimable. board() touches state/dispatch.kick on any of them, which
# hub-dispatch.path turns into a dispatcher run; a plain note or notify must not, or dispatch's
# own messages would re-trigger it.
KICK_EVENTS = {"created", "done", "released", "unblocked", "assigned", "delegated", "reopened"}

# Agent names become file paths (inbox/<Agent>.jsonl), so they are validated rather than
# trusted: os.path.join with an absolute or traversing name silently escapes INBOX_DIR.
# Every agent can already run shell, so this is not a privilege boundary -- it stops a
# typo from creating a ghost inbox nobody ever reads.
AGENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
PROJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
MESSAGE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,96}$")

# whoami() falls back to this when no identity variable is in scope. It may act (reads,
# and writes attributed honestly as unknown) but must never own or receive: a message
# delivered to "Unknown" is a message nobody is watching for.
UNKNOWN = "Unknown"


def _fsync_dir(path):
    """A rename is only durable once the *directory* entry is flushed."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _fsync_dir(os.path.dirname(path) or ".")


def _repair_jsonl_tail(path):
    """Drop only a torn final JSONL record, preserving every complete record."""
    try:
        with open(path, "rb+") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if not size:
                return
            f.seek(-1, os.SEEK_END)
            if f.read(1) == b"\n":
                return
            f.seek(0)
            data = f.read()
            end = data.rfind(b"\n") + 1
            f.truncate(end)
            f.flush()
            os.fsync(f.fileno())
    except FileNotFoundError:
        pass


def read_events(repair=True):
    """Read complete ledger records.

    Callers holding the board lock repair a crash-torn final append. Lock-free readers pass
    repair=False and skip an unterminated last line instead: it may be a concurrent
    writer's append still in progress, and truncating it would tear the ledger mid-file.
    """
    if repair:
        _repair_jsonl_tail(EVENTS)
    records = []
    try:
        with open(EVENTS) as f:
            for line in f:
                if not line.endswith("\n"):
                    break
                if line.strip():
                    records.append(json.loads(line))
    except FileNotFoundError:
        pass
    return records


def _recover_wal():
    """Apply a complete WAL only when its transaction reached the fsynced journal."""
    if not os.path.exists(WAL):
        return
    with open(WAL) as f:
        wal = json.load(f)
    txid = wal.get("txid")
    committed = any(
        event.get("txid") == txid and event.get("event") == "commit"
        for event in read_events()
    )
    if committed:
        _write_json_atomic(BOARD, wal["board"])
    else:
        with open(EVENTS, "a") as f:
            f.write(json.dumps({"at": now(), "by": "recovery", "event": "abort", "task": "-", "txid": txid}) + "\n")
            f.flush()
            os.fsync(f.fileno())
    os.remove(WAL)
    _fsync_dir(HUB_DIR)


def migrate(data):
    """Bring an older board up to SCHEMA_VERSION. Returns True if anything changed."""
    v = data.get("schema_version", 1)
    if v > SCHEMA_VERSION:
        sys.exit(
            f"board.json is schema v{v}, but this board.py understands only "
            f"v{SCHEMA_VERSION}. Update board.py rather than downgrading the board."
        )
    changed = "schema_version" not in data
    data["schema_version"] = SCHEMA_VERSION
    for t in data.get("tasks", []):  # hand-written or fixture tasks may lack a notes list; everything appends to it
        if "notes" not in t:
            t["notes"], changed = [], True
    return changed


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canon(name):
    """One agent, one spelling, one inbox file. zeus / ZEUS / Zeus are the same agent."""
    name = (name or "").strip()
    return name[:1].upper() + name[1:].lower()


# The planning agent: hears about blocked tasks and alone clears 'untrusted'. shell.sh exports it.
LEAD_AGENT = canon(os.environ.get("HUB_LEAD") or "Zeus")


def valid_agent(name, what="agent"):
    """Canonical form, or exit. Rejects path separators, traversal and absolute paths."""
    c = canon(name)
    if not AGENT_RE.match(c):
        sys.exit(
            f"invalid {what} name: {name!r}\n"
            f"names are letters, digits, _ and -, starting with a letter (max 32)."
        )
    return c


def valid_project(name):
    """Canonical project tag, or exit. Lowercased so webapp / Webapp are one project."""
    c = (name or "").strip().lower()
    if not PROJECT_RE.match(c):
        sys.exit(
            f"invalid project name: {name!r}\n"
            f"projects are letters, digits, _ - and . (max 48)."
        )
    return c


def which_project(explicit=None):
    """Project scope. Explicit flag wins, then $HUB_PROJECT. None means the whole board."""
    if explicit:
        return valid_project(explicit)
    if os.environ.get("HUB_PROJECT"):
        return valid_project(os.environ["HUB_PROJECT"])
    return None


def addressable(name, what="agent"):
    """An agent that can own work or receive mail."""
    c = valid_agent(name, what)
    if c == UNKNOWN:
        sys.exit(
            f"refusing to use {UNKNOWN!r} as a {what}: this session has no identity.\n"
            f"set $HUB_AGENT, or pass --as <Name>."
        )
    return c


def _read_environ(pid):
    with open(f"/proc/{pid}/environ", "rb") as f:
        raw = f.read().decode("utf-8", "replace")
    return dict(kv.split("=", 1) for kv in raw.split("\0") if "=" in kv)


def _ppid(pid):
    with open(f"/proc/{pid}/stat") as f:
        return int(f.read().rpartition(")")[2].split()[1])


def whoami(explicit=None):
    """Agent name. Claude Code strips CLAUDE_CODE_* from tool subprocesses, so when the
    variables aren't in our own environment we walk up to the session process that has them."""
    if explicit:
        return valid_agent(explicit, "agent (--as)")
    for var in IDENTITY_VARS:
        if os.environ.get(var):
            return valid_agent(os.environ[var], f"agent (${var})")
    pid = os.getpid()
    for _ in range(12):
        try:
            env = _read_environ(pid)
            for var in IDENTITY_VARS:
                if env.get(var):
                    return valid_agent(env[var], f"agent (${var})")
            pid = _ppid(pid)
        except (OSError, ValueError, IndexError):
            break
        if pid <= 1:
            break
    return UNKNOWN


def _acquire(fh):
    """Bounded wait. A crashed holder is not a problem — the kernel drops flock when the
    process dies — but a hung one would block every other agent forever without this."""
    deadline = time.monotonic() + LOCK_TIMEOUT
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                sys.exit(
                    f"board locked by another agent for >{LOCK_TIMEOUT:.0f}s — it is probably hung.\n"
                    f"check with: hubs     then stop the stuck agent with: hubkill <agent>"
                )
            time.sleep(0.1)


@contextmanager
def board(write=False):
    if not os.path.isdir(HUB_DIR):
        sys.exit(f"HUB_DIR is not a directory: {HUB_DIR}")
    with open(LOCK, "a") as lk:
        _acquire(lk)
        try:
            _recover_wal()
            try:
                with open(BOARD) as f:
                    data = json.load(f)
            except FileNotFoundError:  # a fresh hub, or a test's scratch one: an empty board
                data = {"next_id": 1, "tasks": [], "schema_version": SCHEMA_VERSION}
            migrate(data)
            events = []
            yield data, events
            if write:
                txid = f"{time.time_ns()}-{os.getpid()}"
                _write_json_atomic(WAL, {"txid": txid, "board": data})
                # Journal FIRST. HUB.md tells agents the ledger is what to trust when the
                # snapshot looks wrong; writing the snapshot first made that false, because
                # a crash in between lost the record of a change that had already
                # committed. Appending and fsyncing the events before the snapshot means
                # the ledger is never behind reality -- at worst it is briefly ahead, which
                # is the recoverable direction.
                if events:
                    _repair_jsonl_tail(EVENTS)
                    with open(EVENTS, "a") as f:
                        for e in events:
                            e["txid"] = txid
                            f.write(json.dumps(e) + "\n")
                        f.write(json.dumps({"at": now(), "by": "board", "event": "commit", "task": "-", "txid": txid}) + "\n")
                        f.flush()
                        os.fsync(f.fileno())

                _write_json_atomic(BOARD, data)
                os.remove(WAL)
                _fsync_dir(HUB_DIR)
                _kick(data, events)
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def _kick(data, events):
    """Wake the dispatcher, and on done the project's hub live loop. Best effort: the commit
    has landed, and the timers still catch a missed kick."""
    if not KICK_EVENTS & {e["event"] for e in events}:
        return
    paths = [os.path.join(HUB_DIR, "state", "dispatch.kick")]
    tasks = {t["id"]: t for t in data["tasks"]}
    for e in events:
        p = e["event"] == "done" and tasks.get(e["task"], {}).get("project")
        if p and os.path.isdir(os.path.join(HUB_DIR, "projects", p)):
            paths.append(os.path.join(HUB_DIR, "projects", p, ".tick-now"))
    for path in paths:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "a").close()
            os.utime(path)
        except OSError:
            pass


def log(events, who, event, task_id, **extra):
    events.append({"at": now(), "by": who, "event": event, "task": task_id, **extra})


def norm_id(tid):
    """T-003, t-3 and 3 all name the same task."""
    tid = str(tid).strip().upper()
    if tid.startswith("T-"):
        tid = tid[2:]
    return "T-" + tid.zfill(3)


def find(data, tid):
    tid = norm_id(tid)
    for t in data["tasks"]:
        if t["id"] == tid:
            return t
    sys.exit(f"no such task: {tid}")


def is_hackathon(project):
    return bool(project) and os.path.exists(
        os.path.join(HUB_DIR, "projects", project, "hackathon.json"))


def roster_rules(t):
    """Hackathon ownership (a roster human owns, an agent is delegated, gh-sync closes the issue's
    task) for a task in a hackathon project. Not for a factory task: the poll made it from an
    `agent` issue with no roster owner, and no gh-sync closes it (hub live runs factory repos too)."""
    return is_hackathon(t.get("project")) and t.get("kind") != "factory"


def label(t):
    if t.get("issue") and is_hackathon(t.get("project")):
        return f"#{t['issue']}"
    return t["id"]


def resolve(data, ref, project=None):
    s = str(ref).strip()
    bare = s[1:] if s.startswith("#") else s
    if bare.isdigit() and is_hackathon(project):
        n = int(bare)
        for t in data["tasks"]:
            if t.get("project") == project and t.get("issue") == n:
                return t
        sys.exit(f"no task has issue #{n} in {project} yet; use its T-id (hub list)")
    return find(data, bare)


def roster(project):
    if not is_hackathon(project):
        return None
    with open(os.path.join(HUB_DIR, "projects", project, "hackathon.json")) as f:
        return json.load(f)


def humans_of(project):
    return {canon(p["name"]) for p in (roster(project) or {}).get("roster", [])}


def agents_of(project):
    return {canon(a["name"]): canon(p["name"])
            for p in (roster(project) or {}).get("roster", []) for a in p.get("agents", [])}


def actor(t):
    return t.get("agent") or t.get("owner")


def check_owner(project, owner, ref="<n>"):
    if not is_hackathon(project) or owner is None or owner == "Pool" or owner in humans_of(project):
        return
    human = agents_of(project).get(owner)
    if human:
        sys.exit(f"{owner} is an agent, not a roster human: "
                 f"hub assign {ref} {human}, then hub delegate {ref} {owner}")
    sys.exit(f"{owner} is not a roster human in {project}: "
             "owners are the roster humans in hackathon.json")


def transition(t, verb, me, force=False, who=None):
    """Authorise and apply one status change, or exit explaining what is allowed.

    Returns True if an ownership/state rule was overridden, so the caller can record that
    in the ledger -- an override that leaves no trace is how two agents end up disagreeing
    about who did what.
    """
    allowed = FROM_STATES[verb]
    status = t["status"]
    overridden = False

    if status not in allowed:
        if force:
            overridden = True
        else:
            sys.exit(
                f"cannot {verb} {label(t)}: it is {status}.\n"
                f"{verb} is legal from: {', '.join(allowed)}\n"
                f"use --force to override, or check: hub show {label(t)}"
            )

    owner = who if who is not None else t.get("owner")
    # Ownership blocks a claim whatever the status: `hub new --owner Hermes` assigns work
    # up front, and letting anyone claim it anyway would make that assignment advisory.
    # An unowned task (never assigned, or released) is free for anyone to take.
    if verb == "claim" and owner and owner != me:
        if force:
            overridden = True
        else:
            held = "already claimed by" if status == "claimed" else "assigned to"
            sys.exit(
                f"{label(t)} is {held} {owner}, not {me}.\n"
                f"take it over with: hub claim {label(t)} --force"
            )

    if verb in OWNED_VERBS and owner and owner != me:
        if force:
            overridden = True
        else:
            sys.exit(
                f"cannot {verb} {label(t)}: it belongs to {owner}, not {me}.\n"
                f"ask them, or take it over with: hub claim {label(t)} --force"
            )

    t["status"] = TO_STATE[verb]
    t["updated"] = now()
    return overridden


def validate_deps(data, deps, own_id, project=None):
    """Deps are normalised and proven sane at creation -- the only point they enter."""
    seen, out = set(), []
    for d in deps:
        d = (resolve(data, d, project)["id"]
             if is_hackathon(project) and str(d).lstrip("#").isdigit() else norm_id(d))
        if d == own_id:
            sys.exit(f"a task cannot depend on itself ({d})")
        if not any(t["id"] == d for t in data["tasks"]):
            sys.exit(f"unknown dependency: {d}\nexisting tasks: hub list --all")
        if d not in seen:
            seen.add(d)
            out.append(d)

    # A brand-new task has nothing pointing at it, so it cannot close a cycle -- but deps
    # are also the one place a pre-existing cycle would surface, so check the whole graph.
    edges = {t["id"]: list(t.get("deps", [])) for t in data["tasks"]}
    edges[own_id] = out
    state = {}

    def walk(nid):
        if state.get(nid) == "done":
            return
        if state.get(nid) == "open":
            sys.exit(f"dependency cycle through {nid}")
        state[nid] = "open"
        for nxt in edges.get(nid, []):
            walk(nxt)
        state[nid] = "done"

    walk(own_id)
    return out


def unmet_deps(data, task):
    done = {t["id"] for t in data["tasks"] if t["status"] == "done"}
    return [d for d in task.get("deps", []) if d not in done]


@contextmanager
def inbox_lock(agent):
    """Per-inbox, not the board lock.

    Taking the global board lock for every delivery would make notifications contend with
    task writes, and `hub done` delivers while already holding it. One lock per inbox
    keeps mail off the board's critical path.
    """
    # Inboxes carry inter-agent traffic; keep them private to this user.
    os.makedirs(INBOX_DIR, mode=0o700, exist_ok=True)
    with open(os.path.join(INBOX_DIR, f".{agent}.lock"), "a") as lk:
        _acquire(lk)
        try:
            yield
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def read_msgs(path):
    """Tolerate a torn trailing line: a reader must never crash on a concurrent append."""
    msgs = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msgs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # partial write in flight; it will be complete next read
    except FileNotFoundError:
        pass
    return msgs


def deliver(agent, text, message_id=None, key=None):
    """Durable notification. This does NOT ping a live session — see notify_hint().

    A `key` marks a status line that only matters while it is current (a watchdog alert): it
    replaces every earlier message with that key, and text=None only withdraws them. Without it,
    alerts about sessions long since relaunched piled up in Zeus's inbox (2026-11-01)."""
    agent = addressable(agent, "recipient")
    path = os.path.join(INBOX_DIR, f"{agent}.jsonl")
    with inbox_lock(agent):
        # Every append happens under this lock, so an unterminated last line here can only
        # be a crashed writer's leftover. Drop it first: appending onto it would fuse the
        # new record into the torn one, and a message acknowledged as queued would be lost.
        _repair_jsonl_tail(path)
        if message_id and any(m.get("id") == message_id for m in read_msgs(path)):
            return
        msgs = read_msgs(path) if key else []
        if any(m.get("key") == key for m in msgs):
            for m in msgs:  # superseded counts as received, so a wake still listing it is dropped
                if m.get("key") == key and MESSAGE_ID_RE.match(m.get("id") or ""):
                    take_receipt(os.path.join(INBOX_DIR, ".received", agent), m["id"])
            fd, tmp = tempfile.mkstemp(dir=INBOX_DIR, prefix=f".{agent}.")
            with os.fdopen(fd, "w") as f:
                f.writelines(json.dumps(m) + "\n" for m in msgs if m.get("key") != key)
            os.replace(tmp, path)
        if text is None:
            return
        with open(path, "a") as f:
            f.write(json.dumps({"at": now(), "text": text, **({"id": message_id} if message_id else {}),
                                **({"key": key} if key else {})}) + "\n")


def new_message_id():
    return f"{time.time_ns()}-{os.getpid()}-{os.urandom(2).hex()}"


def notify_hint(targets):
    """The queued message is passive; this is the ping half of queue-and-ping.

    It must name a command *every* agent can run. SendMessage is a Claude-only tool, so
    hinting it told Prometheus (Codex) to do something impossible and the ping was simply
    never sent. hubmsg works for every agent regardless of vendor and does both halves in
    one call, so it is the honest universal hint.
    """
    if not targets:
        return
    print("\nto ping them live (wakes them; --id reuses the message already queued):")
    for agent, text, message_id in targets:
        # shlex.quote so the line stays copy-pasteable when a task title contains
        # quotes, apostrophes or $ -- which task titles routinely do. --id makes hubmsg's
        # own queueing a no-op, so running the hint never lands the message twice.
        print(f"  hubmsg {shlex.quote(agent)} {shlex.quote(text)} --id {message_id}")


def fmt_row(t, data=None):
    mark = {"open": "○", "claimed": "◐", "done": "●", "blocked": "✗"}[t["status"]]
    kind = "▣ " if t.get("kind") == "vertical" else ""
    progress = ""
    if data and t.get("kind") == "vertical":
        children = [x for x in data["tasks"] if x.get("parent") == t["id"]]
        progress = f"  {sum(x['status'] == 'done' for x in children)}/{len(children)}"
    owner = (f" @{t['owner']}" if t.get("owner") else "") + (f"→{t['agent']}" if t.get("agent") else "")
    blocked = ""
    if data and t["status"] in ("open", "claimed"):
        missing = unmet_deps(data, t)
        if missing:
            by_id = {x["id"]: x for x in data["tasks"]}
            blocked = f"  ⇠ waits on {','.join(label(by_id[m]) if m in by_id else m for m in missing)}"
    tag = f" [{t['project']}]" if t.get("project") else ""
    gh_status = t.get("gh_status")
    activity = f" · {gh_status.lower()}" if t["status"] == "open" and gh_status in (
        "In progress", "In review") else ""
    return f"  {mark} {kind}{label(t)}  {t['title']}{progress}{tag}{owner}{blocked}{activity}"


def paused():
    """The kill switch's reason, or None. dispatch.py, live.py and the watchdog read it too."""
    try:
        with open(PAUSE) as f:
            return f.read().strip() or "no reason given"
    except FileNotFoundError:
        return None


def refuse_if_paused(verb):
    reason = paused()
    if reason:
        sys.exit(f"hub is paused, so {verb} is refused: {reason}\n`hub resume` lifts it.")


def cmd_pause(a):
    me = whoami(a.as_agent)
    reason = " ".join(a.reason).strip() or "no reason given"
    with board(write=True) as (_, events):
        with open(PAUSE + ".tmp", "w") as f:
            f.write(f"{reason} (by {me} at {now()})\n")
        os.replace(PAUSE + ".tmp", PAUSE)
        log(events, me, "paused", "-", reason=reason)
    print(f"hub paused: {reason}\nhub next and hub claim refuse until `hub resume`.")


def cmd_resume(a):
    me = whoami(a.as_agent)
    with board(write=True) as (_, events):
        was = paused()
        if was is None:
            print("hub is not paused")
            return
        os.remove(PAUSE)
        log(events, me, "resumed", "-", was=was)
    print(f"hub resumed (was paused: {was})")


def task_repo(t):
    """The task's checkout, resolved the way shell.sh's _hub_project_dir does."""
    p = t.get("project")
    code = os.environ.get("HUB_CODE_DIR") or os.path.expanduser("~/code")
    for d in ((os.path.join(code, p), os.path.expanduser(f"~/{p}")) if p else ()):
        if os.path.isdir(os.path.join(d, ".git")):
            return d
    return None


def verify_checkout(repo, workspace=None):
    """The task's claim workspace, else the caller's worktree when it is a checkout of the
    task's repo, else the repo itself.

    Builders work in linked worktrees on branches; verifying the main checkout would test
    the wrong tree."""
    if workspace and os.path.isdir(workspace):
        return workspace
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}

    def rev_parse(d, flag):
        r = subprocess.run(["git", "-C", d, "rev-parse", flag], env=env,
                           capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None

    def common(d):
        c = rev_parse(d, "--git-common-dir")
        return c and os.path.realpath(os.path.join(d, c))

    here = os.getcwd()
    if repo and common(here) and common(here) == common(repo):
        return rev_parse(here, "--show-toplevel") or repo
    return repo


def verify_command(t, repo):
    """The task's own verify: line; unset means `make check` when the repo has that target."""
    if "verify" in t:
        # "" is an explicit "no verify", and so is '' that a re-quoting caller stored literally (T-556)
        return t["verify"] if (t["verify"] or "").strip("'\" ") else None
    if not repo:
        return None
    try:
        with open(os.path.join(repo, "Makefile")) as f:
            return "make check" if re.search(r"^check\s*:", f.read(), re.M) else None
    except OSError:
        return None


def sh_log(me, name):
    os.makedirs(d := os.path.join(SH_LOGS, me), exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return os.path.join(d, f"{stamp}-{re.sub(r'[^A-Za-z0-9._-]', '_', name)[:60]}.log")


def run_verify(cmd, cwd, log=None, strip_hub_env=True, tail=VERIFY_TAIL):
    """(exit code, output lines, last `tail` lines); 124 on timeout. Own session so a timeout
    kills the whole tree. Output goes straight to `log` when given, so a killed run keeps it."""
    timeout = int(os.environ.get("HUB_VERIFY_TIMEOUT") or VERIFY_TIMEOUT)
    # A repo check is not a board operation: without this a hub test suite run as verify
    # would inherit HUB_DIR and write to whichever board the caller is pointed at.
    env = {k: v for k, v in os.environ.items()
           if not (strip_hub_env and k in ("HUB_DIR", "HUB_AGENT"))}
    with open(log, "w+b") if log else tempfile.TemporaryFile() as f:
        p = subprocess.Popen(cmd, shell=True, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                             stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = p.wait(timeout=timeout)
            rc = 128 - rc if rc < 0 else rc   # killed by a signal: report it as a shell would
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            rc = 124
            f.seek(0, os.SEEK_END)
            f.write(f"\n(timed out after {timeout}s)\n".encode())
        f.seek(0)
        lines = f.read().decode(errors="replace").rstrip("\n").splitlines()
    return rc, len(lines), "\n".join(lines[-tail:] if tail else [])


def cmd_sh(a):
    argv = a.argv[1:] if a.argv[:1] == ["--"] else a.argv
    if not argv or not argv[0].strip():
        sys.exit("usage: hub sh [--tail N] [--name x] -- <cmd...>")
    cmd = argv[0] if len(argv) == 1 else shlex.join(argv)   # one argument is a shell line
    log = sh_log(whoami(a.as_agent), a.name or os.path.basename(argv[0].split()[0]))
    start = time.monotonic()
    rc, n, tail = run_verify(cmd, None, log=log, strip_hub_env=False, tail=a.tail)
    print(f"exit {rc} · {n} lines · {time.monotonic() - start:.1f}s · log {log}")
    if tail:
        print(tail)
    sys.exit(rc)


def bump_attempts(tid, me, why, tail):
    """Count a failed attempt that is not hub done's verify (hub live: a red CI run on the task's
    PR) and keep its tail on the task. Returns the new count, or None when there is no such task."""
    with board(write=True) as (data, events):
        t = next((x for x in data["tasks"] if x["id"] == norm_id(tid)), None)
        if t is None:
            return None
        t["attempts"] = n = t.get("attempts", 0) + 1
        t["notes"].append({"at": now(), "by": me, "text": f"{why} (attempt {n})\n{tail}"})
        t["updated"] = now()
        log(events, me, "attempt_failed", t["id"], why=why, attempts=n)
    return n


def verify_failed(tid, me, cmd, tail):
    """Count the attempt, keep the tail on the task, block at MAX_ATTEMPTS and tell the lead."""
    with board(write=True) as (data, events):
        t = find(data, tid)
        t["attempts"] = n = t.get("attempts", 0) + 1
        t["notes"].append({"at": now(), "by": me,
                           "text": f"verify failed (attempt {n}): {cmd}\n{tail}"})
        t["updated"] = now()
        log(events, me, "verify_failed", tid, cmd=cmd, attempts=n)
        blocked = n >= MAX_ATTEMPTS
        if blocked:
            t["status"] = "blocked"
            log(events, me, "blocked", tid, reason=f"verify failed {n} times")
            alert = (f"{label(t)} blocked: verify `{cmd}` failed {n} times. "
                     f"Output tail is on the task: hub show {label(t)}")
            log(events, me, "notify", tid, to=LEAD_AGENT, text=alert)
    if blocked:
        mid = new_message_id()
        deliver(LEAD_AGENT, f"{alert}  (from {me})", mid)
        notify_hint([(LEAD_AGENT, alert, mid)])
    sys.exit(f"{tail}\n\nverify failed: {cmd} (attempt {n} of {MAX_ATTEMPTS})\n"
             + (f"{label(t)} is now blocked and {LEAD_AGENT} has been told." if blocked
                else f"{label(t)} stays claimed: fix it and run hub done again."))


def check_tags(tags):
    bad = [x for x in tags if not re.fullmatch(r"[a-z0-9-]+", x)]
    if bad:
        sys.exit(f"tag names must match [a-z0-9-]+: {', '.join(map(repr, bad))}")
    if "stale" in tags:
        sys.exit("'stale' belongs to the Spec Tree: hub spec apply sets and clears it")


# T-1089: the callers allowed to file intake tasks; a new caller is added here, in review.
INTAKE_SOURCES = ("penpot-comment", "penpot-design")


def cmd_new(a):
    me = whoami(a.as_agent)
    check_tags(a.tag)
    if a.owner:
        a.owner = addressable(a.owner, "owner")
    project = which_project(getattr(a, "project", None))
    check_owner(project, a.owner)
    if a.intake is not None:  # T-1089: outside text enters a spec-locked project as data, held for triage
        given = [f for f, on in (("--req", a.req), ("--from-spec", a.from_spec), ("--generated-from", a.generated_from),
                                 ("--verify", a.verify is not None), ("--owner", a.owner), ("--vertical", a.vertical))
                 if on]
        if given:
            sys.exit(f"--intake tasks wait for triage: drop {', '.join(given)}")
        if a.intake not in INTAKE_SOURCES:  # a fixed list: any slug passes a character check, instructions too
            print(f"--intake <source> must be one of: {', '.join(INTAKE_SOURCES)}", file=sys.stderr)
            sys.exit(2)
        if "\n" in a.title or "\r" in a.title:
            sys.exit("--intake title must be one line")
        import gh_sync  # lazy, as in cmd_edit
        # The caller's title is data too: it goes inside the wrapper, and the stored title is fixed text.
        a.detail = gh_sync.untrusted(a.intake, f"Title: {a.title}" + (f"\n\n{a.detail}" if a.detail else ""))
        a.title = f"intake: {a.intake} {hashlib.sha1(a.title.encode()).hexdigest()[:8]}"
        a.verify = ""  # no check until triage sets one (hub edit --verify)
        a.tag = list(dict.fromkeys(a.tag + ["intake", "untrusted"]))  # untrusted: unclaimable until Zeus clears it
    if project and not a.from_spec and a.intake is None:
        import spec  # lazy, as in main(): spec imports board
        # A draft PRD with no spec.lock is not live yet (hub spec init writes the lock), so it gates nothing.
        if os.path.isfile(spec.spec_path(project)) and os.path.isfile(os.path.join(spec.spec_dir(project), "spec.lock")):
            sys.exit(f"tasks for {project} come from hub spec apply")
    if a.from_spec and not a.generated_from:
        sys.exit("--from-spec needs --generated-from")
    if a.generated_from and not a.from_spec:
        sys.exit("--generated-from needs --from-spec")
    if a.budget is not None and a.budget < 1:
        sys.exit("--budget is whole minutes above 0")
    with board(write=True) as (data, events):
        nid = f"T-{data['next_id']:03d}"
        data["next_id"] += 1
        deps = validate_deps(data, a.dep or [], nid, project)
        data["tasks"].append({
            "id": nid,
            "title": a.title,
            "detail": a.detail or "",
            "status": "open",
            "owner": a.owner,
            "deps": deps,
            "created_by": me,
            "created": now(),
            "updated": now(),
            "notes": [],
            "project": project,
            **({"reqs": a.req} if a.req else {}),
            **({"generated_from": a.generated_from} if a.generated_from else {}),
            **({"kind": "vertical"} if a.vertical else {}),
            **({"verify": a.verify} if a.verify is not None else {}),
            **({"tags": list(dict.fromkeys(a.tag))} if a.tag else {}),
            **({"budget_minutes": a.budget} if a.budget else {}),
        })
        log(events, me, "created", nid, title=a.title, deps=deps, owner=a.owner,
            project=project, **({"tags": list(dict.fromkeys(a.tag))} if a.tag else {}))
        active_project_tasks = sum(t.get("project") == project and t["status"] in ACTIVE
                                   for t in data["tasks"]) if project and not a.from_spec else 0
    print(f"created {nid}: {a.title}" + (f"  [{project}]" if project else ""))
    if active_project_tasks >= 4:
        template = os.path.join(os.path.dirname(os.path.realpath(__file__)), "templates", "prd", "project.json")
        print(f"  note: {project} has {active_project_tasks} active tasks and no live PRD. "
              f"For substantial work, use `hub prd grill {project}`.")
        print(f"  template: {template}; approved spec/design flow: hub-planning.")
    # The project is where this SESSION started, not what it is planning. A lead started
    # in one repo that plans a new one would file the new board under the first.
    if not getattr(a, "project", None):
        if project:
            print(f"  note: tagged [{project}] because this session started there. Planning "
                  f"another repo? `hub note`/recreate with --project <repo>.")
        else:
            print("  note: no project. Scoped agents will not see this; pass --project <repo>.")
    if not a.detail:
        print("  note: no --detail given. Tasks should carry enough plan for another agent to execute cold.")
    if a.owner and a.owner != "Pool" and a.owner not in humans_of(project):
        mid = new_message_id()
        deliver(a.owner, f"{nid} assigned to you: {a.title}", mid)
        notify_hint([(a.owner, f"{nid} is yours: {a.title}. Run: hub show {nid}", mid)])


def cmd_list(a):
    with board() as (data, _):
        tasks = data["tasks"]
        if a.status:
            tasks = [t for t in tasks if t["status"] == a.status]
        elif not a.all:
            tasks = [t for t in tasks if t["status"] in ACTIVE]
        if a.owner:
            tasks = [t for t in tasks if (t.get("owner") or "").lower() == a.owner.lower()]
        project = which_project(getattr(a, "project", None))
        if project:
            tasks = [t for t in tasks if (t.get("project") or "") == project]
        if a.json:
            print(json.dumps(tasks, indent=2))
            return
        if not tasks:
            print("board is empty" if not data["tasks"] else "no tasks match")
            return
        for status in STATUSES:
            group = [t for t in tasks if t["status"] == status]
            if group:
                print(f"\n{status.upper()} ({len(group)})")
                nested = {t["id"]: [] for t in group if t.get("kind") == "vertical"}
                for t in group:
                    if t.get("parent") in nested:
                        nested[t["parent"]].append(t)
                for t in group:
                    if t.get("parent") in nested:
                        continue
                    print(fmt_row(t, data))
                    for child in nested.get(t["id"], []):
                        print("  " + fmt_row(child, data))
        print()


def cmd_show(a):
    with board() as (data, _):
        t = resolve(data, a.id, which_project(getattr(a, "project", None)))
        print(f"\n{'▣ ' if t.get('kind') == 'vertical' else ''}{label(t)}  [{t['status']}"
              f"{', retired: closed, not built' if t.get('retired') and t['status'] == 'done' else ''}]  {t['title']}")
        if t.get("tags"):
            print(f"tags: {', '.join(t['tags'])}")
        if t.get("reqs"):
            print(f"reqs: {', '.join(t['reqs'])}")
        if t.get("generated_from"):
            print(f"generated from: {t['generated_from']}")
        print(f"owner: {t.get('owner') or '-'}   project: {t.get('project') or '-'}"
              f"   created by {t['created_by']} at {t['created']}"
              + (f"   key: {t['id']}" if label(t) != t["id"] else ""))
        if t.get("deps"):
            missing = unmet_deps(data, t)
            by_id = {x["id"]: x for x in data["tasks"]}
            named = lambda ids: ",".join(label(by_id[d]) if d in by_id else d for d in ids)
            print(f"deps: {named(t['deps'])}" + (f"   UNMET: {named(missing)}" if missing else "   (all met)"))
        print(f"\n{t['detail'] or '(no detail)'}\n")
        notes = t["notes"] if a.full else t["notes"][-SHOW_NOTES:]
        if len(notes) < len(t["notes"]):
            print(f"  ({len(t['notes']) - len(notes)} earlier notes: hub show {label(t)} --full)")
        for n in notes:
            text, half = n["text"], NOTE_CUT // 2
            if not a.full and len(text) > NOTE_CUT:   # both ends: a verify tail's summary and log path are last
                text = f"{text[:half]} …(--full)… {text[-half:]}"
            print(f"  · [{n['at']}] {n['by']}: {text}")
        if t["notes"]:
            print()


def strip_issue_extras(body):
    lines = [line.rstrip() for line in (body or "").replace("\r\n", "\n").split("\n")
             if not line.startswith("<!-- hub-task: ") and not line.startswith("Depends on: ")]
    return "\n".join(lines).strip()


def set_deadline(detail, name, project):
    if not is_hackathon(project):
        sys.exit("--deadline needs a hackathon project")
    with open(os.path.join(HUB_DIR, "projects", project, "hackathon.json")) as f:
        names = [d["name"] for d in json.load(f)["deadlines"]]
    if name not in names:
        sys.exit(f"{name!r} is not a deadline in hackathon.json (choose from {', '.join(names)})")
    if re.search(r"^Deadline:", detail, re.M):
        return re.sub(r"^(Deadline:[ \t]*).*$", lambda m: m.group(1) + name, detail,
                      count=1, flags=re.M)
    return detail.rstrip("\n") + f"\nDeadline:     {name}"


def edit_in_editor(text):
    editor = os.environ.get("EDITOR") or ("nano" if shutil.which("nano") else "vi")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(text)
        path = f.name
    try:
        subprocess.run([*shlex.split(editor), path], check=True)
        with open(path, encoding="utf-8") as f:
            return f.read()
    finally:
        os.remove(path)


def cmd_edit(a):
    me = whoami(a.as_agent)
    project = which_project(a.project)
    with board() as (data, _):
        t = dict(resolve(data, a.id, project))
    if t["status"] == "done":
        sys.exit(f"{label(t)} is done; reopen it before editing its brief")
    if t.get("generated_from") and (a.title or a.detail_file or a.take_github or a.deadline or
                                    not (a.keep_hub or a.verify is not None or a.tag or a.untag or a.drop_dep)):
        sys.exit(f"{label(t)} was generated from the PRD; change its brief through hub spec apply")
    if t.get("generated_from") and a.verify is not None and me != LEAD_AGENT and not a.force:
        sys.exit(f"{label(t)} was generated from the PRD; change its verify through hub spec apply")
    if a.take_github and a.keep_hub:
        sys.exit("choose one of --take-github and --keep-hub")
    if (a.take_github or a.keep_hub) and a.detail_file:
        sys.exit("--take-github and --keep-hub don't combine with --detail-file")
    with board() as (data, _):  # a dep may be named by issue number, as hub new --dep takes it
        dropped = list(dict.fromkeys(resolve(data, d, project)["id"] for d in a.drop_dep))
    if missing := [d for d in dropped if d not in (t.get("deps") or [])]:
        sys.exit(f"{label(t)} does not depend on {', '.join(missing)}")
    if dropped and t.get("generated_from") and me != "Zeus" and not a.force:  # spec apply drew that order
        sys.exit(f"{label(t)} was generated from the PRD; only Zeus drops its deps; --force overrides (recorded)")
    bad = [x for x in a.tag + a.untag if not re.fullmatch(r"[a-z0-9-]+", x)]
    if bad:
        sys.exit(f"tag names must match [a-z0-9-]+: {', '.join(map(repr, bad))}")
    if set(a.tag) & set(a.untag):
        sys.exit("a tag can't be both added and removed")
    old_tags = t.get("tags") or []
    tagged = [x for x in dict.fromkeys(a.tag) if x not in old_tags]
    untagged = [x for x in dict.fromkeys(a.untag) if x in old_tags]
    # The dispatcher holds untrusted tasks for the lead; injected text would ask any reader to lift that.
    # shortcut: identity is self-declared (--as / HUB_AGENT), so this stops a naive injection or a slip, not a
    # determined one; upgrade with signed identities, together with signed LGTMs in live_merge.py.
    for protected in ("untrusted", "stale"):
        if protected in untagged and me != LEAD_AGENT and not a.force:
            sys.exit(f"only {LEAD_AGENT} clears '{protected}' on {label(t)}; --force overrides (recorded)")
    old_detail = t.get("detail") or ""
    new_title, new_detail, extra = a.title or t["title"], old_detail, {}
    if a.take_github or a.keep_hub:
        if not t.get("issue"):
            sys.exit(f"{label(t)} has no issue yet")
        import gh_sync
        try:
            with open(gh_sync.config_path(t["project"])) as f:
                repo = json.load(f)["repo"]
            remote = gh_sync.Gh().json("issue", "view", t["issue"], "-R", repo,
                                       "--json", "body")["body"]
        except (OSError, gh_sync.GhError) as e:
            sys.exit(f"hub edit: {e}")
        if a.keep_hub:
            extra["issue_hash"] = gh_sync.digest(remote)
        else:
            new_detail = strip_issue_extras(remote)
    elif a.detail_file:
        with open(a.detail_file, encoding="utf-8") as f:
            new_detail = f.read()
    elif not (a.title or a.deadline or a.verify is not None or a.tag or a.untag or dropped) and sys.stdin.isatty():
        new_detail = edit_in_editor(old_detail)
    if a.deadline:
        new_detail = set_deadline(new_detail, a.deadline, t.get("project"))
    new_detail = new_detail.replace("\r\n", "\n").rstrip()
    if not new_detail.strip() and old_detail.strip():  # wiping a brief; a task that never had one may keep none
        sys.exit("refusing an empty brief")
    diff = []
    if new_title != t["title"]:
        diff += [f"-title: {t['title']}", f"+title: {new_title}"]
    if a.verify is not None and a.verify != t.get("verify"):
        diff += [f"-verify: {t.get('verify', '(default)')}", f"+verify: {a.verify or '(none)'}"]
    diff += [f"+tag: {x}" for x in tagged] + [f"-tag: {x}" for x in untagged]
    diff += [f"-dep: {d}" for d in dropped]
    diff += list(difflib.unified_diff(old_detail.splitlines(), new_detail.splitlines(),
                                     "brief (hub)", "brief (new)", lineterm=""))
    if not diff and not extra:
        sys.exit("nothing changed")
    print("\n".join(diff) if diff else
          f"{label(t)}: the next hub gh-sync overwrites GitHub with the hub brief")
    if not a.yes:
        if not sys.stdin.isatty():
            sys.exit("not a terminal: pass --yes to save")
        if input("Save? [y/N] ").strip().lower() != "y":
            sys.exit("not saved")
    with board(write=True) as (data, events):
        cur = find(data, t["id"])
        if cur["status"] == "done":
            sys.exit(f"{label(cur)} is done; reopen it before editing its brief")
        if cur["title"] != t["title"] or (cur.get("detail") or "") != old_detail \
                or (cur.get("deps") or []) != (t.get("deps") or []):
            sys.exit(f"{label(cur)} changed while you were editing; run hub edit again")
        if cur.get("generated_from") and (new_title != cur["title"] or new_detail != old_detail.replace("\r\n", "\n").rstrip()):
            sys.exit(f"{label(cur)} was generated from the PRD; change its brief through hub spec apply")
        if cur.get("generated_from") and a.verify is not None and me != LEAD_AGENT and not a.force:
            sys.exit(f"{label(cur)} was generated from the PRD; change its verify through hub spec apply")
        fields = []
        if new_title != cur["title"]:
            cur["title"] = new_title
            fields.append("title")
        if new_detail != old_detail:
            cur["detail"] = new_detail
            fields.append("detail")
        if a.verify is not None and a.verify != cur.get("verify"):
            cur["verify"] = a.verify
            fields.append("verify")
        if tagged or untagged:
            cur["tags"] = [x for x in cur.get("tags") or [] if x not in untagged] + \
                          [x for x in tagged if x not in (cur.get("tags") or [])]
            fields.append("tags")
        if dropped:
            waited = bool(unmet_deps(data, cur))
            cur["deps"] = [d for d in cur["deps"] if d not in dropped]
            fields.append("deps")
        cur.update(extra)
        cur["updated"] = now()
        log(events, me, "edited", cur["id"], fields=fields, keep_hub=bool(a.keep_hub),
            **({"tagged": tagged, "untagged": untagged} if tagged or untagged else {}),
            **({"dropped_deps": dropped} if dropped else {}),
            **({"forced": True} if a.force and
               (any(tag in untagged for tag in ("untrusted", "stale")) or
                (cur.get("generated_from") and (a.verify is not None or dropped))) else {}))
        if dropped and waited and cur["status"] == "open" and not unmet_deps(data, cur):
            log(events, me, "unblocked", cur["id"], dropped_deps=dropped)  # kicks the dispatcher
    print(f"{label(t)} saved" + ("; the next hub gh-sync pushes it" if is_hackathon(t.get("project")) else ""))


def cmd_tag(a):
    """hub edit's tag path, so the untrusted rule and the ledger event stay in one place."""
    if not (a.tags or a.rm):
        sys.exit("name a tag to add, or --rm <tag>")
    check_tags(a.tags + a.rm)
    vars(a).update(tag=a.tags, untag=a.rm, title=None, deadline=None, detail_file=None,
                   take_github=False, keep_hub=False, verify=None, yes=True, force=False, drop_dep=[])
    cmd_edit(a)


def next_candidates(tasks, agent, project=None):
    """Open tasks agent may pick up, in hub next's order: its own, then unassigned, then its own in
    other projects. A vertical with children stands for its ready children. hub next takes the
    first; dispatch.py walks on past the ones it skips. The one copy of this order."""
    data, me = {"tasks": tasks}, agent.lower()
    # Strict: an unscoped task is not this project's work either. Without this an agent that
    # clears its own queue falls through to unrelated tasks, which is the whole reason project
    # scoping exists.
    # untrusted waits for Zeus's clear (hub edit --untag untrusted), like stale waits for hub spec.
    held = lambda t: bool({"stale", "untrusted"} & set(t.get("tags") or []))
    pool = [t for t in tasks if t["status"] == "open" and not held(t)
            and (not project or (t.get("project") or "") == project)]
    # Scope keeps an agent out of unrelated FREE work; it must not hide work someone assigned to
    # it by name. A project-scoped Prometheus was offered T-078 and never shown T-101..T-103,
    # which Zeus had assigned it under project hub/testbed.
    elsewhere = [t for t in tasks if t["status"] == "open" and project
                 and not held(t)
                 and (t.get("project") or "") != project and (actor(t) or "").lower() == me]
    out = []
    for group, scoped in (([t for t in pool if (actor(t) or "").lower() == me], True),
                          ([t for t in pool if not actor(t)], True), (elsewhere, False)):
        for t in group:
            if unmet_deps(data, t):
                continue
            children = [x for x in tasks if x.get("parent") == t["id"]] if t.get("kind") == "vertical" else []
            if not children:
                out.append(t)  # an ordinary task, or a vertical that still needs its breakdown
            for child in children:
                who = actor(child)
                if (child["status"] == "open" and not held(child)
                        and child.get("project") == t.get("project")
                        and (who or scoped) and (not who or who.lower() == me)
                        and not unmet_deps(data, child)):
                    out.append(child)
    seen = set()
    return [t for t in out if not (t["id"] in seen or seen.add(t["id"]))]


def cmd_next(a):
    me = whoami(a.as_agent)
    refuse_if_paused("hub next")
    project = which_project(getattr(a, "project", None))
    with board() as (data, _):
        pick = next(iter(next_candidates(data["tasks"], me, project)), None)
        elsewhere = [t for t in data["tasks"] if project and (t.get("project") or "") != project
                     and "stale" not in (t.get("tags") or [])
                     and t["status"] == "open" and (actor(t) or "").lower() == me.lower()
                     and not unmet_deps(data, t)]
        if not pick:
            scope = f" in project {project}" if project else ""
            print(f"nothing available to pick up{scope}")
            return
        print(f"{label(pick)}  {pick['title']}\n")
        print(pick["detail"] or "(no detail)")
        others = [t for t in elsewhere if t is not pick and t["id"] != pick.get("parent")]
        if others:
            print("\nalso assigned to you in other projects:")
            for t in others:
                print(f"  {label(t)}  [{t.get('project') or '-'}] {t['title']}")


def cmd_claim(a):
    # An owner must be addressable: a task owned by "Unknown" can never be released or
    # finished by a real agent without --force.
    me = addressable(whoami(a.as_agent), "claiming agent")
    refuse_if_paused("hub claim")
    import autonomy
    if autonomy.lacks(me, "claim"):
        sys.exit(f"{me}'s phase {autonomy.lacks(me, 'claim')} may not claim (factory.json autonomy; hub agents)")
    with board(write=True) as (data, events):
        t = resolve(data, a.id, which_project(getattr(a, "project", None)))
        if "stale" in (t.get("tags") or []):
            sys.exit(f"{label(t)} superseded: hub spec regenerates it")
        if "untrusted" in (t.get("tags") or []):
            sys.exit(f"{label(t)} is untrusted: it waits for Zeus to clear it (hub edit {t['id']} --untag untrusted)")
        missing = unmet_deps(data, t)
        if missing and not a.force:
            by_id = {x["id"]: x for x in data["tasks"]}
            sys.exit(f"{label(t)} waits on unmet deps: "
                     f"{','.join(label(by_id[d]) for d in missing)} (use --force to override)")
        if roster_rules(t):
            if t.get("owner") in (None, "Pool"):
                sys.exit(f"{label(t)} is pool work: hub assign {label(t).lstrip('#')} <person>, "
                         "then hub delegate ... <agent>")
            if me == t.get("owner"):
                t["agent"] = None
            elif not t.get("agent") and agents_of(t["project"]).get(me) == t.get("owner"):
                t["agent"] = me
            overridden = transition(t, "claim", me, a.force, who=actor(t))
            if actor(t) != me:
                t["agent"] = me
        else:
            overridden = transition(t, "claim", me, a.force)
            t["owner"] = me
            if t.get("kind") == "factory":
                t["agent"] = me  # hub live's builder(): the agent that built the PR
        t["claimed_at"] = now()
        log(events, me, "claimed", t["id"], forced=bool(missing) or overridden)
    print(f"{label(t)} claimed by {me}")
    if not t.get("project"):
        return
    # Outside the lock: create fetches, and the claim must stand whatever it does.
    try:
        import workspace
        path = workspace.create(t)
    except Exception as exc:
        print(f"workspace: not created ({exc}); claim stands")
        return
    if path:
        with board(write=True) as (data, _):
            find(data, t["id"])["workspace"] = str(path)


def cmd_release(a):
    me = whoami(a.as_agent)
    with board(write=True) as (data, events):
        t = resolve(data, a.id, which_project(getattr(a, "project", None)))
        hackathon = roster_rules(t)
        overridden = transition(t, "release", me, a.force, who=actor(t) if hackathon else None)
        if hackathon:
            t["agent"] = None
        else:
            t["owner"] = None
            if t.get("kind") == "factory":
                t["agent"] = None
        t.pop("claimed_at", None)
        log(events, me, "released", t["id"], forced=overridden)
    print(f"{label(t)} released back to open")
    try:
        import workspace
        workspace.gc([t], False)
    except Exception as exc:
        print(f"workspace: gc skipped ({exc})")



def cmd_assign(a):
    """The planner hands a task to another agent. Open tasks only, unless --force (then the claim is dropped)."""
    me = whoami(a.as_agent)
    owner = addressable(a.owner, "owner")
    with board(write=True) as (data, events):
        t = resolve(data, a.id, which_project(getattr(a, "project", None)))
        check_owner(t.get("project"), owner, label(t).lstrip("#"))
        if t.get("status") not in ("open", None) and not a.force:
            sys.exit(f"{label(t)} is {t['status']} by {t.get('owner')}; reassigning it drops that work. Use --force.")
        before = t.get("owner")
        t["owner"], t["status"], t["updated"] = owner, "open", now()
        if is_hackathon(t.get("project")):
            t["agent"] = None
        log(events, me, "assigned", t["id"], owner=owner, was=before, forced=bool(a.force))
    if owner != "Pool" and owner not in humans_of(t.get("project")):
        mid = new_message_id()
        deliver(owner, f"{label(t)} assigned to you: {t['title']}", mid)
        notify_hint([(owner, f"{label(t)} is yours: {t['title']}. Run: hub show {label(t)}", mid)])
    print(f"{label(t)} assigned to {owner} (was {before or 'nobody'})")


def cmd_delegate(a):
    me = whoami(a.as_agent)
    if bool(a.agent) == bool(a.clear):
        sys.exit("name an agent, or pass --clear")
    with board(write=True) as (data, events):
        t = resolve(data, a.id, which_project(a.project))
        agent = None if a.clear else addressable(a.agent, "agent")
        if agent and is_hackathon(t.get("project")):
            owner = t.get("owner")
            if agents_of(t["project"]).get(agent) != owner:
                sys.exit(f"{agent} is not one of {owner}'s agents in hackathon.json")
        was = t.get("agent")
        t["agent"], t["updated"] = agent, now()
        log(events, me, "delegated", t["id"], agent=agent, was=was)
    if agent:
        message = f"{label(t)} delegated to you by {t.get('owner') or me}: {t['title']}"
        mid = new_message_id()
        deliver(agent, message, mid)
        notify_hint([(agent, f"{message}. Run: hub show {label(t)}", mid)])
    print(f"{label(t)} " + (f"delegated to {agent}" if agent else "delegate cleared"))


def _harness_nudge():
    """Warn if this repo has harness files committed but not yet pushed.

    `hub done` is the one moment every agent passes through, which makes it the only
    place a reminder actually lands. Deliberately advisory and never fatal: a task board
    that fails because of an unrelated git state is a task board people stop using.
    """
    try:
        import subprocess
        sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
        import clean_repo

        def g(*args):
            r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else ""

        root = g("rev-parse", "--show-toplevel")
        if not root:
            return
        # The hub is where harness output is SUPPOSED to live. Flagging it here would
        # cry wolf 98 times and teach everyone to ignore the line.
        if os.path.realpath(root) == os.path.realpath(HUB_DIR):
            return
        base = clean_repo.find_base(root)
        if not base:
            return  # nothing to push to yet; "would ship" has no meaning
        names = g("diff", "--name-only", "--diff-filter=ACRT", f"{base}...HEAD")
        hits = [f for f in names.splitlines() if clean_repo.classify(f) == "harness"]
        if hits:
            print(f"  ! {len(hits)} harness file(s) would ship: " + ", ".join(hits[:3])
                  + ("..." if len(hits) > 3 else ""))
            print("    run `hub ship-check` before anyone pushes")
    except Exception:
        pass  # never let a nudge break the board


def done_guard(data, t, me, a):
    """Every refusal hub done makes; returns whether a rule was overridden with --force."""
    if t.get("kind") == "vertical":
        open_children = [label(x) for x in data["tasks"]
                         if x.get("parent") == t["id"] and x["status"] != "done"]
        if open_children:
            sys.exit(f"{label(t)} still has open tasks: {', '.join(open_children)}")
    # The hackathon skill's rule for Prometheus, true of every agent: gh-sync closes an issue's
    # task when the issue closes, and reopens it only if it closed it, so a smoke revert
    # would reopen the issue under a task already marked done.
    issue_rule = bool(t.get("issue") and t.get("agent") == me and roster_rules(t))
    if issue_rule and not a.force:
        sys.exit(f"cannot done {label(t)} as its agent: issue #{t['issue']} closes it. Push, then open the PR "
                 f"with `Closes #{t['issue']}` (or post DONE: on the issue): the merge closes the issue, the next "
                 f"gh-sync closes this task, and a smoke revert reopens both. To drop it "
                 f"instead: hub done {label(t)} --force --note \"dropped: <why>\"")
    # Only the board, inbox, git and memory survive a reset, so the note is the handoff. Every factory.json
    # agent, reset or not (living spec M1), so a phase change never drops the guard.
    import autonomy
    short_note = len((a.note or "").strip()) < 20 and autonomy.entry(me) is not None
    if short_note and not a.force:
        sys.exit(f"cannot done {label(t)} without a handoff note: the next session on it starts from the note.\n"
                 f"add --note \"<what changed, branch and commit, what is left>\" (20+ characters), "
                 f"or --force (recorded in the ledger)")
    return issue_rule or short_note


def pr_evidence_guard(t):
    """A factory task's open PR must carry its builder's own Evidence and `Not verified:` before hub done:
    hub live holds a PR without them, and on 2026-10-18 that cost a round-trip. hub live fills Closes,
    Req and Task itself. gh unreachable (a sandboxed builder): warn, never block."""
    import gh_sync
    from live_merge import EVIDENCE
    repo = t.get("issue") and gh_sync.factory_entry(t.get("project")).get("repo")
    if not repo:
        return
    try:
        prs = gh_sync.Gh().json("pr", "list", "-R", repo, "--state", "open", "--limit", "100",
                                "--json", "number,body,headRefName")
    except gh_sync.GhError as e:
        print(f"warning: could not check {label(t)}'s PR body for Evidence: {e}", file=sys.stderr)
        return
    pr = next((p for p in prs or [] if p.get("headRefName") == f"task/{t['id']}"
               or (p.get("headRefName") or "").startswith(f"{t['issue']}-")), None)
    body = (pr or {}).get("body") or ""
    missing = [line for line, ok in (
        ("an `## Evidence` block (or a `Verified:` line): each command you ran in a clean checkout and its counts",
         EVIDENCE.search(body)),
        ("a `Not verified:` line: what you did not check, or \"nothing\"", re.search(r"(?m)^Not verified:", body)))
        if not ok]
    if pr and missing:
        sys.exit(f"cannot done {label(t)}: PR #{pr['number']} on {repo} needs, in your own words,\n  - "
                 + "\n  - ".join(missing)
                 + f"\nadd them to the PR body (`gh pr edit {pr['number']} -R {repo} --body-file <file>`, keeping "
                 f"its other lines), then hub done again")


def studio_gate(t):
    """A task tagged ui, on a product in Studio's sites.yaml, needs `studio gate` to pass: an approved design
    proposal, or a lead waiver recorded in Studio. --force does not skip it; the waiver is the bypass.
    No Studio configured leaves the task ungated, with nothing printed; once it is, any failure to get a clear pass refuses."""
    if "ui" not in (t.get("tags") or []):
        return
    studio = os.path.expanduser(os.environ.get("HUB_STUDIO_DIR") or os.path.join(os.environ.get("HUB_CODE_DIR") or "~/code", "studio"))
    sites = os.environ.get("STUDIO_SITES") or os.path.join(studio, "sites.yaml")
    if not os.environ.get("STUDIO_SITES") and not os.path.exists(sites):
        return  # Studio is optional; without it a ui task is ungated, silently
    where = f"{label(t)} is a UI task on {t.get('project')}"
    try:
        with open(os.path.expanduser(sites)) as f:
            text = f.read()
    except OSError as e:
        sys.exit(f"{where}, and Studio's sites file is unreadable: {e}")
    if t.get("project") not in re.findall(r"^\s*hub_project:\s*['\"]?([\w.-]+)", text, re.M):
        return
    exe = shutil.which("studio")
    cmd = ([exe] if exe else ["uv", "run", "--quiet", "--project", studio, "python", "-m", "studio.cli"]) + \
          ["gate", t["id"], "--project", t["project"]]
    try:
        r = subprocess.run(cmd, cwd=None if exe else studio, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        sys.exit(f"{where}, and studio gate could not run: {e}")
    out = (r.stdout + r.stderr).strip()[-1500:]
    try:
        decision = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        decision = None
    if r.returncode or not isinstance(decision, dict) or decision.get("allowed") is not True:
        why = (f"exit {r.returncode}" if r.returncode else
               "its output is not a gate decision" if not isinstance(decision, dict) else "allowed is not true")
        sys.exit(f"{where}; studio gate refused it ({why}):\n{out}\n"
                 f"get its design proposal approved in Penpot, or a lead waiver recorded in Studio")


def cmd_done(a):
    me = whoami(a.as_agent)
    import autonomy
    for flag, used in (("--force", a.force), ("--no-verify", a.no_verify)):
        if used and autonomy.lacks(me, "done_force"):
            sys.exit(f"{flag} needs done_force; {me}'s phase {autonomy.lacks(me, 'done_force')} has none. "
                     f"Fix what it would skip, or ask Zeus")
    project = which_project(getattr(a, "project", None))
    # Every refusal first, on a copy and outside the write lock: verify can run for minutes,
    # and holding the board that long would time out every other agent.
    with board() as (data, _):
        t = resolve(data, a.id, project)
        done_guard(data, t, me, a)
        transition(dict(t), "done", me, a.force,
                   who=actor(t) if is_hackathon(t.get("project")) else None)
        repo = verify_checkout(task_repo(t), t.get("workspace"))
        cmd = verify_command(t, repo)
    if not a.force:
        pr_evidence_guard(t)
    studio_gate(t)
    verdict, tail = None, ""
    if cmd and a.no_verify:
        verdict = "skipped"
    elif cmd:
        if not repo:
            sys.exit(f"{label(t)} has verify `{cmd}` but no checkout for project "
                     f"{t.get('project') or '(none)'} (looked in $HUB_CODE_DIR/<project> and ~/<project>).\n"
                     f"fix the project, or pass --no-verify (recorded in the ledger)")
        print(f"verify: {cmd}  (in {repo})", flush=True)
        path = sh_log(me, f"verify-{label(t)}")
        rc, n, tail = run_verify(cmd, repo, log=path)
        if rc:
            verify_failed(t["id"], me, cmd, f"{tail}\n(exit {rc}, log {path})")
        verdict, tail = "passed", f"verify passed: {cmd} ({n} lines, log {path})"
        print(tail)
    with board(write=True) as (data, events):
        t = resolve(data, a.id, project)
        issue_rule = done_guard(data, t, me, a)
        blocked_before = {x["id"] for x in data["tasks"] if unmet_deps(data, x)}
        overridden = transition(t, "done", me, a.force,
                                who=actor(t) if is_hackathon(t.get("project")) else None) or issue_rule
        if overridden:
            log(events, me, "override", t["id"], verb="done")
        note = "\n".join(filter(None, [a.note, verdict == "passed" and tail,
                                       verdict == "skipped" and f"verify skipped: {cmd} (--no-verify)"]))
        if note:
            t["notes"].append({"at": now(), "by": me, "text": note})
        t.pop("retired", None)  # a retired task reopened and then built counts as built
        log(events, me, "done", t["id"], note=a.note or "",
            **({"verify": verdict, "cmd": cmd} if verdict else {}))
        pings = unblock(data, events, me, t, blocked_before)
    print(f"{label(t)} marked done by {me}")
    _harness_nudge()
    print_pings(pings)


def unblock(data, events, me, t, blocked_before):
    """Log and deliver every task t's closing made claimable; returns [(recipient or None, text, message id)]."""
    pings, unblocked_by_recipient = [], {}
    for x in data["tasks"]:
        if x["id"] in blocked_before and x["status"] == "open" and not unmet_deps(data, x):
            log(events, me, "unblocked", x["id"], by_task=t["id"])
            recipient = actor(x) if is_hackathon(x.get("project")) else x.get("owner")
            if recipient in humans_of(x.get("project")):
                continue  # humans read their GitHub issue; no hub inbox or pool notice
            if recipient and recipient != "Pool":
                unblocked_by_recipient.setdefault(recipient, []).append(x)
            else:
                pings.append((None, f"{label(x)} is now claimable: {x['title']}", None))
    for recipient, tasks in unblocked_by_recipient.items():
        if len(tasks) == 1:
            x = tasks[0]
            text = f"{label(x)} is ready — unblocked by {label(t)}: {x['title']}"
        else:
            text = f"Unblocked by {label(t)}: " + "; ".join(
                f"{label(x)} {x['title']}" for x in tasks)
        mid = new_message_id()
        deliver(recipient, text, mid)
        pings.append((recipient, text, mid))
    return pings


def print_pings(pings):
    for _, text, _ in (p for p in pings if p[0] is None):
        print(f"  → {text}")
    notify_hint([p for p in pings if p[0]])


def cmd_retire(a):
    """Close a task that will never be built (a phantom or superseded task). It meets its dependents' deps as
    done does, but hub spec apply never counts it as building its reqs. A lead action: it needs done_force."""
    me = whoami(a.as_agent)
    import autonomy
    if autonomy.lacks(me, "done_force"):
        sys.exit(f"hub retire needs done_force; {me}'s phase {autonomy.lacks(me, 'done_force')} has none. Ask Zeus")
    if not (a.note or "").strip():
        sys.exit("hub retire needs --note \"<why it will never be built>\"")
    with board(write=True) as (data, events):
        t = resolve(data, a.id, which_project(a.project))
        if t["status"] == "done":
            sys.exit(f"{label(t)} is already {'retired' if t.get('retired') else 'done'}")
        if t.get("kind") == "vertical":
            open_children = [label(x) for x in data["tasks"]
                             if x.get("parent") == t["id"] and x["status"] != "done"]
            if open_children:
                sys.exit(f"{label(t)} still has open tasks: {', '.join(open_children)}")
        blocked_before = {x["id"] for x in data["tasks"] if unmet_deps(data, x)}
        was = t["status"]
        t.update(status="done", retired=True, updated=now())
        t.setdefault("notes", []).append({"at": now(), "by": me, "text": f"retired: {a.note}"})
        log(events, me, "retired", t["id"], note=a.note, was=was)
        pings = unblock(data, events, me, t, blocked_before)
    print(f"{label(t)} retired by {me}: closed, not built")
    print_pings(pings)


def cmd_block(a):
    me = whoami(a.as_agent)
    with board(write=True) as (data, events):
        t = resolve(data, a.id, which_project(getattr(a, "project", None)))
        overridden = transition(t, "block", me, a.force,
                                who=actor(t) if is_hackathon(t.get("project")) else None)
        t["notes"].append({"at": now(), "by": me, "text": a.note})
        log(events, me, "blocked", t["id"], reason=a.note, forced=overridden)
    print(f"{label(t)} marked blocked by {me}")


def cmd_note(a):
    me = whoami(a.as_agent)
    with board(write=True) as (data, events):
        t = resolve(data, a.id, which_project(getattr(a, "project", None)))
        t["notes"].append({"at": now(), "by": me, "text": a.text})
        t["updated"] = now()
        log(events, me, "note", t["id"], text=a.text)
    print(f"note added to {label(t)}")


def cmd_notify(a):
    me = whoami(a.as_agent)
    target = addressable(a.agent, "recipient")
    if a.message_id and not MESSAGE_ID_RE.match(a.message_id):
        sys.exit(f"invalid message id: {a.message_id!r}")
    mid = a.message_id or new_message_id()
    deliver(target, f"{a.text}  (from {me})", mid, a.key)
    with board(write=True) as (_, events):
        log(events, me, "notify", a.task or "-", to=target, text=a.text)
    print(f"queued for {target}: {a.text}")
    notify_hint([(target, a.text, mid)])


def _brief_messages(msgs):
    """Hide superseded/healthy watchdog status without consuming durable work instructions."""
    # Unknown states or extra prose stay visible; only known, bare transitions are noise.
    states = (r"(?:healthy|idle|busy|working|running|stopped|stuck|rate\s+limited|logged\s+out|"
              r"at\s+a\s+prompt|asking\s+a\s+question|permission\s+prompt|no\s+session)")
    status = re.compile(rf"\[watchdog\] ([\w-]+): {states} -> ({states})(?:\s+\(from [\w-]+\))?")
    parsed = [status.fullmatch(m.get("text", "")) for m in msgs]
    latest = {m[1]: i for i, m in enumerate(parsed) if m}
    healthy = {"idle", "busy", "working", "running", "healthy"}
    return [m for i, m in enumerate(msgs)
            if not parsed[i] or (latest[parsed[i][1]] == i and " ".join(parsed[i][2].split()) not in healthy)]


def cmd_brief(a):
    """A standing orientation for an agent starting work: who you are, what is waiting,
    and what everyone else is holding. Read by _hub_enter at launch and injected into the
    agent's system prompt, so a session begins already knowing the state of the board
    rather than spending its first turn discovering it."""
    import autonomy
    me = whoami(a.as_agent)
    project = which_project(getattr(a, "project", None))
    scope = f" · project {project}" if project else " · all projects"
    reason = paused()
    out = ([f"HUB PAUSED: {reason}. hub next and hub claim refuse until `hub resume`.\n"]
           if reason else [])
    out += [f"HUB BRIEFING — you are {me}{scope}.",
            "Snapshot taken when this session started; re-run `hub brief` for current state."]
    cfg = autonomy.factory()
    phase, policy = autonomy.phase_of(me, cfg)
    if policy is not None:
        out.append(f"POLICY — phase {phase}; build dispatch {'on' if policy['dispatch'] else 'off'}; "
                   f"reset {'per-task' if policy['reset'] == 'per-task' else 'off'}. "
                   f"Reviewer: {autonomy.reviewer(cfg)}. Source: factory.json (`hub agents`).")

    path = os.path.join(INBOX_DIR, f"{me}.jsonl")
    msgs = read_msgs(path) if os.path.exists(path) else []
    notices = _brief_messages(msgs)
    if notices:
        out.append(f"\nINBOX — {len(notices)} notice(s). Latest 5 below; `hub inbox` shows the latest 20, `hub inbox --all` the full backlog.")
        for m in notices[-5:]:
            mid = f" [{m['id']}]" if m.get("id") else ""
            out.append(f"  · [{m['at']}]{mid} {m['text']}"[:160])
    elif msgs:
        out.append("\nINBOX — routine status only; full backlog: `hub inbox --all`.")
    else:
        out.append("\nINBOX — empty.")

    with board() as (data, _):
        tasks = data["tasks"]
        if project:
            tasks = [t for t in tasks if (t.get("project") or "") == project]

        mine = [t for t in tasks if t["status"] == "claimed"
                and (t.get("owner") or "").lower() == me.lower()]
        if mine:
            out.append("\nYOURS, IN PROGRESS —")
            out += [f"  {label(t)}  {t['title']}" for t in mine]

        avail = [t for t in tasks if t["status"] == "open"
                 and not unmet_deps(data, t)
                 and (t.get("owner") or "").lower() in ("", me.lower())]
        if avail:
            out.append(f"\nAVAILABLE TO YOU — {len(avail)}. Take one with `hub claim <id>`.")
            out += [f"  {label(t)}  {t['title']}" for t in avail[:8]]

        # Whole board, not just this project: knowing a peer is mid-task elsewhere is
        # what stops two agents starting the same work or colliding on one file.
        others = [t for t in data["tasks"] if t["status"] == "claimed"
                  and (t.get("owner") or "").lower() != me.lower()]
        # Out of scope only as a count: the list cost every briefing ~200 tokens (token review 2026-10-20).
        here = [t for t in others if not project or (t.get("project") or "") == project]
        elsewhere = len(others) - len(here)
        if others:
            out.append("\nPEERS ARE HOLDING —")
            for t in here:
                tag = f" [{t['project']}]" if t.get("project") else ""
                out.append(f"  {label(t)}  {t['title']}{tag}  @{t['owner']}")
            if elsewhere:
                out.append(f"  + {elsewhere} claimed in other projects")

        all_blocked = [t for t in tasks if t["status"] == "blocked"]
        blocked = [t for t in all_blocked if phase == "lead" or me.lower() in {
            (t.get("owner") or "").lower(), (actor(t) or "").lower()}]
        if blocked:
            out.append("\nBLOCKED —")
            out += [f"  {label(t)}  {t['title']}  @{t.get('owner') or '-'}" for t in blocked]
        if len(all_blocked) > len(blocked):
            out.append(f"\n{len(all_blocked) - len(blocked)} blocked for other owners; `hub list` for details.")

    print("\n".join(out))


# Routine hub live chatter: `--unseen` feeds a hook that interrupts an attached agent, and
# these would bury the one alert that matters ("Smoke failed ...").
INBOX_NOISE = re.compile(r"not accepted the invite yet|deployed [0-9a-f]{12}:|deploy started"
                         r"|^\[watchdog\] \w+: [a-z ]+ -> [a-z ]+")  # health changes: Stop still delivers them


def take_receipt(receipt_dir, mid):
    """The receive receipt, O_EXCL: True only for the one caller that created it."""
    os.makedirs(receipt_dir, exist_ok=True)
    try:
        os.close(os.open(os.path.join(receipt_dir, mid), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        return False
    return True


def inbox_unseen(me, path):
    """New messages since the last --unseen, for the inbox-surface hook. Never consumes:
    the cursor is the set of keys already shown, pruned to what is still in the inbox, so a
    --clear (which restarts the file) cannot hide what arrives after it.

    A message with an id shares receipts with `hub receive`: one already received is not shown,
    and one shown in full is received, so the Stop hook and the relay do not deliver it again
    (live rollout 2026-10-18). Only a line without an id is cut at 200 characters."""
    cursor = os.path.join(INBOX_DIR, f".{me}.unseen.json")
    receipt_dir = os.path.join(INBOX_DIR, ".received", me)

    def has_id(m):
        return bool(m.get("id")) and bool(MESSAGE_ID_RE.match(m["id"]))

    with inbox_lock(me):
        msgs = read_msgs(path)
        try:
            with open(cursor) as f:
                seen = set(json.load(f))
        except (OSError, ValueError):
            seen = set()
        keys = [m.get("id") or f"{m.get('at')}|{m.get('text')}" for m in msgs]
        new = [m for m, k in zip(msgs, keys) if k not in seen and not INBOX_NOISE.search(m.get("text", ""))
               and not (has_id(m) and os.path.exists(os.path.join(receipt_dir, m["id"])))]
        lines = []
        for m in new[-8:]:
            mid = f" [{m['id']}]" if m.get("id") else ""
            line = f"  · [{m['at']}]{mid} {m['text']}"
            if has_id(m):  # shown whole: Zeus has no Stop hook to deliver a cut message later
                take_receipt(receipt_dir, m["id"])
                lines.append(line)
            else:
                lines.append(line[:200])
        # Overflow past 8 stays out of the cursor, so the next call shows it rather than losing it.
        shown = set(keys) - {m.get("id") or f"{m.get('at')}|{m.get('text')}" for m in new[:-8]}
        if shown != seen:
            _write_json_atomic(cursor, sorted(shown))
    for line in lines:
        print(line)
    if len(new) > 8:
        print(f"  (+{len(new) - 8} more, shown next time)")


def cmd_inbox(a):
    me = valid_agent(a.agent, "agent") if a.agent else whoami(a.as_agent)
    path = os.path.join(INBOX_DIR, f"{me}.jsonl")
    if getattr(a, "unseen", False):  # callers that build the Namespace by hand predate it
        inbox_unseen(me, path)
        return
    if a.clear:
        # Atomic consume. Reading then unlinking loses any message that lands in between:
        # it is acknowledged to the sender and then destroyed. Renaming under the lock
        # means a concurrent delivery opens a fresh file and survives.
        with inbox_lock(me):
            if not os.path.exists(path):
                print(f"no messages for {me}")
                return
            taken = f"{path}.consumed.{os.getpid()}"
            os.rename(path, taken)
        msgs = read_msgs(taken)
        for m in msgs:
            mid = f" [{m['id']}]" if m.get("id") else ""
            print(f"  · [{m['at']}]{mid} {m['text']}")
            if m.get("id"):
                try:
                    os.remove(os.path.join(INBOX_DIR, ".received", me, m["id"]))
                except FileNotFoundError:
                    pass
        os.remove(taken)
        print(f"\ncleared {len(msgs)} message(s)")
        return

    if not os.path.exists(path):
        print(f"no messages for {me}")
        return
    # The whole inbox ran to 22k-33k tokens on a relaunch (token review 2026-10-20): latest 20 unless --all.
    msgs = read_msgs(path)
    shown = msgs if a.all else msgs[-20:]
    if len(shown) < len(msgs):
        print(f"{len(msgs)} message(s); the latest {len(shown)} (hub inbox --all for every one):")
    for m in shown:
        mid = f" [{m['id']}]" if m.get("id") else ""
        print(f"  · [{m['at']}]{mid} {m['text']}")


def receive_pending(me, path, receipt_dir):
    """Agent OS §5.1: reveal every recent message without a receipt, writing the receipts, so the
    Stop hook and the relay's one coalesced wake both pull the whole backlog at once. Messages older
    than the wake horizon (hubwaked drops such wakes too) stay in the inbox for `hub inbox`."""
    horizon = time.time() - int(os.environ.get("HUB_WAKE_MAX_AGE") or 21600)
    with inbox_lock(me):
        fresh = []
        for m in read_msgs(path):
            if not m.get("id") or not MESSAGE_ID_RE.match(m["id"]):
                continue
            try:
                if datetime.fromisoformat(m["at"]).timestamp() < horizon:
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            if take_receipt(receipt_dir, m["id"]):
                fresh.append(m)
    for m in fresh:
        print(f"  · [{m['at']}] [{m['id']}] {m['text']}")
    if not fresh:
        print("nothing pending")


def cmd_receive(a):
    """Atomically reveal a durable message once; duplicate wake prompts are harmless."""
    me = addressable(whoami(a.as_agent), "receiving agent")
    path = os.path.join(INBOX_DIR, f"{me}.jsonl")
    receipt_dir = os.path.join(INBOX_DIR, ".received", me)
    if a.pending:
        return receive_pending(me, path, receipt_dir)
    if not a.id:
        sys.exit("usage: hub receive <id> | hub receive --pending")
    if not MESSAGE_ID_RE.match(a.id):
        sys.exit(f"invalid message id: {a.id!r}")
    receipt = os.path.join(receipt_dir, a.id)
    with inbox_lock(me):
        matches = [m for m in read_msgs(path) if m.get("id") == a.id]
        if not matches:
            sys.exit(f"no message {a.id} for {me}; run: hub inbox")
        os.makedirs(receipt_dir, exist_ok=True)
        try:
            fd = os.open(receipt, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            print(f"message {a.id} already received")
            return
        os.close(fd)
    print(matches[0]["text"])


def ledger():
    """The ledger's actions: commit markers and aborted transactions dropped."""
    lines = read_events(repair=False)
    aborted = {e.get("txid") for e in lines if e.get("event") == "abort"}
    return [e for e in lines if e.get("event") not in ("commit", "abort") and e.get("txid") not in aborted]


def cmd_events(a):
    if not os.path.exists(EVENTS):
        print("no events recorded yet")
        return
    lines = ledger()
    if a.task:
        tid = norm_id(a.task)
        lines = [e for e in lines if e.get("task") == tid]
    for e in lines[-a.tail:]:
        extra = {k: v for k, v in e.items() if k not in ("at", "by", "event", "task") and v}
        tail = f"  {extra}" if extra else ""
        line = f"  [{e['at']}] {e['by']:<10} {e['event']:<10} {e['task']}{tail}".replace("\n", " ")
        print(line if getattr(a, "full", False) else line[:120])


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--as", dest="as_agent", default=argparse.SUPPRESS,
                        help="acting agent name (defaults to $HUB_AGENT, then $CLAUDE_CODE_SESSION_NAME)")

    p = argparse.ArgumentParser(prog="hub", description="shared agent task board", parents=[common])
    sub = p.add_subparsers(dest="cmd", required=True,
                           parser_class=lambda **kw: argparse.ArgumentParser(parents=[common], **kw))

    n = sub.add_parser("new", help="create a task")
    n.add_argument("title")
    n.add_argument("--detail", help="full plan: context, files, approach, acceptance criteria")
    n.add_argument("--dep", action="append", help="task id this depends on (repeatable)")
    n.add_argument("--owner", help="assign to an agent up front")
    n.add_argument("--project", help="project this task belongs to (defaults to $HUB_PROJECT)")
    n.add_argument("--vertical", action="store_true", help="create an owner-area vertical")
    n.add_argument("--verify", help="command hub done must pass in the task's repo "
                   "(default: make check if the repo has that target; \"\" for none)")
    n.add_argument("--req", action="append", help="acceptance line and version, e.g. A-3.2@1")
    n.add_argument("--tag", action="append", default=[], help="tag the task, e.g. read (repeatable)")
    n.add_argument("--budget", type=int, help="minutes this task may stay claimed before the watchdog tells Zeus "
                   "(default: the claimer's phase budget)")
    n.add_argument("--intake", metavar="SOURCE", help=f"external intake, one of {', '.join(INTAKE_SOURCES)}: allowed in spec-locked projects; "
                   "the detail is wrapped as untrusted data, tagged intake + untrusted, no verify until triage")
    n.add_argument("--from-spec", action="store_true", help=argparse.SUPPRESS)
    n.add_argument("--generated-from", help=argparse.SUPPRESS)
    n.set_defaults(fn=cmd_new)

    l = sub.add_parser("list", help="list tasks")
    l.add_argument("--status", choices=STATUSES)
    l.add_argument("--owner")
    l.add_argument("--all", action="store_true", help="include done tasks")
    l.add_argument("--json", action="store_true")
    l.add_argument("--project", help="only this project (defaults to $HUB_PROJECT)")
    l.set_defaults(fn=cmd_list)

    s = sub.add_parser("show", help="show one task in full")
    s.add_argument("id")
    s.add_argument("--project", help="project for issue numbers (defaults to $HUB_PROJECT)")
    s.add_argument("--full", action="store_true", help=f"every note, uncut (default: last {SHOW_NOTES}, "
                   f"each cut to {NOTE_CUT} characters)")
    s.set_defaults(fn=cmd_show)

    ed = sub.add_parser("edit", help="change a task's title, brief, deadline or tags")
    ed.add_argument("id", help="T-id, or in a hackathon the issue number")
    ed.add_argument("--project", help="project for issue numbers (defaults to $HUB_PROJECT)")
    ed.add_argument("--title")
    ed.add_argument("--deadline", help="a deadline name from hackathon.json")
    ed.add_argument("--detail-file", help="new brief from this file (for agents)")
    ed.add_argument("--take-github", action="store_true", help="adopt the issue's GitHub body")
    ed.add_argument("--keep-hub", action="store_true", help="next sync overwrites GitHub")
    ed.add_argument("--verify", help="set the task's verify command (\"\" for none)")
    ed.add_argument("--tag", action="append", default=[], help="add a tag, e.g. standing (repeatable)")
    ed.add_argument("--untag", action="append", default=[], help="remove a tag (repeatable)")
    ed.add_argument("--drop-dep", action="append", default=[], metavar="ID",
                    help="remove a dependency (repeatable); to close a task never built, see hub retire")
    ed.add_argument("--yes", action="store_true", help="save without asking")
    ed.add_argument("--force", action="store_true", help="override stale/untrusted tags or generated verify (recorded)")
    ed.set_defaults(fn=cmd_edit)

    tg = sub.add_parser("tag", help="add tags to a task, or remove one with --rm")
    tg.add_argument("id", help="T-id, or in a hackathon the issue number")
    tg.add_argument("tags", nargs="*", help="tags to add, e.g. read")
    tg.add_argument("--rm", action="append", default=[], help="remove a tag (repeatable)")
    tg.add_argument("--project", help="project for issue numbers (defaults to $HUB_PROJECT)")
    tg.set_defaults(fn=cmd_tag)

    nx = sub.add_parser("next", help="show the next task available to you")
    nx.add_argument("--project", help="only this project (defaults to $HUB_PROJECT)")
    nx.set_defaults(fn=cmd_next)

    c = sub.add_parser("claim", help="claim a task")
    c.add_argument("id")
    c.add_argument("--force", action="store_true")
    c.add_argument("--project", help="project for issue numbers (defaults to $HUB_PROJECT)")
    c.set_defaults(fn=cmd_claim)

    r = sub.add_parser("release", help="release a claimed task")
    r.add_argument("id")
    r.add_argument("--force", action="store_true",
                       help="override state/ownership rules (recorded in the ledger)")
    r.add_argument("--project", help="project for issue numbers (defaults to $HUB_PROJECT)")
    r.set_defaults(fn=cmd_release)

    g = sub.add_parser("assign", help="hand a task to another owner (planner)")
    g.add_argument("id")
    g.add_argument("owner")
    g.add_argument("--force", action="store_true", help="also reassign a claimed or blocked task (recorded)")
    g.add_argument("--project", help="project for issue numbers (defaults to $HUB_PROJECT)")
    g.set_defaults(fn=cmd_assign)

    dg = sub.add_parser("delegate", help="hand a task to one of its owner's agents")
    dg.add_argument("id", help="T-id, or in a hackathon the issue number")
    dg.add_argument("agent", nargs="?")
    dg.add_argument("--clear", action="store_true", help="remove the delegate")
    dg.add_argument("--project", help="project for issue numbers (defaults to $HUB_PROJECT)")
    dg.set_defaults(fn=cmd_delegate)

    d = sub.add_parser("done", help="mark a task done")
    d.add_argument("id")
    d.add_argument("--note")
    d.add_argument("--force", action="store_true",
                       help="override state/ownership rules (recorded in the ledger)")
    d.add_argument("--project", help="project for issue numbers (defaults to $HUB_PROJECT)")
    d.add_argument("--no-verify", action="store_true",
                   help="skip the task's verify command (recorded in the ledger)")
    d.set_defaults(fn=cmd_done)

    rt = sub.add_parser("retire", help="close a task that will never be built: it meets dependents' deps, "
                                       "but spec apply never counts it as building its reqs")
    rt.add_argument("id")
    rt.add_argument("--note", required=True, help="why it will never be built")
    rt.add_argument("--project", help="project for issue numbers (defaults to $HUB_PROJECT)")
    rt.set_defaults(fn=cmd_retire)

    pz = sub.add_parser("pause", help="kill switch: hub next and hub claim refuse until resume")
    pz.add_argument("reason", nargs="*")
    pz.set_defaults(fn=cmd_pause)

    rs = sub.add_parser("resume", help="lift the kill switch")
    rs.set_defaults(fn=cmd_resume)

    b = sub.add_parser("block", help="mark a task blocked")
    b.add_argument("id")
    b.add_argument("note")
    b.add_argument("--force", action="store_true",
                       help="override state/ownership rules (recorded in the ledger)")
    b.add_argument("--project", help="project for issue numbers (defaults to $HUB_PROJECT)")
    b.set_defaults(fn=cmd_block)

    nt = sub.add_parser("note", help="add a note to a task")
    nt.add_argument("id")
    nt.add_argument("text")
    nt.add_argument("--project", help="project for issue numbers (defaults to $HUB_PROJECT)")
    nt.set_defaults(fn=cmd_note)

    nf = sub.add_parser("notify", help="queue a durable message for an agent")
    nf.add_argument("agent")
    nf.add_argument("text")
    nf.add_argument("--task", help="task id this concerns")
    nf.add_argument("--message-id", help=argparse.SUPPRESS)
    nf.add_argument("--key", help="replace the recipient's earlier message with this key (a status line)")
    nf.set_defaults(fn=cmd_notify)

    br = sub.add_parser("brief", help="orientation: your inbox, your work, what peers hold")
    br.add_argument("--project", help="scope to one project (defaults to $HUB_PROJECT)")
    br.set_defaults(fn=cmd_brief)

    ib = sub.add_parser("inbox", help="read queued messages")
    ib.add_argument("agent", nargs="?", help="whose inbox (defaults to you)")
    ib.add_argument("--clear", action="store_true")
    ib.add_argument("--all", action="store_true", help="every stored message, not just the latest 20")
    ib.add_argument("--unseen", action="store_true",
                    help="only messages not shown by --unseen before; leaves the inbox intact")
    ib.set_defaults(fn=cmd_inbox)

    recv = sub.add_parser("receive", help="receive one durable message idempotently")
    recv.add_argument("id", nargs="?")
    recv.add_argument("--pending", action="store_true",
                      help="every recent message not yet received, once (the coalesced wake and the Stop hook)")
    recv.set_defaults(fn=cmd_receive)

    import gh_sync
    gh_sync.register(sub)
    import live
    live.register(sub)
    import host
    host.register(sub)
    # Repo hygiene lives in its own module -- this file is a task board, and the two
    # concerns should not grow into each other. See ~/hub/CLEAN-REPO.md.
    import clean_repo
    clean_repo.register(sub, common)
    import review
    review.register(sub)
    import dashboard
    dashboard.register(sub)
    import spec
    spec.register(sub)
    import prd; prd.register(sub)
    import hub_trace
    hub_trace.register(sub)
    import workspace
    workspace.register(sub)
    import autonomy
    autonomy.register(sub)
    import map as _map; _map.register(sub)
    import harness_sync; harness_sync.register(sub)

    sh = sub.add_parser("sh", help="run a long or noisy command: full output to a log, "
                        "a header and the tail to you, its exit code kept")
    sh.add_argument("--tail", type=int, default=20, help="lines of output to print (default 20)")
    sh.add_argument("--name", help="log name (default: the command's name)")
    sh.add_argument("argv", nargs=argparse.REMAINDER, metavar="-- cmd")
    sh.set_defaults(fn=cmd_sh)

    ev = sub.add_parser("events", help="read the append-only ledger")
    ev.add_argument("--tail", type=int, default=30)
    ev.add_argument("--task", help="filter to one task")
    ev.add_argument("--full", action="store_true", help="whole events, not one line cut to 120 characters")
    ev.set_defaults(fn=cmd_events)

    a = p.parse_args()
    a.as_agent = getattr(a, "as_agent", None)
    a.fn(a)


if __name__ == "__main__":
    main()
