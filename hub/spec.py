"""hub spec: the PRD tree (docs/hub/living-spec.md).

The PRD (projects/<project>/spec/prd.json, or legacy requirements.json) is the root. An approved change
(spec/changes/C-NNN.json)
writes PRD v+1 and regenerates the project's whole task tree: done tasks outside the blast radius are carried
over, done tasks inside it are rewound on branch change/C-NNN, unfinished tasks citing a changed line are marked
stale (tasks with no spec lineage are never touched), and new
tasks are generated for every acceptance line no carried-over task covers. Deterministic: no model anywhere,
standard library plus git. Same spec, board and repo in, same bytes out.

    hub spec init <project> [--from FILE]
    hub spec bootstrap-sha --project P T-n=<sha> ...
    hub spec check [--project P] [--repo DIR]
    hub spec lint C-NNN             deterministic overlap checks
    hub spec impact C-NNN            the radius from the graph alone
    hub spec rewind C-NNN --dry-run  the radius, the rewind in a throwaway clone, and the check run
    hub spec apply C-NNN [--force] [--yes]  all of it, for real
    hub spec converge [--project P]  weekly: one board task per drift from origin's live line
"""

import copy
import difflib
import fnmatch
import glob
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

import autonomy
import board as hb
import gh_sync
import spec_lint

CODE_DIR = os.environ.get("HUB_CODE_DIR") or os.path.expanduser("~/code")

TRIES = 3  # each kept check runs this many times; a mixed result is flaky and quarantined, not a hidden dependency
DEFAULT_CHECK = "uv run pytest -q {test}"
DEFAULT_COLLECT = "uv run pytest -q --collect-only {test}"  # the check-writer's gate: its checks are red by design
PROTECTED = ("spec/", "tests/acceptance/")  # as live_merge.PROTECTED: the check-writer's, never a builder's
ACCEPT_TEST = re.compile(r"^test_A_\d+_\d+\.py$")
CHANGE_ID = re.compile(r"^C-\d{3,}$")
LEAD_AGENT = os.environ.get("HUB_LEAD") or "Zeus"


def die(msg):
    sys.exit(f"hub spec: {msg}")


def spec_dir(project):
    return os.path.join(hb.HUB_DIR, "projects", project, "spec")


def spec_path(project):
    """The project's one source file: the full PRD if present, else the legacy requirements."""
    d = spec_dir(project)
    prd = os.path.join(d, "prd.json")
    return prd if os.path.isfile(prd) else os.path.join(d, "requirements.json")


def touches_overlap(a, b):
    if fnmatch.fnmatchcase(a, b) or fnmatch.fnmatchcase(b, a):
        return True
    if not (glob.has_magic(a) and glob.has_magic(b)):
        return False
    # shortcut: compatible glob prefixes may still be disjoint; refine if false conflicts block parallel work.
    x, y = (re.split(r"[*?\[]", p, maxsplit=1)[0] for p in (a, b))
    return x.startswith(y) or y.startswith(x)


def default_test(aid):
    return f"tests/acceptance/test_{aid.replace('-', '_').replace('.', '_')}.py"


class ApprovalResult(tuple):
    def __new__(cls, ok, why, reviewer=None, receipt_file=None):
        inst = super().__new__(cls, (ok, why))
        inst.ok = ok
        inst.why = why
        inst.reviewer = reviewer
        inst.receipt_file = receipt_file
        return inst


def approval(project, cid):
    """(approved?, by what). Only a `hub review` receipt approves: it names the change file (approved_path) and
    holds the sha256 of the bytes the lead approved, which must equal the file's bytes now. A hash written into
    the change itself proves nothing, since anyone who can write the file can compute it."""
    path = os.path.realpath(os.path.join(spec_dir(project), "changes", f"{cid}.json"))
    root = os.path.join(hb.HUB_DIR, "projects", project)
    sha, found = file_sha(path), False
    for r in sorted(glob.glob(os.path.join(root, "**", "reviews", "*.json"), recursive=True)):
        try:
            with open(r) as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and rec.get("decision") == "approve" and rec.get("approved_path") \
                and os.path.realpath(rec["approved_path"]) == path:
            if rec.get("approved_sha256") == sha:
                reviewer = rec.get("reviewer") or rec.get("by")
                return ApprovalResult(True, f"receipt {os.path.relpath(r, root)}", reviewer=reviewer, receipt_file=r)
            found = True
    return ApprovalResult(False, ("no receipt matches the file's current bytes" if found else
                   "no `hub review` receipt approves this change file"))


def file_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_spec(project):
    path = spec_path(project)
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        die(f"no spec for {project}: {path}")


def load_change(project, cid):
    if not CHANGE_ID.match(cid):
        die(f"bad change id {cid!r}: want C-NNN")
    try:
        with open(os.path.join(spec_dir(project), "changes", f"{cid}.json")) as f:
            return json.load(f)
    except FileNotFoundError:
        die(f"no change {cid} for {project}")


def repo_cfg(project):
    """The factory.json repo entry for this project: optional shared, migrations, acceptance_cmd and collect_cmd."""
    try:
        with open(os.path.join(hb.HUB_DIR, "factory.json")) as f:
            repos = json.load(f).get("repos", [])
    except FileNotFoundError:
        return {}
    for r in repos:
        if isinstance(r, dict) and (r.get("repo") or "").split("/")[-1].lower() == project.lower():
            return r
    return {}


def under(path, prefixes):
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in prefixes)


def lines_of(spec):
    return {a["id"]: (r["id"], a) for r in spec["requirements"] for a in r.get("acceptance", [])}


# ---------------------------------------------------------------- check

def schema_errors(spec):
    errs = []
    if not isinstance(spec.get("version"), int) or spec["version"] < 1:
        errs.append("version must be a positive integer")
    reqs = spec.get("requirements")
    if not isinstance(reqs, list):
        return errs + ["requirements must be a list"]
    rids = [r.get("id") for r in reqs]
    aids = []
    for r in reqs:
        rid = r.get("id")
        if not re.fullmatch(r"R-\d+", str(rid)):
            errs.append(f"bad requirement id {rid!r}")
            continue
        if not isinstance(r.get("title"), str):
            errs.append(f"{rid}: title must be a string")
        errs += [f"{rid} needs unknown {n}" for n in r.get("needs", []) if n not in rids]
        for a in r.get("acceptance", []):
            aid = a.get("id")
            aids.append(aid)
            if not re.fullmatch(rf"A-{rid[2:]}\.\d+", str(aid)):
                errs.append(f"{rid}: acceptance id {aid!r} must be A-{rid[2:]}.<n>")
            if not isinstance(a.get("v"), int) or a["v"] < 1:
                errs.append(f"{aid}: v must be a positive integer")
            if not isinstance(a.get("text"), str) or not isinstance(a.get("test"), str):
                errs.append(f"{aid}: text and test must be strings")
    errs += [f"duplicate id {x}" for x in sorted({x for x in rids + aids if (rids + aids).count(x) > 1}, key=str)]
    return errs


def check_errors(project, repo, only=None):
    """Schema and lock always; test files only for the `only` lines when given (a task's own verify),
    so an untouched requirement that never got checks cannot block an unrelated task."""
    d = spec_dir(project)
    path = spec_path(project)
    if os.path.isfile(os.path.join(d, "prd.json")) and os.path.isfile(os.path.join(d, "requirements.json")):
        return [f"both prd.json and requirements.json in {d}: one source only; remove requirements.json once "
                "prd.json carries everything"]
    spec = load_spec(project)
    errs = schema_errors(spec)
    try:
        with open(os.path.join(d, "spec.lock")) as f:
            lock = json.load(f)
        if lock.get("sha256") != file_sha(path):
            errs.append(f"spec.lock: sha256 does not match {os.path.basename(path)} (edited outside hub spec apply?)")
        if lock.get("version") != spec.get("version"):
            errs.append(f"spec.lock: version {lock.get('version')} but {os.path.basename(path)} is v{spec.get('version')}")
    except FileNotFoundError:
        errs.append("spec.lock missing")
    if errs:
        return errs
    tests = {a["test"]: aid for aid, (_, a) in lines_of(spec).items()}
    errs += [f"--lines {aid}: no active acceptance line by that id" for aid in sorted((only or set()) - set(tests.values()))]
    errs += [f"{aid}: test file missing: {t}" for t, aid in sorted(tests.items(), key=lambda x: x[1])
             if (only is None or aid in only) and not os.path.isfile(os.path.join(repo, t))]
    acc = os.path.join(repo, "tests", "acceptance")
    for name in sorted(os.listdir(acc)) if os.path.isdir(acc) else []:
        if ACCEPT_TEST.match(name) and f"tests/acceptance/{name}" not in tests:
            errs.append(f"tests/acceptance/{name} maps to no active acceptance line")
    return errs


# ---------------------------------------------------------------- the change

def set_errors(change):
    """Reject PRD updates outside the three editable top-level sections."""
    updates = change.get("set", {})
    if not isinstance(updates, dict):
        return ["set must be an object"]
    if not updates:
        return []
    import prd

    errs = []
    allowed = {"header": prd.HEADER, "constraints": prd.CONSTRAINTS, "references": prd.REFS}
    for path, value in updates.items():
        root, dot, field = path.partition(".") if isinstance(path, str) else ("", "", "")
        if not dot or not field or "." in field or field not in allowed.get(root, ()):
            errs.append(f"unknown set path {path!r}")
        elif root == "references" and not isinstance(value, dict):
            errs.append(f"{path}: reference must be an object")
        elif root in ("header", "constraints") and value is not None \
                and not isinstance(value, (prd.HEADER if root == "header" else prd.CONSTRAINTS)[field]):
            errs.append(f"{path}: wrong value type")
    return errs


def apply_change(spec, change):
    """PRD v+1 from an approved delta. Removed, then modified, then added."""
    if errs := set_errors(change):
        die(f"{change['id']} has invalid set: " + "; ".join(errs))
    new = copy.deepcopy(spec)
    new["version"] += 1
    for path, value in change.get("set", {}).items():
        root, field = path.split(".", 1)
        new.setdefault(root, {})[field] = copy.deepcopy(value)
    reqs = {r["id"]: r for r in new["requirements"]}
    lines = lines_of(new)
    for x in change.get("removed", []):
        if x in reqs:
            new["requirements"].remove(reqs.pop(x))
        elif x in lines:
            reqs[lines[x][0]]["acceptance"].remove(lines[x][1])
        else:
            die(f"{change['id']} removes unknown {x}")
    for x in change.get("modified", []):
        if x["id"] in lines:
            a = lines[x["id"]][1]
            a.update({k: x[k] for k in ("text", "test", "fixtures") if k in x})
            if change.get("kind") != "correction":
                a["v"] += 1
        elif x["id"] in reqs:  # prose: rebuilds nothing
            reqs[x["id"]].update({k: x[k] for k in ("title", "why", "rank", "needs", "touches") if k in x})
        else:
            die(f"{change['id']} modifies unknown {x['id']}")
    for x in change.get("added", []):
        line = lambda a: {**{k: v for k, v in a.items() if k != "req"},
                          "v": 1, "test": a.get("test") or default_test(a["id"])}
        if x["id"].startswith("R-"):
            new["requirements"].append({**x, "needs": x.get("needs", []),
                                        "acceptance": [line(a) for a in x.get("acceptance", [])]})
        elif x.get("req") in reqs:
            reqs[x["req"]]["acceptance"].append(line(x))
        else:
            die(f"{change['id']}: added {x['id']} names no existing req")
    errs = schema_errors(new)
    if change.get("set"):
        import prd
        errs += prd.validate(new)[0]
    if errs:
        die(f"{change['id']} would make an invalid spec: " + "; ".join(errs))
    return new


def changed_lines(spec, change):
    """Acceptance ids whose old version no longer holds: {id: 'modified' | 'removed'}.

    For corrections (Living spec §4), the blast radius is 0 by design:
    corrections fix wording, typos, or test paths within bounded limits (enforced by
    cmd_correct) without bumping line versions or invalidating existing code/tasks.
    Therefore, no existing tasks or commits are rewound.
    """
    if change.get("kind") == "correction":
        return {}
    old = lines_of(spec)
    out = {x["id"]: "modified" for x in change.get("modified", []) if x["id"] in old}
    for x in change.get("removed", []):
        out.update({aid: "removed" for aid, (rid, _) in old.items() if x in (aid, rid)})
    return out


# ---------------------------------------------------------------- the radius (section 3, v1: file-level cascade)

def base_ref(repo, cfg):
    """Fetch origin, then the live line: origin/<base_branch>, else origin/integration if it exists, else
    origin/main. Never a local ref, which can be stale. Returns (name, sha)."""
    r = git(repo, "fetch", "-q", "origin", check=False, timeout=NET_TIMEOUT)
    if r.returncode:
        die(f"origin unreachable, so the live line cannot be read: {(r.stderr or r.stdout).strip()}")
    has = lambda b: git(repo, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{b}", check=False).returncode == 0
    name = cfg.get("base_branch") or ("integration" if has("integration") else "main")
    if not has(name):
        die(f"origin has no branch {name}")
    return f"origin/{name}", git(repo, "rev-parse", f"refs/remotes/origin/{name}").strip()


def merge_shas(t):
    m = t.get("merge_sha") or []
    return [m] if isinstance(m, str) else list(m)


CHANGE_MERGE = re.compile(r"^Merge change/C-\d+\b")  # land_change's --no-ff merge of a change branch
REWIND = re.compile(r"^Rewind for (C-\d+)\b")  # rewind()'s commit


def history(repo, base, tasks, rewound=None):
    """base's first-parent commits, oldest first: sha, merge?, tasks (Task: trailer plus any task whose merge_sha
    names the commit, since a squash merge carries no trailer), Req trailers, {path: status}. A change branch's
    merge is replaced by the branch's own commits, in order (its squashes sit on the merge's second parent).
    A rewind commit never appears: it belongs to no task. rewound is the lock's {change: [the shas its rewind
    reverted]}; those are skipped only once that change's rewind is on the walked line (matched by subject, so a
    rebased branch counts), since then they are no longer live code and must not be reverted twice."""
    claims = [(m, t["id"]) for t in tasks for m in merge_shas(t) if len(m) >= 7]
    def log(*rev):
        out = git(repo, "log", *rev, "--reverse", "--no-renames", "--name-status",
                  "--format=%x1e%H%x1f%P%x1f%s%x1f%(trailers:key=Task,valueonly,separator=%x2c)"
                  "%x1f%(trailers:key=Req,valueonly,separator=%x2c)")
        commits = []
        for chunk in out.split("\x1e")[1:]:
            head, *rest = chunk.split("\n")
            sha, parents, subject, task, req = head.split("\x1f")
            files = {}
            for ln in rest:
                if "\t" in ln:
                    st, path = ln.split("\t", 1)
                    files[path] = st
            mine = {hb.norm_id(task.split(",")[0])} if task.strip() else set()
            mine |= {tid for m, tid in claims if sha.startswith(m)}
            commits.append({"sha": sha, "merge": len(parents.split()) > 1, "files": files, "tasks": sorted(mine),
                            "req": sorted(r.strip() for r in req.split(",") if r.strip()), "subject": subject})
        return commits
    commits = []
    for c in log(base, "--first-parent", "--diff-merges=first-parent"):
        commits += log("--no-merges", f"{c['sha']}^1..{c['sha']}^2") if c["merge"] and CHANGE_MERGE.match(c["subject"]) else [c]
    landed = {m[1] for c in commits if (m := REWIND.match(c["subject"]))}
    skip = {sha for cid in landed for sha in (rewound or {}).get(cid, [])}
    return [c for c in commits if not REWIND.match(c["subject"]) and c["sha"] not in skip]


def unlanded(repo, base_sha, cid):
    """The other changes whose change/C-NNN branch is on origin but not in the base."""
    r = git(repo, "ls-remote", "--heads", "origin", "refs/heads/change/*", check=False, timeout=NET_TIMEOUT)
    if r.returncode:
        die(f"origin unreachable, so open change branches cannot be read: {(r.stderr or r.stdout).strip()}")
    heads = [line.split("\t") for line in r.stdout.splitlines()]
    return [ref.removeprefix("refs/heads/change/") for sha, ref in heads if ref != f"refs/heads/change/{cid}"
            and git(repo, "merge-base", "--is-ancestor", sha, base_sha, check=False).returncode]


def radius(spec, change, tasks, commits, cfg):
    """K: {unit: reason}. A unit is a task id, or a commit sha for a commit no task claims. A commit claimed by
    two tasks belongs to both: either one in K reverts it, and K pulls in both."""
    changed = changed_lines(spec, change)
    shared = cfg.get("shared", [])
    done = {t["id"]: t for t in tasks if t["status"] == "done"}
    k = {}
    for tid in sorted(done):
        cited = [c for c in done[tid].get("reqs", []) if c.split("@")[0] in changed]
        if cited:
            k[tid] = "cites " + ", ".join(f"{c} ({changed[c.split('@')[0]]})" for c in cited)
    for c in commits:  # a commit whose Req: trailer cites a changed line is in K whatever its task listed
        cited = [r for r in c["req"] if r.split("@")[0] in changed]
        for u in units(c) if cited else []:
            k.setdefault(u, f"commit {c['sha'][:12]} trailer Req: " + ", ".join(
                f"{r} ({changed[r.split('@')[0]]})" for r in cited))
    grew = True
    while grew:  # to a fixpoint
        grew = False
        for j, c in enumerate(commits):
            out = [u for u in units(c) if u not in k]
            inn = [u for u in units(c) if u in k]
            if out and inn:  # this commit reverts, so every task that claims it is rewound too
                k.update({u: f"shares commit {c['sha'][:12]} with {inn[0]}" for u in out})
                grew = True
                continue
            for p in commits[:j] if out else []:  # a later commit touching a non-shared file a K commit touched
                by = [u for u in units(p) if u in k]
                hit = sorted(f for f in c["files"] if f in p["files"] and not under(f, shared))
                if by and hit:
                    k.update({u: f"entangled with {by[0]} via {hit[0]}" for u in out})
                    grew = True
                    break
    return k


def units(c):
    return c["tasks"] or [c["sha"][:12]]


def analyse(project, repo, cid):
    spec, change = load_spec(project), load_change(project, cid)
    if change.get("id") != cid:
        die(f"{cid}.json says id {change.get('id')!r}")
    if change.get("base_version") != spec["version"]:
        die(f"{cid} was written against v{change.get('base_version')}, the spec is v{spec['version']}: rewrite it")
    new = apply_change(spec, change)
    cfg = repo_cfg(project)
    with hb.board() as (data, _):
        tasks = [t for t in data["tasks"] if tree_task(t, project)]
    base, base_sha = base_ref(repo, cfg)
    try:
        with open(os.path.join(spec_dir(project), "spec.lock")) as f:
            rewound = json.load(f).get("rewound") or {}
    except (OSError, ValueError):
        rewound = {}
    commits = history(repo, base_sha, tasks, rewound)
    k = radius(spec, change, tasks, commits, cfg)
    revert = [c for c in reversed(commits) if any(u in k for u in units(c))]  # newest first
    carry = [t for t in tasks if t["status"] == "done" and t["id"] not in k]
    kept = sorted({c.split("@")[0] for t in carry for c in t.get("reqs", [])} & set(lines_of(new)), key=sort_key)
    added = {f for c in revert for f, st in c["files"].items() if st == "A"}
    return {"project": project, "kept": kept, "base": base, "base_sha": base_sha, "rewound": rewound,
            "restored": sorted(added & {lines_of(new)[a][1]["test"] for a in kept}), "spec": spec, "change": change, "new": new, "cfg": cfg, "tasks": tasks, "k": k, "revert": revert,
            "commits": commits, "changed": changed_lines(spec, change), "radius": len(k),
            "migrations": sorted({f for c in revert for f, st in c["files"].items()
                                  if st == "A" and under(f, cfg.get("migrations", []))})}


def tree_task(t, project):
    """A task of the project's spec tree. A retired task (hub retire) was closed without being built, so it is left
    out: it carries no reqs as built, is never stamped or staled, and its lines are rebuilt or reported unchecked."""
    return (t.get("project") == project and "stale" not in (t.get("tags") or [])
            and not (t.get("retired") and t["status"] == "done"))


def lineage(t):
    return bool(t.get("reqs") or t.get("generated_from"))


def cites_changed(t, changed):
    return any(c.split("@")[0] in changed for c in t.get("reqs") or [])


def plan_tree(an, cid, hidden):
    """Section 9: carry over lineage tasks outside K, stale K and unfinished tasks on a changed line, and generate a task for
    every acceptance line of the new PRD that no carried-over task covers: one check-writer first, then one
    task per requirement, each depending on the check-writer and on the tasks of the requirements it needs."""
    import prd

    new, change, k = an["new"], an["change"], an["k"]
    context = prd.load(an["project"])
    header, constraints, refs = (new.get(key) or context.get(key) or {}
                                 for key in ("header", "constraints", "references"))
    guidance = []
    if non_goals := header.get("non_goals"):
        guidance.append("Non-goals: " + "; ".join(non_goals))
    if constraints.get("limits"):
        guidance.append("Limits: " + "; ".join(prd._limit(x) for x in constraints["limits"]))
    if constraints.get("invariants"):
        guidance.append("Invariants: " + "; ".join(prd._limit(x) for x in constraints["invariants"]))
    if constraints.get("stack"):
        guidance.append(f"Stack: {constraints['stack']}")
    if constraints.get("offline_tests") is not None:
        guidance.append("Offline tests: " + ("required" if constraints["offline_tests"] else "not required"))
    if constraints.get("tags"):
        guidance.append("Tags: " + ", ".join(constraints["tags"]))
    if spine := refs.get("spine"):
        guidance.append(f"Spine: {spine['path']} sha256 {spine['sha256']}")
    lines = lines_of(new)
    cur = {aid: a["v"] for aid, (_, a) in lines.items()}
    # Only the tree's own tasks: one with no spec lineage is never carried (stamped) or staled, even when its
    # commit is entangled into K and rewound (T-1088); an unfinished one is superseded only when it cites a line
    # the change modified or removed.
    stale = [t for t in an["tasks"] if lineage(t)
             and (t["id"] in k or (t["status"] != "done" and cites_changed(t, an["changed"])))]
    carry = [t for t in an["tasks"] if lineage(t) and t not in stale]
    covered = {c.split("@")[0] for t in carry for c in t.get("reqs", [])} - set(hidden)
    added = {x["id"] for x in change.get("added", [])}
    touched = [aid for aid, (rid, _) in lines.items()
               if aid in added or rid in added or an["changed"].get(aid) == "modified"]
    # A change builds only what it adds or modifies, what it rewinds or leaves unfinished, and hidden reds. An
    # untouched line nobody covers was built without its check: reported, never rebuilt.
    redo = set(touched) | set(hidden) | {c.split("@")[0] for t in stale for c in t.get("reqs", [])}
    unchecked = sorted((a for a in lines if a not in covered and a not in redo), key=sort_key)
    gone = sorted((aid for aid, why in an["changed"].items() if why == "removed"), key=sort_key)
    pin = lambda aid: f"{aid}@{cur[aid]}"
    req_of = {aid: rid for aid, (rid, _) in lines_of(an["spec"]).items()}
    by_id = {t["id"]: t for t in an["tasks"]}
    no_files = PROTECTED + tuple(an["cfg"].get("migrations", []))  # migrations are kept, never rewound

    def rewound_files(rid):
        """The files the rewind reverted for this requirement (its commits' Req: trailers or tasks' reqs)."""
        files = set()
        for c in an["revert"]:
            cites = c["req"] + [r for u in units(c) for r in by_id.get(u, {}).get("reqs", [])]
            if rid in {req_of.get(x.split("@")[0]) for x in cites}:
                files |= {f for f in c["files"] if not under(f, no_files)}
        return sorted(files)
    ver, head = f"v{new['version']}", (f"Generated from spec v{new['version']} by `hub spec apply {cid}`. Do not "
                                        f"edit this task: change the spec. Work on branch change/{cid}.\n\n"
                                        + ("\n".join(guidance) + "\n\n" if guidance else ""))
    out = []
    if touched or gone:
        detail = head + ("Check-writer: whoever owns this task never builds a requirement it writes checks for. "
                         "Write one acceptance test per line, protected paths:\n")
        detail += "".join(f"- {pin(a)}: {lines[a][1]['text']}  -> {lines[a][1]['test']}\n" for a in touched)
        detail += "".join(f"- delete the test of retired line {a}\n" for a in gone)
        ids = [pin(a) for a in touched] or gone
        title = f"{cid}: land acceptance checks for " + ", ".join(ids)
        if len(title) > 250:  # GitHub refuses an issue title over 256 characters
            title = f"{cid}: land acceptance checks for {len(ids)} lines, {ids[0]} to {ids[-1]}"
        out.append({"key": "checks", "title": title, "owner": hb.LEAD_AGENT, "reqs": list(map(pin, touched)),
                    "detail": detail + "\nDone when each new check lands, is collected and runs, and fails only "
                    "for the missing behaviour (an expected red: the build tasks wait on this one, so a check of "
                    "absent behaviour cannot pass first, shown by running it independently), the repo's lint is "
                    "clean on it, and `hub spec check` passes its schema and lock parts. The full `make check` "
                    "runs later, at the green gate. The build tasks keep the green-required gate.",
                    "deps": []})
    def rank_key(r):
        rank = r.get("rank")
        return (type(rank) is not int, rank if type(rank) is int else 0)

    for r in sorted(new["requirements"], key=rank_key):
        mine = [a["id"] for a in r.get("acceptance", []) if a["id"] not in covered and a["id"] in redo]
        if not mine:
            continue
        detail = head + f"{r['id']} {r['title']}\n"
        if r.get("why"):
            detail += f"Why: {r['why']}\n"
        if r.get("touches"):
            detail += "Touches: " + ", ".join(r["touches"]) + "\n"
        detail += "Every check below must turn green, and the full suite stay green:\n"
        detail += "".join(f"- {pin(a)}: {lines[a][1]['text']}  (check: {lines[a][1]['test']})"
                          + (f"  [its code is kept; this check went red when {cid} rewound code it depends on]"
                             if a in hidden else "") + "\n" for a in mine)
        reverted = rewound_files(r["id"])
        files = sorted(set(reverted + r.get("touches", [])))
        if reverted:
            detail += "\nThe rewind reverted this requirement's code in these files:\n"
        if files:  # the builder's area (gh_sync.files_line), so it need not ask
            detail += f"Files: {', '.join(files)}\n"
            detail += "File conflict rule: edit only these files; overlapping touches wait on the earlier task.\n"
        out.append({"key": r["id"], "title": f"{r['id']} {r['title']}: {', '.join(map(pin, mine))}",
                    "owner": None, "reqs": list(map(pin, mine)), "detail": detail, "files": files,
                    "deps": (["checks"] if out and out[0]["key"] == "checks" else []) + r.get("needs", [])})
    keys = {t["key"]: t for t in out}
    for t in out:
        t["deps"] = [d for d in t["deps"] if d in keys]

    def waits(a, b):
        """Does task a wait on task b, directly or transitively?"""
        seen, todo = set(), list(keys[a]["deps"])
        while todo:
            x = todo.pop()
            if x == b:
                return True
            if x not in seen:
                seen.add(x)
                todo += keys[x]["deps"]
        return False
    # Two builders must never own one file at once: a later task sharing files with an earlier one, with no
    # path between them, waits on it. Nearest earlier first, so a chain of three needs two edges, not three.
    overlaps, reqs = [], [t for t in out if t["key"] != "checks"]
    for j, b in enumerate(reqs):
        for a in reversed(reqs[:j]):
            both = sorted({f for f in a["files"] for g in b["files"] if touches_overlap(f, g)})
            if both and not waits(b["key"], a["key"]) and not waits(a["key"], b["key"]):
                b["deps"].append(a["key"])
                overlaps.append((a["key"], b["key"], both))
    # e.g. a commit pulled in only by the cascade, citing no current requirement: Zeus widens a task by hand
    unowned = sorted({f for c in an["revert"] for f in c["files"] if not under(f, no_files)}
                     - {f for t in reqs for f in t["files"]})
    return {"cur": cur, "carry": carry, "stale": stale, "new": out, "version": ver, "overlaps": overlaps,
            "unowned": unowned, "unchecked": unchecked}


# ---------------------------------------------------------------- the rewind and the check run

NET_TIMEOUT = 120  # seconds for any git call that talks to origin


def git(repo, *args, check=True, timeout=None):
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        r = subprocess.CompletedProcess(args, 124, "", f"timed out after {timeout}s")
    if check and r.returncode:
        die(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()}")
    return r.stdout if check else r


def keep_main(clone, path):
    """A conflicted shared file: main's side wins each conflicting hunk; the reverts land everywhere else."""
    stages = {ln.split()[2]: ln.split()[1] for ln in git(clone, "ls-files", "-u", "--", path).splitlines()}
    if not {"1", "2", "3"} <= set(stages):
        git(clone, "checkout", "--ours", "--", path) if "2" in stages else git(clone, "rm", "-q", "--", path)
    else:
        tmp = tempfile.mkdtemp()
        names = [os.path.join(tmp, s) for s in "213"]
        for s, name in zip("213", names):
            with open(name, "w") as f:
                f.write(git(clone, "cat-file", "-p", stages[s]))
        subprocess.run(["git", "merge-file", "--ours", *names], check=False)
        shutil.copyfile(names[0], os.path.join(clone, path))
        shutil.rmtree(tmp)
    git(clone, "add", "--", path)


def rewind(an, repo, cid, clone):
    """Cut change/<cid> from the base in a throwaway clone with one rewind commit. Returns the shared files kept."""
    git(repo, "clone", "-q", "--no-hardlinks", "--no-checkout", repo, clone)
    git(clone, "fetch", "-q", "origin", an["base_sha"])  # origin here is the product checkout, which has it
    git(clone, "checkout", "-q", "-b", f"change/{cid}", an["base_sha"])
    shared, kept = an["cfg"].get("shared", []), []
    for c in an["revert"]:
        r = git(clone, "revert", "--no-commit", *(["-m", "1"] if c["merge"] else []), c["sha"], check=False)
        if r.returncode:
            conflicted = git(clone, "diff", "--name-only", "--diff-filter=U").split()
            bad = [f for f in conflicted if not under(f, shared)] or ([] if conflicted else ["(unknown)"])
            if bad:
                die(f"reverting {c['sha'][:12]} conflicts in non-shared {', '.join(bad)}: the cascade missed a "
                    f"commit. Nothing was changed.\n{(r.stderr or r.stdout).strip()}")
            for f in conflicted:
                keep_main(clone, f)
            kept += conflicted
            git(clone, "revert", "--quit", check=False)
    # Migrations are never reverted: data already migrated cannot be un-migrated by git. A kept line's check
    # that a K commit added comes back too, or its absence would read as a hidden dependency.
    for f in an["migrations"] + an["restored"]:
        git(clone, "checkout", an["base_sha"], "--", f)
    if an["revert"]:
        units = sorted(an["k"])
        ident = []  # the product repo's own identity, which a fresh clone does not inherit
        for key in ("user.name", "user.email"):
            v = git(repo, "config", key, check=False).stdout.strip()
            ident += ["-c", f"{key}={v}"] if v else []
        git(clone, *ident, "commit", "-q", "--allow-empty", "-m", f"Rewind for {cid}: {', '.join(units)}")
    return sorted(set(kept))


def verdict(cfg, clone, test):
    """One acceptance check in clone with the repo's acceptance_cmd: "pass", "fail" (a timeout too) or
    "unverified": pytest's exit 5, no tests collected (e.g. every test live-only and deselected). Exit 5 means
    that only from a pytest runner; from any other command it is a failure like any non-zero exit."""
    argv = [x.replace("{test}", test) for x in shlex.split(cfg.get("acceptance_cmd", DEFAULT_CHECK))]
    env = {k: v for k, v in os.environ.items() if k not in ("HUB_DIR", "HUB_AGENT")}  # as board.run_verify
    try:
        code = subprocess.run(argv, cwd=clone, env=env, capture_output=True, stdin=subprocess.DEVNULL,
                              timeout=cfg.get("acceptance_timeout", 300)).returncode
    except subprocess.TimeoutExpired:
        return "fail"
    return "pass" if code == 0 else "unverified" if code == 5 and runs_pytest(argv) else "fail"


# Only these options are understood, with their arity; any other option means the launcher is not recognised.
UV_RUN_OPTS = {**dict.fromkeys(("--with", "--with-editable", "--with-requirements", "--python", "-p", "--project",
                                "--directory", "--extra", "--group", "--env-file", "--package", "--index",
                                "--default-index", "--cache-dir"), 1),
               **dict.fromkeys(("--no-project", "--offline", "--frozen", "--locked", "--isolated", "--no-sync",
                                "--exact", "--all-extras", "--no-dev", "--active", "--no-cache", "-q", "--quiet",
                                "-v", "--verbose"), 0)}
PYTHON_OPTS = {**dict.fromkeys(("-W", "-X"), 1),
               **dict.fromkeys(("-b", "-B", "-d", "-E", "-i", "-I", "-O", "-OO", "-P", "-q", "-s", "-S", "-u",
                                "-v", "-x", "-R"), 0)}


def runs_pytest(argv):
    """The command launched is pytest itself: `pytest`, `python -m pytest`, either behind `uv run [options]`.
    Only the launched executable or module counts, never an argument that merely names pytest, and an option
    this does not know makes the command unrecognised (not pytest) rather than guessed at."""
    i = 0
    if argv[:2] and os.path.basename(argv[0]) == "uv" and argv[1:2] == ["run"]:
        i = 2
        while i < len(argv) and argv[i].startswith("-"):
            if argv[i] == "--":
                i += 1
                break
            key, eq, _ = argv[i].partition("=")
            if UV_RUN_OPTS.get(key) is None or (eq and UV_RUN_OPTS[key] != 1):
                return False
            i += 1 if eq else 1 + UV_RUN_OPTS[key]
    if i >= len(argv):
        return False
    exe = os.path.basename(argv[i])
    if exe in ("pytest", "py.test"):
        return True
    if not re.fullmatch(r"python[\d.]*", exe):
        return False
    i += 1
    while i < len(argv) and argv[i] in PYTHON_OPTS:  # interpreter options before -m; `--` or a script ends them
        i += 1 + PYTHON_OPTS[argv[i]]
    return argv[i:i + 2] in (["-m", "pytest"], ["-m", "py.test"])


def run_checks(an, clone):
    """Every check of a carried-over line on the rewound tree, TRIES times. Red every time = hidden dependency;
    a check that ran no tests is unverified: neither green nor a hidden dependency."""
    lines = lines_of(an["new"])
    hidden, flaky, unverified = [], [], []
    for aid in an["kept"]:
        vs = [verdict(an["cfg"], clone, lines[aid][1]["test"]) for _ in range(TRIES)]
        reds = vs.count("fail")
        (hidden if reds == TRIES else flaky if reds else unverified if "unverified" in vs else []).append(aid)
    return an["kept"], hidden, flaky, unverified


def sort_key(aid):
    return [int(n) for n in re.findall(r"\d+", aid)]


# ---------------------------------------------------------------- report, apply, CLI

def cross_cutting(an):
    done = [t for t in an["tasks"] if t["status"] == "done"]
    return 2 * sum(t["id"] in an["k"] for t in done) > len(done)


def report(an, cid, checks=None, shared_kept=(), plan=None):
    spec, ch, new, k = an["spec"], an["change"], an["new"], an["k"]
    old, now_ = lines_of(spec), lines_of(new)
    ok, why = approval(an["project"], cid)
    out = [f"{cid}: spec v{spec['version']} -> v{new['version']}",
           f"sha256 {file_sha(os.path.join(spec_dir(an['project']), 'changes', f'{cid}.json'))} ({'approved, ' if ok else 'NOT approved: '}{why})"]
    for aid in sorted(set(old) | set(now_), key=sort_key):
        if aid not in now_:
            out.append(f"  removed  {aid}@{old[aid][1]['v']}")
        elif aid not in old:
            out.append(f"  added    {aid}@1  {now_[aid][1]['text']}")
        elif now_[aid][1]["v"] != old[aid][1]["v"]:
            out.append(f"  modified {aid}@{old[aid][1]['v']} -> @{now_[aid][1]['v']}  {now_[aid][1]['text']}")
    prose = [x["id"] for x in ch.get("modified", []) if x["id"].startswith("R-")]
    if prose:
        out.append(f"  prose    {', '.join(prose)} (rebuilds nothing)")
    if not an["changed"]:
        out.append("prose changed, no acceptance line changed or removed: nothing will be rewound")
    done = [t for t in an["tasks"] if t["status"] == "done"]
    out.append(f"radius: {sum(t['id'] in k for t in done)} of {len(done)} done tasks")
    out += [f"  {u}  {k[u]}" for u in sorted(k)]
    if cross_cutting(an):
        out.append("CROSS-CUTTING: the radius is over half the done tasks; rewind costs about as much as a restart")
    out.append(f"base: {an['base']} {an['base_sha'][:12]}")
    out.append("rewind, newest first: " + (", ".join(f"{'+'.join(units(c))} {c['sha'][:12]}" for c in an["revert"])
                                           or "-"))
    mixed = sorted({c.split("@")[0] for u in k for t in an["tasks"] if t["id"] == u and k[u].startswith("cites")
                    for c in t.get("reqs", []) if c.split("@")[0] not in an["changed"]}, key=sort_key)
    out.append("must-pass, same commit as a changed line: " + (", ".join(mixed) or "-"))
    out.append("shared, not cascaded: " + (", ".join(an["cfg"].get("shared", [])) or "-"))
    out.append("migrations kept: " + (", ".join(an["migrations"]) or "-"))
    out.append("kept checks restored from the base: " + (", ".join(an["restored"]) or "-"))
    hit = {old.get(a, now_.get(a, ("",)))[0] for a in an["changed"]}
    hit |= {r["id"] for r in new["requirements"] for a in r.get("acceptance", []) if a["id"] not in old}
    suspect, grew = set(), True
    while grew:  # reverse needs, to a fixpoint
        more = {r["id"] for r in new["requirements"] if set(r.get("needs", [])) & (hit | suspect)} - suspect
        suspect |= more
        grew = bool(more)
    out.append("suspect, re-verify: " + (", ".join(sorted(suspect, key=sort_key)) or "-"))
    if checks:
        ran, hidden, flaky, unverified = checks
        out.append(f"checks on the rewound tree, {TRIES} runs each: {len(ran) - len(hidden) - len(flaky) - len(unverified)}"
                   f" of {len(ran)} kept checks green")
        out += [f"  unverified: {a} ran no tests (pytest exit 5); not green, not a hidden dependency" for a in unverified]
        out += [f"  hidden dependency: {a} red after the rewind; joins the rebuild (depends on rewound behaviour)"
                for a in hidden]
        out += [f"  flaky, quarantined: {a}" for a in flaky]
    if shared_kept:
        out.append("shared, rebuild must reconcile: " + ", ".join(shared_kept))
    if plan:
        out.append(f"tree from spec {plan['version']}:")
        out.append("  carried over: " + (", ".join(t["id"] for t in plan["carry"]) or "-"))
        out.append("  stale: " + (", ".join(f"{t['id']} ({t['status']})" for t in plan["stale"]) or "-"))
        out += [f"  new [{t['key']}] {t['title']}" + (f"  deps {', '.join(t['deps'])}" if t["deps"] else "")
                for t in plan["new"]]
        out += [f"  files shared by {a} and {b} without a needs edge: {', '.join(fs)}; {b} now waits on {a}"
                for a, b, fs in plan["overlaps"]]
        if plan["unowned"]:
            out.append("  rewound files no task owns: " + ", ".join(plan["unowned"]))
        if plan.get("unchecked"):
            out.append("  no checks yet, not rebuilt (untouched by this change): " + ", ".join(plan["unchecked"]))
    return "\n".join(out)


def own_verify(an, reqs, project, collect=False):
    """A generated task's verify: its own acceptance checks (the repo's acceptance_cmd), then hub spec check
    on schema, lock and its own lines' test files (other lines' gaps are reported by apply, not gated here).
    The check-writer's (collect) only needs its checks collected: they wait on the build tasks to turn green."""
    lines = lines_of(an["new"])
    cmd = shlex.split(an["cfg"].get("collect_cmd", DEFAULT_COLLECT) if collect
                      else an["cfg"].get("acceptance_cmd", DEFAULT_CHECK))
    mine = [r.split("@")[0] for r in reqs if r.split("@")[0] in lines]
    own = [shlex.join([x.replace("{test}", lines[a][1]["test"]) for x in cmd]) for a in mine]
    return " && ".join(own + [f"hub spec check --project {project} --repo . --lines {shlex.quote(','.join(mine))}"])


def write_tree(an, cid, plan, project, who):
    snap = {t["id"]: t["status"] for t in an["tasks"]}
    with hb.board(write=True) as (data, events):
        mine = [t for t in data["tasks"] if tree_task(t, project)]
        if {t["id"]: t["status"] for t in mine} != snap:
            die("the board changed while apply ran; nothing was written. Run it again.")
        by = {t["id"]: t for t in mine}
        for t in plan["carry"]:
            x = by[t["id"]]
            x["reqs"] = [f"{c.split('@')[0]}@{plan['cur'][c.split('@')[0]]}" if c.split("@")[0] in plan["cur"]
                         else c for c in x.get("reqs", [])]
            x["generated_from"], x["updated"] = plan["version"], hb.now()
            hb.log(events, who, "carried", x["id"], change=cid, generated_from=plan["version"])
        for t in plan["stale"]:
            x = by[t["id"]]
            x["tags"] = (x.get("tags") or []) + ["stale"]
            x["notes"].append({"at": hb.now(), "by": who, "text": f"superseded by {cid}"})
            x["updated"] = hb.now()
            hb.log(events, who, "stale", x["id"], change=cid)
        ids = {}
        for n in plan["new"]:
            ids[n["key"]] = f"T-{data['next_id']:03d}"
            data["next_id"] += 1
        for n in plan["new"]:
            tid = ids[n["key"]]
            data["tasks"].append({"id": tid, "title": n["title"], "detail": n["detail"], "status": "open",
                                  "owner": n["owner"], "deps": [ids[d] for d in n["deps"]], "created_by": who,
                                  "created": hb.now(), "updated": hb.now(), "notes": [], "project": project,
                                  "reqs": n["reqs"], "generated_from": plan["version"],
                                  # hub done runs it in the task's worktree. Only this task's own lines: a sibling's
                                  # unbuilt check must not block it; the change gate runs make check and every line.
                                  "verify": own_verify(an, n["reqs"], project, collect=n["key"] == "checks"),
                                  # a factory repo's builders claim it directly; roster pool rules would refuse them
                                  **({"kind": "factory"} if repo_cfg(project) else {})})
            hb.log(events, who, "created", tid, title=n["title"], project=project, change=cid)
    notices = [(hb.actor(t), f"{t['id']} is superseded by {cid}: stop and abandon its branch. "
                             f"The regenerated tree: hub list --project {project}")
               for t in plan["stale"] if t["status"] in ("claimed", "blocked") and hb.actor(t)]
    return ids, notices


def commit_spec(project, cid, version, receipt):
    """Commit the applied spec in the hub repo itself, exact paths only (never `git add .`). None when the hub
    dir is not the top of a git repo (tests); else the failed git call, or False on success."""
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}  # a hook's leaked GIT_DIR

    def g(*args):
        try:
            return subprocess.run(["git", "-C", hb.HUB_DIR, *args], env=env, capture_output=True, text=True,
                                  timeout=60)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(args, 124, "", "timed out after 60s")
    top = g("rev-parse", "--show-toplevel")
    if top.returncode or os.path.realpath(top.stdout.strip()) != os.path.realpath(hb.HUB_DIR):
        return None
    d = spec_dir(project)
    paths = [spec_path(project), os.path.join(d, "spec.lock"),
             os.path.join(d, "changes", f"{cid}.json"), os.path.join(hb.HUB_DIR, "projects", project, receipt)]
    r = g("add", "--", *paths)
    if not r.returncode and g("diff", "--cached", "--quiet", "HEAD", "--", *paths).returncode == 0:
        return False  # already committed with these bytes (a re-run after a hand commit): nothing to do
    if not r.returncode:  # `commit -- paths` takes only these, whatever else is staged
        r = g("commit", "-q", "-m", f"spec {project} v{version}: {cid} applied", "--", *paths)
    return r if r.returncode else False


def cmd_init(a):
    project = hb.valid_project(a.project_name)
    d = spec_dir(project)
    existing = spec_path(project)
    promoting_draft = (os.path.exists(existing) and os.path.basename(existing) == "prd.json"
                       and a.from_file and os.path.realpath(a.from_file) == os.path.realpath(existing)
                       and not os.path.exists(os.path.join(d, "requirements.json")))
    if os.path.exists(os.path.join(d, "spec.lock")) or (os.path.exists(existing) and not promoting_draft):
        die(f"{project} already has a spec; change it with an approved C-NNN")
    spec = {"requirements": []}
    if a.from_file:
        try:
            with open(a.from_file) as f:
                spec = json.load(f)
        except (OSError, ValueError) as e:
            die(f"cannot read {a.from_file}: {e}")
    if not isinstance(spec, dict):
        die("the spec must be a JSON object")
    if promoting_draft:
        import prd
        import prd_grill
        if spec.get("version") != 1 or not prd_grill.ready(spec, prd.bases(project)):
            die(f"finish `hub prd grill {project}` on the initial v1 draft before initializing it")
    spec = {**spec, "version": 1}
    errs = schema_errors(spec)
    if errs:
        die("invalid spec: " + "; ".join(errs))
    name = "prd.json" if promoting_draft or (a.from_file and os.path.basename(a.from_file) == "prd.json") else "requirements.json"
    path = os.path.join(d, name)
    os.makedirs(os.path.join(d, "changes"), exist_ok=True)
    hb._write_json_atomic(path, spec)
    hb._write_json_atomic(os.path.join(d, "spec.lock"), {"version": 1, "sha256": file_sha(path)})
    print(f"spec for {project}: v1, {len(lines_of(spec))} acceptance lines, locked")


def cmd_bootstrap_sha(a):
    """One-time: record the merge commit of tasks merged before live_merge recorded merge_sha (squash merges carry
    no Task: trailer, so without it their commits belong to no task and a rewind reverts nothing)."""
    project, repo = where(a)
    base, base_sha = base_ref(repo, repo_cfg(project))  # fetch origin, so a sha merged there resolves
    line = {c["sha"] for c in history(repo, base_sha, [])}  # all history() ever walks
    pairs = []
    for x in a.pairs:
        tid, _, sha = x.partition("=")
        if not sha:
            die(f"want T-n=<sha>, got {x!r}")
        r = git(repo, "rev-parse", "--verify", "-q", f"{sha}^{{commit}}", check=False)
        if r.returncode:
            die(f"{sha} is not a commit in {repo}")
        if r.stdout.strip() not in line:  # recorded, it would never match: the silent no-op this tool prevents
            die(f"{sha} is not on {base}'s first-parent line")
        pairs.append((hb.norm_id(tid), r.stdout.strip()))
    who = hb.whoami(a.as_agent)
    with hb.board(write=True) as (data, events):
        by = {t["id"]: t for t in data["tasks"]}
        for tid, sha in pairs:
            t = by.get(tid)
            if not t or t.get("project") != project:
                die(f"no task {tid} in {project}; nothing was written")
            if merge_shas(t) and merge_shas(t) != [sha]:
                die(f"{tid} already has merge_sha {t['merge_sha']}; nothing was written")
        for tid, sha in pairs:
            by[tid]["merge_sha"], by[tid]["updated"] = sha, hb.now()
            hb.log(events, who, "merge_sha", tid, sha=sha, via="hub spec bootstrap-sha")
    for tid, sha in pairs:
        print(f"{tid} merge_sha {sha}")


def where(a):
    project = hb.which_project(a.project)
    if not project:
        die("which project? pass --project or set $HUB_PROJECT")
    return project, os.path.abspath(os.path.expanduser(a.repo or os.path.join(CODE_DIR, project)))


def heldout_warnings(project):
    """Never errors (check is in every task's verify): stale entries the gate skips, and files without a canary."""
    warns = [f"held-out {s}: skipped by the gate" for s in gh_sync.heldout_stale(project)]
    root = gh_sync.heldout_dir(project)
    for aid, e in sorted(gh_sync.heldout_index(project).items()):
        for t in e.get("tests") or []:
            try:
                with open(os.path.join(root, t)) as f:
                    marked = bool(gh_sync.CANARY.search(f.read()))
            except OSError:
                warns.append(f"held-out {aid}: {t} missing")
                continue
            if not marked:
                warns.append(f"held-out {aid}: {t} has no HELDOUT_CANARY line")
    return warns


def heldout_reds(checks, clone, base, cfg):
    """Each held-out check (gh_sync.heldout_checks) run in clone, re-run while red up to TRIES times. Red every
    time is a drift that names the line alone; the output goes to heldout/gate.log only (design section 3)."""
    env = {k: v for k, v in os.environ.items() if k not in ("HUB_DIR", "HUB_AGENT")}
    reds = []
    for label, argv in checks:
        for _ in range(TRIES):
            try:
                if not subprocess.run(argv, cwd=clone, env=env, stdin=subprocess.DEVNULL,
                                      timeout=cfg.get("acceptance_timeout", 300)).returncode:
                    break
            except subprocess.TimeoutExpired:
                pass
        else:
            reds.append(f"{label} red on {base}")
    return reds


def cmd_check(a):
    project, repo = where(a)
    only = None if a.lines is None else {x for x in a.lines.split(",") if x}
    errs = check_errors(project, repo, only)
    for e in errs:
        print(f"  {e}")
    if errs:
        die(f"check failed for {project}: {len(errs)} problem(s)")
    for w in heldout_warnings(project):
        print(f"  warning: {w}")
    print(f"spec ok: {project} v{load_spec(project)['version']}, {len(lines_of(load_spec(project)))} acceptance lines")


def lint_findings(project, cid):
    spec = load_spec(project)
    change = load_change(project, cid)
    if change.get("id") != cid or change.get("base_version") != spec["version"]:
        die(f"{cid} does not match the current spec v{spec['version']}")
    pending = []
    for path in sorted(glob.glob(os.path.join(spec_dir(project), "changes", "C-*.json"))):
        if os.path.basename(path) == f"{cid}.json":
            continue
        with open(path) as f:
            other = json.load(f)
        if other.get("base_version") == spec["version"]:
            pending.append(other)
    return spec_lint.lint(spec, change, pending, gh_sync.heldout_index(project))


def print_lint(project, cid):
    findings = lint_findings(project, cid)
    print("lint:")
    for level, rule, message in findings:
        print(f"  {level} {rule}: {message}")
    if not findings:
        print("  clean")
    return any(level == "error" for level, _, _ in findings)


def cmd_lint(a):
    project, _ = where(a)
    if print_lint(project, a.change):
        die(f"{a.change} has lint errors")


def cmd_impact(a):
    project, repo = where(a)
    print_lint(project, a.change)
    print(report(analyse(project, repo, a.change), a.change))


def cmd_rewind(a):
    if not a.dry_run:
        die("a real rewind happens only inside `hub spec apply`; use --dry-run here")
    run(a, apply=False)


def cmd_apply(a):
    run(a, apply=True)


def next_cid(project):
    nums = []
    for p in glob.glob(os.path.join(spec_dir(project), "changes", "C-*.json")):
        base = os.path.splitext(os.path.basename(p))[0]
        if m := re.match(r"^C-(\d+)$", base):
            nums.append(int(m.group(1)))
    return f"C-{max(nums, default=0) + 1:03d}"


def cmd_correct(a):
    project, repo = where(a)
    spec = load_spec(project)
    who = hb.whoami(a.as_agent)
    file_path = os.path.abspath(os.path.expanduser(a.file))
    try:
        with open(file_path) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        die(f"cannot read {file_path}: {e}")
    if not isinstance(data, dict):
        die("correction input must be a JSON object")
    if data.get("added"):
        die("corrections cannot add requirements or acceptance lines; use propose")
    if data.get("removed"):
        die("corrections cannot remove requirements or acceptance lines; use propose")
    if data.get("set"):
        die("corrections cannot modify header/constraints/references; use propose")
    modified = data.get("modified")
    if not modified:
        die("corrections must modify at least one existing acceptance line")
    lines = lines_of(spec)
    allowed_keys = {"id", "text", "test"}
    processed_modified = []
    for item in modified:
        if not isinstance(item, dict) or not item.get("id"):
            die("each modified entry must be an object with an id")
        aid = item["id"]
        if aid not in lines:
            die(f"unknown or non-acceptance line {aid!r} (corrections cannot modify requirements or unknown ids)")
        extra = set(item.keys()) - allowed_keys
        if extra:
            die(f"correction {aid} has disallowed fields: {', '.join(sorted(extra))}; only text or test may be modified")
        if "text" not in item and "test" not in item:
            die(f"correction {aid} must modify text or test")
        orig = lines[aid][1]
        entry = {"id": aid}
        if "text" in item:
            if not isinstance(item["text"], str):
                die(f"correction {aid} text must be a string")
            orig_text = orig.get("text", "")
            new_text = item["text"]
            sm = difflib.SequenceMatcher(None, orig_text, new_text)
            ratio = sm.ratio()
            diff_chars = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")
            if ratio < 0.8 or diff_chars > 80:
                die(f"correction {aid} text change is too large (similarity {ratio:.2f}, changed chars {diff_chars}; the bound is >= 0.80 and <= 80); use propose")
            entry["text"] = new_text
        if "test" in item:
            if not isinstance(item["test"], str):
                die(f"correction {aid} test must be a string")
            orig_test = orig.get("test", "")
            new_test = item["test"]
            sm = difflib.SequenceMatcher(None, orig_test, new_test)
            ratio = sm.ratio()
            diff_chars = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")
            if ratio < 0.8 or diff_chars > 80:
                die(f"correction {aid} test path change is too large (similarity {ratio:.2f}, changed chars {diff_chars}; the bound is >= 0.80 and <= 80); use propose")
            entry["test"] = new_test
        entry["previous"] = {k: orig[k] for k in ("text", "test") if k in orig and k in entry}
        processed_modified.append(entry)

    cid = next_cid(project)
    out_path = os.path.join(spec_dir(project), "changes", f"{cid}.json")
    if os.path.exists(out_path):
        die(f"change file {out_path} already exists")
    spec_sha = file_sha(spec_path(project))
    change = {
        "id": cid,
        "kind": "correction",
        "author": who,
        "by": who,
        "base_version": spec["version"],
        "based_on_version": spec["version"],
        "based_on_sha256": spec_sha,
        "modified": processed_modified,
    }
    if "note" in data:
        change["note"] = data["note"]
    elif "reason" in data:
        change["reason"] = data["reason"]

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    created = False
    try:
        hb._write_json_atomic(out_path, change)
        created = True
        errs = print_lint(project, cid)
        if errs:
            if created:
                try:
                    os.unlink(out_path)
                except OSError:
                    pass
            die(f"{cid} has lint errors; cannot create correction")
        an = analyse(project, repo, cid)
        if an.get("radius", 0) != 0 or an.get("revert"):
            if created:
                try:
                    os.unlink(out_path)
                except OSError:
                    pass
            die(f"{cid} has non-zero blast radius ({an.get('radius')}); corrections must have 0 blast radius")
    except BaseException:
        if created:
            try:
                os.unlink(out_path)
            except OSError:
                pass
        raise
    print(f"wrote {os.path.relpath(out_path, hb.HUB_DIR)} (kind: correction)")
    print(report(an, cid))


def cmd_propose(a):
    project, repo = where(a)
    spec = load_spec(project)
    who = hb.whoami(a.as_agent)
    file_path = os.path.abspath(os.path.expanduser(a.file))
    try:
        with open(file_path) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        die(f"cannot read {file_path}: {e}")
    if not isinstance(data, dict):
        die("proposal input must be a JSON object")

    cid = next_cid(project)
    out_path = os.path.join(spec_dir(project), "changes", f"{cid}.json")
    if os.path.exists(out_path):
        die(f"change file {out_path} already exists")
    spec_sha = file_sha(spec_path(project))
    change = {
        "id": cid,
        "kind": "proposal",
        "author": who,
        "by": who,
        "base_version": spec["version"],
        "based_on_version": spec["version"],
        "based_on_sha256": spec_sha,
    }
    for k in ("added", "modified", "removed", "set", "reason", "why", "note"):
        if k in data:
            change[k] = data[k]

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    hb._write_json_atomic(out_path, change)

    print_lint(project, cid)
    an = analyse(project, repo, cid)
    print(report(an, cid))

    page_path = os.path.join(spec_dir(project), f"review-{cid}.html")
    html_content = f"""<!doctype html>
<html lang="en" data-approves="changes/{cid}.json">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Approve {cid}</title>
</head>
<body>
<h1>Approve {cid}</h1>
<p>{project}, spec v{spec['version']} &rarr; v{an['new']['version']}. Approving records a receipt for changes/{cid}.json.</p>
<textarea id="note" placeholder="Optional note; required if you request changes"></textarea><br>
<button id="approve">Approve</button> <button id="changes">Request changes</button> <span id="status"></span>
</body>
</html>
"""
    with open(page_path, "w") as f:
        f.write(html_content)
    print(f"wrote review page {os.path.relpath(page_path, hb.HUB_DIR)}")


def cmd_revert(a):
    project, repo = where(a)
    spec = load_spec(project)
    who = hb.whoami(a.as_agent)
    orig_cid = a.change
    orig_change = load_change(project, orig_cid)
    lines = lines_of(spec)
    reverse_modified = []
    for item in orig_change.get("modified", []):
        aid = item["id"]
        if aid not in lines:
            continue
        prev = item.get("previous")
        if not prev:
            rel_spec = os.path.relpath(spec_path(project), hb.HUB_DIR)
            r = git(hb.HUB_DIR, "log", "-n", "20", "--format=%H %s", "--", spec_path(project), check=False)
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    if f"{orig_cid} applied" in line:
                        commit_hash = line.split()[0]
                        parent_show = git(hb.HUB_DIR, "show", f"{commit_hash}~1:{rel_spec}", check=False)
                        if parent_show.returncode == 0:
                            try:
                                prev_doc = json.loads(parent_show.stdout)
                                prev_lines = lines_of(prev_doc)
                                if aid in prev_lines:
                                    prev = {k: prev_lines[aid][1][k] for k in ("text", "test", "fixtures") if k in prev_lines[aid][1]}
                            except (ValueError, KeyError):
                                pass
                        break
        if not prev:
            die(f"cannot determine previous text for {aid} to revert {orig_cid}")
        rev_entry = {"id": aid}
        for k in ("text", "test", "fixtures"):
            if k in prev:
                rev_entry[k] = prev[k]
        reverse_modified.append(rev_entry)

    if not reverse_modified:
        die(f"no modified lines found in {orig_cid} to revert")

    cid = next_cid(project)
    out_path = os.path.join(spec_dir(project), "changes", f"{cid}.json")
    if os.path.exists(out_path):
        die(f"change file {out_path} already exists")
    spec_sha = file_sha(spec_path(project))
    change = {
        "id": cid,
        "kind": "correction",
        "author": who,
        "by": who,
        "base_version": spec["version"],
        "based_on_version": spec["version"],
        "based_on_sha256": spec_sha,
        "note": f"Revert {orig_cid}",
        "modified": reverse_modified,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    hb._write_json_atomic(out_path, change)

    print_lint(project, cid)
    an = analyse(project, repo, cid)
    print(f"wrote {os.path.relpath(out_path, hb.HUB_DIR)} (kind: correction, reverts {orig_cid})")
    print(report(an, cid))


def cmd_approve(a):
    project, repo = where(a)
    cid = a.change
    who = hb.whoami(a.as_agent)
    if autonomy.lacks(who, "review"):
        die(f"agent {who} lacks review capability; cannot approve spec changes")
    path = os.path.realpath(os.path.join(spec_dir(project), "changes", f"{cid}.json"))
    if not os.path.isfile(path):
        die(f"no change {cid} for {project}")
    change = load_change(project, cid)
    author = change.get("author") or change.get("by")
    # Only a correction (an agent's own fix) needs another approver; a proposal carries the human's approved intent.
    if change.get("kind") == "correction" and author and hb.canon(who) == hb.canon(author):
        die(f"author {who} cannot approve their own correction {cid}")
    who_phase, _ = autonomy.phase_of(who)
    if change.get("kind") == "correction":
        if hb.canon(who) not in ("hermes", "zeus") and who_phase not in ("reviewer", "lead"):
            die(f"correction {cid} must be approved by Hermes or Zeus (phase reviewer or lead); {who} is {who_phase}")
    else:
        if hb.canon(who) != "zeus" and who_phase != "lead":
            die(f"regular change {cid} must be approved by lead (Zeus); {who} is {who_phase}")
    sha = file_sha(path)
    receipt_dir = os.path.join(spec_dir(project), "reviews")
    os.makedirs(receipt_dir, exist_ok=True)
    receipt_path = os.path.join(receipt_dir, f"{cid}-review.json")
    receipt_data = {
        "name": f"{cid}-review",
        "decision": "approve",
        "reviewer": who,
        "note": a.why or f"LGTM {sha[:12]} by {who}",
        "at": hb.now(),
        "approved_path": path,
        "approved_sha256": sha,
    }
    hb._write_json_atomic(receipt_path, receipt_data)
    print(f"approved {cid}: receipt {os.path.relpath(receipt_path, hb.HUB_DIR)}")


def run(a, apply):
    project, repo = where(a)
    cid = a.change
    if not apply:
        print_lint(project, cid)
    an = analyse(project, repo, cid)
    for other in unlanded(repo, an["base_sha"], cid):  # its rewind is not on the line yet: radii would overlap
        if apply:
            die(f"{other} has not landed: merge or abandon it first")
        print(f"warning: {other} has not landed: merge or abandon it first")
    if apply:
        who = hb.whoami(a.as_agent)
        who_phase, _ = autonomy.phase_of(who)
        if who_phase == "off":
            die(f"agent {who} is in phase off; cannot apply spec changes")

        app = approval(project, cid)
        if not app.ok:
            die(f"{cid} is not approved: {app.why}")
        receipt = app.why
        reviewer = app.reviewer

        change = an["change"]
        author = change.get("author") or change.get("by")
        if change.get("kind") == "correction" and reviewer and author and hb.canon(reviewer) == hb.canon(author):
            die(f"correction {cid} was approved by its author {reviewer}; self-approval is forbidden")

        is_correction = change.get("kind") == "correction"
        if is_correction:
            expected_hash = change.get("based_on_sha256")
            if not expected_hash:
                die(f"correction {cid} missing based_on_sha256")
            actual_hash = file_sha(spec_path(project))
            if expected_hash != actual_hash:
                die(f"correction {cid} was written against spec sha256 {expected_hash[:12]}, but current spec is {actual_hash[:12]}: rewrite it")
            if reviewer:
                rev_phase, _ = autonomy.phase_of(reviewer)
                if hb.canon(reviewer) not in ("hermes", "zeus") and rev_phase not in ("reviewer", "lead"):
                    die(f"correction {cid} approver must be Hermes or Zeus (phase reviewer or lead); receipt is from {reviewer}")
        else:
            # M7: the receipt is the gate; any agent (not off) may apply with a valid lead receipt.
            if reviewer is not None and reviewer.lower() != "zeus" and autonomy.phase_of(reviewer)[0] != "lead":
                die(f"{cid} is a regular change: regular change requires lead approval receipt; receipt is from {reviewer}")

        lock = [e for e in check_errors(project, repo) if e.startswith(("spec.lock", "both prd.json"))]
        if lock:
            die("; ".join(lock))
        if print_lint(project, cid):
            die(f"{cid} has lint errors")
        if git(repo, "rev-parse", "--verify", "-q", f"refs/heads/change/{cid}", check=False).returncode == 0:
            die(f"branch change/{cid} already exists in {repo}")
        if git(repo, "ls-remote", "--exit-code", "--heads", "origin", f"change/{cid}",
               check=False, timeout=NET_TIMEOUT).returncode != 2:  # 2: reached origin, no such branch
            die(f"origin unreachable, or change/{cid} already exists on it")
        if cross_cutting(an) and not a.force:
            die("cross-cutting: the radius is over half the done tasks. Restart, amend, or --force the rewind.\n"
                + report(an, cid))
    tmp = tempfile.mkdtemp(prefix="hub-spec-")
    try:
        clone = os.path.join(tmp, "repo")
        shared_kept = rewind(an, repo, cid, clone)
        checks = run_checks(an, clone)
        plan = plan_tree(an, cid, checks[1])
        print(report(an, cid, checks, shared_kept, plan))
        print(f"marks {len(plan['stale'])} task(s) stale: " + (", ".join(t["id"] for t in plan["stale"]) or "-"))
        reach = {t["id"] for t in an["tasks"] if t["id"] in an["k"] or cites_changed(t, an["changed"])}
        if apply and len(plan["stale"]) > len(reach) and not a.yes:  # a guard against a sweep like T-1088's
            die(f"{len(plan['stale'])} tasks to mark stale, but the change's blast radius reaches {len(reach)}; "
                "nothing written. Check the list, then rerun with --yes.")
        if not apply:
            print("dry run: nothing written")
            return
        git(repo, "fetch", "-q", clone, f"change/{cid}:change/{cid}")
        # what the rewind reverted: once it lands, history() never walks these again (they would revert twice)
        rewound = {**an["rewound"], cid: [c["sha"] for c in an["revert"]]} if an["revert"] else an["rewound"]
        pushed = False
        try:  # builders open PRs against origin's change branch, and hub live reads origin
            pushed = True  # before the attempt: a push that times out may still have landed on origin
            git(repo, "push", "-q", "origin", f"change/{cid}", timeout=NET_TIMEOUT)
            ids, notices = write_tree(an, cid, plan, project, hb.whoami(a.as_agent))
        except BaseException:  # the board is untouched (its write lock commits nothing on an error): undo the branch
            git(repo, "branch", "-q", "-D", f"change/{cid}", check=False)
            r = git(repo, "push", "-q", "origin", "--delete", f"change/{cid}", check=False, timeout=NET_TIMEOUT) \
                if pushed else None
            if r is not None and r.returncode:
                print(f"hub spec: could not delete change/{cid} on origin; delete it by hand: "
                      f"{(r.stderr or r.stdout).strip()}", file=sys.stderr)
            raise
        d = spec_dir(project)
        path = spec_path(project)
        hb._write_json_atomic(path, an["new"])
        hb._write_json_atomic(os.path.join(d, "spec.lock"), {
            "version": an["new"]["version"], "change": cid, "sha256": file_sha(path),
            "rewound": rewound})
        print(f"applied {cid}: spec v{an['new']['version']}, branch change/{cid}, new tasks "
              + (", ".join(ids[n["key"]] for n in plan["new"]) or "-"))
        bad = commit_spec(project, cid, an["new"]["version"], receipt.removeprefix("receipt "))
        if bad:  # reported, never undone: the board and the branch are already written
            print(f"hub spec: {cid} is applied, but committing its spec in the hub failed; commit it by hand: "
                  f"{(bad.stderr or bad.stdout).strip()}", file=sys.stderr)
        if is_correction:
            try:
                hb.deliver(LEAD_AGENT, f"Correction {cid} applied on {project}: spec v{an['new']['version']}")
            except (SystemExit, OSError) as e:
                print(f"hub spec: could not notify lead: {e}", file=sys.stderr)
        failed = []
        for agent, text in notices:  # after everything is written: a failed notice must not undo the apply
            try:
                hb.deliver(agent, text)
            except (SystemExit, OSError) as e:
                failed.append(f"{agent}: {e}")
        if failed:
            die(f"{cid} is applied, but these superseded notices failed; tell them by hand: " + "; ".join(failed))
        if bad:
            sys.exit(1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def drifts(project, repo):
    """(base, every way the spec and origin's live line disagree, flaky lines, unverified lines): `check` on a
    fresh clone of the live line, then each acceptance check whose test exists, re-run while red up to TRIES times.
    Red every time is drift, mixed is flaky (as run_checks), no tests run is unverified (not counted as run).
    Every check red is the environment, not the code: one drift for it."""
    cfg = repo_cfg(project)
    base, base_sha = base_ref(repo, cfg)
    tmp = tempfile.mkdtemp(prefix="hub-spec-converge-")
    try:
        clone = os.path.join(tmp, "repo")
        git(repo, "clone", "-q", "--no-hardlinks", "--no-checkout", repo, clone)
        git(clone, "fetch", "-q", "origin", base_sha)
        git(clone, "checkout", "-q", "--detach", base_sha)
        if os.path.isfile(os.path.join(repo, ".env")):  # as live_merge's gate, so a check sees what the gate sees
            shutil.copy2(os.path.join(repo, ".env"), os.path.join(clone, ".env"))
        errs, spec, ran, reds, flaky, unverified = check_errors(project, clone), load_spec(project), 0, [], [], []
        if not schema_errors(spec):
            for aid, (_, a) in sorted(lines_of(spec).items(), key=lambda x: sort_key(x[0])):
                if not os.path.isfile(os.path.join(clone, a["test"])):
                    continue
                vs = [verdict(cfg, clone, a["test"])]
                while vs[-1] == "fail" and len(vs) < TRIES:
                    vs.append(verdict(cfg, clone, a["test"]))
                if vs[-1] == "unverified" and "fail" not in vs:
                    unverified.append(aid)
                    continue
                ran += 1
                n = vs.count("fail")
                if n == TRIES:
                    reds.append(f"{aid}@{a['v']}: acceptance check red on {base}: {a['test']}")
                elif n:
                    flaky.append(aid)
            held = gh_sync.heldout_checks(project)
            ran, reds = ran + len(held), reds + heldout_reds(held, clone, base, cfg)
        # shortcut: one check alone cannot tell code from environment, so a lone red line stays a code drift
        errs += [f"converge could not run checks on {base}"] if ran > 1 and len(reds) == ran else reds
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return f"{base} {base_sha[:12]}", errs, flaky, unverified


def cmd_converge(a):
    """Weekly (hub-weekly.service): one open board task per drift, deduped by title. Never edits the spec."""
    reason = hb.paused()
    if reason:
        print(f"hub is paused ({reason}); opening nothing")
        return
    one = hb.which_project(a.project)
    projects = [one] if one else sorted({os.path.basename(os.path.dirname(os.path.dirname(p)))
                                        for name in ("requirements.json", "prd.json") for p in glob.glob(
                                            os.path.join(hb.HUB_DIR, "projects", "*", "spec", name))
                                        if repo_cfg(os.path.basename(os.path.dirname(os.path.dirname(p))))})
    # Only factory.json projects: an archived project opened 41 drift tasks nobody would build (26 Oct).
    if a.repo and len(projects) != 1:
        die("--repo needs --project")
    who, opened, failed = hb.whoami(a.as_agent), [], []
    for p in projects:
        try:
            base, errs, flaky, unverified = drifts(p, os.path.abspath(os.path.expanduser(a.repo or os.path.join(CODE_DIR, p))))
        except SystemExit as e:  # one project's dead origin must not hide the others' drift
            failed.append(f"{p}: {e}")
            continue
        print(f"{p}: {len(errs)} drift(s) from {base}")
        if flaky:
            print(f"  flaky: {', '.join(flaky)}")
        if unverified:  # shown, never a drift task: the check ran no tests offline
            print(f"  unverified, no tests ran: {', '.join(unverified)}")
        with hb.board(write=True) as (data, events):
            live = {t["title"] for t in data["tasks"] if t["status"] != "done" and "stale" not in (t.get("tags") or [])}
            for e in errs:
                title = f"{p} spec drift: {e}"
                if title in live:
                    print(f"  already open: {title}")
                    continue
                tid = f"T-{data['next_id']:03d}"
                data["next_id"] += 1
                live.add(title)
                data["tasks"].append({
                    "id": tid, "title": title, "status": "open", "owner": hb.LEAD_AGENT, "deps": [], "created_by": who,
                    "created": hb.now(), "updated": hb.now(), "notes": [], "project": p,
                    "detail": f"Opened by `hub spec converge` (weekly): the {p} spec disagrees with {base}.\n\n{e}\n\n"
                              "Fix the code or the test on the live line, or write a change (spec/changes/C-NNN.json) "
                              f"and take it through review; never edit {os.path.basename(spec_path(p))} by hand. Done when "
                              f"`hub spec converge --project {p}` no longer reports it."})
                hb.log(events, who, "created", tid, title=title, project=p, via="hub spec converge")
                opened.append(tid)
                print(f"  opened {tid}: {title}")
    if opened:
        hb.deliver(hb.LEAD_AGENT, f"hub spec converge opened {', '.join(opened)} (spec drift): hub show <id>")
    if failed:
        die("converge could not check " + "; ".join(failed))


def register(sub):
    p = sub.add_parser("spec", help="the PRD tree: check, lint, impact, rewind --dry-run, apply")
    s = p.add_subparsers(dest="spec_cmd", required=True)
    i = s.add_parser("init", help="a project's first PRD v1 and spec.lock")
    i.add_argument("project_name", metavar="project")
    i.add_argument("--from", dest="from_file", help="a PRD or requirements JSON to start from (default: empty)")
    i.set_defaults(fn=cmd_init)
    bs = s.add_parser("bootstrap-sha", help="one-time: set merge_sha on tasks merged before it was recorded")
    bs.add_argument("pairs", nargs="+", metavar="T-n=<sha>")
    bs.add_argument("--project", help="defaults to $HUB_PROJECT")
    bs.add_argument("--repo", help="the product repo (default $HUB_CODE_DIR/<project>, else ~/code/<project>)")
    bs.set_defaults(fn=cmd_bootstrap_sha)
    cr = s.add_parser("correct", help="propose a bounded correction (small typo/clarity, 0 blast radius)")
    cr.add_argument("file", help="path to JSON file with modified acceptance lines")
    cr.add_argument("--project", help="defaults to $HUB_PROJECT")
    cr.add_argument("--repo", help="the product repo (default $HUB_CODE_DIR/<project>, else ~/code/<project>)")
    cr.set_defaults(fn=cmd_correct)
    pr = s.add_parser("propose", help="propose a spec change and generate review page")
    pr.add_argument("file", help="path to JSON file describing the change")
    pr.add_argument("--project", help="defaults to $HUB_PROJECT")
    pr.add_argument("--repo", help="the product repo (default $HUB_CODE_DIR/<project>, else ~/code/<project>)")
    pr.set_defaults(fn=cmd_propose)
    rv = s.add_parser("revert", help="restore previous version by creating a reversing correction")
    rv.add_argument("change", help="C-NNN to revert")
    rv.add_argument("--project", help="defaults to $HUB_PROJECT")
    rv.add_argument("--repo", help="the product repo (default $HUB_CODE_DIR/<project>, else ~/code/<project>)")
    rv.set_defaults(fn=cmd_revert)
    ap = s.add_parser("approve", help="reviewer approves a change file, recording a receipt")
    ap.add_argument("change", help="C-NNN")
    ap.add_argument("--why", help="optional note / LGTM reason")
    ap.add_argument("--project", help="defaults to $HUB_PROJECT")
    ap.add_argument("--repo", help="the product repo (default $HUB_CODE_DIR/<project>, else ~/code/<project>)")
    ap.set_defaults(fn=cmd_approve)
    for name, fn, hlp in (("check", cmd_check, "schema, lock hash, acceptance tests both ways"),
                          ("lint", cmd_lint, "deterministic overlap checks for a change"),
                          ("impact", cmd_impact, "a change's blast radius, from the graph alone"),
                          ("rewind", cmd_rewind, "--dry-run: the rewind and check run in a throwaway clone"),
                          ("apply", cmd_apply, "write PRD v+1, cut change/C-NNN, regenerate the task tree")):
        c = s.add_parser(name, help=hlp)
        if name != "check":
            c.add_argument("change", help="C-NNN")
        c.add_argument("--project", help="defaults to $HUB_PROJECT")
        c.add_argument("--repo", help="the product repo (default $HUB_CODE_DIR/<project>, else ~/code/<project>)")
        if name == "check":
            c.add_argument("--lines", help="A-x.y,... : check test files only for these lines (a task's verify)")
        if name == "rewind":
            c.add_argument("--dry-run", action="store_true")
        if name == "apply":
            c.add_argument("--force", action="store_true", help="rewind even a cross-cutting radius")
            c.add_argument("--yes", action="store_true", help="mark stale more tasks than the blast radius reaches")
        c.set_defaults(fn=fn)
    cv = s.add_parser("converge", help="weekly: one board task per drift of each spec project from its live line")
    cv.add_argument("--project", help="one project (default: $HUB_PROJECT, else every spec project)")
    cv.add_argument("--repo", help="the product repo (default $HUB_CODE_DIR/<project>, else ~/code/<project>)")
    cv.set_defaults(fn=cmd_converge)
