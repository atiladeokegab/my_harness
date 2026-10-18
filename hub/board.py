#!/usr/bin/env python3
"""Shared task board for the agent hub. Safe for concurrent access by multiple agents.

State lives in board.json (current snapshot) and events.jsonl (append-only ledger).
The ledger is the audit trail: every transition is recorded there even if a later write
to the snapshot is lost, so it's the place to look when debugging a race.
"""

import argparse
import difflib
import fcntl
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
                f"cannot {verb} {t['id']}: it is {status}.\n"
                f"{verb} is legal from: {', '.join(allowed)}\n"
                f"use --force to override, or check: hub show {t['id']}"
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
    return f"  {mark} {kind}{label(t)}  {t['title']}{progress}{tag}{owner}{blocked}"


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


def verify_checkout(repo):
    """The caller's worktree when it is a checkout of the task's repo, else the repo itself.

    Builders work in linked worktrees on branches; verifying the main checkout would test
    the wrong tree."""
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
        return t["verify"] or None   # "" is an explicit "no verify"
    if not repo:
        return None
    try:
        with open(os.path.join(repo, "Makefile")) as f:
            return "make check" if re.search(r"^check\s*:", f.read(), re.M) else None
    except OSError:
        return None


def run_verify(cmd, cwd):
    """(passed, last VERIFY_TAIL lines of output). Own session so a timeout kills the whole tree."""
    timeout = int(os.environ.get("HUB_VERIFY_TIMEOUT") or VERIFY_TIMEOUT)
    # A repo check is not a board operation: without this a hub test suite run as verify
    # would inherit HUB_DIR and write to whichever board the caller is pointed at.
    env = {k: v for k, v in os.environ.items() if k not in ("HUB_DIR", "HUB_AGENT")}
    p = subprocess.Popen(cmd, shell=True, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         errors="replace", start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        ok = p.returncode == 0
        if not ok:
            out += f"\n(exit {p.returncode})"
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, _ = p.communicate()
        ok = False
        out += f"\n(timed out after {timeout}s)"
    return ok, "\n".join(out.rstrip("\n").splitlines()[-VERIFY_TAIL:])


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


def cmd_new(a):
    me = whoami(a.as_agent)
    if a.owner:
        a.owner = addressable(a.owner, "owner")
    project = which_project(getattr(a, "project", None))
    check_owner(project, a.owner)
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
            **({"kind": "vertical"} if a.vertical else {}),
            **({"verify": a.verify} if a.verify is not None else {}),
        })
        log(events, me, "created", nid, title=a.title, deps=deps, owner=a.owner,
            project=project)
    print(f"created {nid}: {a.title}" + (f"  [{project}]" if project else ""))
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
        print(f"\n{'▣ ' if t.get('kind') == 'vertical' else ''}{label(t)}  [{t['status']}]  {t['title']}")
        if t.get("tags"):
            print(f"tags: {', '.join(t['tags'])}")
        print(f"owner: {t.get('owner') or '-'}   project: {t.get('project') or '-'}"
              f"   created by {t['created_by']} at {t['created']}"
              + (f"   key: {t['id']}" if label(t) != t["id"] else ""))
        if t.get("deps"):
            missing = unmet_deps(data, t)
            by_id = {x["id"]: x for x in data["tasks"]}
            named = lambda ids: ",".join(label(by_id[d]) if d in by_id else d for d in ids)
            print(f"deps: {named(t['deps'])}" + (f"   UNMET: {named(missing)}" if missing else "   (all met)"))
        print(f"\n{t['detail'] or '(no detail)'}\n")
        for n in t["notes"]:
            print(f"  · [{n['at']}] {n['by']}: {n['text']}")
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
    if a.take_github and a.keep_hub:
        sys.exit("choose one of --take-github and --keep-hub")
    if (a.take_github or a.keep_hub) and a.detail_file:
        sys.exit("--take-github and --keep-hub don't combine with --detail-file")
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
    if "untrusted" in untagged and me != LEAD_AGENT and not a.force:
        sys.exit(f"only {LEAD_AGENT} clears 'untrusted' on {label(t)}; --force overrides (recorded)")
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
    elif not (a.title or a.deadline or a.verify is not None or a.tag or a.untag) and sys.stdin.isatty():
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
        if cur["title"] != t["title"] or (cur.get("detail") or "") != old_detail:
            sys.exit(f"{label(cur)} changed while you were editing; run hub edit again")
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
        cur.update(extra)
        cur["updated"] = now()
        log(events, me, "edited", cur["id"], fields=fields, keep_hub=bool(a.keep_hub),
            **({"tagged": tagged, "untagged": untagged} if tagged or untagged else {}),
            **({"forced": True} if a.force and "untrusted" in untagged else {}))
    print(f"{label(t)} saved" + ("; the next hub gh-sync pushes it" if is_hackathon(t.get("project")) else ""))


def next_candidates(tasks, agent, project=None):
    """Open tasks agent may pick up, in hub next's order: its own, then unassigned, then its own in
    other projects. A vertical with children stands for its ready children. hub next takes the
    first; dispatch.py walks on past the ones it skips. The one copy of this order."""
    data, me = {"tasks": tasks}, agent.lower()
    # Strict: an unscoped task is not this project's work either. Without this an agent that
    # clears its own queue falls through to unrelated tasks, which is the whole reason project
    # scoping exists.
    pool = [t for t in tasks if t["status"] == "open"
            and (not project or (t.get("project") or "") == project)]
    # Scope keeps an agent out of unrelated FREE work; it must not hide work someone assigned to
    # it by name. A project-scoped Prometheus was offered T-078 and never shown T-101..T-103,
    # which Zeus had assigned it under project hub/testbed.
    elsewhere = [t for t in tasks if t["status"] == "open" and project
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
                if (child["status"] == "open" and child.get("project") == t.get("project")
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
    with board(write=True) as (data, events):
        t = resolve(data, a.id, which_project(getattr(a, "project", None)))
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
        log(events, me, "claimed", t["id"], forced=bool(missing) or overridden)
    print(f"{label(t)} claimed by {me}")


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
        log(events, me, "released", t["id"], forced=overridden)
    print(f"{label(t)} released back to open")



def cmd_assign(a):
    """The planner hands a task to another agent. Open tasks only, unless --force (then the claim is dropped)."""
    me = whoami(a.as_agent)
    owner = addressable(a.owner, "owner")
    with board(write=True) as (data, events):
        t = resolve(data, a.id, which_project(getattr(a, "project", None)))
        check_owner(t.get("project"), owner, label(t).lstrip("#"))
        if t.get("status") not in ("open", None) and not a.force:
            sys.exit(f"{t['id']} is {t['status']} by {t.get('owner')}; reassigning it drops that work. Use --force.")
        before = t.get("owner")
        t["owner"], t["status"], t["updated"] = owner, "open", now()
        if is_hackathon(t.get("project")):
            t["agent"] = None
        log(events, me, "assigned", t["id"], owner=owner, was=before, forced=bool(a.force))
    if owner != "Pool" and owner not in humans_of(t.get("project")):
        mid = new_message_id()
        deliver(owner, f"{t['id']} assigned to you: {t['title']}", mid)
        notify_hint([(owner, f"{t['id']} is yours: {t['title']}. Run: hub show {t['id']}", mid)])
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
        notify_hint([(agent, f"{message}. Run: hub show {t['id']}", mid)])
    print(f"{label(t)} " + (f"delegated to {agent}" if agent else "delegate cleared"))

def done_guard(data, t, me, a):
    """Every refusal hub done makes; returns whether the issue rule was overridden."""
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
    return issue_rule


def cmd_done(a):
    me = whoami(a.as_agent)
    pings = []
    project = which_project(getattr(a, "project", None))
    # Every refusal first, on a copy and outside the write lock: verify can run for minutes,
    # and holding the board that long would time out every other agent.
    with board() as (data, _):
        t = resolve(data, a.id, project)
        done_guard(data, t, me, a)
        transition(dict(t), "done", me, a.force,
                   who=actor(t) if is_hackathon(t.get("project")) else None)
        repo = verify_checkout(task_repo(t))
        cmd = verify_command(t, repo)
    verdict, tail = None, ""
    if cmd and a.no_verify:
        verdict = "skipped"
    elif cmd:
        if not repo:
            sys.exit(f"{label(t)} has verify `{cmd}` but no checkout for project "
                     f"{t.get('project') or '(none)'} (looked in $HUB_CODE_DIR/<project> and ~/<project>).\n"
                     f"fix the project, or pass --no-verify (recorded in the ledger)")
        print(f"verify: {cmd}  (in {repo})", flush=True)
        ok, tail = run_verify(cmd, repo)
        if not ok:
            verify_failed(t["id"], me, cmd, tail)
        verdict = "passed"
    with board(write=True) as (data, events):
        t = resolve(data, a.id, project)
        issue_rule = done_guard(data, t, me, a)
        blocked_before = {x["id"] for x in data["tasks"] if unmet_deps(data, x)}
        overridden = transition(t, "done", me, a.force,
                                who=actor(t) if is_hackathon(t.get("project")) else None) or issue_rule
        if overridden:
            log(events, me, "override", t["id"], verb="done")
        note = "\n".join(filter(None, [a.note, verdict == "passed" and f"verify passed: {cmd}\n{tail}",
                                       verdict == "skipped" and f"verify skipped: {cmd} (--no-verify)"]))
        if note:
            t["notes"].append({"at": now(), "by": me, "text": note})
        log(events, me, "done", t["id"], note=a.note or "",
            **({"verify": verdict, "cmd": cmd} if verdict else {}))

        for x in data["tasks"]:
            if x["id"] in blocked_before and x["status"] == "open" and not unmet_deps(data, x):
                log(events, me, "unblocked", x["id"], by_task=t["id"])
                text = f"{x['id']} is ready — unblocked by {t['id']}: {x['title']}"
                recipient = actor(x) if is_hackathon(x.get("project")) else x.get("owner")
                if recipient in humans_of(x.get("project")):
                    continue  # humans read their GitHub issue; no hub inbox or pool notice
                if recipient and recipient != "Pool":
                    mid = new_message_id()
                    deliver(recipient, text, mid)
                    pings.append((recipient, text, mid))
                else:
                    pings.append((None, f"{x['id']} is now claimable: {x['title']}", None))
    print(f"{label(t)} marked done by {me}")
    unowned = [p for p in pings if p[0] is None]
    for _, text, _ in unowned:
        print(f"  → {text}")
    notify_hint([p for p in pings if p[0]])


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
    reason = paused()
    out = ([f"HUB PAUSED: {reason}. hub next and hub claim refuse until `hub resume`.\n"]
           if reason else [])
    out += [f"HUB BRIEFING — you are {me}{scope}.",
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
        if others:
            out.append("\nPEERS ARE HOLDING —")
            for t in others:
                tag = f" [{t['project']}]" if t.get("project") else ""
                out.append(f"  {label(t)}  {t['title']}{tag}  @{t['owner']}")

        blocked = [t for t in tasks if t["status"] == "blocked"]
        if blocked:
            out.append("\nBLOCKED —")
            out += [f"  {label(t)}  {t['title']}  @{t.get('owner') or '-'}" for t in blocked]

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
    n.add_argument("--vertical", action="store_true", help="create an owner-area vertical")
    n.add_argument("--verify", help="command hub done must pass in the task's repo "
                   "(default: make check if the repo has that target; \"\" for none)")
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
    ed.add_argument("--yes", action="store_true", help="save without asking")
    ed.add_argument("--force", action="store_true", help="let a non-lead clear 'untrusted' (recorded)")
    ed.set_defaults(fn=cmd_edit)

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

    g = sub.add_parser("assign", help="hand a task to another owner (planner)")
    g.add_argument("id")
    g.add_argument("owner")
    g.add_argument("--force", action="store_true", help="also reassign a claimed or blocked task (recorded)")
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

    import gh_sync
    gh_sync.register(sub)
    import live
    live.register(sub)
    import review
    review.register(sub)

    ev = sub.add_parser("events", help="read the append-only ledger")
    ev.add_argument("--tail", type=int, default=30)
    ev.add_argument("--task", help="filter to one task")
    ev.set_defaults(fn=cmd_events)

    a = p.parse_args()
    a.as_agent = getattr(a, "as_agent", None)
    a.fn(a)


if __name__ == "__main__":
    main()
