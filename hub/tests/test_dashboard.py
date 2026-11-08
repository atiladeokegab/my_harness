"""Hub dashboard: the rules that decide what "needs you", and the server around them.

Numbered as in the dashboard's design notes.

    uv run python tests/test_dashboard.py
"""

import fcntl
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HUB))
import dashboard  # noqa: E402


def sockets_allowed():
    """The Codex sandbox (Prometheus) refuses socket() outright, even on 127.0.0.1."""
    try:
        socket.socket().close()
        return True
    except OSError:
        return False


needs_sockets = unittest.skipUnless(sockets_allowed(), "no sockets here (the Codex sandbox)")

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat(timespec="seconds")


def task(id, status, owner=None, project="hub", notes=(), updated=NOW, deps=()):
    return {"id": id, "title": f"title {id}", "status": status, "owner": owner,
            "project": project, "deps": list(deps), "detail": "d", "created": iso(NOW),
            "updated": iso(updated), "notes": [{"at": iso(NOW), "by": "Zeus", "text": n}
                                                 for n in notes]}


def ev(at, by, event, task="-", **extra):
    return {"at": iso(at), "by": by, "event": event, "task": task, **extra}


def run(tasks, events=(), alive=("Zeus", "Prometheus"), tmux_ok=True, screens=None):
    return dashboard.state({"next_id": 99, "tasks": list(tasks)}, list(events), set(alive),
                           tmux_ok, screens or {}, NOW)


class TestRules(unittest.TestCase):
    def test_1_blocked_shows_its_last_note(self):
        s = run([task("T-1", "blocked", "Zeus", notes=["first", "needs the human"])])
        self.assertEqual([(n["kind"], n["task"], n["why"]) for n in s["needs_you"]],
                         [("blocked", "T-1", "needs the human")])

    def test_1b_waiting_on_a_prompt_comes_first(self):
        screen = ("  git add x\n  Would you like to run the following command?\n"
                  "  Environment: local\n  $ git add x\n› 1. Yes, proceed (y)\n  2. No")
        s = run([task("T-1", "blocked", "Zeus", notes=["x"]),
                 task("T-0", "claimed", "Prometheus", updated=NOW - timedelta(hours=1)),
                 task("T-2", "claimed", "Prometheus", updated=NOW)],
                screens={"Prometheus": screen, "Zeus": "all quiet\n$ "})
        self.assertEqual(s["needs_you"][0]["kind"], "waiting")
        self.assertEqual(s["needs_you"][0]["agent"], "Prometheus")
        self.assertEqual(s["needs_you"][0]["task"], "T-2")
        self.assertIn("Would you like to run", s["needs_you"][0]["why"])
        self.assertEqual([n["kind"] for n in s["needs_you"]], ["waiting", "blocked"])

    def test_1b_claude_prompts_count_and_ordinary_output_does_not(self):
        for text, want in (("Do you want to proceed?\n❯ 1. Yes", ["waiting"]),
                           ("Do you want to allow this connection?\n❯ 1. Yes\n  2. No", ["waiting"]),
                           ("I would like to refactor this later.", []),
                           # The two false alarms from the first live run, verbatim:
                           ('4 + {"kind": "waiting", "task": "T-101", "why": '
                            '"Would you like to run the following command?"},', []),
                           ("P=$(tmux capture-pane -p -t hub-prometheus | grep -cE "
                            "\"Would you like to\"); if [", []),
                           ("  Would you like to run the following command?\n  (no options below)", []),
                           # A real Codex prompt: blank lines push "1. Yes" 10 lines down.
                           ("  Would you like to run the following command?\n\n  Environment: local\n\n"
                            "  Reason: Allow a temporary localhost HTTP server so I can smoke-test.\n\n"
                            "  $ cp a b;\n  python3 -m http.server 18765 --bind 127.0.0.1 &\n\n"
                            "› 1. Yes, proceed (y)\n  2. Yes, and don't ask again (p)", ["waiting"])):
            s = run([], screens={"Zeus": text})
            self.assertEqual([n["kind"] for n in s["needs_you"]], want, text)

    def test_2_stopped_only_when_tmux_could_be_checked(self):
        t = task("T-3", "claimed", "Hermes", updated=NOW)
        self.assertEqual([n["kind"] for n in run([t])["needs_you"]], ["stopped"])
        self.assertEqual(run([t], tmux_ok=False)["needs_you"], [])

    def test_3_silent_at_two_hours_by_the_last_event_on_that_task(self):
        t = task("T-4", "claimed", "Prometheus", updated=NOW - timedelta(days=1))
        other = ev(NOW - timedelta(minutes=1), "Prometheus", "note", "T-9")  # not this task
        for age, want in ((timedelta(hours=2, minutes=1), ["silent"]),
                          (timedelta(hours=1, minutes=59), [])):
            s = run([t], [ev(NOW - age, "Zeus", "note", "T-4"), other])
            self.assertEqual([n["kind"] for n in s["needs_you"]], want, age)

    def test_3_silent_falls_back_to_updated_with_no_events(self):
        t = task("T-4", "claimed", "Prometheus", updated=NOW - timedelta(hours=3))
        self.assertEqual([n["kind"] for n in run([t])["needs_you"]], ["silent"])

    def test_4_done_tasks_and_commit_events_are_left_out(self):
        s = run([task("T-5", "done", "Zeus"), task("T-6", "open")],
                [ev(NOW, "board", "commit"), ev(NOW, "Zeus", "claimed", "T-6")])
        self.assertEqual([t["id"] for t in s["tasks"]], ["T-6"])
        self.assertEqual([e["event"] for e in s["recent"]], ["claimed"])

    def test_4_recent_is_newest_first_with_first_line_of_text(self):
        s = run([], [ev(NOW - timedelta(minutes=5), "Zeus", "notify", to="P", text="one\ntwo"),
                     ev(NOW, "Zeus", "blocked", "T-1", reason="why\nmore")])
        self.assertEqual([(e["event"], e["text"]) for e in s["recent"]],
                         [("blocked", "why"), ("notify", "one")])

    def test_5_agent_rows_named_five_then_other_holders(self):
        s = run([task("T-7", "claimed", "Testagent"), task("T-8", "claimed", "Prometheus")],
                [ev(NOW, "Prometheus", "claimed", "T-8"), ev(NOW, "Unknown", "note", "T-1")])
        rows = s["agents"]
        self.assertEqual([a["name"] for a in rows],
                         ["Zeus", "Apollo", "Hermes", "Athena", "Prometheus", "Testagent"])
        p = rows[4]
        self.assertEqual((p["running"], p["tasks"], p["last_event_at"]), (True, ["T-8"], iso(NOW)))
        self.assertFalse(rows[1]["running"])


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "board.json").write_text(json.dumps({"next_id": 2, "tasks": [task("T-1", "open")]}))

    def test_6_a_half_written_last_event_line_is_skipped(self):
        (self.dir / "events.jsonl").write_text(json.dumps(ev(NOW, "Zeus", "created", "T-1"))
                                               + '\n{"at": "2026-09-21T12:00', encoding="utf-8")
        board, events = dashboard.load(self.dir)
        self.assertEqual(len(board["tasks"]), 1)
        self.assertEqual([e["event"] for e in events], ["created"])

    def test_7_missing_board_is_unreadable_not_a_crash(self):
        (self.dir / "board.json").unlink()
        with self.assertRaises(dashboard.BoardUnreadable):
            dashboard.load(self.dir)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PHASES = {"title": "P", "phases": [
    {"id": "0", "name": "Built", "goal": "g0", "tasks": ["T-1", "T-2"], "waiting_on_you": None},
    {"id": "1", "name": "Going", "goal": "g1", "tasks": ["T-3", "T-4"], "waiting_on_you": "rule the sheet"},
    {"id": "2", "name": "Later", "goal": "g2", "tasks": ["T-5", "T-9"], "waiting_on_you": None}]}


class TestPhases(unittest.TestCase):
    def test_phase_status_comes_from_the_live_board(self):
        tasks = [task("T-1", "done", project="p"), task("T-2", "done", project="p"),
                 task("T-3", "done", project="p"), task("T-4", "claimed", "Zeus", project="p", notes=["old", "latest"]),
                 task("T-5", "open", project="p"), task("T-6", "open", project="p"), task("T-7", "open", project="other")]
        out = dashboard.phases({"tasks": tasks}, PHASES, "p")
        self.assertEqual([(p["name"], p["status"], p["done"], p["total"]) for p in out["phases"]],
                         [("Built", "done", 2, 2), ("Going", "in progress", 1, 2), ("Later", "not started", 0, 2)])
        going = out["phases"][1]
        self.assertEqual(going["waiting_on_you"], "rule the sheet")
        self.assertEqual(going["tasks"][1]["last_note"]["text"], "latest")
        self.assertEqual(out["phases"][2]["tasks"][1]["status"], "missing")  # T-9 is not on the board
        self.assertEqual([t["id"] for t in out["unphased"]], ["T-6"])  # this project's, never another's

    def test_a_blocked_task_blocks_its_phase(self):
        tasks = [task("T-3", "done", project="p"), task("T-4", "blocked", project="p")]
        self.assertEqual(dashboard.phases({"tasks": tasks}, PHASES, "p")["phases"][1]["status"], "blocked")

    def test_project_names_cannot_leave_the_projects_folder(self):
        hub = Path(tempfile.mkdtemp())
        (hub / "projects" / "p").mkdir(parents=True)
        (hub / "projects" / "p" / "phases.json").write_text(json.dumps(PHASES))
        self.assertEqual(dashboard.phase_projects(hub), ["p"])
        self.assertIsNotNone(dashboard.phase_file(hub, "p"))
        for bad in ("../p", "p/../../x", "", "q"):
            self.assertIsNone(dashboard.phase_file(hub, bad))


@needs_sockets
class Served(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "board.json").write_text(json.dumps({"next_id": 2, "tasks": [task("T-1", "open")]}))
        (self.dir / "events.jsonl").write_text("")
        self.httpd = dashboard.make_server(self.dir, 0)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.url + path, timeout=5) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            e.close()
            return e.code, e.headers.get("Content-Type", ""), body


class TestServer(Served):
    def test_phases_page_and_json(self):
        (self.dir / "projects" / "p").mkdir(parents=True)
        (self.dir / "projects" / "p" / "phases.json").write_text(json.dumps(PHASES))
        code, ctype, body = self.get("phases.json")
        self.assertEqual((code, json.loads(body)), (200, {"projects": ["p"]}))
        code, ctype, body = self.get("phases.json?project=p")
        self.assertEqual((code, json.loads(body)["title"]), (200, "P"))
        self.assertEqual(self.get("phases.json?project=..%2Fp")[0], 404)
        code, ctype, body = self.get("phases")
        self.assertEqual((code, ctype.split(";")[0]), (200, "text/html"))

    def test_7_missing_board_is_a_503_with_the_reason(self):
        (self.dir / "board.json").unlink()
        code, _, body = self.get("state.json")
        self.assertEqual(code, 503)
        self.assertIn("board.json", json.loads(body)["error"])

    def test_8_serves_the_page_and_the_state(self):
        code, ctype, _ = self.get("")
        self.assertEqual((code, ctype.split(";")[0]), (200, "text/html"))
        code, ctype, body = self.get("state.json")
        self.assertEqual((code, ctype.split(";")[0]), (200, "application/json"))
        self.assertEqual([t["id"] for t in json.loads(body)["tasks"]], ["T-1"])
        self.assertEqual(self.get("../board.json")[0], 404)

    def test_10_never_takes_the_board_lock(self):
        with open(self.dir / ".board.lock", "a") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            start = time.monotonic()
            code, _, _ = self.get("state.json")
            self.assertEqual(code, 200)
            self.assertLess(time.monotonic() - start, 1.0)


class TestFiles(Served):
    def setUp(self):
        super().setUp()
        self.p = self.dir / "projects" / "p"
        (self.p / "sub").mkdir(parents=True)
        (self.p / "sub" / "a b.pdf").write_bytes(b"%PDF-1.4 x")
        (self.p / "notes.md").write_text("# hi")
        (self.p / "phases.json").write_text("{}")
        (self.dir / "secret.md").write_text("outside")
        self.out = Path(tempfile.mkdtemp())
        (self.out / "far.md").write_text("far away")
        (self.p / "link.md").symlink_to(self.dir / "secret.md")
        (self.p / "dirlink").symlink_to(self.out)

    def test_serves_a_pdf_inline(self):
        with urllib.request.urlopen(self.url + "files/p/sub/a%20b.pdf", timeout=5) as r:
            self.assertEqual((r.status, r.headers["Content-Type"], r.read()),
                             (200, "application/pdf", b"%PDF-1.4 x"))
            self.assertEqual(r.headers["Content-Disposition"], "inline")
        code, ctype, body = self.get("files/p/notes.md")
        self.assertEqual((code, ctype.split(";")[0], body), (200, "text/plain", b"# hi"))

    def test_refuses_anything_outside_projects(self):
        for bad in ("files/p/../../secret.md", "files/p/%2e%2e/%2e%2e/secret.md", "files/%2e%2e/secret.md",
                    f"files/{self.out}/far.md", f"files/{str(self.out).replace('/', '%2F')}/far.md",
                    "files/p/link.md", "files/p/dirlink/far.md", "files/p/phases.json", "files/p",
                    "files/p/sub", "files/p/missing.md"):
            self.assertEqual(self.get(bad)[0], 404, bad)

    def test_index_lists_files_newest_first(self):
        os.utime(self.p / "notes.md", (1, 1))
        code, ctype, body = self.get("files")
        page = body.decode()
        self.assertEqual((code, ctype.split(";")[0]), (200, "text/html"))
        self.assertIn('href="/files/p/sub/a%20b.pdf"', page)
        self.assertLess(page.index("a%20b.pdf"), page.index("notes.md"))
        for hidden in ("phases.json", "link.md", "far.md"):
            self.assertNotIn(hidden, page)

    def test_main_page_links_files_and_a_live_review(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            port = s.getsockname()[1]
            os.environ["HUB_REVIEW_PORT"] = str(port)
            try:
                page = self.get("")[2].decode()
                self.assertIn('href="/files"', page)
                self.assertIn(f'href="http://127.0.0.1:{port}/"', page)
            finally:
                del os.environ["HUB_REVIEW_PORT"]
        os.environ["HUB_REVIEW_PORT"] = str(port)
        try:
            self.assertNotIn("Open review", self.get("")[2].decode())
        finally:
            del os.environ["HUB_REVIEW_PORT"]


@needs_sockets
class TestCommandLine(unittest.TestCase):
    def test_9_port_in_use_is_one_line_not_a_traceback(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            port = s.getsockname()[1]
            env = dict(os.environ, HUB_DIR=tempfile.mkdtemp())
            env.pop("HUB_AGENT", None)
            env.pop("HUB_PROJECT", None)
            r = subprocess.run([sys.executable, str(HUB / "board.py"), "dashboard", "--port", str(port)],
                               capture_output=True, text=True, env=env, timeout=10)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("--port", r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)


if __name__ == "__main__":
    unittest.main()
