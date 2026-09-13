#!/usr/bin/env python3
"""Shared task board for the agent hub. Safe for concurrent access by multiple agents.

State lives in board.json (current snapshot) and events.jsonl (append-only ledger).
The ledger is the audit trail: every transition is recorded there even if a later write
to the snapshot is lost, so it's the place to look when debugging a race.
"""

import argparse
import fcntl
import json
import os
import re
import shlex
import sys
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

# Bumped when board.json's shape changes; migrate() upgrades older boards in place.
# A board written before versioning existed has no field at all, which is version 1.
SCHEMA_VERSION = 1

IDENTITY_VARS = ("HUB_AGENT", "CLAUDE_CODE_SESSION_NAME")

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
    return changed


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canon(name):
    """One agent, one spelling, one inbox file. zeus / ZEUS / Zeus are the same agent."""
    name = (name or "").strip()
    return name[:1].upper() + name[1:].lower()


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
    """Canonical project tag, or exit. Lowercased so refinery / Refinery are one project."""
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
    with open(LOCK, "a") as lk:
        _acquire(lk)
        try:
            _recover_wal()
            with open(BOARD) as f:
                data = json.load(f)
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
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


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


def transition(t, verb, me, force=False):
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
                f"cannot {verb} {t['id']}: it is {status}.\n"
                f"{verb} is legal from: {', '.join(allowed)}\n"
                f"use --force to override, or check: hub show {t['id']}"
            )

    owner = t.get("owner")
    # Ownership blocks a claim whatever the status: `hub new --owner Hermes` assigns work
    # up front, and letting anyone claim it anyway would make that assignment advisory.
    # An unowned task (never assigned, or released) is free for anyone to take.
    if verb == "claim" and owner and owner != me:
        if force:
            overridden = True
        else:
            held = "already claimed by" if status == "claimed" else "assigned to"
            sys.exit(
                f"{t['id']} is {held} {owner}, not {me}.\n"
                f"take it over with: hub claim {t['id']} --force"
            )

    if verb in OWNED_VERBS and owner and owner != me:
        if force:
            overridden = True
        else:
            sys.exit(
                f"cannot {verb} {t['id']}: it belongs to {owner}, not {me}.\n"
                f"ask them, or take it over with: hub claim {t['id']} --force"
            )

    t["status"] = TO_STATE[verb]
    t["updated"] = now()
    return overridden


def validate_deps(data, deps, own_id):
    """Deps are normalised and proven sane at creation -- the only point they enter."""
    seen, out = set(), []
    for d in deps:
        d = norm_id(d)
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


def deliver(agent, text, message_id=None):
    """Durable notification. This does NOT ping a live session — see notify_hint()."""
    agent = addressable(agent, "recipient")
    path = os.path.join(INBOX_DIR, f"{agent}.jsonl")
    with inbox_lock(agent):
        # Every append happens under this lock, so an unterminated last line here can only
        # be a crashed writer's leftover. Drop it first: appending onto it would fuse the
        # new record into the torn one, and a message acknowledged as queued would be lost.
        _repair_jsonl_tail(path)
        if message_id and any(m.get("id") == message_id for m in read_msgs(path)):
            return
        with open(path, "a") as f:
            f.write(json.dumps({"at": now(), "text": text, **({"id": message_id} if message_id else {})}) + "\n")


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
    owner = f" @{t['owner']}" if t.get("owner") else ""
    blocked = ""
    if data and t["status"] in ("open", "claimed"):
        missing = unmet_deps(data, t)
        if missing:
            blocked = f"  ⇠ waits on {','.join(missing)}"
    tag = f" [{t['project']}]" if t.get("project") else ""
    return f"  {mark} {t['id']}  {t['title']}{tag}{owner}{blocked}"


def cmd_new(a):
    me = whoami(a.as_agent)
    if a.owner:
        a.owner = addressable(a.owner, "owner")
    project = which_project(getattr(a, "project", None))
    with board(write=True) as (data, events):
        nid = f"T-{data['next_id']:03d}"
        data["next_id"] += 1
        deps = validate_deps(data, a.dep or [], nid)
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
        })
        log(events, me, "created", nid, title=a.title, deps=deps, owner=a.owner,
            project=project)
    print(f"created {nid}: {a.title}" + (f"  [{project}]" if project else ""))
    if not a.detail:
        print("  note: no --detail given. Tasks should carry enough plan for another agent to execute cold.")
    if a.owner:
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
                for t in group:
                    print(fmt_row(t, data))
        print()


def cmd_show(a):
    with board() as (data, _):
        t = find(data, a.id)
        print(f"\n{t['id']}  [{t['status']}]  {t['title']}")
        print(f"owner: {t.get('owner') or '-'}   project: {t.get('project') or '-'}"
              f"   created by {t['created_by']} at {t['created']}")
        if t.get("deps"):
            missing = unmet_deps(data, t)
            print(f"deps: {', '.join(t['deps'])}" + (f"   UNMET: {','.join(missing)}" if missing else "   (all met)"))
        print(f"\n{t['detail'] or '(no detail)'}\n")
        for n in t["notes"]:
            print(f"  · [{n['at']}] {n['by']}: {n['text']}")
        if t["notes"]:
            print()


def cmd_next(a):
    me = whoami(a.as_agent)
    project = which_project(getattr(a, "project", None))
    with board() as (data, _):
        pool = data["tasks"]
        if project:
            # Strict: an unscoped task is not this project's work either. Without this
            # an agent that clears its own queue falls through to unrelated tasks, which
            # is the whole reason project scoping exists.
            pool = [t for t in pool if (t.get("project") or "") == project]
        mine = [t for t in pool
                if t["status"] == "open" and (t.get("owner") or "").lower() == me.lower()]
        free = [t for t in pool
                if t["status"] == "open" and not t.get("owner") and not unmet_deps(data, t)]
        pick = next((t for t in mine if not unmet_deps(data, t)), None) or (free[0] if free else None)
        if not pick:
            scope = f" in project {project}" if project else ""
            print(f"nothing available to pick up{scope}")
            return
        print(f"{pick['id']}  {pick['title']}\n")
        print(pick["detail"] or "(no detail)")


def cmd_claim(a):
    # An owner must be addressable: a task owned by "Unknown" can never be released or
    # finished by a real agent without --force.
    me = addressable(whoami(a.as_agent), "claiming agent")
    with board(write=True) as (data, events):
        t = find(data, a.id)
        missing = unmet_deps(data, t)
        if missing and not a.force:
            sys.exit(f"{t['id']} waits on unmet deps: {','.join(missing)} (use --force to override)")
        overridden = transition(t, "claim", me, a.force)
        t["owner"] = me
        log(events, me, "claimed", t["id"], forced=bool(missing) or overridden)
    print(f"{t['id']} claimed by {me}")


def cmd_release(a):
    me = whoami(a.as_agent)
    with board(write=True) as (data, events):
        t = find(data, a.id)
        overridden = transition(t, "release", me, a.force)
        t["owner"] = None
        log(events, me, "released", t["id"], forced=overridden)
    print(f"{t['id']} released back to open")


def cmd_done(a):
    me = whoami(a.as_agent)
    pings = []
    with board(write=True) as (data, events):
        t = find(data, a.id)
        blocked_before = {x["id"] for x in data["tasks"] if unmet_deps(data, x)}
        overridden = transition(t, "done", me, a.force)
        if overridden:
            log(events, me, "override", t["id"], verb="done")
        if a.note:
            t["notes"].append({"at": now(), "by": me, "text": a.note})
        log(events, me, "done", t["id"], note=a.note or "")

        for x in data["tasks"]:
            if x["id"] in blocked_before and x["status"] == "open" and not unmet_deps(data, x):
                log(events, me, "unblocked", x["id"], by_task=t["id"])
                text = f"{x['id']} is ready — unblocked by {t['id']}: {x['title']}"
                if x.get("owner"):
                    mid = new_message_id()
                    deliver(x["owner"], text, mid)
                    pings.append((x["owner"], text, mid))
                else:
                    pings.append((None, f"{x['id']} is now claimable: {x['title']}", None))
    print(f"{t['id']} marked done by {me}")
    unowned = [p for p in pings if p[0] is None]
    for _, text, _ in unowned:
        print(f"  → {text}")
    notify_hint([p for p in pings if p[0]])


def cmd_block(a):
    me = whoami(a.as_agent)
    with board(write=True) as (data, events):
        t = find(data, a.id)
        overridden = transition(t, "block", me, a.force)
        t["notes"].append({"at": now(), "by": me, "text": a.note})
        log(events, me, "blocked", t["id"], reason=a.note, forced=overridden)
    print(f"{t['id']} marked blocked by {me}")


def cmd_note(a):
    me = whoami(a.as_agent)
    with board(write=True) as (data, events):
        t = find(data, a.id)
        t["notes"].append({"at": now(), "by": me, "text": a.text})
        t["updated"] = now()
        log(events, me, "note", t["id"], text=a.text)
    print(f"note added to {t['id']}")


def cmd_notify(a):
    me = whoami(a.as_agent)
    target = addressable(a.agent, "recipient")
    if a.message_id and not MESSAGE_ID_RE.match(a.message_id):
        sys.exit(f"invalid message id: {a.message_id!r}")
    mid = a.message_id or new_message_id()
    deliver(target, f"{a.text}  (from {me})", mid)
    with board(write=True) as (_, events):
        log(events, me, "notify", a.task or "-", to=target, text=a.text)
    print(f"queued for {target}: {a.text}")
    notify_hint([(target, a.text, mid)])


def cmd_brief(a):
    """A standing orientation for an agent starting work: who you are, what is waiting,
    and what everyone else is holding. Read by _hub_enter at launch and injected into the
    agent's system prompt, so a session begins already knowing the state of the board
    rather than spending its first turn discovering it."""
    me = whoami(a.as_agent)
    project = which_project(getattr(a, "project", None))
    scope = f" · project {project}" if project else " · all projects"
    out = [f"HUB BRIEFING — you are {me}{scope}.",
           "Snapshot taken when this session started; re-run `hub brief` for current state."]

    path = os.path.join(INBOX_DIR, f"{me}.jsonl")
    msgs = read_msgs(path) if os.path.exists(path) else []
    if msgs:
        out.append(f"\nINBOX — {len(msgs)} message(s) waiting. Read with `hub inbox`.")
        for m in msgs[-5:]:
            mid = f" [{m['id']}]" if m.get("id") else ""
            out.append(f"  · [{m['at']}]{mid} {m['text']}")
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
            out += [f"  {t['id']}  {t['title']}" for t in mine]

        avail = [t for t in tasks if t["status"] == "open"
                 and not unmet_deps(data, t)
                 and (t.get("owner") or "").lower() in ("", me.lower())]
        if avail:
            out.append(f"\nAVAILABLE TO YOU — {len(avail)}. Take one with `hub claim <id>`.")
            out += [f"  {t['id']}  {t['title']}" for t in avail[:8]]

        # Whole board, not just this project: knowing a peer is mid-task elsewhere is
        # what stops two agents starting the same work or colliding on one file.
        others = [t for t in data["tasks"] if t["status"] == "claimed"
                  and (t.get("owner") or "").lower() != me.lower()]
        if others:
            out.append("\nPEERS ARE HOLDING —")
            for t in others:
                tag = f" [{t['project']}]" if t.get("project") else ""
                out.append(f"  {t['id']}  {t['title']}{tag}  @{t['owner']}")

        blocked = [t for t in tasks if t["status"] == "blocked"]
        if blocked:
            out.append("\nBLOCKED —")
            out += [f"  {t['id']}  {t['title']}  @{t.get('owner') or '-'}" for t in blocked]

    print("\n".join(out))


def cmd_inbox(a):
    me = valid_agent(a.agent, "agent") if a.agent else whoami(a.as_agent)
    path = os.path.join(INBOX_DIR, f"{me}.jsonl")
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
    for m in read_msgs(path):
        mid = f" [{m['id']}]" if m.get("id") else ""
        print(f"  · [{m['at']}]{mid} {m['text']}")


def cmd_receive(a):
    """Atomically reveal a durable message once; duplicate wake prompts are harmless."""
    me = addressable(whoami(a.as_agent), "receiving agent")
    if not MESSAGE_ID_RE.match(a.id):
        sys.exit(f"invalid message id: {a.id!r}")
    path = os.path.join(INBOX_DIR, f"{me}.jsonl")
    receipt_dir = os.path.join(INBOX_DIR, ".received", me)
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


def cmd_events(a):
    if not os.path.exists(EVENTS):
        print("no events recorded yet")
        return
    lines = read_events(repair=False)
    aborted = {e.get("txid") for e in lines if e.get("event") == "abort"}
    lines = [e for e in lines if e.get("event") not in ("commit", "abort") and e.get("txid") not in aborted]
    if a.task:
        tid = norm_id(a.task)
        lines = [e for e in lines if e.get("task") == tid]
    for e in lines[-a.tail:]:
        extra = {k: v for k, v in e.items() if k not in ("at", "by", "event", "task") and v}
        tail = f"  {extra}" if extra else ""
        print(f"  [{e['at']}] {e['by']:<10} {e['event']:<10} {e['task']}{tail}")


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
    s.set_defaults(fn=cmd_show)

    nx = sub.add_parser("next", help="show the next task available to you")
    nx.add_argument("--project", help="only this project (defaults to $HUB_PROJECT)")
    nx.set_defaults(fn=cmd_next)

    c = sub.add_parser("claim", help="claim a task")
    c.add_argument("id")
    c.add_argument("--force", action="store_true")
    c.set_defaults(fn=cmd_claim)

    r = sub.add_parser("release", help="release a claimed task")
    r.add_argument("id")
    r.add_argument("--force", action="store_true",
                       help="override state/ownership rules (recorded in the ledger)")
    r.set_defaults(fn=cmd_release)

    d = sub.add_parser("done", help="mark a task done")
    d.add_argument("id")
    d.add_argument("--note")
    d.add_argument("--force", action="store_true",
                       help="override state/ownership rules (recorded in the ledger)")
    d.set_defaults(fn=cmd_done)

    b = sub.add_parser("block", help="mark a task blocked")
    b.add_argument("id")
    b.add_argument("note")
    b.add_argument("--force", action="store_true",
                       help="override state/ownership rules (recorded in the ledger)")
    b.set_defaults(fn=cmd_block)

    nt = sub.add_parser("note", help="add a note to a task")
    nt.add_argument("id")
    nt.add_argument("text")
    nt.set_defaults(fn=cmd_note)

    nf = sub.add_parser("notify", help="queue a durable message for an agent")
    nf.add_argument("agent")
    nf.add_argument("text")
    nf.add_argument("--task", help="task id this concerns")
    nf.add_argument("--message-id", help=argparse.SUPPRESS)
    nf.set_defaults(fn=cmd_notify)

    br = sub.add_parser("brief", help="orientation: your inbox, your work, what peers hold")
    br.add_argument("--project", help="scope to one project (defaults to $HUB_PROJECT)")
    br.set_defaults(fn=cmd_brief)

    ib = sub.add_parser("inbox", help="read queued messages")
    ib.add_argument("agent", nargs="?", help="whose inbox (defaults to you)")
    ib.add_argument("--clear", action="store_true")
    ib.set_defaults(fn=cmd_inbox)

    recv = sub.add_parser("receive", help="receive one durable message idempotently")
    recv.add_argument("id")
    recv.set_defaults(fn=cmd_receive)

    ev = sub.add_parser("events", help="read the append-only ledger")
    ev.add_argument("--tail", type=int, default=30)
    ev.add_argument("--task", help="filter to one task")
    ev.set_defaults(fn=cmd_events)

    a = p.parse_args()
    a.as_agent = getattr(a, "as_agent", None)
    a.fn(a)


if __name__ == "__main__":
    main()
