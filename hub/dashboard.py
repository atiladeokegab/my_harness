"""Hub dashboard and local OTLP metrics sink: `hub dashboard [--port 8765]`.

Serves dashboard.html, /state.json and /files (what projects/ holds, read-only) on 127.0.0.1.

It never takes .board.lock. board.json is replaced by atomic rename, so reading it bare
sees the old snapshot or the new one, never half of either -- and a page polling every
5 seconds through board()'s exclusive lock would make five agents queue behind a browser.
"""

import html
import json
import re
import os
import socket
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

HERE = Path(__file__).resolve().parent
NAMED = list(dict.fromkeys([os.environ.get("HUB_LEAD") or "Zeus",  # the roster, as shell.sh and dispatch.py read it
                             *os.environ.get("HUB_CLAUDE_AGENTS", "Zeus Apollo Hermes Athena").split(),
                             *os.environ.get("HUB_CODEX_AGENTS", "Prometheus").split()]))
SILENT_AFTER = timedelta(hours=2)
RECENT_MAX = 100
# Permission prompts, as the two CLIs print them. A worker sitting on one looks exactly
# like a working one on the board: Prometheus sat on the Codex one for over two hours.
#
# Matched by SHAPE, not by words: the question alone on its line, then a numbered
# "1. Yes" option below it. Matching the words anywhere flagged two false alarms on the
# first live run -- a diff of a test fixture that quoted the prompt, and a shell command
# that grepped for it.
PROMPT_RX = re.compile(r"^\s*(Would you like to .*\?|Do you want to proceed\?|Do you want to allow .*\?)\s*$")
OPTION_RX = re.compile(r"^\s*[›❯>]?\s*1\.\s+Yes\b")
KIND_ORDER = {"waiting": 0, "blocked": 1, "stopped": 2, "silent": 3}


class BoardUnreadable(Exception):
    pass


def load(hub_dir):
    """(board, events). Raises BoardUnreadable; a torn last event line is skipped."""
    hub_dir = Path(hub_dir)
    try:
        board = json.loads((hub_dir / "board.json").read_text())
    except (OSError, ValueError) as e:
        raise BoardUnreadable(f"board.json: {e}") from e
    try:
        lines = (hub_dir / "events.jsonl").read_text().splitlines()
    except OSError:
        lines = []
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except ValueError:
            pass  # a write in progress; the next poll has it whole
    return board, events


def _agent(session):
    name = session[4:]
    return next((n for n in NAMED if n.lower() == name), name.title())


def alive():
    """({running agent names}, tmux_ok). tmux_ok False means "cannot tell", not "none"."""
    try:
        r = subprocess.run(["tmux", "list-sessions", "-F", "#S"], capture_output=True,
                           text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return set(), False
    if r.returncode != 0:
        return set(), False
    # hub-relay and hub-dashboard are the hub's own daemons, not agents.
    return {_agent(s) for s in r.stdout.split()
            if s.startswith("hub-") and s not in ("hub-relay", "hub-dashboard")}, True


def screens(running):
    """{agent: last 15 lines of its pane}. An unreadable pane is simply absent."""
    out = {}
    for name in running:
        try:
            r = subprocess.run(["tmux", "capture-pane", "-p", "-t", f"hub-{name.lower()}",
                                "-S", "-15"], capture_output=True, text=True, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0:
            out[name] = r.stdout
    return out


def _prompt(text):
    """The prompt line if the screen shows a live permission prompt, else None."""
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if PROMPT_RX.match(l) and any(OPTION_RX.match(n) for n in lines[i + 1:i + 16]):
            return l.strip()
    return None


def _when(s):
    return datetime.fromisoformat(s) if s else None


def _ago(delta):
    h, m = divmod(int(delta.total_seconds()) // 60, 60)
    return f"{h}h {m}m without activity"


def agent_outcomes(tasks, events, now):
    """Calendar-week completions and recorded run costs; attempts are board totals."""
    utc_now = now.astimezone(timezone.utc)
    week = utc_now.replace(hour=0, minute=0, second=0,
                           microsecond=0) - timedelta(days=utc_now.weekday())
    by_task = {t["id"]: t for t in tasks}
    outcome = {}

    def row(name):
        return outcome.setdefault(name, {"done_this_week": 0, "attempts": 0,
                                         "runs": 0, "cost_usd": None, "prs_merged": None})

    for task in tasks:
        if task.get("owner"):
            row(task["owner"])["attempts"] += task.get("attempts", 0)
    for event in events:
        at = _when(event.get("at"))
        if not at or at < week:
            continue
        if event.get("event") == "done" and event.get("by"):
            row(event["by"])["done_this_week"] += 1
        if event.get("event") != "note" or not (event.get("text") or "").startswith("hub_run: "):
            continue
        try:
            run = json.loads(event["text"][len("hub_run: "):])
        except ValueError:
            continue
        task = by_task.get(event.get("task"), {})
        name = task.get("agent") or task.get("owner") or event.get("by")
        if not name:
            continue
        agent = row(name)
        agent["runs"] += 1
        cost = run.get("total_cost_usd")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            agent["cost_usd"] = round((agent["cost_usd"] or 0) + cost, 6)
    return outcome


def merge_counts(hub_dir, tasks, now):
    """Count this week's recorded PR merges still active, attributed by project and issue."""
    utc_now = now.astimezone(timezone.utc)
    week = utc_now.replace(hour=0, minute=0, second=0,
                           microsecond=0) - timedelta(days=utc_now.weekday())
    owners = {(t.get("project"), str(t.get("issue"))): t.get("owner") for t in tasks
              if t.get("issue") is not None and t.get("owner")}
    counts = {}
    for path in (Path(hub_dir) / "projects").glob("*/live-state.json"):
        try:
            events = json.loads(path.read_text()).get("merge_events", [])
        except (OSError, ValueError, AttributeError):
            continue
        latest = {}
        for event in events:
            if not isinstance(event, dict) or event.get("event") not in ("merged", "reverted"):
                continue
            try:
                at = _when(event.get("at"))
            except (ValueError, TypeError):
                continue
            if at and at.tzinfo and isinstance(event.get("pr"), (int, str)):
                latest[event["pr"]] = (event, at)
        for event, at in latest.values():
            if event["event"] != "merged" or at < week:
                continue
            owner = owners.get((path.parent.name, str(event.get("issue"))))
            if owner:
                counts[owner] = counts.get(owner, 0) + 1
    return counts


def state(board, events, running, tmux_ok, screens, now, pr_counts=None):
    """Everything the page shows. Pure: same inputs, same answer."""
    tasks = board.get("tasks", [])
    claimed = [t for t in tasks if t.get("status") == "claimed"]
    needs = []

    for name, text in screens.items():
        line = _prompt(text)
        if line:
            # The task it is most likely on: its most recently touched claim.
            held = max((t for t in claimed if t.get("owner") == name),
                       key=lambda t: t.get("updated") or "", default=None)
            needs.append({"kind": "waiting", "agent": name, "task": held and held["id"],
                          "title": held["title"] if held else "", "why": line})

    for t in tasks:
        if t.get("status") == "blocked":
            notes = t.get("notes") or []
            needs.append({"kind": "blocked", "agent": t.get("owner"), "task": t["id"],
                          "title": t.get("title", ""), "why": notes[-1]["text"] if notes else ""})

    last_on = {}
    for e in events:
        if e.get("task", "-") != "-":
            last_on[e["task"]] = max(last_on.get(e["task"], ""), e.get("at", ""))
    waiting = {n["agent"] for n in needs if n["kind"] == "waiting"}
    for t in claimed:
        owner = t.get("owner")
        base = {"agent": owner, "task": t["id"], "title": t.get("title", "")}
        if tmux_ok and owner not in running:
            needs.append({"kind": "stopped", **base, "why": f"no hub-{(owner or '?').lower()} session"})
            continue
        if owner in waiting:
            continue
        last = _when(last_on.get(t["id"]) or t.get("updated"))
        if last and now - last >= SILENT_AFTER:
            needs.append({"kind": "silent", **base, "why": _ago(now - last)})
    needs.sort(key=lambda n: KIND_ORDER[n["kind"]])

    last_by = {}
    for e in events:
        last_by[e.get("by")] = max(last_by.get(e.get("by"), ""), e.get("at", ""))
    holders = sorted({t.get("owner") for t in claimed if t.get("owner")} - set(NAMED))
    outcomes = agent_outcomes(tasks, events, now)
    agents = [{"name": n, "running": n in running,
               "tasks": [t["id"] for t in claimed if t.get("owner") == n],
               "last_event_at": last_by.get(n) or None,
               **outcomes.get(n, {"done_this_week": 0, "attempts": 0, "runs": 0,
                                  "cost_usd": None, "prs_merged": None}),
               "prs_merged": pr_counts.get(n, 0) if pr_counts is not None else None}
              for n in NAMED + holders]

    shown = [{k: t.get(k) for k in ("id", "title", "status", "owner", "project", "deps",
                                     "detail", "notes")}
             for t in tasks if t.get("status") in ("open", "claimed", "blocked")]

    recent = []
    for e in reversed(events):
        if e.get("event") == "commit":
            continue
        text = e.get("text") or e.get("note") or e.get("reason") or ""
        recent.append({"at": e.get("at"), "by": e.get("by"), "event": e.get("event"),
                       "task": e.get("task"), "text": text.splitlines()[0] if text else ""})
        if len(recent) == RECENT_MAX:
            break

    return {"server_time": now.isoformat(timespec="seconds"), "needs_you": needs,
            "agents": agents, "tasks": shown, "recent": recent}


PLACEHOLDER = "<!doctype html><title>Hub dashboard</title><p>dashboard.html is not built yet.</p>"
PROJECT_RX = re.compile(r"^[\w-]+$")


# Phase view: projects/<project>/phases.json names each phase and its task ids; status is
# always the live board's, so the page never goes stale between conversations.
def phase_projects(hub_dir):
    return sorted(f.parent.name for f in (Path(hub_dir) / "projects").glob("*/phases.json"))


def phase_file(hub_dir, project):
    if not project or not PROJECT_RX.match(project):
        return None  # the name becomes a path: nothing that can leave projects/
    f = Path(hub_dir) / "projects" / project / "phases.json"
    return f if f.is_file() else None


def _row(t):
    notes = t.get("notes") or []
    return {"id": t["id"], "title": t.get("title", ""), "status": t.get("status"), "owner": t.get("owner"),
            "deps": t.get("deps") or [], "updated": t.get("updated"), "last_note": notes[-1] if notes else None}


def phases(board, spec, project):
    by_id = {t["id"]: t for t in board.get("tasks", [])}
    placed, out = set(), []
    for ph in spec.get("phases", []):
        rows = []
        for tid in ph.get("tasks", []):
            placed.add(tid)
            rows.append(_row(by_id[tid]) if tid in by_id else
                        {"id": tid, "title": "", "status": "missing", "owner": None, "deps": [], "updated": None,
                         "last_note": None})
        statuses = [r["status"] for r in rows]
        done = statuses.count("done")
        status = ("done" if rows and done == len(rows) else "blocked" if "blocked" in statuses
                  else "in progress" if done or "claimed" in statuses else "not started")
        out.append({"id": ph.get("id"), "name": ph.get("name"), "goal": ph.get("goal"),
                    "waiting_on_you": ph.get("waiting_on_you"), "status": status, "done": done,
                    "total": len(rows), "tasks": rows})
    unphased = [_row(t) for t in board.get("tasks", []) if t.get("project") == project and t["id"] not in placed]
    return {"title": spec.get("title", project), "project": project, "phases": out, "unphased": unphased}


# The Files page: what is worth opening in a browser, and the only types it will serve.
FILE_TYPES = {".pdf": "application/pdf", ".html": "text/html; charset=utf-8", ".png": "image/png",
              ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".md": "text/plain; charset=utf-8"}
FILES_MAX = 200


def project_file(hub_dir, rel):
    """The file under projects/ that rel names, or None. Resolved first, so ../, absolute
    paths and symlinks that leave projects/ all come out None."""
    root = (Path(hub_dir) / "projects").resolve()
    try:
        f = (root / rel).resolve()
        ok = f.is_relative_to(root) and f.suffix.lower() in FILE_TYPES and f.is_file()
    except (OSError, ValueError):
        return None
    return f if ok else None


def files_page(hub_dir):
    root = (Path(hub_dir) / "projects").resolve()
    found = []
    for d, dirs, names in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".") and x != "node_modules"]
        for n in names:
            f = Path(d) / n
            if f.suffix.lower() in FILE_TYPES and not f.is_symlink() and f.parent != root:
                found.append((f.stat().st_mtime, f.relative_to(root)))
    groups = {}
    for mtime, rel in sorted(found, reverse=True)[:FILES_MAX]:
        when = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        groups.setdefault(rel.parts[0], []).append(
            f'<li><a href="/files/{quote(rel.as_posix())}">{html.escape(rel.relative_to(rel.parts[0]).as_posix())}'
            f'</a> <span class="muted">{when}</span></li>')
    body = "".join(f"<h2>{html.escape(p)}</h2><ul>{''.join(rows)}</ul>" for p, rows in groups.items())
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            "<title>Hub files</title><style>:root{color-scheme:light dark;font:16px system-ui,sans-serif}"
            "body{max-width:1100px;margin:0 auto;padding:1rem}.muted{opacity:.75}</style>"
            f"<h1>Files</h1><p><a href=\"/\">Dashboard</a> · newest first, at most {FILES_MAX}</p>"
            + (body or "<p>Nothing under projects/ yet.</p>"))


def nav():
    """Links for the top of the main page. The review link only while `hub review` is listening."""
    port = int(os.environ.get("HUB_REVIEW_PORT", "8766"))
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
        review = f' · <a href="http://127.0.0.1:{port}/">Open review</a>'
    except OSError:
        review = ""
    return f'<p><a href="/factory">Factory outcomes</a> · <a href="/files">Files</a>{review}</p>'


def factory_page(board, events, now, pr_counts=None):
    outcomes = agent_outcomes(board.get("tasks", []), events, now)
    names = NAMED + sorted(set(outcomes) - set(NAMED))
    rows = []
    for name in names:
        item = outcomes.get(name, {})
        cost = item.get("cost_usd")
        cost_text = f"${cost:.2f}" if cost is not None else "—"
        prs = pr_counts.get(name, 0) if pr_counts is not None else item.get("prs_merged")
        pr_text = str(prs) if prs is not None else "—"
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
            name, item.get("done_this_week", 0), pr_text, item.get("attempts", 0),
            item.get("runs", 0), cost_text)) + "</tr>")
    return ("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            "<meta http-equiv='refresh' content='30'><title>Factory outcomes</title>"
            "<style>body{font:16px system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem}"
            "table{border-collapse:collapse;width:100%}th,td{padding:.7rem;border-bottom:1px solid #999;text-align:left}"
            "@media(max-width:700px){table{display:block;overflow-x:auto}}</style>"
            "<p><a href='/'>← Dashboard</a></p><h1>Factory outcomes</h1>"
            "<p>Week starts Monday UTC. Attempts are failed verification attempts on the board. "
            "Cost includes only runs that reported USD.</p>"
            "<table><thead><tr><th>Agent</th><th>Tasks done this week</th><th>PRs merged (not reverted)</th>"
            "<th>Attempts</th><th>Runs this week</th><th>Known cost this week</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def make_server(hub_dir, port):
    hub_dir = Path(hub_dir)
    metrics_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype, headers=()):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            for h in headers:
                self.send_header(*h)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != "/v1/metrics":
                return self.send(404, "not found", "text/plain; charset=utf-8")
            try:
                size = int(self.headers.get("Content-Length", ""))
            except ValueError:
                size = 0
            if size < 1 or size > 1_000_000:
                return self.send(413, "invalid metrics size", "text/plain; charset=utf-8")
            try:
                payload = json.loads(self.rfile.read(size))
            except ValueError:
                return self.send(400, "invalid metrics JSON", "text/plain; charset=utf-8")
            if not isinstance(payload, dict) or "resourceMetrics" not in payload:
                return self.send(400, "missing resourceMetrics", "text/plain; charset=utf-8")
            folder = hub_dir / "inbox" / "telemetry"
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = folder / f"metrics-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
            with metrics_lock:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, "w") as output:
                    output.write(json.dumps(payload, separators=(",", ":")) + "\n")
            return self.send(200, "{}", "application/json")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                page = HERE / "dashboard.html"
                text = page.read_text() if page.is_file() else PLACEHOLDER
                return self.send(200, text.replace("</h1>", "</h1>" + nav(), 1), "text/html; charset=utf-8")
            if path == "/factory":
                try:
                    board, events = load(hub_dir)
                except BoardUnreadable as error:
                    return self.send(503, str(error), "text/plain; charset=utf-8")
                now = datetime.now(timezone.utc)
                counts = merge_counts(hub_dir, board.get("tasks", []), now)
                return self.send(200, factory_page(board, events, now, counts),
                                 "text/html; charset=utf-8")
            if path == "/files":
                return self.send(200, files_page(hub_dir), "text/html; charset=utf-8")
            if path.startswith("/files/"):
                f = project_file(hub_dir, unquote(path[len("/files/"):]))
                if f:
                    return self.send(200, f.read_bytes(), FILE_TYPES[f.suffix.lower()],
                                     [("Content-Disposition", "inline")])
            if path == "/phases":
                page = HERE / "phases.html"
                return self.send(200, page.read_text() if page.is_file() else PLACEHOLDER,
                                 "text/html; charset=utf-8")
            if path == "/phases.json":
                project = (parse_qs(urlsplit(self.path).query).get("project") or [None])[0]
                if project is None:
                    return self.send(200, json.dumps({"projects": phase_projects(hub_dir)}), "application/json")
                f = phase_file(hub_dir, project)
                if not f:
                    return self.send(404, json.dumps({"error": f"no phases for {project!r}"}), "application/json")
                try:
                    board, _ = load(hub_dir)
                    spec = json.loads(f.read_text())
                except (BoardUnreadable, ValueError) as e:
                    return self.send(503, json.dumps({"error": str(e)}), "application/json")
                return self.send(200, json.dumps(phases(board, spec, project)), "application/json")
            if path == "/state.json":
                try:
                    board, events = load(hub_dir)
                except BoardUnreadable as e:
                    return self.send(503, json.dumps({"error": str(e)}), "application/json")
                running, tmux_ok = alive()
                now = datetime.now(timezone.utc)
                counts = merge_counts(hub_dir, board.get("tasks", []), now)
                body = state(board, events, running, tmux_ok, screens(running), now, counts)
                return self.send(200, json.dumps(body), "application/json")
            self.send(404, "not found", "text/plain; charset=utf-8")

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def cmd_dashboard(a):
    hub_dir = os.environ.get("HUB_DIR") or HERE
    try:
        httpd = make_server(hub_dir, a.port)
    except OSError as e:
        # The hub-dashboard session normally already runs it; --open then just opens.
        if a.open and _is_dashboard(a.port):
            _open(f"http://127.0.0.1:{a.port}/")
            return
        sys.exit(f"dashboard: cannot listen on 127.0.0.1:{a.port} ({e.strerror}); "
                 f"pick another with --port")
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"hub dashboard: {url}  (Ctrl-C to stop)", flush=True)
    if a.open:
        _open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def _is_dashboard(port):
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/state.json", timeout=3) as r:
            return "needs_you" in json.load(r)
    except (OSError, ValueError):
        return False


def _open(url):
    import review
    exe = review.browser()
    if not exe:
        print("no Chrome or Chromium found; open the URL yourself (or set HUB_BROWSER)", flush=True)
        return
    # A profile of its own that persists, so the page's localStorage (the project
    # filter, "since you last looked") survives closing the window.
    prof = Path.home() / ".config" / "hub-dashboard-browser"
    prof.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={prof}", "--no-first-run",
                      "--no-default-browser-check"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def register(sub):
    d = sub.add_parser("dashboard", help="web page and local metrics sink for hub activity")
    d.add_argument("--port", type=int, default=8765)
    d.add_argument("--open", action="store_true", help="open it in a browser window")
    d.set_defaults(fn=cmd_dashboard)
