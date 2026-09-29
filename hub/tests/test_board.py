#!/usr/bin/env python3
"""Regression tests for board.py. Run: python3 tests/test_board.py"""

import argparse
import contextlib
import fcntl
import importlib.util
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BOARD_PY = ROOT / "board.py"


class BoardCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hub-board-test-")
        self.root = Path(self.temp.name)
        self.write_board({"next_id": 1, "tasks": []})

    def tearDown(self):
        self.temp.cleanup()

    def write_board(self, data):
        (self.root / "board.json").write_text(json.dumps(data) + "\n")

    def read_board(self):
        return json.loads((self.root / "board.json").read_text())

    def run_hub(self, *args, agent="Zeus", project=None, stdin=None):
        env = {k: v for k, v in os.environ.items()
               if k not in ("HUB_DIR", "HUB_AGENT", "HUB_PROJECT")}
        env.update(HUB_DIR=str(self.root), HUB_AGENT=agent)
        if project:
            env["HUB_PROJECT"] = project
        return subprocess.run(
            [str(BOARD_PY), *map(str, args)], env=env, text=True, capture_output=True,
            input=stdin,
        )

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def load_module(self):
        name = f"board_under_test_{id(self)}_{os.getpid()}"
        spec = importlib.util.spec_from_file_location(name, BOARD_PY)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, {"HUB_DIR": str(self.root), "HUB_AGENT": "Zeus"}):
            spec.loader.exec_module(module)
        return module

    def make_claimed(self, owner="Zeus"):
        self.assert_ok(self.run_hub("new", "work", "--owner", owner))
        self.assert_ok(self.run_hub("claim", "1", agent=owner))

    def events(self):
        path = self.root / "events.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_state_machine_ownership_force_and_double_done(self):
        self.assert_ok(self.run_hub("new", "assigned", "--owner", "Zeus"))
        stolen = self.run_hub("claim", "1", agent="Hermes")
        self.assertNotEqual(stolen.returncode, 0, "an open task assigned to Zeus was stolen")
        self.assert_ok(self.run_hub("claim", "1", agent="Zeus"))
        takeover = self.run_hub("claim", "1", "--force", agent="Hermes")
        self.assert_ok(takeover)
        self.assertTrue(any(e.get("forced") for e in self.events() if e["event"] == "claimed"))
        self.assert_ok(self.run_hub("done", "1", agent="Hermes"))
        again = self.run_hub("done", "1", agent="Hermes")
        self.assertNotEqual(again.returncode, 0)

        self.assert_ok(self.run_hub("new", "not claimed"))
        self.assertNotEqual(self.run_hub("done", "2", agent="Zeus").returncode, 0)

    def test_next_shows_assigned_work_outside_the_scope(self):
        """Zeus, 2026-09-21: a project-scoped Prometheus never saw T-101..T-103."""
        self.assert_ok(self.run_hub("new", "free here", "--project", "webapp"))
        self.assert_ok(self.run_hub("new", "yours there", "--project", "hub", "--owner", "P"))
        r = self.run_hub("next", "--project", "webapp", agent="P")
        self.assert_ok(r)
        self.assertIn("free here", r.stdout)
        self.assertIn("also assigned to you in other projects", r.stdout)
        self.assertIn("yours there", r.stdout)
        self.assert_ok(self.run_hub("claim", "1", agent="Q"))
        r = self.run_hub("next", "--project", "webapp", agent="P")
        self.assertIn("yours there", r.stdout.splitlines()[0])

    def test_vertical_creation_and_markers_leave_ordinary_tasks_unchanged(self):
        self.assert_ok(self.run_hub("new", "area", "--vertical", "--owner", "Zeus"))
        self.assert_ok(self.run_hub("new", "ordinary", "--owner", "Zeus"))
        vertical, ordinary = self.read_board()["tasks"]
        self.assertEqual(vertical["kind"], "vertical")
        self.assertNotIn("kind", ordinary)
        listed = self.run_hub("list")
        self.assert_ok(listed)
        self.assertIn("▣ T-001  area", listed.stdout)
        self.assertNotIn("▣ T-002", listed.stdout)
        self.assertIn("▣ T-001  [open]", self.run_hub("show", "1").stdout)
        self.assertNotIn("▣", self.run_hub("show", "2").stdout)

    def test_vertical_done_refuses_open_children_even_with_force(self):
        (self.root / "projects" / "hk").mkdir(parents=True)
        (self.root / "projects" / "hk" / "hackathon.json").write_text(json.dumps(HK))
        vertical = task("T-001", "hk", issue=10, status="claimed", owner="Alex")
        vertical["kind"] = "vertical"
        first = task("T-002", "hk", issue=11, owner="Alex")
        second = task("T-003", "hk", issue=12, status="blocked", owner="Alex")
        first["parent"] = second["parent"] = "T-001"
        self.write_board({"next_id": 4, "tasks": [vertical, first, second]})
        for flags in ((), ("--force",)):
            refused = self.run_hub("done", "10", *flags, project="hk", agent="Alex")
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("#10 still has open tasks: #11, #12", refused.stdout + refused.stderr)
            self.assertEqual(self.read_board()["tasks"][0]["status"], "claimed")
        data = self.read_board()
        data["tasks"][1]["status"] = data["tasks"][2]["status"] = "done"
        self.write_board(data)
        self.assert_ok(self.run_hub("done", "10", project="hk", agent="Alex"))

    def test_vertical_without_children_and_ordinary_task_can_finish(self):
        self.assert_ok(self.run_hub("new", "area", "--vertical", "--owner", "Zeus"))
        self.assert_ok(self.run_hub("new", "ordinary", "--owner", "Zeus"))
        for n in (1, 2):
            self.assert_ok(self.run_hub("claim", n))
            self.assert_ok(self.run_hub("done", n))

    def test_cross_agent_note_is_deliberately_allowed(self):
        self.make_claimed("Zeus")
        self.assert_ok(self.run_hub("note", "1", "peer review", agent="Athena"))
        self.assertEqual(self.read_board()["tasks"][0]["notes"][0]["by"], "Athena")

    def test_dependency_validation_and_normalization(self):
        self.assertNotEqual(self.run_hub("new", "bad", "--dep", "999").returncode, 0)
        self.assertNotEqual(self.run_hub("new", "self", "--dep", "1").returncode, 0)
        self.assert_ok(self.run_hub("new", "base"))
        self.assert_ok(self.run_hub("new", "dependent", "--dep", "1"))
        self.assertEqual(self.read_board()["tasks"][1]["deps"], ["T-001"])

        data = self.read_board()
        data["tasks"][0]["deps"] = ["T-002"]
        self.write_board(data)
        cycle = self.run_hub("new", "reaches cycle", "--dep", "1")
        self.assertNotEqual(cycle.returncode, 0)
        self.assertIn("cycle", cycle.stderr)

    def test_agent_names_are_safe_and_case_canonical(self):
        traversal_target = self.root / "escaped.jsonl"
        absolute_target = self.root / "absolute-escaped.jsonl"
        for bad in ("../escaped", str(absolute_target.with_suffix(""))):
            result = self.run_hub("notify", bad, "nope")
            self.assertNotEqual(result.returncode, 0)
        self.assertFalse(traversal_target.exists())
        self.assertFalse(absolute_target.exists())
        self.assert_ok(self.run_hub("notify", "zeus", "lower"))
        self.assert_ok(self.run_hub("notify", "ZEUS", "upper"))
        files = list((self.root / "inbox").glob("*.jsonl"))
        self.assertEqual([f.name for f in files], ["Zeus.jsonl"])
        self.assertEqual(len(files[0].read_text().splitlines()), 2)

    def test_notify_hint_is_universal_and_shell_quoted(self):
        result = self.run_hub("new", "it's $ready", "--owner", "Prometheus")
        self.assert_ok(result)
        self.assertIn("hubmsg", result.stdout)
        self.assertNotIn("SendMessage", result.stdout)
        self.assertIn("Prometheus", result.stdout)

    def test_unknown_identity_cannot_own_a_task(self):
        self.assert_ok(self.run_hub("new", "work"))
        refused = self.run_hub("claim", "1", "--as", "Unknown")
        self.assertNotEqual(refused.returncode, 0, "a session with no identity became an owner")
        self.assertEqual(self.read_board()["tasks"][0]["status"], "open")

    def test_events_task_filter_accepts_every_id_spelling(self):
        self.assert_ok(self.run_hub("new", "work"))
        for spelling in ("1", "t-1", "T-001"):
            out = self.run_hub("events", "--task", spelling)
            self.assert_ok(out)
            self.assertIn("T-001", out.stdout, f"--task {spelling} matched nothing")

    def test_events_reader_never_truncates_an_append_in_progress(self):
        self.assert_ok(self.run_hub("new", "work"))
        path = self.root / "events.jsonl"
        with open(path, "a") as f:
            f.write('{"at": "x", "by": "Zeus", "event": "note", "task": "T-0')  # half-written
        before = path.read_bytes()
        self.assert_ok(self.run_hub("events"))
        self.assertEqual(path.read_bytes(), before, "a lock-free reader truncated the ledger")

    def test_ping_hint_reuses_the_queued_message(self):
        result = self.run_hub("new", "handoff", "--owner", "Prometheus")
        self.assert_ok(result)
        match = re.search(r"--id (\S+)$", result.stdout, re.M)
        self.assertIsNotNone(match, result.stdout)
        # What running the printed hubmsg hint does for its durable half:
        self.assert_ok(self.run_hub("notify", "Prometheus", "handoff", "--message-id", match.group(1)))
        inbox = self.load_module().read_msgs(self.root / "inbox" / "Prometheus.jsonl")
        self.assertEqual(len(inbox), 1, f"the hint queued the message twice: {inbox}")

    def test_durable_message_receive_is_idempotent(self):
        mid = "msg-123"
        self.assert_ok(self.run_hub("notify", "Zeus", "do the work", "--message-id", mid, agent="Hermes"))
        first = self.run_hub("receive", mid, agent="Zeus")
        self.assert_ok(first)
        self.assertIn("do the work", first.stdout)
        second = self.run_hub("receive", mid, agent="Zeus")
        self.assert_ok(second)
        self.assertIn("already received", second.stdout)
        self.assert_ok(self.run_hub("notify", "Zeus", "do the work", "--message-id", mid, agent="Hermes"))
        records = [m for m in self.load_module().read_msgs(self.root / "inbox" / "Zeus.jsonl") if m.get("id") == mid]
        self.assertEqual(len(records), 1)
        self.assert_ok(self.run_hub("inbox", "--clear", agent="Zeus"))
        self.assertFalse((self.root / "inbox" / ".received" / "Zeus" / mid).exists())
        self.assertNotEqual(self.run_hub("receive", mid, agent="Zeus").returncode, 0)

    def test_atomic_consume_preserves_delivery_inside_read_window(self):
        board = self.load_module()
        board.deliver("Zeus", "before")
        original = board.read_msgs

        def inject(path):
            board.deliver("Zeus", "during-clear")
            return original(path)

        args = argparse.Namespace(agent=None, as_agent="Zeus", clear=True)
        with mock.patch.object(board, "read_msgs", side_effect=inject), contextlib.redirect_stdout(io.StringIO()):
            board.cmd_inbox(args)
        remaining = board.read_msgs(self.root / "inbox" / "Zeus.jsonl")
        self.assertEqual([m["text"] for m in remaining], ["during-clear"])

    def test_torn_trailing_inbox_line_is_ignored(self):
        inbox = self.root / "inbox"
        inbox.mkdir()
        (inbox / "Zeus.jsonl").write_text('{"at":"now","text":"good"}\n{"at":')
        result = self.run_hub("inbox")
        self.assert_ok(result)
        self.assertIn("good", result.stdout)

    def test_concurrent_deliverers_and_consumers_lose_no_messages(self):
        tokens = [f"mail-{i:03d}-unique" for i in range(40)]

        def send(token):
            return ("send", self.run_hub("notify", "Zeus", token, agent="Hermes"))

        def clear(_):
            return ("clear", self.run_hub("inbox", "--clear", agent="Zeus"))

        jobs = [(send, token) for token in tokens] + [(clear, i) for i in range(12)]
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda job: job[0](job[1]), jobs))
        observed = ""
        for kind, result in results:
            self.assert_ok(result)
            if kind == "clear":
                observed += result.stdout
        final = self.run_hub("inbox", agent="Zeus")
        self.assert_ok(final)
        observed += final.stdout
        missing = [token for token in tokens if token not in observed]
        self.assertEqual(missing, [], f"messages lost during concurrent clear: {missing}")

    def test_concurrent_writers_serialize_without_lost_ids(self):
        def create(i):
            return self.run_hub("new", f"work-{i}", agent=f"Agent{i % 4}")

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(create, range(24)))
        for result in results:
            self.assert_ok(result)
        tasks = self.read_board()["tasks"]
        self.assertEqual(len(tasks), 24)
        self.assertEqual(len({t["id"] for t in tasks}), 24)

    def test_lock_wait_is_bounded_and_actionable(self):
        board = self.load_module()
        board.LOCK_TIMEOUT = 0.05
        with open(board.LOCK, "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(SystemExit) as caught:
                with board.board():
                    pass
        self.assertIn("probably hung", str(caught.exception))

    def test_schema_migration_and_journal_first_fault(self):
        board = self.load_module()
        with board.board(write=True) as (data, events):
            data["tasks"].append({"id": "T-001"})
            board.log(events, "Zeus", "created", "T-001")
        self.assertEqual(self.read_board()["schema_version"], board.SCHEMA_VERSION)

        snapshot_before = self.read_board()
        real_replace = board.os.replace

        def crash_on_snapshot(src, dst):
            if dst == board.BOARD:
                raise OSError("injected crash after journal")
            return real_replace(src, dst)

        with mock.patch.object(board.os, "replace", side_effect=crash_on_snapshot):
            with self.assertRaises(OSError):
                with board.board(write=True) as (data, events):
                    data["tasks"].append({"id": "T-002"})
                    board.log(events, "Zeus", "created", "T-002")
        self.assertEqual(self.read_board(), snapshot_before)
        self.assertTrue(any(e.get("task") == "T-002" for e in self.events()))
        self.assertTrue(Path(board.WAL).exists())

        # The next reader automatically applies the journal-committed WAL; no manual
        # ledger/snapshot reconciliation is required.
        with board.board() as (recovered, _):
            self.assertEqual(recovered["tasks"][-1]["id"], "T-002")
        self.assertFalse(Path(board.WAL).exists())
        self.assertEqual(self.read_board()["tasks"][-1]["id"], "T-002")

    def test_uncommitted_and_torn_journal_transaction_is_discarded(self):
        board = self.load_module()
        original = self.read_board()
        candidate = {**original, "tasks": [{"id": "T-999"}]}
        txid = "interrupted-transaction"
        Path(board.WAL).write_text(json.dumps({"txid": txid, "board": candidate}) + "\n")
        Path(board.EVENTS).write_bytes(
            (json.dumps({"at": board.now(), "by": "Zeus", "event": "created",
                         "task": "T-999", "txid": txid}) + "\n{\"torn\":").encode()
        )

        with board.board() as (recovered, _):
            self.assertEqual(recovered, {**original, "schema_version": board.SCHEMA_VERSION})

        self.assertFalse(Path(board.WAL).exists())
        records = board.read_events()
        self.assertTrue(any(e.get("event") == "abort" and e.get("txid") == txid
                            for e in records))
        args = argparse.Namespace(task=None, tail=30)
        shown = io.StringIO()
        with contextlib.redirect_stdout(shown):
            board.cmd_events(args)
        self.assertNotIn("T-999", shown.getvalue())


class TestAssign(BoardCase):
    def test_an_open_task_changes_owner_and_the_ledger_records_it(self):
        self.assert_ok(self.run_hub("new", "work", "--owner", "Apollo"))
        tid = self.read_board()["tasks"][0]["id"]
        self.assert_ok(self.run_hub("assign", tid, "Prometheus"))
        t = self.read_board()["tasks"][0]
        self.assertEqual((t["owner"], t["status"]), ("Prometheus", "open"))
        self.assertIn("assigned", [e["event"] for e in self.events()])

    def test_a_claimed_task_needs_force(self):
        self.make_claimed("Zeus")
        tid = self.read_board()["tasks"][0]["id"]
        r = self.run_hub("assign", tid, "Prometheus")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.read_board()["tasks"][0]["owner"], "Zeus")
        self.assert_ok(self.run_hub("assign", tid, "Prometheus", "--force"))
        t = self.read_board()["tasks"][0]
        self.assertEqual((t["owner"], t["status"]), ("Prometheus", "open"))


def task(tid, project, issue=None, status="open", owner="Zeus", deps=(), detail=None):
    t = {"id": tid, "title": f"title {tid}", "status": status, "owner": owner,
         "deps": list(deps), "created_by": "Zeus", "created": "2026-09-28T00:00:00+00:00",
         "updated": "2026-09-28T00:00:00+00:00", "notes": [], "project": project,
         "detail": detail if detail is not None else f"Context: {tid}\nDeadline:     code freeze"}
    if issue is not None:
        t["issue"] = issue
    return t


HK = {"repo": "o/hk", "timezone": "Europe/London",
      "deadlines": [{"name": "code freeze", "at": "2026-10-04T14:00:00Z"},
                    {"name": "submit", "at": "2026-10-04T15:00:00Z"}],
      "roster": [{"name": "Alex", "github": "lead-gh", "lead": True}]}


class TestIssueNumbers(unittest.TestCase):
    tearDown = BoardCase.tearDown
    write_board = BoardCase.write_board
    read_board = BoardCase.read_board
    run_hub = BoardCase.run_hub
    assert_ok = BoardCase.assert_ok
    events = BoardCase.events

    def setUp(self):
        BoardCase.setUp(self)
        for name in ("hk", "hk2"):
            (self.root / "projects" / name).mkdir(parents=True)
            (self.root / "projects" / name / "hackathon.json").write_text(json.dumps(HK))
        self.write_board({"next_id": 11, "tasks": [
            task("T-007", "hk", issue=5),
            task("T-008", "hk"),
            task("T-005", "other"),
            task("T-009", "hk2", issue=1),
            task("T-010", "hk", issue=1),
        ]})

    def test_bare_number_is_the_issue_in_a_hackathon(self):
        r = self.run_hub("show", "5", project="hk")
        self.assert_ok(r)
        self.assertIn("#5", r.stdout)
        self.assertIn("title T-007", r.stdout)
        self.assertIn("key: T-007", r.stdout)

    def test_hash_form_and_project_flag(self):
        r = self.run_hub("show", "#5", "--project", "hk")
        self.assert_ok(r)
        self.assertIn("title T-007", r.stdout)

    def test_t_id_still_works_in_a_hackathon(self):
        r = self.run_hub("show", "T-008", project="hk")
        self.assert_ok(r)
        self.assertIn("T-008", r.stdout)

    def test_unsynced_number_is_a_clear_error(self):
        r = self.run_hub("show", "8", project="hk")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no task has issue #8 in hk yet", r.stdout + r.stderr)

    def test_outside_a_hackathon_a_number_is_a_t_id(self):
        r = self.run_hub("show", "5", project="other")
        self.assert_ok(r)
        self.assertIn("title T-005", r.stdout)

    def test_no_project_means_t_id(self):
        r = self.run_hub("show", "5")
        self.assert_ok(r)
        self.assertIn("title T-005", r.stdout)

    def test_same_number_in_two_hackathons_stays_in_its_project(self):
        self.assertIn("title T-010", self.run_hub("show", "1", project="hk").stdout)
        self.assertIn("title T-009", self.run_hub("show", "1", project="hk2").stdout)

    def test_list_names_synced_tasks_by_issue(self):
        r = self.run_hub("list", project="hk")
        self.assert_ok(r)
        self.assertIn("#5", r.stdout)
        self.assertNotIn("○ T-007", r.stdout)
        self.assertIn("T-008", r.stdout)

    def test_brief_and_next_name_synced_task_by_issue(self):
        brief = self.run_hub("brief", project="hk")
        self.assert_ok(brief)
        self.assertIn("#5  title T-007", brief.stdout)
        self.assertNotIn("T-007  title T-007", brief.stdout)
        nxt = self.run_hub("next", project="hk")
        self.assert_ok(nxt)
        self.assertIn("#5  title T-007", nxt.stdout)

    def test_claim_and_done_by_issue_number(self):
        r = self.run_hub("claim", "5", project="hk")
        self.assert_ok(r)
        self.assertIn("#5 claimed by Zeus", r.stdout)
        self.assertEqual({t["id"]: t for t in self.read_board()["tasks"]}["T-007"]["status"], "claimed")
        r = self.run_hub("done", "5", project="hk")
        self.assert_ok(r)
        self.assertIn("#5 marked done", r.stdout)

    def test_dep_by_issue_number_and_waits_on_label(self):
        self.assert_ok(self.run_hub("new", "later", "--dep", "5", "--project", "hk",
                                    "--detail", "x", project="hk"))
        new = self.read_board()["tasks"][-1]
        self.assertEqual(new["deps"], ["T-007"])
        self.assertIn("waits on #5", self.run_hub("list", project="hk").stdout)


ROSTER_HK = {**HK, "roster": [
    {"name": "Alex", "github": "lead-gh", "lead": True,
     "agents": [{"name": "Zeus"}, {"name": "Prometheus", "github": "bot-gh"}]},
    {"name": "Robin", "github": "mx-gh", "agents": [{"name": "Hermes"}]}]}


class TestOwnership(unittest.TestCase):
    tearDown = BoardCase.tearDown
    write_board = BoardCase.write_board
    read_board = BoardCase.read_board
    run_hub = BoardCase.run_hub
    assert_ok = BoardCase.assert_ok
    events = BoardCase.events

    def setUp(self):
        BoardCase.setUp(self)
        (self.root / "projects" / "hk").mkdir(parents=True)
        (self.root / "projects" / "hk" / "hackathon.json").write_text(json.dumps(ROSTER_HK))
        self.write_board({"next_id": 9, "tasks": [
            task("T-007", "hk", issue=5, owner="Alex"),
            task("T-008", "hk", issue=6, owner="Robin"),
            task("T-005", "other", owner="Zeus")]})

    def t(self, tid):
        return {x["id"]: x for x in self.read_board()["tasks"]}[tid]

    def test_agent_cannot_own_in_a_hackathon(self):
        r = self.run_hub("assign", "5", "Zeus", project="hk")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("hub delegate 5 Zeus", r.stdout + r.stderr)
        r = self.run_hub("new", "x", "--owner", "Prometheus", "--project", "hk", "--detail", "d")
        self.assertNotEqual(r.returncode, 0)

    def test_human_owner_and_pool_are_fine(self):
        self.assert_ok(self.run_hub("assign", "5", "Robin", project="hk"))
        self.assert_ok(self.run_hub("assign", "6", "pool", project="hk"))

    def test_delegate_own_agent_logs_and_messages(self):
        self.assert_ok(self.run_hub("delegate", "5", "Prometheus", project="hk"))
        self.assertEqual(self.t("T-007")["agent"], "Prometheus")
        self.assertEqual(self.t("T-007")["owner"], "Alex")
        self.assertTrue(any(e["event"] == "delegated" for e in self.events()))
        inbox = self.root / "inbox" / "Prometheus.jsonl"
        self.assertTrue(inbox.exists() and "#5 delegated to you by Alex" in inbox.read_text())

    def test_delegate_to_another_humans_agent_is_refused(self):
        r = self.run_hub("delegate", "5", "Hermes", project="hk")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not one of Alex's agents", r.stdout + r.stderr)

    def test_delegate_clear(self):
        self.assert_ok(self.run_hub("delegate", "5", "Zeus", project="hk"))
        self.assert_ok(self.run_hub("delegate", "5", "--clear", project="hk"))
        self.assertIsNone(self.t("T-007").get("agent"))

    def test_claim_by_delegate_keeps_owner(self):
        self.assert_ok(self.run_hub("delegate", "5", "Prometheus", project="hk"))
        self.assert_ok(self.run_hub("claim", "5", agent="Prometheus", project="hk"))
        t = self.t("T-007")
        self.assertEqual((t["owner"], t["agent"], t["status"]), ("Alex", "Prometheus", "claimed"))

    def test_claim_by_undelegated_own_agent_sets_agent(self):
        self.assert_ok(self.run_hub("claim", "5", agent="Zeus", project="hk"))
        self.assertEqual((self.t("T-007")["owner"], self.t("T-007")["agent"]), ("Alex", "Zeus"))

    def test_owner_can_claim_a_delegated_task(self):
        self.assert_ok(self.run_hub("delegate", "5", "Zeus", project="hk"))
        self.assert_ok(self.run_hub("claim", "5", agent="Alex", project="hk"))
        t = self.t("T-007")
        self.assertEqual((t["owner"], t.get("agent"), t["status"]), ("Alex", None, "claimed"))

    def test_claim_by_other_humans_agent_is_refused(self):
        r = self.run_hub("claim", "5", agent="Hermes", project="hk")
        self.assertNotEqual(r.returncode, 0)
        self.assertIsNone(self.t("T-007").get("agent"))

    def test_release_clears_agent_only(self):
        self.assert_ok(self.run_hub("claim", "5", agent="Zeus", project="hk"))
        self.assert_ok(self.run_hub("release", "5", agent="Zeus", project="hk"))
        t = self.t("T-007")
        self.assertEqual((t["owner"], t.get("agent"), t["status"]), ("Alex", None, "open"))

    def test_delegate_can_block_and_finish(self):
        self.assert_ok(self.run_hub("delegate", "5", "Zeus", project="hk"))
        self.assert_ok(self.run_hub("claim", "5", agent="Zeus", project="hk"))
        self.assert_ok(self.run_hub("block", "5", "waiting", agent="Zeus", project="hk"))
        self.assert_ok(self.run_hub("claim", "5", agent="Zeus", project="hk"))
        self.assert_ok(self.run_hub("done", "5", agent="Zeus", project="hk"))
        self.assertEqual((self.t("T-007")["owner"], self.t("T-007")["status"]), ("Alex", "done"))

    def test_done_does_not_call_human_claimable(self):
        data = self.read_board()
        data["tasks"][1]["deps"] = ["T-007"]
        self.write_board(data)
        self.assert_ok(self.run_hub("claim", "5", agent="Alex", project="hk"))
        r = self.run_hub("done", "5", agent="Alex", project="hk")
        self.assert_ok(r)
        self.assertNotIn("now claimable", r.stdout)

    def test_next_offers_by_actor(self):
        self.assert_ok(self.run_hub("delegate", "5", "Prometheus", project="hk"))
        self.assertIn("#5", self.run_hub("next", agent="Prometheus", project="hk").stdout)

    def test_list_shows_owner_arrow_agent(self):
        self.assert_ok(self.run_hub("delegate", "5", "Prometheus", project="hk"))
        self.assertIn("@Alex→Prometheus", self.run_hub("list", project="hk").stdout)

    def test_outside_hackathons_agents_still_own(self):
        self.assert_ok(self.run_hub("claim", "5", agent="Zeus", project="other"))
        self.assertEqual(self.t("T-005")["owner"], "Zeus")

    def test_pool_has_no_wake_hint(self):
        r = self.run_hub("new", "free", "--owner", "pool", "--project", "hk", "--detail", "d")
        self.assert_ok(r)
        self.assertNotIn("hubmsg Pool", r.stdout)
        r = self.run_hub("assign", "5", "pool", project="hk")
        self.assert_ok(r)
        self.assertNotIn("hubmsg Pool", r.stdout)

    def test_pool_cannot_be_claimed_even_with_force(self):
        self.assert_ok(self.run_hub("assign", "5", "pool", project="hk"))
        r = self.run_hub("claim", "5", "--force", agent="Zeus", project="hk")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("hub assign 5 <person>", r.stdout + r.stderr)
        self.assertEqual((self.t("T-007")["owner"], self.t("T-007")["status"]), ("Pool", "open"))

    def test_edit_outside_hackathon_does_not_mention_sync(self):
        self.assert_ok(self.run_hub("edit", "T-005", "--title", "renamed", "--yes", project="other"))
        r = self.run_hub("edit", "T-005", "--title", "again", "--yes", project="other")
        self.assert_ok(r)
        self.assertNotIn("gh-sync", r.stdout)


GH_STUB = r'''#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
if a[:2] == ["issue", "view"]:
    print(json.dumps({"body": open(os.path.join(os.environ["GH_STUB"], f"body-{a[2]}.txt"),
                                   newline="").read()}))
'''


class TestEdit(unittest.TestCase):
    tearDown = BoardCase.tearDown
    write_board = BoardCase.write_board
    read_board = BoardCase.read_board
    assert_ok = BoardCase.assert_ok
    events = BoardCase.events

    def setUp(self):
        BoardCase.setUp(self)
        (self.root / "projects" / "hk").mkdir(parents=True)
        (self.root / "projects" / "hk" / "hackathon.json").write_text(json.dumps(HK))
        self.write_board({"next_id": 9, "tasks": [task("T-007", "hk", issue=5)]})
        self.stub = self.root / "stub"
        (self.stub / "bin").mkdir(parents=True)
        (self.stub / "bin" / "gh").write_text(GH_STUB)
        (self.stub / "bin" / "gh").chmod(0o755)

    def edit(self, *args):
        env = {k: v for k, v in os.environ.items()
               if k not in ("HUB_DIR", "HUB_AGENT", "HUB_PROJECT")}
        env.update(HUB_DIR=str(self.root), HUB_AGENT="Zeus", HUB_PROJECT="hk",
                   GH_STUB=str(self.stub), PATH=f"{self.stub / 'bin'}:{os.environ['PATH']}")
        return subprocess.run([str(BOARD_PY), "edit", *map(str, args)], env=env, text=True,
                              capture_output=True, stdin=subprocess.DEVNULL)

    def detail(self):
        return self.read_board()["tasks"][0]["detail"]

    def test_detail_file_with_yes_saves_shows_diff_and_logs(self):
        f = self.root / "brief.md"
        f.write_text("Context: rewritten\nDeadline:     code freeze\n")
        r = self.edit("5", "--detail-file", f, "--yes")
        self.assert_ok(r)
        self.assertIn("-Context: T-007", r.stdout)
        self.assertIn("+Context: rewritten", r.stdout)
        self.assertEqual(self.detail(), "Context: rewritten\nDeadline:     code freeze")
        edited = [e for e in self.events() if e["event"] == "edited"]
        self.assertEqual(edited[-1]["fields"], ["detail"])

    def test_empty_brief_is_refused(self):
        f = self.root / "brief.md"
        f.write_text("  \n")
        r = self.edit("5", "--detail-file", f, "--yes")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("empty", r.stdout + r.stderr)
        self.assertEqual(self.detail(), "Context: T-007\nDeadline:     code freeze")

    def test_done_task_is_refused(self):
        self.write_board({"next_id": 9, "tasks": [task("T-007", "hk", issue=5, status="done")]})
        r = self.edit("5", "--title", "new", "--yes")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("reopen", r.stdout + r.stderr)

    def test_no_terminal_without_yes_is_refused(self):
        r = self.edit("5", "--title", "new")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--yes", r.stdout + r.stderr)
        self.assertEqual(self.read_board()["tasks"][0]["title"], "title T-007")

    def test_deadline_rewrites_the_line(self):
        self.assert_ok(self.edit("5", "--deadline", "submit", "--yes"))
        self.assertEqual(self.detail(), "Context: T-007\nDeadline:     submit")

    def test_unknown_deadline_is_refused(self):
        r = self.edit("5", "--deadline", "lunch", "--yes")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a deadline", r.stdout + r.stderr)

    def test_nothing_changed_is_refused(self):
        r = self.edit("5", "--title", "title T-007", "--yes")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing changed", r.stdout + r.stderr)

    def test_take_github_copies_the_body_without_extras(self):
        (self.stub / "body-5.txt").write_bytes(
            b"Context: from github\r\nDeadline: submit\r\n\r\nDepends on: #1\r\n\r\n"
            b"<!-- hub-task: T-007 -->\r\n")
        self.assert_ok(self.edit("5", "--take-github", "--yes"))
        self.assertEqual(self.detail(), "Context: from github\nDeadline: submit")

    def test_keep_hub_marks_github_as_last_pushed(self):
        (self.stub / "body-5.txt").write_text("teammate text\n\n<!-- hub-task: T-007 -->\n")
        self.assert_ok(self.edit("5", "--keep-hub", "--yes"))
        import hashlib
        self.assertEqual(self.read_board()["tasks"][0]["issue_hash"],
                         hashlib.sha256(b"teammate text").hexdigest())
        self.assertEqual(self.detail(), "Context: T-007\nDeadline:     code freeze")

if __name__ == "__main__":
    unittest.main(verbosity=2)
