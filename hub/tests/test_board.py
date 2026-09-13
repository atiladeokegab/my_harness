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

    def run_hub(self, *args, agent="Zeus"):
        env = {**os.environ, "HUB_DIR": str(self.root), "HUB_AGENT": agent}
        return subprocess.run(
            [str(BOARD_PY), *map(str, args)], env=env, text=True, capture_output=True
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
