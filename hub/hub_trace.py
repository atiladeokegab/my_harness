"""hub trace: why does this exist, who asked, who approved, who built it.

One read-only, offline command: why does this exist, who asked, who approved, who built it, where did it land.

    hub trace <A-n.m[@v] | R-n | T-n | sha | #N | PR#N> [--project P]

An acceptance line or requirement walks up (the changes that touched it, their receipts, the ~/hub commit that
applied each) and down (tasks citing it, their events and merges, Req:-trailered commits on origin/main). A task,
sha or PR walks up only. A broken link prints as "untraced: ..." or "NOT approved: ...", never skipped. Exit 1
only when the id is found nowhere. Reads spec files, board.json, events.jsonl, live-state.json and two git logs;
writes nothing, calls no gh and fetches nothing.
"""

import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from functools import lru_cache

import board as hb
import spec

LINE = re.compile(r"^A-(\d+)\.\d+(?:@(\d+))?$")
REQ = re.compile(r"^R-(\d+)$")
TASK = re.compile(r"^T-\d+$", re.I)
PR = re.compile(r"^(?:PR)?#(\d+)$", re.I)
SHA = re.compile(r"^[0-9a-f]{7,40}$")
APPLIED = re.compile(r"\b(C-\d{3,}) applied\b")
KEEP = ("created", "claimed", "done", "stale", "carried", "merge_sha")
UNTRACED = "untraced: no Task: trailer, no merge_sha, no merge_event"

lines = []


def out(ind, text):
    lines.append("  " * ind + text)


def uk(at):
    """An ISO time in this machine's local time zone ($TZ), for the lead; the raw value if it cannot be read."""
    try:
        return datetime.fromisoformat(str(at)).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        return str(at)


def one_line(text, n=200):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 3] + "..."


def git(repo, *args):
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}  # a hook's leaked GIT_DIR
    try:
        r = subprocess.run(["git", "-C", repo, *args], env=env, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------- sources, each read once per call

@lru_cache(None)
def tasks():
    return [t for t in read_json(hb.BOARD, {}).get("tasks", []) if isinstance(t, dict)]


@lru_cache(None)
def events():
    """{task: [event]} for the events a trace prints, streamed once (no tail repair: that would write)."""
    by = {}
    try:
        with open(hb.EVENTS) as f:
            for raw in f:
                try:
                    e = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(e, dict) and e.get("event") in KEEP:
                    by.setdefault(e.get("task"), []).append(e)
    except OSError:
        pass
    return by


def spec_projects():
    return sorted({os.path.basename(os.path.dirname(os.path.dirname(p)))
                   for name in ("prd.json", "requirements.json")
                   for p in glob.glob(os.path.join(hb.HUB_DIR, "projects", "*", "spec", name))})


def state_projects():
    return sorted(os.path.basename(os.path.dirname(p))
                  for p in glob.glob(os.path.join(hb.HUB_DIR, "projects", "*", "live-state.json")))


@lru_cache(None)
def current(p):
    return read_json(spec.spec_path(p), {"requirements": []})


@lru_cache(None)
def changes(p):
    """[(cid, change)] in id order."""
    found = []
    for path in glob.glob(os.path.join(spec.spec_dir(p), "changes", "C-*.json")):
        cid = os.path.basename(path)[:-5]
        c = read_json(path, None)
        if spec.CHANGE_ID.match(cid) and isinstance(c, dict):
            found.append((cid, c))
    return sorted(found, key=lambda x: int(x[0][2:]))


@lru_cache(None)
def known(p):
    """({line id: (req id, text, current v or None)}, {req id: (title, in the current spec?)}): every line and
    requirement the spec or any change has named, the current spec winning."""
    ls, rs = {}, {}
    for _, c in changes(p):
        for x in c.get("added", []) + c.get("modified", []):
            if REQ.match(str(x.get("id"))):
                rs[x["id"]] = (x.get("title") or rs.get(x["id"], ("", 0))[0], False)
                for a in x.get("acceptance", []):
                    ls[a["id"]] = (x["id"], a.get("text", ""), None)
            elif LINE.match(str(x.get("id"))):
                old = ls.get(x["id"], (None, "", None))
                ls[x["id"]] = (x.get("req") or old[0] or "R-" + LINE.match(x["id"]).group(1),
                               x.get("text") or old[1], None)
    for r in current(p).get("requirements", []):
        rs[r["id"]] = (r.get("title", ""), True)
        for a in r.get("acceptance", []):
            ls[a["id"]] = (r["id"], a.get("text", ""), a.get("v"))
    return ls, rs


@lru_cache(None)
def applied(p):
    """{cid: (short sha, subject)} from the ~/hub commits that wrote this project's spec file: prd.json, or the
    legacy requirements.json (both, so a project that migrated keeps the changes applied before the rename)."""
    log = git(hb.HUB_DIR, "log", "--format=%h%x1f%s", "--",
              *(os.path.join(spec.spec_dir(p), name) for name in ("prd.json", "requirements.json")))
    found = {}
    for row in (log or "").splitlines():
        sha, _, subject = row.partition("\x1f")
        m = APPLIED.search(subject)
        if m:
            found.setdefault(m.group(1), (sha, subject))
    return found


@lru_cache(None)
def merge_events(p):
    st = read_json(os.path.join(hb.HUB_DIR, "projects", p, "live-state.json"), {})
    return [e for e in (st.get("merge_events") or []) if isinstance(e, dict)]


def clone(p):
    return os.path.expanduser(f"~/code/{p}")


@lru_cache(None)
def commits(p):
    """origin/main's commits in the local clone, newest first, or None with no clone or no origin/main."""
    log = git(clone(p), "log", "origin/main", "--format=%x1e%H%x1f%s%x1f"
              "%(trailers:key=Task,valueonly,separator=%x2c)%x1f%(trailers:key=Req,valueonly,separator=%x2c)")
    if log is None:
        return None
    found = []
    for chunk in log.split("\x1e")[1:]:
        sha, subject, tk, rq = (chunk.strip("\n").split("\x1f") + ["", "", "", ""])[:4]
        found.append({"sha": sha, "subject": subject, "tasks": [x.strip() for x in tk.split(",") if x.strip()],
                      "reqs": [x.strip() for x in rq.split(",") if x.strip()]})
    return found


def fetched(p):
    try:
        return "fetched " + uk(datetime.fromtimestamp(os.path.getmtime(os.path.join(clone(p), ".git", "FETCH_HEAD")),
                                                      timezone.utc).isoformat())
    except OSError:
        return "never fetched"


# ---------------------------------------------------------------- the walk

def change_hops(p, aid, rid):
    """[(verb, cid, change)] for every change that touched the line (aid) or, with aid None, the requirement."""
    hops = []
    for cid, c in changes(p):
        verb = None
        for x in c.get("added", []):
            if x.get("id") == (aid or rid) or (aid and x.get("id") == rid and
                                               any(a.get("id") == aid for a in x.get("acceptance", []))):
                verb = "added"
        if any(x.get("id") == (aid or rid) for x in c.get("modified", [])):
            verb = "modified"
        if (aid or rid) in c.get("removed", []) or rid in c.get("removed", []):
            verb = "removed"
        if verb:
            hops.append((verb, cid, c))
    return hops


def print_hop(p, verb, cid, c, ind):
    base = c.get("base_version")
    vers = f" (v{base} -> v{base + 1})" if isinstance(base, int) else ""
    out(ind, f"{verb} by {cid}{vers}: {one_line(c.get('reason'))}")
    ok, why = spec.approval(p, cid)
    if ok:
        rec = read_json(os.path.join(hb.HUB_DIR, "projects", p, why[len("receipt "):]), {})
        out(ind + 1, f"approved {uk(rec.get('at'))}, {why}, bytes match")
        if rec.get("note"):
            out(ind + 2, f'note: "{one_line(rec["note"])}"')
    else:
        out(ind + 1, f"NOT approved: {why}")
    if cid in applied(p):
        sha, subject = applied(p)[cid]
        out(ind + 1, f'applied in ~/hub {sha} "{subject}"')
    else:
        out(ind + 1, f"untraced: no ~/hub commit says {cid} applied")


def print_task(t, label, ind):
    p = t.get("project")
    tags = f" [{', '.join(t['tags'])}]" if t.get("tags") else ""
    out(ind, f"{label} {t['id']} (generated_from {t.get('generated_from') or '-'}, owner {t.get('owner') or '-'}, "
             f"agent {t.get('agent') or '-'}), {t.get('status')}{tags}: {t.get('title', '')}")
    carried = []
    for e in events().get(t["id"], []):
        ev = e["event"]
        if ev == "carried":
            carried.append(e.get("change") or "?")
        elif ev == "done":
            out(ind + 1, f'done {uk(e.get("at"))} by {e.get("by")}: "{one_line(e.get("note"))}"'
                         + (f" (verify {e['verify']})" if e.get("verify") else ""))
        elif ev == "stale":
            out(ind + 1, f"stale {uk(e.get('at'))}, superseded by {e.get('change') or '?'}")
        elif ev == "merge_sha":
            out(ind + 1, f"merge_sha {str(e.get('sha'))[:12]} set {uk(e.get('at'))} by {e.get('by')}")
        else:
            out(ind + 1, f"{ev} {uk(e.get('at'))} by {e.get('by')}")
    if carried:
        out(ind + 1, "carried over by " + ", ".join(carried))
    shas = spec.merge_shas(t)
    mes = [e for e in (merge_events(p) if p else []) if e.get("event") == "merged" and (
        e.get("task") == t["id"] or (t.get("issue") is not None and e.get("issue") == t.get("issue")))]
    for e in mes:
        into = f" into {e['base']}" if e.get("base") else ""
        sha = f", sha {e['sha'][:12]}" if e.get("sha") else ""
        out(ind + 1, f"PR #{e.get('pr')} merged {uk(e.get('at'))} by {'hand' if e.get('by') == 'hand' else 'hub live'}"
                     f"{into}{sha}")
    for m in shas:
        out(ind + 1, f"merge_sha {m[:12]}")
    cs = commits(p) if p else None
    hits = [c for c in cs or [] if t["id"] in c["tasks"] or any(c["sha"].startswith(m) for m in shas if len(m) >= 7)]
    for c in hits:
        out(ind + 1, f"origin/main {c['sha'][:12]} {c['subject']}" +
                     (f" (Task: {', '.join(c['tasks'])})" if c["tasks"] else " (no Task: trailer)"))
    if not (mes or shas or any(t["id"] in c["tasks"] for c in hits)):
        out(ind + 1, UNTRACED)
    if p and cs is None:
        out(ind + 1, f"untraced: no clone with origin/main at {clone(p)}")


def trace_line(p, aid, ver, down, ind=0):
    ls, rs = known(p)
    cites = [t for t in tasks() if t.get("project") == p and any(
        str(q).split("@")[0] == aid and (ver is None or str(q) == f"{aid}@{ver}") for q in t.get("reqs") or [])]
    if aid not in ls and not cites:
        return False
    rid, text, v = ls.get(aid, ("R-" + LINE.match(aid).group(1), "", None))
    where = "" if v is not None else f"; not in the current spec (v{current(p).get('version', '?')})"
    out(ind, f"{aid}{f'@{v}' if v is not None else ''}  {text}   ({rid} {rs.get(rid, ('?',))[0]}){where}")
    hops = change_hops(p, aid, rid)
    for verb, cid, c in hops:
        print_hop(p, verb, cid, c, ind + 1)
    if not hops:
        out(ind + 1, f"untraced: no change touches {aid} (in the spec from v1, or edited by hand)")
    if not down:
        return True
    for t in cites:
        print_task(t, "built by" if t.get("status") == "done" else "cited by", ind + 1)
    if not cites:
        out(ind + 1, f"untraced: no task cites {aid}")
    cs = commits(p)
    if cs is None:
        out(ind + 1, f"untraced: no clone with origin/main at {clone(p)}")
    else:
        hit = [c["sha"][:12] for c in cs if any(q.split("@")[0] == aid for q in c["reqs"])]
        out(ind + 1, (f"origin/main commits with Req: {aid}: {', '.join(hit)}" if hit else
                      f"untraced: no origin/main commit carries Req: {aid}") + f" ({fetched(p)})")
    return True


def trace_req(p, rid):
    ls, rs = known(p)
    if rid not in rs:
        return False
    title, live = rs[rid]
    out(0, f"{rid} {title}" + ("" if live else f"; not in the current spec (v{current(p).get('version', '?')})"))
    for verb, cid, c in change_hops(p, None, rid):
        print_hop(p, verb, cid, c, 1)
    for aid in sorted((a for a, (r, _, _) in ls.items() if r == rid), key=spec.sort_key):
        trace_line(p, aid, None, True, 1)
    return True


def trace_task(t, label="task"):
    print_task(t, label, 0)
    for q in t.get("reqs") or []:
        aid, _, ver = str(q).partition("@")
        if not (LINE.match(aid) and t.get("project") and trace_line(t["project"], aid, ver or None, False, 1)):
            out(1, f"untraced: cites {q}, which no spec or change of {t.get('project')} names")
    if not t.get("reqs"):
        out(1, "untraced: cites no acceptance line")


def trace_pr(p, n):
    found = False
    for e in merge_events(p):
        if e.get("event") != "merged" or e.get("pr") != n:
            continue
        found = True
        t = next((t for t in tasks() if t["id"] == e.get("task")), None) or next(
            (t for t in tasks() if t.get("project") == p and e.get("issue") is not None
             and t.get("issue") == e.get("issue")), None)
        out(0, f"PR #{n} ({p}, issue #{e.get('issue')}), merged {uk(e.get('at'))}")
        if t:
            trace_task(t)
        else:
            out(1, f"untraced: no task for PR #{n} (merge_event names no task, no task has issue "
                   f"#{e.get('issue')})")
    return found


def trace_sha(p, ref):
    seen, found = set(), False
    for c in commits(p) or []:
        if not c["sha"].startswith(ref):
            continue
        found = True
        out(0, f"{p} origin/main {c['sha'][:12]} {c['subject']} ({fetched(p)})")
        byme = [t for t in tasks() if t["id"] in c["tasks"] or any(c["sha"].startswith(m) for m in
                                                                    spec.merge_shas(t) if len(m) >= 7)]
        mes = [e for e in merge_events(p) if str(e.get("sha", "")).startswith(c["sha"][:12])]
        if not (c["tasks"] or byme or mes):
            out(1, UNTRACED)
        for q in c["reqs"]:
            if not byme:
                aid, _, ver = q.partition("@")
                if LINE.match(aid):
                    trace_line(p, aid, ver or None, False, 1)
        seen.update(t["id"] for t in byme)
    for t in tasks():
        if t.get("project") == p and (t["id"] in seen or any(m.startswith(ref) for m in spec.merge_shas(t))):
            found = True
            trace_task(t, "merged by")
    return found


def per_project(projects, fn):
    """fn(p) for each project into its own block; with more than one hit, each block is headed [project]."""
    global lines
    blocks = []
    for p in projects:
        lines = []
        if fn(p):
            blocks.append((p, lines))
    lines = []
    for p, block in blocks:
        if len(blocks) > 1:
            out(0, f"[{p}]")
        lines += block
    return bool(blocks)


def cmd_trace(a):
    ref = a.ref.strip()
    scope = hb.which_project(a.project)
    projects = [scope] if scope else sorted(set(spec_projects()) | set(state_projects()))
    found = False
    if LINE.match(ref):
        m = LINE.match(ref)
        found = per_project(projects, lambda p: trace_line(p, ref.split("@")[0], m.group(2), True))
    elif REQ.match(ref):
        found = per_project(projects, lambda p: trace_req(p, ref))
    elif TASK.match(ref):  # task ids are board-wide, so a task traces whatever the scope
        t = next((t for t in tasks() if t["id"] == hb.norm_id(ref)), None)
        if t:
            found = True
            trace_task(t)
    elif PR.match(ref):
        found = per_project(projects, lambda p: trace_pr(p, int(PR.match(ref).group(1))))
    elif SHA.match(ref.lower()):
        found = per_project(projects, lambda p: trace_sha(p, ref.lower()))
    if lines:
        print("\n".join(lines))
    if not found:
        sys.exit(f"hub trace: {ref} found nowhere (spec, changes, board, merge_events, origin/main of "
                 f"{', '.join(projects) or 'no project'})")


def register(sub):
    t = sub.add_parser("trace", help="read-only: why a line, requirement, task, commit or PR exists, "
                                     "who approved and built it, where it landed")
    t.add_argument("ref", metavar="A-n.m[@v] | R-n | T-n | sha | #N | PR#N")
    t.add_argument("--project", help="one project (default: $HUB_PROJECT, else every project with a spec or live state)")
    t.set_defaults(fn=cmd_trace)
