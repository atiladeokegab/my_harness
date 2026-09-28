"""`hub gh-sync`: carry one hackathon's hub tasks to GitHub Issues, and results back.

Config and sync state live in $HUB_DIR/projects/<project>/hackathon.json, written by the
hackathon skill. The hub is the source of truth for each brief; GitHub is the source of
truth for who picked up pool work and what got closed. See docs/hackathon-kit.md.
"""

import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

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
# Labels that say who owns an issue. They follow the owner; any other label is left alone.
OWNER_LABELS = {"pool", *(f"agent:{a.lower()}" for a in HUB_AGENTS)}


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


def digest(text):
    # GitHub can hand a body back with \r\n or trimmed trailing whitespace.
    norm = "\n".join(line.rstrip() for line in (text or "").replace("\r\n", "\n").strip().split("\n"))
    return hashlib.sha256(norm.encode()).hexdigest()


def is_pool(owner):
    return not owner or hb.canon(owner) == POOL


def target(owner, cfg):
    """(assignee handle or None, labels) for a hub owner."""
    if is_pool(owner):
        return None, ["task", "pool"]
    owner = hb.canon(owner)
    handles = {hb.canon(p["name"]): p["github"] for p in cfg["roster"]}
    lead = next(p["github"] for p in cfg["roster"] if p.get("lead"))
    if owner in HUB_AGENTS:
        return lead, ["task", f"agent:{owner.lower()}"]
    if owner in handles:
        return handles[owner], ["task"]
    raise GhError(f"owner {owner!r} is neither in the roster nor a hub agent")


def check_config(cfg, project):
    """Problems in a hand-editable hackathon.json, one line each, before any GitHub call."""
    if not isinstance(cfg, dict) or not isinstance(cfg.get("roster"), list) \
            or not isinstance(cfg.get("deadlines"), list):
        return ["needs an object with repo, deadlines (a list) and roster (a list)"]
    problems = []
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", str(cfg.get("template", ""))):
        problems.append("template must be owner/name: your copy of the hackathon_teamwork template repo")
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
    return problems


def deadline(detail):
    m = re.search(r"^Deadline:\s*(.+?)\s*$", detail or "", re.M)
    return m.group(1) if m else "code freeze"


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


def pull(tasks, cfg, gh, repo):
    """Returns (changes, issues by number): push reconciles labels against the latter."""
    issues = {i["number"]: i for i in gh.json(
        "issue", "list", "-R", repo, "--state", "all", "--limit", "1000",
        "--json", "number,title,state,stateReason,assignees,labels,url")}
    names = {p["github"].lower(): hb.canon(p["name"]) for p in cfg["roster"]}
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
        # A pool pickup is an assignee GitHub has and we didn't push. The same assignee we
        # pushed means the lead just moved the task back to pool; push removes it.
        if is_pool(t.get("owner")) and i["assignees"]:
            # Two people can grab a pool issue in the same minute. AGENTS.md §3 and this
            # agree: the alphabetically first login keeps it, the rest step back.
            login = min((a["login"] for a in i["assignees"]), key=str.lower)
            if login.lower() != (t.get("issue_assignee") or "").lower() and login.lower() in names:
                changes.append((t["id"], {"owner": names[login.lower()], "issue_assignee": login}, "gh-assigned"))
    seen = cfg.setdefault("sync", {}).setdefault("seen_change_requests", [])
    for n, i in sorted(issues.items()):
        if i["state"] == "OPEN" and n not in seen and any(l["name"] == "change-request" for l in i["labels"]):
            text = f"change-request #{n}: {i['title']} — {i['url']}"
            if gh.dry:
                print("would deliver:", text)
                continue
            hb.deliver(LEAD_AGENT, text, message_id=f"cr-{repo.replace('/', '-')}-{n}")
            seen.append(n)
    return changes, issues


def push(tasks, cfg, gh, repo, failures, assignable, issues):
    """Each change is recorded the moment GitHub has it: a crash after `issue create` but
    before the record would make the next run create the issue again.

    assignable: lowercased logins GitHub will accept as assignees: collaborators who have
    accepted their invite."""
    deadlines = [d["name"] for d in cfg["deadlines"]]
    record = lambda *change: apply([change], gh.dry)
    waiting = set()

    def can_assign(who, t):
        if not who or who.lower() in assignable:
            return True
        if who not in waiting:
            waiting.add(who)
            print(f"warning: {hb.canon(t['owner'])} (@{who}) has not accepted the repo invite yet; "
                  "their issues stay unassigned until a sync after they accept.")
        return False

    for t in tasks:
        if t["status"] == "done":  # finished work is neither created nor re-briefed
            continue
        try:
            body = t.get("detail") or ""
            who, labels = target(t.get("owner"), cfg)
            milestone = deadline(body)
            if milestone not in deadlines:
                raise GhError(f"Deadline: {milestone!r} is not a deadline in hackathon.json "
                              f"(choose from {', '.join(deadlines)})")
            if "issue" not in t:
                assignee = who if can_assign(who, t) else None
                args = ["issue", "create", "-R", repo, "--title", t["title"],
                        "--label", ",".join(labels), "--milestone", milestone]
                if assignee:
                    args += ["--assignee", assignee]
                url = gh(*args, body=body).strip()
                if url:  # empty under --dry-run
                    try:
                        number = int(url.rsplit("/", 1)[1])
                    except (IndexError, ValueError):
                        raise GhError(f"unexpected output from gh issue create: {url!r}") from None
                    record(t["id"], {"issue": number, "issue_hash": digest(body), "issue_assignee": assignee,
                                     "issue_title": t["title"], "issue_milestone": milestone}, "gh-created")
                continue
            n = t["issue"]
            held = False  # the new brief is held back, so its title and deadline are too
            if digest(body) != t["issue_hash"]:
                remote = gh.json("issue", "view", n, "-R", repo, "--json", "body")["body"]
                if digest(remote) != t["issue_hash"]:
                    held = True
                    print(f"warning: #{n} ({t['id']}) was edited on GitHub; not overwriting. "
                          "Fold the edit into the hub task, then rerun.")
                else:
                    gh("issue", "edit", n, "-R", repo, body=body)
                    # The notice is owed until it is posted: a failed comment is retried
                    # next sync, or a teammate keeps working from the old brief.
                    record(t["id"], {"issue_hash": digest(body), "notice_pending": True}, "gh-updated")
                    t["notice_pending"] = True
            if t.get("notice_pending"):
                gh("issue", "comment", n, "-R", repo, body=UPDATED)
                record(t["id"], {"notice_pending": False}, "gh-notified")
            # A replan can retitle a task, move its deadline or change its owner; the issue
            # follows in one edit. Tasks recorded before these fields existed count as in step.
            args, fields = [], {}
            if n in issues:  # owner labels as GitHub has them now, not as we last sent them
                have = {l["name"] for l in issues[n]["labels"]} & OWNER_LABELS
                want = set(labels) & OWNER_LABELS
                for name in sorted(want - have):
                    args += ["--add-label", name]
                for name in sorted(have - want):
                    args += ["--remove-label", name]
            if not held and t["title"] != t.get("issue_title", t["title"]):
                args += ["--title", t["title"]]
                fields["issue_title"] = t["title"]
            if not held and milestone != t.get("issue_milestone", milestone):
                args += ["--milestone", milestone]
                fields["issue_milestone"] = milestone
            if (who or "").lower() != (t.get("issue_assignee") or "").lower() and can_assign(who, t):
                if t.get("issue_assignee"):
                    args += ["--remove-assignee", t["issue_assignee"]]
                if who:
                    args += ["--add-assignee", who]
                fields["issue_assignee"] = who
            if args:
                gh("issue", "edit", n, "-R", repo, *args)
                record(t["id"], fields, "gh-reconciled")
        except GhError as e:
            print(f"error: {t['id']}: {e}", file=sys.stderr)
            failures.append(t["id"])


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
        print(f"warning: {dest} not cloned; run `hub init-repo` on your clone")
    steps = []
    for p in cfg["roster"]:
        if not p.get("lead"):
            steps.append(("api", "-X", "PUT", f"repos/{repo}/collaborators/{p['github']}"))
    for label in ["task", "pool", "change-request", "submission", "question", *(f"agent:{a.lower()}" for a in HUB_AGENTS)]:
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
    branches = ("main", "integration") if ensure_integration(gh, repo, new, failures) else ("main",)
    protection = {"required_status_checks": None, "enforce_admins": False, "restrictions": None,
                  "required_pull_request_reviews": {"required_approving_review_count": 1,
                                                    "require_code_owner_reviews": True,
                                                    # a push after approval voids it, so main
                                                    # only gets what the lead actually reviewed
                                                    "dismiss_stale_reviews": True}}
    for branch in branches:
        try:
            gh("api", "-X", "PUT", f"repos/{repo}/branches/{branch}/protection", "--input", "-",
               stdin=json.dumps(protection))
        except GhError as e:
            print(f"error: branch protection ({branch}): {e}", file=sys.stderr)
            failures.append(f"branch protection {branch}")
    return new


def cmd_gh_sync(a):
    if not shutil.which("gh"):
        sys.exit("gh-sync: the gh CLI is not installed -- see https://cli.github.com")
    gh = Gh(a.dry_run)
    try:
        gh("auth", "status", write=False)
    except GhError as e:
        sys.exit(f"gh-sync: {e} -- check `gh auth login`")
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
    problems = check_config(cfg, project)
    if problems:
        sys.exit(f"gh-sync: fix {path}: " + "; ".join(problems))
    # The live /loop and a manual run can overlap; two pushes at once create every new
    # issue twice. Held until this process exits.
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
            # Provision only. Issues wait for the approved IDEA.md, HACKATHON.md and README
            # to be pushed: publishing them here would skip the lead's gate.
            init(cfg, gh, repo, failures, exists)
            print(f"provisioned {repo}. Push IDEA.md, HACKATHON.md and the README, "
                  f"then run: hub gh-sync --project {project}")
        else:
            changes, issues = pull(snapshot(project), cfg, gh, repo)
            apply(changes, a.dry_run)
            if not a.pull_only:
                assignable = {c["login"].lower() for c in gh.json("api", f"repos/{repo}/collaborators?per_page=100")}
                push(snapshot(project), cfg, gh, repo, failures, assignable, issues)
    except GhError as e:
        failures.append(str(e))
    if not a.dry_run:
        hb._write_json_atomic(config_path(project), cfg)
    if failures:
        sys.exit(f"gh-sync: {len(failures)} failed: {', '.join(failures)}")


def register(sub):
    g = sub.add_parser("gh-sync", help="push a hackathon's tasks to GitHub Issues, pull results back")
    g.add_argument("--project", help="the hackathon's project tag (default: $HUB_PROJECT)")
    g.add_argument("--init", action="store_true", help="first run: repo from template, invites, labels, milestones, protection")
    g.add_argument("--pull-only", action="store_true", help="only pull closed/assigned issues and change-requests")
    g.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    g.set_defaults(fn=cmd_gh_sync)
