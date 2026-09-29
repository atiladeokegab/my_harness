"""`hub gh-sync`: carry one hackathon's hub tasks to GitHub Issues, and results back.

Config and sync state live in $HUB_DIR/projects/<project>/hackathon.json, written by the
hackathon skill. The hub is the source of truth for each brief; GitHub is the source of
truth for who picked up pool work and what got closed. See docs/hackathon-kit.md.
"""

import difflib
import fcntl
import hashlib
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import board as hb

# The same roster shell.sh uses. Hub agents' issues are assigned to the lead's GitHub
# handle and labelled agent:<name>; change-requests go to the lead agent's inbox.
LEAD_AGENT = hb.canon(os.environ.get("HUB_LEAD") or "Zeus")
HUB_AGENTS = tuple(dict.fromkeys(hb.canon(n) for n in (
    LEAD_AGENT, *os.environ.get("HUB_CLAUDE_AGENTS", "Zeus Apollo Hermes Athena").split(),
    *os.environ.get("HUB_CODEX_AGENTS", "Prometheus").split())))
UPDATED = "Brief updated by the lead — re-read before continuing."
# The hub stores every owner through canon() ("pool" -> "Pool", "DeShawn" -> "Deshawn"), so
# every name comparison here goes through canon() too.
POOL = "Pool"


class GhError(Exception):
    pass


class Gh:
    """Every GitHub call goes through here, so --dry-run is one branch, not twenty."""

    def __init__(self, dry=False):
        self.dry = dry

    def __call__(self, *args, write=True, stdin=None, cwd=None, body=None):
        if body is not None:
            with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", suffix=".md") as f:
                f.write(body)
                f.flush()
                return self(*args, "--body-file", f.name, write=write, stdin=stdin, cwd=cwd)
        cmd = ["gh", *map(str, args)]
        if self.dry and write:
            print("would run:", shlex.join(cmd))
            return ""
        try:
            r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=60, cwd=cwd)
        except subprocess.TimeoutExpired:
            raise GhError(f"{shlex.join(cmd)}: timed out after 60 seconds") from None
        except OSError as e:
            raise GhError(f"{shlex.join(cmd)}: {e}") from None
        if r.returncode:
            raise GhError(f"{shlex.join(cmd)}: {' '.join(r.stderr.split()) or r.returncode}")
        return r.stdout

    def json(self, *args):
        try:
            return json.loads(self(*args, write=False) or "null")
        except json.JSONDecodeError:
            raise GhError(f"gh {shlex.join(args)}: invalid JSON response") from None


def config_path(project):
    return os.path.join(hb.HUB_DIR, "projects", project, "hackathon.json")


MARKER = "<!-- hub-task: {} -->"


def digest(text):
    # GitHub can hand a body back with \r\n or trimmed trailing whitespace. The task marker
    # is bookkeeping, not brief: a teammate deleting it is not an edit to fold in.
    lines = (text or "").replace("\r\n", "\n").strip().split("\n")
    norm = "\n".join(l.rstrip() for l in lines if not l.startswith("<!-- hub-task: ")).strip()
    return hashlib.sha256(norm.encode()).hexdigest()


def issue_body(t, by_id):
    """The brief, its prerequisites as issue links, and a marker that finds the issue again
    if GitHub created it but the reply was lost."""
    body = (t.get("detail") or "").rstrip()
    if t.get("kind") == "gh-imported" and hb.strip_issue_extras(t.get("issue_source_body")) == body:
        return t["issue_source_body"]
    deps = [f"#{by_id[d]['issue']}" if "issue" in by_id.get(d, {}) else f"{d} (not published yet)"
            for d in t.get("deps") or []]
    if deps:
        body += "\n\nDepends on: " + ", ".join(deps)
    return body if t.get("kind") == "gh-imported" else body + "\n\n" + MARKER.format(t["id"])


def edit_warning(n, hub_body, remote):
    def lines(s):
        return [l.rstrip() for l in (s or "").replace("\r\n", "\n").strip().split("\n")
                if not l.startswith("<!-- hub-task: ")]
    unified = list(difflib.unified_diff(lines(hub_body), lines(remote), "hub brief",
                                        "GitHub", lineterm="", n=0))
    diff = [l for l in unified[2:] if not l.startswith("@@")]
    plus = sum(l.startswith("+") for l in diff)
    minus = sum(l.startswith("-") for l in diff)
    shown = diff[:20] + ([f"... {len(diff) - 20} more lines"] if len(diff) > 20 else [])
    return (f"warning: #{n} was edited on GitHub; not overwriting (+{plus}/-{minus} lines vs "
            f"the hub brief). Run `hub edit {n} --take-github`, or `hub edit {n} --keep-hub` "
            "to overwrite it.\n" + "\n".join("    " + l for l in shown))


def last_editor(gh, repo, n):
    owner, name = repo.split("/")
    query = ("query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){issue(number:$n)"
             "{userContentEdits(first:20){nodes{editedAt editor{login}}}}}}")
    try:
        data = gh.json("api", "graphql", "-f", f"query={query}", "-f", f"o={owner}",
                       "-f", f"r={name}", "-F", f"n={n}")
        nodes = data["data"]["repository"]["issue"]["userContentEdits"]["nodes"]
        # GitHub doesn't document the order of userContentEdits: take the latest editedAt.
        latest = max(nodes, key=lambda e: e.get("editedAt") or "", default=None)
        return ((latest or {}).get("editor") or {}).get("login")
    except (GhError, KeyError, TypeError, IndexError):
        return None


def field_line(text, name):
    text = (text or "").replace("\r\n", "\n")
    form = re.search(rf"^###[ \t]+{re.escape(name)}[ \t]*\n(.*?)(?=^### |\Z)", text, re.M | re.S)
    plain = None if form else re.search(rf"^{re.escape(name)}:[ \t]*([^\n]*)", text, re.M)
    value = (form or plain).group(1).strip() if form or plain else ""
    return value if value and value != "_No response_" else None


def files_line(text):
    return field_line(text, "Files")


def files_inside(child, vertical):
    def paths(body):
        raw = re.split(r"[,\n]", files_line(body) or "")
        return [p for entry in raw if (p := re.sub(r"^[-*][ \t]+", "", entry.strip()).strip("` "))]

    allowed, wanted = paths(vertical), paths(child)
    return bool(allowed and wanted) and all(
        not path.startswith("/") and posixpath.normpath(path) != ".."
        and not posixpath.normpath(path).startswith("../")
        and any(posixpath.normpath(path) == posixpath.normpath(area)
                or posixpath.normpath(path).startswith(posixpath.normpath(area) + "/")
                for area in allowed)
        for path in wanted)


def is_pool(owner):
    return not owner or hb.canon(owner) == POOL


def target(t, cfg):
    """Assign the human owner; represent the delegate with an agent label."""
    owner = t.get("owner")
    labels = ["task"]
    if t.get("kind") == "vertical":
        labels.append("vertical")
    if t.get("agent"):
        labels.append(f"agent:{t['agent'].lower()}")
    if is_pool(owner):
        return None, labels + ["pool"]
    owner = hb.canon(owner)
    handles = {hb.canon(p["name"]): p["github"] for p in cfg["roster"]}
    if owner in handles:
        return handles[owner], labels
    raise GhError(f"owner {owner!r} is not a roster human (agents are delegates: hub delegate)")


def check_config(cfg, project, init=False):
    """Problems in a hand-editable hackathon.json, one line each, before any GitHub call."""
    if not isinstance(cfg, dict) or not isinstance(cfg.get("roster"), list) \
            or not isinstance(cfg.get("deadlines"), list):
        return ["needs an object with repo, deadlines (a list) and roster (a list)"]
    problems = []
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", str(cfg.get("template", ""))):
        problems.append("template must be owner/name: your copy of the hackathon_teamwork template repo")
    if init:
        for field in ("event", "title", "summary", "smoke"):
            if not isinstance(cfg.get(field), str) or not cfg[field].strip():
                problems.append(f"{field} needs non-empty text")
        if "rules" in cfg and (not isinstance(cfg["rules"], str) or not cfg["rules"].strip()):
            problems.append("rules must be text or a link")
        if "judging" in cfg and (not isinstance(cfg["judging"], list) or
                                  not all(isinstance(s, str) and s.strip() for s in cfg["judging"])):
            problems.append("judging must be a list of non-empty strings")
        try:
            ZoneInfo(cfg["timezone"])
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
            problems.append("timezone must be a valid IANA timezone")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", str(cfg.get("repo", ""))):
        problems.append("repo must be owner/name")
    elif cfg["repo"].split("/")[1].lower() != project:
        # One event, one name. Also the cheapest guard against a typo aimed at a real repo.
        problems.append(f"repo {cfg['repo']!r} must be named after the project ({project!r})")
    names = []
    for d in cfg["deadlines"]:
        name = d.get("name") if isinstance(d, dict) else None
        if not isinstance(name, str) or not name.strip():
            problems.append("every deadline needs a name")
        elif name in names:
            problems.append(f"deadline {name!r} is listed twice")
        names.append(name)
        try:
            if datetime.fromisoformat(d["at"]).tzinfo is None:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            problems.append(f"deadline {name!r}: 'at' must be ISO 8601 with a timezone, e.g. 2026-10-04T14:00+01:00")
    for need in ("code freeze", "submit"):
        if need not in names:
            problems.append(f"no {need!r} deadline")
    roster = [p for p in cfg["roster"] if isinstance(p, dict)]
    if len(roster) != len(cfg["roster"]) or sum(1 for p in roster if p.get("lead")) != 1:
        problems.append("roster needs objects, with exactly one marked \"lead\": true")
    designers = [p.get("name") for p in roster if p.get("designer") is True]
    if len(designers) > 1:
        problems.append(f"roster has more than one designer: {', '.join(map(str, designers))}")
    for p in roster:
        if "designer" in p and not isinstance(p["designer"], bool):
            problems.append(f"roster entry {p.get('name')!r}: designer must be a boolean")
        if p.get("designer") is True and not str(p.get("tool") or "").strip():
            problems.append(f"designer {p.get('name')!r} has no AI tool: the designer's agent builds the mockup")
    seen = set()
    for p in roster:
        name = hb.canon(str(p.get("name", "")))
        if not hb.AGENT_RE.match(name):
            problems.append(f"roster name {p.get('name')!r} must be one word (letters, digits, _ or -): the hub uses it as a task owner")
        elif name in (*HUB_AGENTS, POOL) or name in seen:
            problems.append(f"roster name {p.get('name')!r} is taken (hub agent, pool, or a duplicate)")
        seen.add(name)
        if not isinstance(p.get("github"), str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", p["github"]):
            problems.append(f"roster entry {p.get('name')!r} needs a GitHub handle (letters, digits, -)")
    humans = {hb.canon(str(p.get("name", ""))) for p in roster}
    handles = {str(p.get("github", "")).lower() for p in roster}
    agent_names, agent_handles = set(), set()
    for p in roster:
        agents = p.get("agents", [])
        if not isinstance(agents, list) or not all(isinstance(x, dict) for x in agents):
            problems.append(f"roster entry {p.get('name')!r}: agents must be a list of objects")
            continue
        for ag in agents:
            name = hb.canon(str(ag.get("name", "")))
            if not hb.AGENT_RE.match(name):
                problems.append(f"agent {ag.get('name')!r} must be one word")
            elif name in humans or name == POOL or name in agent_names:
                problems.append(f"agent {name!r} is a roster human, pool, or listed twice")
            agent_names.add(name)
            handle = ag.get("github")
            if handle is not None:
                if not isinstance(handle, str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", handle):
                    problems.append(f"agent {name!r}: github must be a handle")
                elif handle.lower() in handles or handle.lower() in agent_handles:
                    problems.append(f"agent {name!r}: github {handle!r} is already a human's or another agent's")
                else:
                    agent_handles.add(handle.lower())
    return problems


def deadline(detail):
    return field_line(detail, "Deadline") or "code freeze"


def snapshot(project):
    with hb.board() as (data, _):
        return [dict(t) for t in data["tasks"] if t.get("project") == project]


def apply(changes, dry):
    """changes: [(task_id, {field: value}, event)]. One short locked write, no network inside."""
    if dry:
        for tid, fields, _ in changes:
            print(f"would set {tid}: {fields}")
        return
    if not changes:
        return
    who = hb.whoami()
    with hb.board(write=True) as (data, events):
        for tid, fields, event in changes:
            hb.find(data, tid).update(fields, updated=hb.now())
            hb.log(events, who, event, tid, **{k: v for k, v in fields.items() if k in ("status", "owner")})


def repo_state(gh, repo, template):
    """'missing', or 'ours' for a repo made from the template. Anything else is refused
    before a single write: --init rewrites branch protection and invites people."""
    try:
        info = gh.json("repo", "view", repo, "--json", "templateRepository")
    except GhError as e:
        if "Could not resolve to a Repository" in str(e):
            return "missing"
        # A 401, a 502 or a timeout is not "missing": never answer it with `repo create`.
        sys.exit(f"gh-sync: can't read {repo}: {e}")
    tpl = (info or {}).get("templateRepository") or {}
    made_from = f"{(tpl.get('owner') or {}).get('login')}/{tpl.get('name')}"
    if made_from.lower() != template.lower():
        sys.exit(f"gh-sync: refusing to touch {repo}: it was not created from {template}. "
                 "Check the repo in hackathon.json.")
    return "ours"


def list_issues(gh, repo):
    return {i["number"]: i for i in gh.json(
        "issue", "list", "-R", repo, "--state", "all", "--limit", "1000",
        "--json", "number,title,state,stateReason,assignees,labels,url,body")}


def import_subissues(tasks, cfg, gh, repo):
    seen = {t["issue"] for t in tasks if t.get("project") == cfg["repo"].split("/")[1] and "issue" in t}
    pending = []
    for vertical in tasks:
        if vertical.get("kind") != "vertical" or "issue" not in vertical:
            continue
        children = gh.json("api", f"repos/{repo}/issues/{vertical['issue']}/sub_issues?per_page=100")
        for child in children:
            n = child["number"]
            labels = {l["name"] for l in child["labels"]}
            if child["state"].lower() != "open" or "task" not in labels or "draft" in labels or n in seen:
                continue
            if not files_inside(child.get("body"), vertical.get("detail")):
                print(f"warning: #{n} Files: {files_line(child.get('body')) or '-'} is outside "
                      f"#{vertical['issue']} Files: {files_line(vertical.get('detail')) or '-'}")
                continue
            pending.append((vertical, child))
            seen.add(n)
    if not pending:
        return 0
    if gh.dry:
        for vertical, child in pending:
            print(f"would import #{child['number']} under #{vertical['issue']}")
        return 0
    project = cfg["repo"].split("/")[1]
    imported = []
    with hb.board(write=True) as (data, events):
        by_issue = {t["issue"]: t["id"] for t in data["tasks"]
                    if t.get("project") == project and "issue" in t}
        for vertical, child in pending:
            n = child["number"]
            if n in by_issue:  # another sync may have imported it since our snapshot
                continue
            tid = f"T-{data['next_id']:03d}"
            data["next_id"] += 1
            body = child.get("body") or ""
            agent = next((hb.canon(l["name"][6:]) for l in child["labels"]
                          if l["name"].startswith("agent:")), None)
            assignees = [a["login"] for a in child.get("assignees", [])]
            owner_login = next((p["github"] for p in cfg["roster"]
                                if hb.canon(p["name"]) == hb.canon(vertical.get("owner"))), None)
            assignee = owner_login if owner_login in assignees else (assignees[0] if assignees else None)
            t = {"issue": n, "id": tid, "title": child["title"], "detail": hb.strip_issue_extras(body),
                 "status": "open", "owner": vertical.get("owner"), "agent": agent, "deps": [],
                 "parent": vertical["id"], "kind": "gh-imported", "project": project,
                 "created_by": hb.whoami(), "created": hb.now(), "updated": hb.now(), "notes": [],
                 "issue_hash": digest(body), "issue_source_body": body,
                 "issue_assignee": assignee, "issue_agent": agent.lower() if agent else None,
                 "issue_title": child["title"],
                 "issue_milestone": (child.get("milestone") or {}).get("title") or deadline(body)}
            data["tasks"].append(t)
            by_issue[n] = tid
            imported.append((t, body))
            hb.log(events, hb.whoami(), "gh-imported", tid, issue=n, parent=vertical["id"])
        warned = set()
        for t, body in imported:
            for line in re.findall(r"^Depends on:\s*(.+)$", body, re.M):
                for raw in re.findall(r"#(\d+)", line):
                    n = int(raw)
                    if n in by_issue and by_issue[n] != t["id"]:
                        if by_issue[n] not in t["deps"]:
                            t["deps"].append(by_issue[n])
                    elif (t["issue"], n) not in warned:
                        print(f"warning: #{t['issue']} Depends on: #{n} is not on the hub; importing without it")
                        warned.add((t["issue"], n))
    return len(imported)


def pull(tasks, cfg, gh, repo):
    """Returns (changes, issues by number, imported count)."""
    issues = list_issues(gh, repo)
    names = {p["github"].lower(): hb.canon(p["name"]) for p in cfg["roster"]}
    agent_handles = {a["github"].lower(): (hb.canon(a["name"]), hb.canon(p["name"]))
                     for p in cfg["roster"] for a in p.get("agents", []) if a.get("github")}
    changes = []
    for t in tasks:
        if "issue" not in t:
            continue
        i = issues.get(t["issue"])
        if not i:
            if t["status"] == "done":
                continue
            print(f"warning: #{t['issue']} ({t['id']}) not found on GitHub: deleted or moved? "
                  "Drop the task, or replace it with a new one (see the hackathon skill, Live).")
            continue
        # Straight to done, not through transition(): GitHub closing it is the fact.
        if i["state"] == "CLOSED" and i["stateReason"] == "COMPLETED" and t["status"] != "done":
            changes.append((t["id"], {"status": "done", "closed_by_gh": True}, "gh-closed"))
        elif i["state"] == "CLOSED" and t["status"] != "done":
            print(f"warning: #{t['issue']} ({t['id']}) was closed as not planned; "
                  "the hub task is still open. Drop the task, or reopen the issue.")
        elif i["state"] == "OPEN" and t["status"] == "done" and t.get("closed_by_gh"):
            # Only undo what a sync did; a task the lead closed by hand stays closed.
            changes.append((t["id"], {"status": "open", "closed_by_gh": False}, "gh-reopened"))
        gh_agents = sorted(l["name"][6:] for l in i["labels"] if l["name"].startswith("agent:"))
        if len(gh_agents) > 1:
            print(f"warning: #{t['issue']} has several agent labels; using agent:{gh_agents[0]}")
        gh_agent = hb.canon(gh_agents[0]) if gh_agents else None
        last = hb.canon(t["issue_agent"]) if t.get("issue_agent") else None
        if gh_agent != last:
            changes.append((t["id"], {"agent": gh_agent,
                                      "issue_agent": gh_agent.lower() if gh_agent else None}, "gh-delegated"))
        # A pool pickup is an assignee GitHub has and we didn't push. The same assignee we
        # pushed means the lead just moved the task back to pool; push removes it.
        if is_pool(t.get("owner")) and i["assignees"]:
            logins = [a["login"].lower() for a in i["assignees"]]
            human = min((l for l in logins if l in names), default=None)
            bot = min((l for l in logins if l in agent_handles), default=None)
            if human and human != (t.get("issue_assignee") or "").lower():
                fields = {"owner": names[human], "issue_assignee": human}
                if bot and agent_handles[bot][1] == names[human]:
                    fields.update(agent=agent_handles[bot][0], issue_agent=None)
                changes.append((t["id"], fields, "gh-assigned"))
            elif bot and bot != (t.get("issue_assignee") or "").lower() and not human:
                agent, owner = agent_handles[bot]
                changes.append((t["id"], {"owner": owner, "agent": agent,
                                          "issue_assignee": None, "issue_agent": None}, "gh-assigned"))
    seen = cfg.setdefault("sync", {}).setdefault("seen_change_requests", [])
    for n, i in sorted(issues.items()):
        if i["state"] == "OPEN" and n not in seen and any(l["name"] == "change-request" for l in i["labels"]):
            text = f"change-request #{n}: {i['title']} — {i['url']}"
            if gh.dry:
                print("would deliver:", text)
                continue
            hb.deliver(LEAD_AGENT, text, message_id=f"cr-{repo.replace('/', '-')}-{n}")
            seen.append(n)
    return changes, issues, import_subissues(tasks, cfg, gh, repo)


def push(tasks, cfg, gh, repo, failures, assignable, issues):
    """Each change is recorded the moment GitHub has it: a crash after `issue create` but
    before the record would make the next run create the issue again.

    assignable: lowercased logins GitHub will accept as assignees: collaborators who have
    accepted their invite."""
    deadlines = [d["name"] for d in cfg["deadlines"]]
    record = lambda *change: apply([change], gh.dry)
    waiting = set()
    made_labels = set()
    moved = False

    def can_assign(who, t):
        if not who or who.lower() in assignable:
            return True
        if who not in waiting:
            waiting.add(who)
            print(f"warning: {hb.canon(t['owner'])} (@{who}) has not accepted the repo invite yet; "
                  "their issues stay unassigned until a sync after they accept.")
        return False

    by_id = {t["id"]: t for t in tasks}
    for t in tasks:
        if t["status"] == "done":  # finished work is neither created nor re-briefed
            continue
        try:
            body = issue_body(t, by_id)
            who, labels = target(t, cfg)
            on_issue = {label["name"] for label in issues.get(t.get("issue"), {}).get("labels", [])}
            for name in labels:
                if name.startswith("agent:") and name not in on_issue and name not in made_labels:
                    gh("label", "create", name, "-R", repo, "--force")
                    made_labels.add(name)
            milestone = deadline(t.get("detail"))
            if milestone not in deadlines:
                raise GhError(f"Deadline: {milestone!r} is not a deadline in hackathon.json "
                              f"(choose from {', '.join(deadlines)})")
            if "issue" not in t and t.get("issue_pending"):
                # A create was sent and its reply never recorded: find it before sending another.
                for i in issues.values():
                    if i["title"] == t["title"] and MARKER.format(t["id"]) in \
                            gh.json("issue", "view", i["number"], "-R", repo, "--json", "body")["body"]:
                        record(t["id"], {"issue": i["number"], "issue_hash": digest(body), "issue_assignee": None,
                                         "issue_agent": t.get("agent"),
                                         "issue_title": t["title"], "issue_milestone": milestone,
                                         "issue_pending": False}, "gh-found")
                        t["issue"] = i["number"]
                        break
                if "issue" in t:
                    continue
            if "issue" not in t:
                assignee = who if can_assign(who, t) else None
                args = ["issue", "create", "-R", repo, "--title", t["title"],
                        "--label", ",".join(labels), "--milestone", milestone]
                if assignee:
                    args += ["--assignee", assignee]
                record(t["id"], {"issue_pending": True}, "gh-creating")
                url = gh(*args, body=body).strip()
                if url:  # empty under --dry-run
                    try:
                        number = int(url.rsplit("/", 1)[1])
                    except (IndexError, ValueError):
                        raise GhError(f"unexpected output from gh issue create: {url!r}") from None
                    record(t["id"], {"issue": number, "issue_hash": digest(body), "issue_assignee": assignee,
                                     "issue_agent": t.get("agent"),
                                     "issue_title": t["title"], "issue_milestone": milestone,
                                     "issue_pending": False}, "gh-created")
                    t["issue"] = number  # later tasks' "Depends on" lines link to it
                    moved = True
                continue
            n = t["issue"]
            held = False  # the new brief is held back, so its title and deadline are too
            remote = issues.get(n, {}).get("body")
            if remote is None and digest(body) != t["issue_hash"]:
                remote = gh.json("issue", "view", n, "-R", repo, "--json", "body")["body"]
            if remote is not None and digest(remote) not in (t["issue_hash"], digest(body)):
                own = {handle.lower() for handle in [who] + [a["github"] for p in cfg["roster"]
                       for a in p.get("agents", []) if a.get("github")
                       and hb.canon(a["name"]) == hb.canon(t.get("agent") or "")] if handle}
                hub_unchanged = digest(body) == t["issue_hash"]
                new = hb.strip_issue_extras(remote)
                same_files = files_line(new) == files_line(t.get("detail"))
                editor = last_editor(gh, repo, n) if hub_unchanged and same_files else None
                if hub_unchanged and same_files and editor and editor.lower() in own:
                    fields = {"detail": new, "issue_hash": digest(remote)}
                    if t.get("kind") == "gh-imported":
                        fields["issue_source_body"] = remote
                    record(t["id"], fields, "gh-owner-edited")
                    diff = edit_warning(n, body, remote).split("\n")[1:6]
                    hb.deliver(LEAD_AGENT, f"{hb.canon(t['owner'])} edited #{n}: " +
                               " | ".join(line.strip() for line in diff))
                else:
                    held = True
                    warning = edit_warning(n, body, remote)
                    if not same_files:
                        warning += "\n    the Files: line changed; taking more files needs a change-request"
                    print(warning)
            elif digest(body) != t["issue_hash"]:
                if digest(remote) == digest(body):
                    # The lead took the GitHub edit into the brief: adopt it.
                    fields = {"issue_hash": digest(body), "notice_pending": True}
                    if t.get("kind") == "gh-imported":
                        fields["issue_source_body"] = body
                    record(t["id"], fields, "gh-adopted")
                    t["notice_pending"] = True
                else:
                    gh("issue", "edit", n, "-R", repo, body=body)
                    # The notice is owed until it is posted: a failed comment is retried
                    # next sync, or a teammate keeps working from the old brief.
                    fields = {"issue_hash": digest(body), "notice_pending": True}
                    if t.get("kind") == "gh-imported":
                        fields["issue_source_body"] = body
                    record(t["id"], fields, "gh-updated")
                    t["notice_pending"] = True
            if t.get("notice_pending"):
                gh("issue", "comment", n, "-R", repo, body=UPDATED)
                record(t["id"], {"notice_pending": False}, "gh-notified")
            # A replan can retitle a task, move its deadline or change its owner; the issue
            # follows in one edit. Tasks recorded before these fields existed count as in step.
            args, fields = [], {}
            if n in issues:  # owner labels as GitHub has them now, not as we last sent them
                owned = lambda value: value == "pool" or value.startswith("agent:")
                have = {l["name"] for l in issues[n]["labels"] if owned(l["name"])}
                want = {name for name in labels if owned(name)}
                for name in sorted(want - have):
                    args += ["--add-label", name]
                for name in sorted(have - want):
                    args += ["--remove-label", name]
                if have != want:
                    fields["issue_agent"] = t.get("agent")
            if not held and t["title"] != t.get("issue_title", t["title"]):
                args += ["--title", t["title"]]
                fields["issue_title"] = t["title"]
            if not held and milestone != t.get("issue_milestone", milestone):
                args += ["--milestone", milestone]
                fields["issue_milestone"] = milestone
            have_assignees = ({a["login"].lower() for a in issues[n]["assignees"]} if n in issues
                              else {t["issue_assignee"].lower()} if t.get("issue_assignee") else set())
            want_assignees = {who.lower()} if who else set()
            if have_assignees != want_assignees and can_assign(who, t):
                for login in sorted(have_assignees - want_assignees):
                    args += ["--remove-assignee", login]
                if who and who.lower() not in have_assignees:
                    args += ["--add-assignee", who]
                fields["issue_assignee"] = who
            if args:
                gh("issue", "edit", n, "-R", repo, *args)
                record(t["id"], fields, "gh-reconciled")
                moved = moved or "issue_assignee" in fields
        except GhError as e:
            print(f"error: {t['id']}: {e}", file=sys.stderr)
            failures.append(t["id"])
    return moved


def owner_list(tasks, cfg):
    """Who owns which open issue, with delegates shown beside their human owners."""
    people = {hb.canon(p["name"]): p for p in cfg["roster"]}
    groups = {}
    for t in sorted((t for t in tasks if t.get("issue") and t["status"] != "done"),
                    key=lambda t: t["issue"]):
        owner = POOL if is_pool(t.get("owner")) else hb.canon(t["owner"])
        entry = f"#{t['issue']} {t['title']}"
        if t.get("agent"):
            entry += f" [{t['agent']}]"
        groups.setdefault(owner, []).append(entry)
    lines = ["owners (for IDEA.md):"]
    for owner, entries in groups.items():
        who = "pool" if owner == POOL else f"{owner} (@{people[owner]['github']})"
        lines.append(f"  {who}: " + ", ".join(entries))
    return "\n".join(lines)


def update_idea_owners(tasks, cfg, project):
    """Keep the approved IDEA.md area table aligned with published issues."""
    clone = Path(os.environ.get("HUB_CODE_DIR") or os.path.expanduser("~/code")) / project
    if not clone.is_dir():
        if any(t.get("issue") for t in tasks) and (Path(hb.HUB_DIR) / "projects" / project / "IDEA.md").is_file():
            print(f"warning: {clone} is missing; IDEA.md owners table not updated")
        return
    git(clone, "fetch", "origin", "integration")
    with tempfile.TemporaryDirectory(prefix="hub-owners-") as temp:
        work = Path(temp) / "checkout"
        git(clone, "worktree", "add", "--detach", work, "origin/integration")
        try:
            idea = work / "IDEA.md"
            if not idea.is_file():
                raise GhError("IDEA.md is missing on integration")
            lines = idea.read_text().splitlines(keepends=True)
            start = next((i for i, line in enumerate(lines) if line.strip() == "## Areas and owners"), None)
            if start is None:
                raise GhError(f"{idea}: missing Areas and owners section")
            stop = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
            people = {hb.canon(p["name"]): p["github"] for p in cfg["roster"]}
            published = sorted((t for t in tasks if t.get("issue")), key=lambda t: t["issue"])
            matched = set()
            for i in range(start + 1, stop):
                cells = [cell.strip() for cell in lines[i].strip().strip("|").split("|")]
                if len(cells) != 4 or cells[0] == "Area" or cells[0].startswith("---"):
                    continue
                dirs = re.findall(r"`([^`]+)`", cells[1])
                issues = [t for t in published if dirs and files_inside(t.get("detail"),
                                                                        "Files: " + ", ".join(dirs))]
                matched.update(t["issue"] for t in issues)
                owners = []
                for t in issues:
                    if is_pool(t.get("owner")):
                        who = "pool"
                    else:
                        handle = people.get(hb.canon(t["owner"]))
                        if not handle:
                            raise GhError(f"#{t['issue']} owner {t['owner']!r} is not in the roster")
                        who = f"@{handle}"
                        if t.get("agent"):
                            who += f" [{t['agent']}]"
                    if who not in owners:
                        owners.append(who)
                numbers = ", ".join(f"#{t['issue']}" for t in issues)
                lines[i] = f"| {cells[0]} | {cells[1]} | {', '.join(owners) or '—'} | {numbers or '—'} |\n"
            for t in published:
                if t["issue"] not in matched and not (files_line(t.get("detail")) or "none").lower().startswith("none"):
                    print(f"warning: #{t['issue']} Files: {files_line(t.get('detail')) or '-'} matches no IDEA.md area")
            updated = "".join(lines)
            if updated != idea.read_text():
                idea.write_text(updated)
                git(work, "add", "IDEA.md")
                git(work, "commit", "-m", "docs: owners table")
                git(work, "push", "origin", "HEAD:integration")
                print("IDEA.md owners table updated")
        finally:
            git(clone, "worktree", "remove", "--force", work)


def ensure_integration(gh, repo, new, failures):
    """PRs land on `integration` (the default branch); `main` only moves when the smoke is green.
    Returns False when `integration` may not exist, so it isn't protected into a second error."""
    create = ("api", "-X", "POST", f"repos/{repo}/git/refs", "-f", "ref=refs/heads/integration")
    make_default = ("api", "-X", "PATCH", f"repos/{repo}", "-f", "default_branch=integration")
    try:
        if new and gh.dry:  # nothing on GitHub to read yet
            gh(*create, "-f", "sha=<main>")
            gh(*make_default)
            return True
        # matching-refs is a prefix match with no paging; /branches stops at 30, and mid-event
        # issue branches (12-…) sort before "integration"
        refs = gh.json("api", f"repos/{repo}/git/matching-refs/heads/integration") or []
        if not any(r.get("ref") == "refs/heads/integration" for r in refs):
            sha = gh.json("api", f"repos/{repo}/git/ref/heads/main")["object"]["sha"]
            gh(*create, "-f", f"sha={sha}")
        if (gh.json("api", f"repos/{repo}") or {}).get("default_branch") != "integration":
            gh(*make_default)
        return True
    except (GhError, KeyError, TypeError) as e:
        print(f"error: integration branch: {e}", file=sys.stderr)
        failures.append("integration branch")
        return False


def freeze_utc(cfg):
    at = next(d["at"] for d in cfg["deadlines"] if d["name"] == "code freeze")
    return datetime.fromisoformat(at).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def push_freeze(cfg, gh, repo):
    """Keep FREEZE_AT, which the template's freeze-gate workflow reads, in step with hackathon.json."""
    want = freeze_utc(cfg)
    if cfg.get("freeze_at_pushed") != want:
        gh("variable", "set", "FREEZE_AT", "-R", repo, "--body", want)
        if not gh.dry:
            cfg["freeze_at_pushed"] = want


def freeze(gh, repo):
    """At code freeze: tag main once, then re-run each open PR's freeze-gate, since a PR
    checked before the freeze still carries a stale pass. Returns the PRs whose gate could
    not be refreshed: the caller fails the command, so a stale pass is never reported as done."""
    try:
        gh.json("api", f"repos/{repo}/git/ref/tags/freeze")
        print("freeze tag already set; keeping it")
    except GhError as e:
        # Only a confirmed 404 means "no tag yet". A 401, 502 or timeout is not an answer,
        # and creating the tag on a guess could move the freeze point.
        if "HTTP 404" not in str(e) and "Not Found" not in str(e):
            raise
        sha = gh.json("api", f"repos/{repo}/git/ref/heads/main")["object"]["sha"]
        gh("api", "-X", "POST", f"repos/{repo}/git/refs", "-f", "ref=refs/tags/freeze", "-f", f"sha={sha}")
        print(f"tagged freeze at {sha[:7]}")
    stale = []
    # One budget for the whole command: waiting per PR would take hours with many PRs.
    poll = int(os.environ.get("FREEZE_RERUN_POLL", "10"))
    deadline = time.monotonic() + int(os.environ.get("FREEZE_RERUN_WAIT", "120"))
    for pr in gh.json("pr", "list", "-R", repo, "--state", "open", "--json", "number,headRefName",
                      "--limit", "200") or []:
        runs = gh.json("run", "list", "-R", repo, "--workflow", "freeze-gate.yml", "--branch",
                       pr["headRefName"], "--limit", "1", "--json", "databaseId,status") or []
        if runs and runs[0].get("status") not in (None, "completed"):
            # A run already under way may have read the old FREEZE_AT, and GitHub refuses to
            # re-run an unfinished run. Wait for it (bounded), then re-run it below.
            status = runs[0]["status"]
            while status != "completed" and time.monotonic() < deadline:
                time.sleep(poll)
                status = gh.json("run", "view", str(runs[0]["databaseId"]), "-R", repo,
                                 "--json", "status")["status"]
            if status != "completed":
                print(f"warning: the freeze gate for #{pr['number']} is still running and may have read "
                      "the old freeze time; run hub gh-sync --freeze again once it finishes")
                stale.append(pr["number"])
                continue
        if runs:
            try:
                gh("run", "rerun", str(runs[0]["databaseId"]), "-R", repo)
            except GhError as e:
                print(f"warning: could not re-run the freeze gate for #{pr['number']}: {e}")
                stale.append(pr["number"])
    return stale


def git(cwd, *args):
    cmd = ["git", "-C", str(cwd), *map(str, args)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GhError(f"{' '.join(cmd)}: {e}") from None
    if r.returncode:
        raise GhError(f"{' '.join(cmd)}: {r.stderr.strip() or r.returncode}")
    return r.stdout


def event_docs(cfg, project, clone, dry):
    """Fill the template once, then publish the approved event docs on both branches."""
    source = Path(hb.HUB_DIR) / "projects" / project
    if dry:
        print(f"would fill IDEA.md, HACKATHON.md, README.md and C4 images in {clone}")
        print("would commit docs: fill in the event and push integration and main")
        return
    if not clone.is_dir():
        return  # init already warned: gh's clone step did not leave a checkout
    idea = source / "IDEA.md"
    if not idea.is_file():
        raise GhError(f"approved IDEA.md is missing: {idea}")
    if not (cfg.get("board") or {}).get("url"):
        raise GhError("the event board URL is missing; make the board before publishing docs")
    git(clone, "fetch", "origin", "integration")
    with tempfile.TemporaryDirectory(prefix="hub-event-docs-") as temp:
        work = Path(temp) / "checkout"
        git(clone, "worktree", "add", "--detach", work, "origin/integration")
        try:
            if "<Event name>" not in (work / "HACKATHON.md").read_text():
                # A failed second push leaves only integration published; retry that commit.
                if git(work, "log", "-1", "--format=%s").strip() == "docs: fill in the event":
                    git(clone, "fetch", "origin", "main")
                    if git(work, "rev-parse", "HEAD") != git(clone, "rev-parse", "origin/main"):
                        git(work, "push", "origin", "HEAD:main")
                        print("event docs published to main")
                return  # a rerun never overwrites the published docs or owners table
            (work / "IDEA.md").write_text(idea.read_text())
            zone = ZoneInfo(cfg["timezone"])
            deadlines = []
            for d in cfg["deadlines"]:
                when = datetime.fromisoformat(d["at"])
                deadlines.append(f"| {d['name']} | {when.astimezone(zone).isoformat(timespec='minutes')} | "
                                 f"{when.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')} |")
            team = []
            for p in cfg["roster"]:
                role = ", ".join(x for x in ("lead" if p.get("lead") else "",
                                                "designer" if p.get("designer") else "",
                                                p.get("strengths", "")) if x) or "team member"
                team.append(f"| {p['name']} | @{p['github']} | {role} |")
            lead = next(p for p in cfg["roster"] if p.get("lead"))
            agents = ", ".join(a["name"] for a in lead.get("agents", [])) or "none listed"
            (work / "HACKATHON.md").write_text(
                f"# {cfg['event']}\n\n{cfg['summary']}\n\n"
                f"Official rules: {cfg.get('rules', 'the event brief')}\n\n"
                f"Smoke: `{cfg['smoke']}`\n\n"
                "The product that ships is `main`: the last commit that passed the smoke check.\n\n"
                f"Board: {cfg['board']['url']}\n\n## Deadlines\n\n"
                "Your agent checks these every session against the UTC column. GitHub milestones keep only the\n"
                "date, so this UTC column is the clock, never the milestone.\n\n"
                "| Deadline | Event time | UTC |\n|---|---|---|\n" + "\n".join(deadlines) +
                "\n\n## Judging criteria\n\n" +
                "\n".join(f"- {s}" for s in (cfg.get("judging") or ["Not published in the brief."])) +
                "\n\n## Team\n\n| Name | GitHub | Role |\n|---|---|---|\n" + "\n".join(team) +
                f"\n\nThe lead's agents: {agents}. When this page or a review says \"the lead\", "
                "it may be one of them acting for the lead.\n")
            readme = (work / "README.md").read_text()
            readme = re.sub(r"^# .*", lambda _: f"# {cfg['title']}", readme, count=1, flags=re.M)
            readme = re.sub(r"^<One paragraph:.*>$", lambda _: cfg["summary"], readme, count=1, flags=re.M)
            readme = readme.replace("gh repo clone <this repo>", f"gh repo clone {cfg['repo']}")
            images = []
            for level in ("context", "container", "component"):
                image = source / f"c4_{level}.png"
                if image.is_file():
                    dest = work / "docs" / "architecture" / image.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(image, dest)
                    images.append(f"![C4 {level}](docs/architecture/{image.name})")
            readme = readme.replace("<!-- the lead adds the C4 diagrams here -->", "\n\n".join(images))
            (work / "README.md").write_text(readme)
            problems = []
            for name in ("README.md", "IDEA.md", "HACKATHON.md"):
                for number, line in enumerate((work / name).read_text().splitlines(), 1):
                    if re.search(r"<[A-Za-z]|<!--", line):
                        problems.append(f"{name}:{number}: {line}")
            for link in re.findall(r"docs/architecture/c4_[^)]*\.png", readme):
                if not (work / link).is_file():
                    problems.append(f"README.md: missing image {link}")
            if problems:
                raise GhError("placeholders or missing images:\n" + "\n".join(problems))
            staged = ["README.md", "IDEA.md", "HACKATHON.md"]
            if images:
                staged.append("docs/architecture")
            git(work, "add", *staged)
            if subprocess.run(["git", "-C", str(work), "diff", "--cached", "--quiet"], timeout=30).returncode:
                git(work, "commit", "-m", "docs: fill in the event")
                git(work, "push", "origin", "HEAD:integration")
                git(work, "push", "origin", "HEAD:main")
                print("event docs published to integration and main")
        finally:
            git(clone, "worktree", "remove", "--force", work)


def init(cfg, gh, repo, failures, exists):
    """Once per hackathon. Every step checks first, so a rerun only fills gaps.

    Returns True when the repo is new. Under --dry-run a new repo does not exist yet, so
    there is nothing on GitHub to read and every read would 404."""
    code = os.environ.get("HUB_CODE_DIR") or os.path.expanduser("~/code")
    dest = os.path.join(code, repo.split("/")[1])
    new = not exists
    if not gh.dry:
        os.makedirs(code, exist_ok=True)  # a fresh machine has no code dir yet
    if new:
        gh("repo", "create", repo, "--template", cfg["template"], "--public", "--clone", cwd=code)
    elif not os.path.isdir(dest):  # a rerun on another machine, or after a clean-up
        gh("repo", "clone", repo, dest)
    if os.path.isdir(dest) and not gh.dry:
        # Commit as the account that owns the repo, via its no-reply address: a clone that
        # inherits some other global identity credits the lead's work to the wrong person.
        me = gh.json("api", "user")
        for key, value in (("user.email", f"{me['id']}+{me['login']}@users.noreply.github.com"),
                           ("user.name", me["login"])):
            subprocess.run(["git", "-C", dest, "config", key, value], check=False, timeout=30)
    elif not os.path.isdir(dest):
        print(f"warning: {dest} not cloned; clone it there (gh repo clone {repo} {dest}) and rerun --init")
    steps = []
    for p in cfg["roster"]:
        if not p.get("lead"):
            steps.append(("api", "-X", "PUT", f"repos/{repo}/collaborators/{p['github']}"))
        for agent in p.get("agents", []):
            if agent.get("github"):
                steps.append(("api", "-X", "PUT", f"repos/{repo}/collaborators/{agent['github']}"))
    agent_labels = [f"agent:{a['name'].lower()}" for p in cfg["roster"] for a in p.get("agents", [])]
    for label in ["task", "vertical", "draft", "pool", "change-request", "submission", "question", "fix", *agent_labels]:
        steps.append(("label", "create", label, "-R", repo, "--force"))
    have = {} if new and gh.dry else {m["title"]: m for m in gh.json("api", f"repos/{repo}/milestones?state=all")}
    for d in cfg["deadlines"]:
        due = datetime.fromisoformat(d["at"]).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if d["name"] not in have:
            steps.append(("api", "-X", "POST", f"repos/{repo}/milestones",
                          "-f", f"title={d['name']}", "-f", f"due_on={due}"))
        elif (have[d["name"]].get("due_on") or "")[:10] != due[:10]:
            # Organisers moved it. GitHub keeps only the date, so only a new date counts.
            steps.append(("api", "-X", "PATCH", f"repos/{repo}/milestones/{have[d['name']]['number']}",
                          "-f", f"due_on={due}"))
    for s in steps:
        try:
            gh(*s)
        except GhError as e:
            print(f"error: {e}", file=sys.stderr)
            failures.append(" ".join(s[:4]))
    try:
        push_freeze(cfg, gh, repo)
    except GhError as e:
        print(f"error: FREEZE_AT: {e}", file=sys.stderr)
        failures.append("variable FREEZE_AT")
    branches = ("main", "integration") if ensure_integration(gh, repo, new, failures) else ("main",)
    protection = {"required_status_checks": None, "enforce_admins": False, "restrictions": None,
                  "required_pull_request_reviews": {"required_approving_review_count": 1,
                                                    "require_code_owner_reviews": True,
                                                    # a push after approval voids it, so main
                                                    # only gets what the lead actually reviewed
                                                    "dismiss_stale_reviews": True}}
    for branch in branches:
        # After code freeze only PRs labelled fix pass freeze-gate (a template workflow), so
        # GitHub, not just Zeus's clock check, refuses a feature merge into integration.
        checks = {"strict": False, "contexts": ["freeze-gate"]} if branch == "integration" else None
        try:
            gh("api", "-X", "PUT", f"repos/{repo}/branches/{branch}/protection", "--input", "-",
               stdin=json.dumps({**protection, "required_status_checks": checks}))
        except GhError as e:
            print(f"error: branch protection ({branch}): {e}", file=sys.stderr)
            failures.append(f"branch protection {branch}")
    import gh_board  # imported here: gh_board imports this module
    gh_board.init_board(cfg, gh, repo)
    return new


def cmd_gh_sync(a):
    if not shutil.which("gh"):
        sys.exit("gh-sync: the gh CLI is not installed -- see https://cli.github.com")
    gh = Gh(a.dry_run)
    project = hb.which_project(a.project)
    if not project:
        sys.exit("gh-sync: which hackathon? pass --project <name>")
    path = config_path(project)
    try:
        with open(path) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        sys.exit(f"gh-sync: no {path} -- the hackathon skill writes it")
    except json.JSONDecodeError as e:
        sys.exit(f"gh-sync: {path} is not valid JSON ({e})")
    problems = check_config(cfg, project, init=a.init)
    if problems:
        if a.init:
            sys.exit(f"gh-sync: fix {path}:\n" + "\n".join(problems))
        sys.exit(f"gh-sync: fix {path}: " + "; ".join(problems))
    try:
        gh("auth", "status", write=False)
    except GhError as e:
        sys.exit(f"gh-sync: {e} -- check `gh auth login`")
    # The live /loop and a manual run can overlap; two pushes at once create every new
    # issue twice. Held until this process exits.
    if not a.dry_run:  # a dry run writes nothing, not even the lock file
        lock = open(os.path.join(os.path.dirname(path), ".gh-sync.lock"), "a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit(f"gh-sync: another gh-sync is already running for {project}; try again in a minute")
    repo, failures = cfg["repo"], []
    exists = repo_state(gh, repo, cfg["template"]) == "ours"
    if not exists and not a.init:
        sys.exit(f"gh-sync: {repo} doesn't exist yet -- run with --init first")
    try:
        if a.init:
            init(cfg, gh, repo, failures, exists)
            if not failures:
                event_docs(cfg, project, Path(os.environ.get("HUB_CODE_DIR") or os.path.expanduser("~/code")) / project, a.dry_run)
            if not a.dry_run and not failures:
                print(f"provisioned {repo}. After approval 3 run: hub gh-sync --project {project}")
        elif a.freeze:
            push_freeze(cfg, gh, repo)  # the gates re-run below must read the current time
            failures += [f"freeze gate #{n} not refreshed" for n in freeze(gh, repo)]
        else:
            if not a.pull_only:
                push_freeze(cfg, gh, repo)
            changes, issues, imported = pull(snapshot(project), cfg, gh, repo)
            apply(changes, a.dry_run)
            moved = imported or any(kind == "gh-assigned" for _, _, kind in changes)
            if not a.pull_only:
                assignable = {c["login"].lower() for c in gh.json("api", f"repos/{repo}/collaborators?per_page=100")}
                moved = push(snapshot(project), cfg, gh, repo, failures, assignable, issues) or moved
            if moved and not a.dry_run:
                print(owner_list(snapshot(project), cfg))
            if not a.pull_only:
                import gh_board  # imported here: gh_board imports this module
                if a.dry_run:
                    if cfg.get("board"):
                        print(f"would update board {cfg['board']['url']}")
                else:
                    tasks = snapshot(project)
                    if any(t.get("issue") and t["issue"] not in issues for t in tasks):
                        issues = list_issues(gh, repo)  # push created some: the board needs them too
                    gh_board.sync_board(tasks, cfg, gh, repo, issues)
            if not a.dry_run and not failures:
                update_idea_owners(snapshot(project), cfg, project)
    except GhError as e:
        failures.append(str(e))
    if not a.dry_run:
        hb._write_json_atomic(config_path(project), cfg)
    if a.dry_run:
        print("dry run: nothing changed")
    if failures:
        sys.exit(f"gh-sync: {len(failures)} failed: {', '.join(failures)}")


def register(sub):
    g = sub.add_parser("gh-sync", help="push a hackathon's tasks to GitHub Issues, pull results back")
    g.add_argument("--project", help="the hackathon's project tag (default: $HUB_PROJECT)")
    g.add_argument("--init", action="store_true", help="first run: repo from template, invites, labels, milestones, protection")
    g.add_argument("--pull-only", action="store_true", help="only pull closed/assigned issues and change-requests")
    g.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    g.add_argument("--freeze", action="store_true",
                   help="at code freeze: tag main once, re-run every open PR's freeze-gate")
    g.set_defaults(fn=cmd_gh_sync)
