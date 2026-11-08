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
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BOARD_PY = ROOT / "board.py"


class BoardHelpers(unittest.TestCase):
    """Fixtures only, so a subclass does not re-run BoardCase's tests."""

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

    def run_hub(self, *args, agent="Zeus", project=None, stdin=None, cwd=None, env_extra=None, timeout=None):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("HUB_")}  # HUB_CODE_DIR, HUB_LEAD: the roster under test is the default one
        # HOME too: hub done looks for the task's checkout under ~/code, and a real one
        # with a `make check` target would run its suite inside these tests.
        env.update({"HUB_DIR": str(self.root), "HUB_AGENT": agent, "HOME": str(self.root), **(env_extra or {})})
        if project:
            env["HUB_PROJECT"] = project
        return subprocess.run(
            [str(BOARD_PY), *map(str, args)], env=env, text=True, capture_output=True,
            input=stdin, cwd=cwd, timeout=timeout,
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



class BoardCase(BoardHelpers):
    def test_spec_project_tasks_are_generated_and_immutable(self):
        spec = self.root / "projects" / "p" / "spec"
        spec.mkdir(parents=True)
        (spec / "requirements.json").write_text('{"version": 5, "requirements": []}')
        refused = self.run_hub("new", "manual", "--project", "p")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("tasks for p come from hub spec apply", refused.stderr)
        self.assertEqual(self.read_board()["tasks"], [])
        self.assert_ok(self.run_hub("new", "generated", "--project", "p", "--from-spec",
                                    "--generated-from", "v5", "--req", "A-3.2@1",
                                    "--req", "A-5.1@1", "--detail", "build it"))
        t = self.read_board()["tasks"][0]
        self.assertEqual(t["reqs"], ["A-3.2@1", "A-5.1@1"])
        self.assertEqual(t["generated_from"], "v5")
        shown = self.run_hub("show", "1", "--project", "p")
        self.assertIn("reqs: A-3.2@1, A-5.1@1", shown.stdout)
        self.assertIn("generated from: v5", shown.stdout)
        detail = self.root / "brief.md"
        detail.write_text("rewrite")
        for args in (("--title", "rewrite"), ("--detail-file", str(detail))):
            with self.subTest(args=args):
                edited = self.run_hub("edit", "1", *args, "--yes", "--project", "p")
                self.assertNotEqual(edited.returncode, 0)
                self.assertIn("hub spec apply", edited.stderr)
        self.assert_ok(self.run_hub("edit", "1", "--tag", "stale", "--yes", "--project", "p"))
        self.assertEqual(self.read_board()["tasks"][0]["tags"], ["stale"])

    def test_prd_json_only_project_refuses_hand_made_tasks(self):
        spec = self.root / "projects" / "p" / "spec"
        spec.mkdir(parents=True)
        (spec / "prd.json").write_text('{"version": 1, "requirements": []}')
        refused = self.run_hub("new", "manual", "--project", "p")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("tasks for p come from hub spec apply", refused.stderr)
        self.assertEqual(self.read_board()["tasks"], [])

    def test_generated_task_verify_requires_lead_or_recorded_force(self):
        spec = self.root / "projects" / "p" / "spec"
        spec.mkdir(parents=True)
        (spec / "requirements.json").write_text('{"version": 5, "requirements": []}')
        self.assert_ok(self.run_hub("new", "generated", "--project", "p", "--from-spec",
                                    "--generated-from", "v5", "--verify", "make check"))
        refused = self.run_hub("edit", "1", "--verify", "true", "--yes", "--project", "p",
                               agent="Prometheus")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("hub spec apply", refused.stderr)
        self.assertEqual(self.read_board()["tasks"][0]["verify"], "make check")
        self.assert_ok(self.run_hub("edit", "1", "--verify", "make stricter", "--yes",
                                    "--project", "p", agent="Zeus"))
        self.assert_ok(self.run_hub("edit", "1", "--verify", "make strictest", "--yes",
                                    "--project", "p", "--force", agent="Prometheus"))
        self.assertTrue([e for e in self.events() if e["event"] == "edited" and e.get("forced")])

    def test_stale_task_cannot_be_claimed_or_untagged_by_worker(self):
        self.assert_ok(self.run_hub("new", "work", "--owner", "Prometheus"))
        self.assert_ok(self.run_hub("edit", "1", "--tag", "stale", "--yes"))
        for flags in ((), ("--force",)):
            claim = self.run_hub("claim", "1", *flags, agent="Prometheus")
            self.assertNotEqual(claim.returncode, 0)
            self.assertIn("superseded: hub spec regenerates it", claim.stderr)
        self.assertEqual(self.read_board()["tasks"][0]["status"], "open")
        refused = self.run_hub("edit", "1", "--untag", "stale", "--yes", agent="Prometheus")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("only Zeus clears 'stale'", refused.stderr)
        self.assertEqual(self.read_board()["tasks"][0]["tags"], ["stale"])
        self.assert_ok(self.run_hub("edit", "1", "--untag", "stale", "--yes", "--force",
                                    agent="Prometheus"))
        self.assertTrue([e for e in self.events() if e["event"] == "edited" and e.get("forced")])
        self.assert_ok(self.run_hub("claim", "1", agent="Prometheus"))

    def test_untrusted_task_is_not_offered_or_claimable_until_cleared(self):
        self.assert_ok(self.run_hub("new", "designer note", "--owner", "Prometheus", "--tag", "untrusted"))
        self.assert_ok(self.run_hub("new", "ready", "--owner", "Prometheus"))
        nxt = self.run_hub("next", agent="Prometheus")
        self.assertTrue(nxt.stdout.startswith("T-002  ready"), nxt.stdout)
        for flags in ((), ("--force",)):
            claim = self.run_hub("claim", "1", *flags, agent="Prometheus")
            self.assertNotEqual(claim.returncode, 0)
            self.assertIn("is untrusted: it waits for Zeus to clear it", claim.stderr)
        self.assertEqual(self.read_board()["tasks"][0]["status"], "open")
        self.assert_ok(self.run_hub("edit", "1", "--untag", "untrusted", "--yes"))
        self.assert_ok(self.run_hub("claim", "1", agent="Prometheus"))

    def test_next_falls_through_stale_in_scope_and_elsewhere(self):
        for title, project in (("stale here", "p"), ("ready here", "p"),
                               ("stale there", "q"), ("ready there", "q")):
            self.assert_ok(self.run_hub("new", title, "--project", project, "--owner", "Prometheus"))
        for tid in ("1", "3"):
            self.assert_ok(self.run_hub("edit", tid, "--tag", "stale", "--yes"))
        here = self.run_hub("next", "--project", "p", agent="Prometheus")
        self.assertTrue(here.stdout.startswith("T-002  ready here"), here.stdout)
        self.assertNotIn("T-003", here.stdout)
        self.assert_ok(self.run_hub("claim", "2", agent="Prometheus"))
        there = self.run_hub("next", "--project", "p", agent="Prometheus")
        self.assertTrue(there.stdout.startswith("T-004  ready there"), there.stdout)

    def test_next_skips_stale_child_of_vertical(self):
        vertical = task("T-001", "p", owner="Prometheus")
        vertical["kind"] = "vertical"
        stale = task("T-002", "p", owner="Prometheus")
        stale.update(parent="T-001", tags=["stale"])
        ready = task("T-003", "p", owner="Prometheus")
        ready["parent"] = "T-001"
        self.write_board({"next_id": 4, "tasks": [vertical, stale, ready]})
        offered = self.run_hub("next", agent="Prometheus", project="p")
        self.assertTrue(offered.stdout.startswith("T-003"), offered.stdout)

    def test_missing_board_read_is_empty_without_creating_snapshot(self):
        (self.root / "board.json").unlink()
        result = self.run_hub("list")
        self.assert_ok(result)
        self.assertIn("board is empty", result.stdout.lower())
        self.assertFalse((self.root / "board.json").exists())

    def test_missing_board_write_creates_first_task(self):
        (self.root / "board.json").unlink()
        self.assert_ok(self.run_hub("new", "x", "--project", "p"))
        self.assertEqual(self.read_board()["tasks"][0]["id"], "T-001")
        self.assertEqual(self.read_board()["schema_version"], 1)

    def test_first_delivery_creates_inbox(self):
        (self.root / "board.json").unlink()
        self.assert_ok(self.run_hub("new", "y", "--owner", "Prometheus", "--project", "p"))
        self.assertIn("T-001 assigned to you", (self.root / "inbox" / "Prometheus.jsonl").read_text())

    def test_missing_hub_dir_exits_without_traceback(self):
        # HOME stays a real directory: uv, on a cold cache, installs Python under $HOME, and
        # with HOME == HUB_DIR that created the "missing" HUB_DIR, so hub list exited 0.
        result = self.run_hub("list", env_extra={"HUB_DIR": str(self.root / "absent")})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HUB_DIR", result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

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

    def test_done_needs_a_handoff_note_from_every_factory_agent(self):
        """Agent OS §1, and living spec M1: the done note is the handoff for every factory.json agent, reset
        or not, so a phase change never drops the guard."""
        (self.root / "factory.json").write_text(json.dumps({"agents": [
            {"name": "Prometheus", "reset": "per-task"}, {"name": "Hermes", "reset": False}]}))
        for n, agent in enumerate(("Prometheus", "Hermes", "Prometheus", "Zeus"), 1):
            self.assert_ok(self.run_hub("new", f"work {n}", "--owner", agent))
            self.assert_ok(self.run_hub("claim", str(n), agent=agent))
        for tid, agent in (("1", "Prometheus"), ("2", "Hermes")):
            for note in ([], ["--note", "done, see log"]):
                r = self.run_hub("done", tid, *note, agent=agent)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn("handoff note", r.stderr)
        self.assertEqual(self.read_board()["tasks"][0]["status"], "claimed")
        self.assert_ok(self.run_hub("done", "1", "--note", "fixed X on t-1 at abc1234; nothing left",
                                    agent="Prometheus"))
        self.assert_ok(self.run_hub("done", "2", "--note", "reviewed T-9 at abc1234; LGTM posted", agent="Hermes"))
        self.assert_ok(self.run_hub("done", "4", agent="Zeus"))  # not a factory.json agent: no note needed
        self.assertFalse(any(e["event"] == "override" for e in self.events()))
        self.assert_ok(self.run_hub("done", "3", "--force", agent="Prometheus"))
        self.assertTrue(any(e["event"] == "override" and e.get("verb") == "done" and e["task"] == "T-003"
                            for e in self.events()), self.events())

    def test_done_refuses_a_factory_task_whose_open_pr_lacks_evidence(self):
        """2026-10-18: PR #13 had no Evidence, so hub live held it until a reviewer stepped in."""
        (self.root / "factory.json").write_text(json.dumps({"repos": [{"repo": "o/fs"}]}))
        self.write_board({"next_id": 4, "tasks": [
            task(f"T-00{n}", p, issue=12, status="claimed", owner="Hermes") for n, p in ((1, "fs"), (2, "other"), (3, "fs"))]})
        stub, prs = self.root / "stub", self.root / "prs.json"
        stub.mkdir()
        (stub / "gh").write_text('#!/bin/sh\n[ -f "$GH_PRS" ] && exec cat "$GH_PRS"; echo offline >&2; exit 1\n')
        (stub / "gh").chmod(0o755)
        env = {"PATH": f"{stub}:{os.environ['PATH']}", "GH_PRS": str(prs)}
        def done(body, head="task/T-001"):
            prs.write_text(json.dumps([{"number": 9, "headRefName": "x"}, {"number": 13, "headRefName": head, "body": body}]))
            return self.run_hub("done", "1", agent="Hermes", env_extra=env)
        r = done("Closes #12\nTask: T-001")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("PR #13 on o/fs", r.stderr)
        self.assertIn("`## Evidence` block (or a `Verified:` line)", r.stderr)
        self.assertIn("`Not verified:` line", r.stderr)
        r = done("## Evidence\nmake check: 3 passed", head="12-time")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("Evidence` block", r.stderr)
        self.assertIn("`Not verified:` line", r.stderr)
        self.assertEqual(self.read_board()["tasks"][0]["status"], "claimed")
        self.assert_ok(self.run_hub("done", "2", agent="Hermes", env_extra=env))  # not a factory repo
        r = done("Verified: make check: 3 passed\nNot verified: nothing")
        self.assert_ok(r)
        self.assertNotIn("warning", r.stderr)
        prs.unlink()  # gh unreachable, as for a sandboxed builder: warned, not blocked
        r = self.run_hub("done", "3", agent="Hermes", env_extra=env)
        self.assert_ok(r)
        self.assertIn("warning: could not check T-003's PR body", r.stderr)

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

    def test_next_prefers_ready_child_but_offers_unbroken_vertical(self):
        vertical = task("T-001", "p", owner="Prometheus")
        vertical["kind"] = "vertical"
        child = task("T-002", "p", owner="Prometheus")
        child["parent"] = vertical["id"]
        self.write_board({"next_id": 3, "tasks": [vertical]})
        self.assertTrue(self.run_hub("next", agent="Prometheus", project="p").stdout.startswith("T-001"))
        self.write_board({"next_id": 3, "tasks": [vertical, child]})
        self.assertTrue(self.run_hub("next", agent="Prometheus", project="p").stdout.startswith("T-002"))

    def test_next_skips_vertical_when_its_children_are_not_ready_for_agent(self):
        vertical = task("T-001", "p", owner="Prometheus")
        vertical["kind"] = "vertical"
        blocked = task("T-002", "p", status="blocked", owner="Prometheus")
        waiting = task("T-003", "p", owner="Prometheus", deps=["T-006"])
        another_agent = task("T-004", "p", owner="Hermes")
        done = task("T-005", "p", status="done", owner="Prometheus")
        for child in (blocked, waiting, another_agent, done):
            child["parent"] = vertical["id"]
        other_work = task("T-006", "p", owner="Prometheus")
        self.write_board({"next_id": 7, "tasks": [vertical, blocked, waiting,
                                                   another_agent, done, other_work]})
        result = self.run_hub("next", agent="Prometheus", project="p")
        self.assert_ok(result)
        self.assertTrue(result.stdout.startswith("T-006"), result.stdout)

    def test_next_does_not_offer_child_delegated_to_another_agent_as_free(self):
        vertical = task("T-001", "p", owner="Prometheus")
        vertical["kind"] = "vertical"
        child = task("T-002", "p", owner=None)
        child.update(parent=vertical["id"], agent="Hermes")
        self.write_board({"next_id": 3, "tasks": [vertical, child]})
        result = self.run_hub("next", agent="Prometheus", project="p")
        self.assert_ok(result)
        self.assertIn("nothing available", result.stdout)

    def test_next_candidates_lists_every_ready_child_in_order_for_dispatch(self):
        vertical = task("T-001", "p", owner="Prometheus")
        vertical["kind"] = "vertical"
        first, second = task("T-002", "p", owner=None), task("T-003", "p", owner=None)
        delegated = task("T-004", "p", owner=None)
        delegated["agent"] = "Hermes"
        for child in (first, second, delegated):
            child["parent"] = vertical["id"]
        free = task("T-005", "p", owner=None)
        tasks = [vertical, first, second, delegated, free]
        ids = [t["id"] for t in self.load_module().next_candidates(tasks, "Prometheus", "p")]
        self.assertEqual(ids, ["T-002", "T-003", "T-005"])  # no vertical, no Hermes task, no repeats

    def test_list_nests_same_status_children_counts_all_and_keeps_json_unchanged(self):
        vertical = task("T-001", "p")
        vertical["kind"] = "vertical"
        ordinary = task("T-002", "p")
        open_child = task("T-003", "p")
        done_child = task("T-004", "p", status="done")
        open_child["parent"] = done_child["parent"] = vertical["id"]
        tasks = [vertical, ordinary, open_child, done_child]
        self.write_board({"next_id": 5, "tasks": tasks})
        listed = self.run_hub("list", "--all", project="p")
        self.assert_ok(listed)
        lines = listed.stdout.splitlines()
        self.assertIn("1/2", lines[2])
        self.assertIn("T-001", lines[2])
        self.assertTrue(lines[3].startswith("    ○ T-003"), listed.stdout)
        self.assertTrue(lines[4].startswith("  ○ T-002"), listed.stdout)
        self.assertTrue(any(line.startswith("  ● T-004") for line in lines), listed.stdout)
        as_json = self.run_hub("list", "--all", "--json", project="p")
        self.assert_ok(as_json)
        self.assertEqual(as_json.stdout, json.dumps(tasks, indent=2) + "\n")

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
    def test_a_keyed_message_replaces_the_last_one_with_that_key_and_receipts_it(self):
        for mid, text in (("k-1", "Hermes: stuck"), ("k-2", "Hermes: permission prompt")):
            self.assert_ok(self.run_hub("notify", "Zeus", text, "--message-id", mid, "--key", "watchdog:Hermes",
                                        agent="Watchdog"))
        self.assert_ok(self.run_hub("notify", "Zeus", "unrelated", agent="Hermes"))
        inbox = self.run_hub("inbox", agent="Zeus").stdout
        self.assertNotIn("Hermes: stuck", inbox)
        self.assertIn("Hermes: permission prompt", inbox)
        self.assertIn("unrelated", inbox)
        pending = self.run_hub("receive", "--pending", agent="Zeus").stdout
        self.assertNotIn("Hermes: stuck", pending)  # superseded counts as received: its wake is dropped

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

    def test_receive_pending_reveals_each_unread_message_once(self):
        """Agent OS §5.1: one call reveals every recent unreceived message and writes receipts."""
        for mid, text in (("m-1", "first job"), ("m-2", "second job")):
            self.assert_ok(self.run_hub("notify", "Zeus", text, "--message-id", mid, agent="Hermes"))
        self.assert_ok(self.run_hub("receive", "m-2", agent="Zeus"))
        self.assert_ok(self.run_hub("notify", "Zeus", "third job", "--message-id", "m-3", agent="Hermes"))
        # Older than the wake horizon: hubwaked drops such wakes, so --pending leaves it in the inbox.
        with open(self.root / "inbox" / "Zeus.jsonl", "a") as f:
            f.write(json.dumps({"at": "2026-09-01T00:00:00+00:00", "text": "ancient", "id": "m-0"}) + "\n")
        first = self.run_hub("receive", "--pending", agent="Zeus")
        self.assert_ok(first)
        self.assertIn("first job", first.stdout)
        self.assertIn("third job", first.stdout)
        self.assertNotIn("second job", first.stdout)
        self.assertNotIn("ancient", first.stdout)
        second = self.run_hub("receive", "--pending", agent="Zeus")
        self.assert_ok(second)
        self.assertEqual(second.stdout.strip(), "nothing pending")
        self.assertIn("already received", self.run_hub("receive", "m-3", agent="Zeus").stdout)
        self.assertNotEqual(self.run_hub("receive", agent="Zeus").returncode, 0)

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

    def test_plain_inbox_shows_a_count_and_the_latest_20_unless_all(self):
        for i in range(25):
            self.assert_ok(self.run_hub("notify", "Zeus", f"mail-{i:02d}-end", agent="Hermes"))
        short = self.run_hub("inbox", agent="Zeus").stdout
        self.assertIn("25 message(s); the latest 20", short)
        self.assertNotIn("mail-04-end", short)
        self.assertIn("mail-05-end", short)
        self.assertIn("mail-04-end", self.run_hub("inbox", "--all", agent="Zeus").stdout)

    def test_brief_counts_peers_in_other_projects_and_cuts_inbox_lines(self):
        t = {"status": "claimed", "owner": "Hermes", "deps": [], "notes": []}
        self.write_board({"next_id": 3, "tasks": [{**t, "id": "T-001", "title": "here-task", "project": "a"},
                                                  {**t, "id": "T-002", "title": "away-task", "project": "b"}]})
        self.assert_ok(self.run_hub("notify", "Zeus", "x" * 400, agent="Hermes"))
        out = self.run_hub("brief", project="a").stdout
        self.assertIn("here-task", out)
        self.assertNotIn("away-task", out)
        self.assertIn("+ 1 claimed in other projects", out)
        self.assertTrue(all(len(l) <= 160 for l in out.splitlines() if "xxx" in l))

    def test_events_are_one_line_cut_to_120_unless_full(self):
        self.assert_ok(self.run_hub("new", "t" * 300))
        short = self.run_hub("events").stdout.splitlines()
        self.assertTrue(short and all(len(l) <= 120 for l in short), short)
        self.assertIn("t" * 200, self.run_hub("events", "--full").stdout)

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
        final = self.run_hub("inbox", "--all", agent="Zeus")
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

    def test_delegate_can_block_but_its_issue_closes_the_task(self):
        """The hackathon skill: an agent never runs `hub done` on a task with an issue. gh-sync closes
        it when the issue closes, so a smoke revert that reopens the issue reopens the task too."""
        self.assert_ok(self.run_hub("delegate", "5", "Prometheus", project="hk"))
        self.assert_ok(self.run_hub("claim", "5", agent="Prometheus", project="hk"))
        self.assert_ok(self.run_hub("block", "5", "waiting", agent="Prometheus", project="hk"))
        self.assert_ok(self.run_hub("claim", "5", agent="Prometheus", project="hk"))
        refused = self.run_hub("done", "5", agent="Prometheus", project="hk")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("cannot done #5 as its agent: issue #5 closes it", refused.stderr)
        self.assertIn("`Closes #5`", refused.stderr)
        self.assertEqual(self.t("T-007")["status"], "claimed")
        self.assert_ok(self.run_hub("done", "5", "--force", agent="Prometheus", project="hk"))
        self.assertEqual((self.t("T-007")["owner"], self.t("T-007")["status"]), ("Alex", "done"))
        self.assertTrue(any(e["event"] == "override" and e.get("verb") == "done" for e in self.events()))

    def test_factory_task_is_claimed_and_done_by_any_agent(self):
        """A factory task (gh_sync's poll of an `agent` issue) has no roster owner, and no gh-sync
        closes it: any agent claims it as owner and agent (live's builder()), and hub done is not held."""
        data = self.read_board()
        data["tasks"].append({**task("T-009", "hk", issue=7, owner=None), "kind": "factory"})
        self.write_board(data)
        self.assert_ok(self.run_hub("claim", "7", agent="Hermes", project="hk"))
        t = self.t("T-009")
        self.assertEqual((t["owner"], t["agent"], t["status"]), ("Hermes", "Hermes", "claimed"))
        self.assert_ok(self.run_hub("release", "7", agent="Hermes", project="hk"))
        t = self.t("T-009")
        self.assertEqual((t["owner"], t.get("agent"), t["status"]), (None, None, "open"))
        self.assert_ok(self.run_hub("claim", "7", agent="Prometheus", project="hk"))
        self.assert_ok(self.run_hub("done", "7", agent="Prometheus", project="hk"))
        t = self.t("T-009")
        self.assertEqual((t["owner"], t["agent"], t["status"]), ("Prometheus", "Prometheus", "done"))
        self.assertFalse(any(e["event"] == "override" for e in self.events()))

    def test_dropping_an_issue_task_is_one_forced_done(self):
        """The hackathon skill's drop, for an issue closed as not planned: the old
        `hub claim --force` then `hub done` is now refused at the done, since the claim makes Zeus the agent."""
        self.assert_ok(self.run_hub("delegate", "5", "Prometheus", project="hk"))
        self.assert_ok(self.run_hub("claim", "5", agent="Prometheus", project="hk"))
        self.assert_ok(self.run_hub("claim", "5", "--force", agent="Zeus", project="hk"))
        self.assertIn("--force --note", self.run_hub("done", "5", agent="Zeus", project="hk").stderr)
        self.assert_ok(self.run_hub("done", "5", "--force", "--note", "dropped: #5", agent="Zeus", project="hk"))
        self.assertEqual(self.t("T-007")["status"], "done")

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


class TestFactoryGate(BoardHelpers):
    """T-499: hub done's verify gate, the attempts counter, and the PAUSE kill switch."""

    def repo(self, makefile=None):
        repo = self.root / "code" / "p"
        (repo / ".git").mkdir(parents=True, exist_ok=True)
        if makefile is not None:
            (repo / "Makefile").write_text(makefile)
        return repo

    def claimed(self, *flags):
        self.assert_ok(self.run_hub("new", "work", "--owner", "Zeus", "--project", "p", *flags))
        self.assert_ok(self.run_hub("claim", "1"))

    def task(self):
        return self.read_board()["tasks"][0]

    def test_passing_verify_runs_in_repo_and_notes_one_line_with_the_log(self):
        self.repo()
        self.claimed("--verify", "pwd; seq 1 100")
        r = self.run_hub("done", "1", "--note", "built it")
        self.assert_ok(r)
        t = self.task()
        self.assertEqual(t["status"], "done")
        built, line = t["notes"][-1]["text"].splitlines()
        self.assertEqual(built, "built it")
        self.assertRegex(line, r"^verify passed: pwd; seq 1 100 \(101 lines, log (\S+)\)$")
        self.assertIn(line, r.stdout)
        log = Path(line.rsplit("log ", 1)[1][:-1])
        self.assertEqual(log.parent, self.root / "logs" / "sh" / "Zeus")
        self.assertEqual(log.read_text().splitlines(), [str(self.root / "code" / "p")]
                         + [str(n) for n in range(1, 101)])
        self.assertEqual(self.events()[-2]["verify"], "passed")

    def test_failed_verify_refuses_counts_attempt_then_blocks_and_tells_zeus(self):
        self.repo()
        self.claimed("--verify", "echo broken-output; exit 3")
        first = self.run_hub("done", "1")
        self.assertNotEqual(first.returncode, 0)
        self.assertIn("broken-output", first.stderr)
        self.assertEqual((self.task()["status"], self.task()["attempts"]), ("claimed", 1))
        self.assertIn("broken-output", self.task()["notes"][-1]["text"])
        self.assertRegex(self.task()["notes"][-1]["text"], r"\(exit 3, log \S+\.log\)$")
        zeus_inbox = self.root / "inbox" / "Zeus.jsonl"
        self.assertNotIn("blocked", zeus_inbox.read_text() if zeus_inbox.exists() else "")

        second = self.run_hub("done", "1")
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual((self.task()["status"], self.task()["attempts"]), ("blocked", 2))
        inbox = (self.root / "inbox" / "Zeus.jsonl").read_text()
        self.assertIn("T-001 blocked: verify", inbox)
        self.assertIn("notify", [e["event"] for e in self.events()])

    def test_verify_timeout_is_a_failure(self):
        self.repo()
        self.claimed("--verify", "sleep 30")
        r = self.run_hub("done", "1", env_extra={"HUB_VERIFY_TIMEOUT": "1"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("timed out after 1s", r.stderr)
        self.assertEqual(self.task()["attempts"], 1)

    def test_no_verify_skips_but_is_recorded(self):
        self.repo()
        self.claimed("--verify", "false")
        self.assert_ok(self.run_hub("done", "1", "--no-verify"))
        self.assertEqual(self.task()["status"], "done")
        done = [e for e in self.events() if e["event"] == "done"][0]
        self.assertEqual((done["verify"], done["cmd"]), ("skipped", "false"))

    def test_default_is_make_check_when_repo_has_that_target(self):
        self.repo("check:\n\t@echo make-check-ran; false\n")
        self.claimed()
        r = self.run_hub("done", "1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("make-check-ran", r.stderr)

    def test_no_default_without_check_target_or_project_and_empty_verify_opts_out(self):
        self.repo("build:\n\tfalse\n")
        self.claimed()
        self.assert_ok(self.run_hub("done", "1"))
        # No project: a Makefile in the caller's cwd must not be mistaken for the task's repo.
        cwd = self.root / "elsewhere"
        cwd.mkdir()
        (cwd / "Makefile").write_text("check:\n\tfalse\n")
        self.assert_ok(self.run_hub("new", "loose", "--owner", "Zeus"))
        self.assert_ok(self.run_hub("claim", "2"))
        self.assert_ok(self.run_hub("done", "2", cwd=cwd))
        # An explicit "" opts out of the default.
        self.repo("check:\n\tfalse\n")
        self.assert_ok(self.run_hub("new", "opt-out", "--owner", "Zeus", "--project", "p", "--verify", ""))
        self.assert_ok(self.run_hub("claim", "3"))
        self.assert_ok(self.run_hub("done", "3"))

    def test_verify_runs_in_the_callers_linked_worktree_of_the_task_repo(self):
        """Builders work in linked worktrees; verifying the main checkout tests the wrong tree."""
        repo = self.repo("check:\n\t@echo main-ok\n")
        (repo / ".git").rmdir()
        git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                        cwd=repo, check=True, capture_output=True)
        git("init", "-q")
        git("add", "Makefile")
        git("commit", "-qm", "init")
        wt = self.root / "wt"
        git("worktree", "add", "-q", "-b", "feature", str(wt))
        (wt / "Makefile").write_text("check:\n\t@echo worktree-broken; false\n")
        self.claimed()
        refused = self.run_hub("done", "1", cwd=wt)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("worktree-broken", refused.stderr)
        self.assertIn(f"(in {wt.resolve()})", refused.stdout)
        passed = self.run_hub("done", "1", cwd=repo)
        self.assert_ok(passed)
        self.assertIn(f"(in {repo})", passed.stdout)

    def test_edit_sets_verify(self):
        self.repo()
        self.claimed("--detail", "the brief")
        self.assert_ok(self.run_hub("edit", "1", "--verify", "exit 1", "--yes"))
        self.assertEqual(self.task()["verify"], "exit 1")
        self.assertNotEqual(self.run_hub("done", "1").returncode, 0)

    def test_edit_tags_and_untags_and_logs_each_change(self):
        self.claimed()
        self.assert_ok(self.run_hub("edit", "1", "--tag", "standing", "--tag", "headless", "--yes"))
        self.assertEqual(self.task()["tags"], ["standing", "headless"])
        self.assert_ok(self.run_hub("edit", "1", "--untag", "headless", "--yes"))
        self.assertEqual(self.task()["tags"], ["standing"])
        self.assertNotEqual(self.run_hub("edit", "1", "--tag", "standing", "--yes").returncode, 0)  # nothing changed
        edits = [(e["fields"], e.get("tagged"), e.get("untagged")) for e in self.events() if e["event"] == "edited"]
        self.assertEqual(edits, [(["tags"], ["standing", "headless"], []), (["tags"], [], ["headless"])])
        for bad in ("Standing", "a b", "x;rm", ""):
            r = self.run_hub("edit", "1", "--tag", bad, "--yes")
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertIn("[a-z0-9-]+", r.stderr)
        self.assertEqual(self.task()["tags"], ["standing"])

    def test_only_zeus_clears_untrusted_unless_forced(self):
        self.claimed()
        self.assert_ok(self.run_hub("edit", "1", "--tag", "untrusted", "--yes"))
        r = self.run_hub("edit", "1", "--untag", "untrusted", "--yes", "--as", "Hermes")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("only Zeus clears 'untrusted'", r.stderr)
        self.assertEqual(self.task()["tags"], ["untrusted"])
        self.assert_ok(self.run_hub("edit", "1", "--untag", "untrusted", "--yes", "--as", "Zeus"))
        self.assertEqual(self.task()["tags"], [])
        self.assert_ok(self.run_hub("edit", "1", "--tag", "untrusted", "--yes"))
        self.assert_ok(self.run_hub("edit", "1", "--untag", "untrusted", "--yes", "--force", "--as", "Hermes"))
        self.assertTrue([e for e in self.events() if e["event"] == "edited" and e.get("forced")])
        self.assertIn("tags: ", self.run_hub("edit", "1", "--tag", "standing", "--yes").stdout + self.run_hub("show", "1").stdout)

    def test_quoted_empty_verify_runs_nothing(self):
        """T-556 stored --verify '' as the literal two quotes, and hub done ran it (exit 127)."""
        self.repo("check:\n\tfalse\n")
        self.claimed("--verify", "''")
        done = self.run_hub("done", "1")
        self.assert_ok(done)
        self.assertNotIn("verify", done.stdout)
        self.assertNotIn("verify", self.events()[-1])

    def test_hub_tag_adds_removes_and_logs_like_edit(self):
        self.claimed()
        self.assert_ok(self.run_hub("tag", "1", "read", "headless", "--as", "Hermes"))
        self.assertEqual(self.task()["tags"], ["read", "headless"])
        self.assert_ok(self.run_hub("tag", "1", "--rm", "headless"))
        self.assertEqual(self.task()["tags"], ["read"])
        edits = [(e["by"], e.get("tagged"), e.get("untagged")) for e in self.events() if e["event"] == "edited"]
        self.assertEqual(edits, [("Hermes", ["read", "headless"], []), ("Zeus", [], ["headless"])])
        self.assertIn("[a-z0-9-]+", self.run_hub("tag", "1", "Read").stderr)
        self.assertNotEqual(self.run_hub("tag", "1").returncode, 0)

    def test_hub_tag_keeps_untrusted_for_zeus_and_never_touches_stale(self):
        self.claimed()
        self.assert_ok(self.run_hub("tag", "1", "untrusted", "--as", "Hermes"))
        r = self.run_hub("tag", "1", "--rm", "untrusted", "--as", "Hermes")
        self.assertIn("only Zeus clears 'untrusted'", r.stderr)
        self.assert_ok(self.run_hub("tag", "1", "--rm", "untrusted"))
        for args in (["stale"], ["--rm", "stale"]):
            r = self.run_hub("tag", "1", *args)
            self.assertNotEqual(r.returncode, 0, args)
            self.assertIn("Spec Tree", r.stderr)
        self.assertEqual(self.task().get("tags"), [])

    def test_new_takes_repeatable_tags_but_not_stale(self):
        self.assert_ok(self.run_hub("new", "look", "--owner", "Zeus", "--tag", "read", "--tag", "headless"))
        self.assertEqual(self.task()["tags"], ["read", "headless"])
        self.assertEqual([e for e in self.events() if e["event"] == "created"][0]["tags"], ["read", "headless"])
        self.assertIn("Spec Tree", self.run_hub("new", "x", "--tag", "stale").stderr)
        self.assertIn("[a-z0-9-]+", self.run_hub("new", "x", "--tag", "a b").stderr)
        self.assertEqual(len(self.read_board()["tasks"]), 1)

    def test_claimed_at_set_on_claim_kept_on_done_cleared_on_release(self):
        self.claimed()
        stamp = self.task()["claimed_at"]
        self.assertRegex(stamp, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")
        self.assert_ok(self.run_hub("release", "1"))
        self.assertNotIn("claimed_at", self.task())
        self.assert_ok(self.run_hub("claim", "1"))
        self.assert_ok(self.run_hub("done", "1"))
        self.assertIn("claimed_at", self.task())

    def test_bump_attempts_counts_on_the_task_and_ignores_a_missing_one(self):
        self.claimed()
        board = self.load_module()
        self.assertEqual(board.bump_attempts("1", "hub-live", "CI smoke failed on PR #7", "E   assert 1 == 2"), 1)
        self.assertEqual(board.bump_attempts("T-001", "hub-live", "CI smoke failed on PR #7", "again"), 2)
        t = self.task()
        self.assertEqual((t["attempts"], t["status"]), (2, "claimed"))  # counting only: hub live tells Zeus
        self.assertEqual(t["notes"][-2]["text"], "CI smoke failed on PR #7 (attempt 1)\nE   assert 1 == 2")
        self.assertEqual([e["attempts"] for e in self.events() if e["event"] == "attempt_failed"], [1, 2])
        self.assertIsNone(board.bump_attempts("T-099", "hub-live", "x", "y"))

    def test_pause_refuses_next_and_claim_and_leads_the_brief_until_resume(self):
        self.assert_ok(self.run_hub("new", "work", "--owner", "Zeus"))
        self.assert_ok(self.run_hub("pause", "deploy", "freeze"))
        self.assertTrue((self.root / "PAUSE").exists())
        self.assertIn("deploy freeze", self.load_module().paused())
        for verb in ("next", "claim"):
            r = self.run_hub(verb, *(["1"] if verb == "claim" else []))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("deploy freeze", r.stderr)
        brief = self.run_hub("brief")
        self.assert_ok(brief)
        self.assertTrue(brief.stdout.startswith("HUB PAUSED: deploy freeze"))
        self.assert_ok(self.run_hub("resume"))
        self.assertFalse((self.root / "PAUSE").exists())
        self.assertIsNone(self.load_module().paused())
        self.assert_ok(self.run_hub("claim", "1"))
        self.assertEqual([e["event"] for e in self.events() if e["event"] in ("paused", "resumed")],
                         ["paused", "resumed"])


class TestKicks(BoardHelpers):
    """T-527: board events that can make work claimable kick hub-dispatch.path."""

    def kick(self):
        return self.root / "state" / "dispatch.kick"

    def test_new_kicks_the_dispatcher_and_note_does_not(self):
        self.assert_ok(self.run_hub("new", "work", "--owner", "Zeus"))
        self.assertTrue(self.kick().exists())
        self.kick().unlink()
        self.assert_ok(self.run_hub("note", "1", "a remark"))
        self.assertFalse(self.kick().exists())

    def test_done_ticks_the_projects_live_loop_only_when_its_directory_exists(self):
        (self.root / "projects" / "p").mkdir(parents=True)
        for project in ("p", "q"):
            self.assert_ok(self.run_hub("new", "work", "--owner", "Zeus", "--project", project))
        self.assert_ok(self.run_hub("claim", "1"))
        self.assert_ok(self.run_hub("claim", "2"))
        tick = self.root / "projects" / "p" / ".tick-now"
        self.assertFalse(tick.exists())
        self.assert_ok(self.run_hub("done", "1"))
        self.assertTrue(tick.exists())
        self.assert_ok(self.run_hub("done", "2"))
        self.assertFalse((self.root / "projects" / "q").exists())

    def test_stop_hook_kicks_for_every_agent_but_zeus(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("HUB_AGENT", "HUB_PROJECT", "CLAUDE_CODE_SESSION_NAME")}

        def hook(event, agent):
            r = subprocess.run([str(ROOT / "heartbeat.sh")], input=json.dumps({"hook_event_name": event}),
                               env={**env, "HUB_DIR": str(self.root), "HUB_AGENT": agent},
                               text=True, capture_output=True, timeout=20)
            self.assertEqual(r.returncode, 0, r.stderr)

        hook("Stop", "Zeus")
        hook("PostToolUse", "Hermes")
        self.assertFalse(self.kick().exists())
        hook("Stop", "Hermes")
        self.assertTrue(self.kick().exists())

    def test_heartbeat_agent_flag_beats_the_environment(self):
        """Codex hooks run in a shared daemon whose HUB_AGENT belongs to whoever started it."""
        env = {k: v for k, v in os.environ.items() if k not in ("HUB_PROJECT", "CLAUDE_CODE_SESSION_NAME")}
        r = subprocess.run([str(ROOT / "heartbeat.sh"), "--agent", "Prometheus"],
                           input=json.dumps({"hook_event_name": "UserPromptSubmit", "turn_id": "t"}),
                           env={**env, "HUB_DIR": str(self.root), "HUB_AGENT": "Hermes"},
                           text=True, capture_output=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        state = self.root / "state"
        self.assertEqual(json.loads((state / "Prometheus.json").read_text())["event"], "UserPromptSubmit")
        self.assertFalse((state / "Hermes.json").exists())


class TestSh(BoardHelpers):
    """T-529: hub sh logs everything, prints a header and a tail, and keeps the exit code."""

    def test_failure_keeps_its_code_prints_header_and_tail_and_logs_everything(self):
        r = self.run_hub("sh", "--", "sh", "-c", "seq 100; exit 3")
        self.assertEqual(r.returncode, 3, r.stderr)
        header, *tail = r.stdout.splitlines()
        m = re.fullmatch(r"exit 3 · 100 lines · [\d.]+s · log (\S+)", header)
        self.assertTrue(m, header)
        self.assertEqual(tail, [str(n) for n in range(81, 101)])
        log = Path(m[1])
        self.assertEqual(log.parent, self.root / "logs" / "sh" / "Zeus")
        self.assertTrue(log.name.endswith("-sh.log"), log.name)
        self.assertEqual(log.read_text().splitlines(), [str(n) for n in range(1, 101)])

    def test_tail_name_one_string_command_and_hub_env_kept(self):
        r = self.run_hub("sh", "--tail", "1", "--name", "env check", "--", "echo $HUB_DIR; echo $HUB_AGENT")
        self.assert_ok(r)
        header, last = r.stdout.splitlines()
        self.assertTrue(header.startswith("exit 0 · 2 lines · "), header)
        self.assertTrue(header.endswith("-env_check.log"), header)
        self.assertEqual(last, "Zeus")
        self.assertIn(str(self.root), Path(header.rsplit("log ", 1)[1]).read_text())


class TestShowNotes(BoardHelpers):
    def test_show_prints_the_five_newest_notes_cut_to_600_unless_full(self):
        self.assert_ok(self.run_hub("new", "work"))
        for n in range(7):
            self.assert_ok(self.run_hub("note", "1", f"note-{n} " + "x" * 700 * (n == 6) + f" end-{n}"))
        short = self.run_hub("show", "1").stdout
        self.assertNotIn("note-1 ", short)
        for n in range(2, 7):
            self.assertIn(f"note-{n} ", short)
            self.assertIn(f"end-{n}", short)
        self.assertIn("2 earlier notes", short)
        self.assertNotIn("x" * 300, short)
        self.assertIn("x" * 290 + " …(--full)… " + "x" * 290, short)
        full = self.run_hub("show", "1", "--full").stdout
        for n in range(7):
            self.assertIn(f"note-{n} ", full)
        self.assertIn("x" * 700, full)


class TestClaimWorkspace(BoardHelpers):
    """T-531: a claim gets a fresh worktree under ~/work, done verifies there, release cleans it."""

    def setUp(self):
        super().setUp()
        self.clone = self.root / "code" / "p"
        self.clone.parent.mkdir()
        self.git(self.root, "init", "-q", "--bare", str(self.root / "origin.git"))
        self.git(self.root, "clone", "-q", str(self.root / "origin.git"), str(self.clone))
        (self.clone / "README").write_text("base\n")
        self.git(self.clone, "add", "README")
        self.git(self.clone, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
        self.git(self.clone, "branch", "-M", "integration")
        self.git(self.clone, "push", "-q", "origin", "integration")
        self.ws = self.root / "work" / "p" / "T-001"

    def git(self, cwd, *args):
        env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
        r = subprocess.run(["git", "-C", str(cwd), *args], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def claim(self, project="p"):
        self.assert_ok(self.run_hub("new", "work", "--owner", "Zeus", "--project", project, "--verify", "pwd"))
        r = self.run_hub("claim", "1")
        self.assert_ok(r)
        return r

    def test_claim_prints_and_stores_the_workspace_and_done_verifies_in_it(self):
        r = self.claim()
        self.assertIn(f"workspace: {self.ws} (detached at origin/integration", r.stdout)
        self.assertEqual(self.read_board()["tasks"][0]["workspace"], str(self.ws))
        self.assertEqual(self.git(self.ws, "rev-parse", "HEAD"), self.git(self.clone, "rev-parse", "origin/integration"))
        done = self.run_hub("done", "1", cwd=self.clone)
        self.assert_ok(done)
        self.assertIn(f"(in {self.ws})", done.stdout)

    def test_release_removes_a_clean_workspace_and_keeps_a_dirty_one(self):
        self.claim()
        r = self.run_hub("release", "1")
        self.assert_ok(r)
        self.assertIn(f"workspace: removed {self.ws}", r.stdout)
        self.assertFalse(self.ws.exists())
        self.assert_ok(self.run_hub("claim", "1"))
        (self.ws / "wip").write_text("unsaved\n")
        r = self.run_hub("release", "1")
        self.assert_ok(r)
        self.assertIn(f"workspace: kept {self.ws} (dirty)", r.stdout)
        self.assertTrue((self.ws / "wip").exists())
        self.assertEqual(self.read_board()["tasks"][0]["status"], "open")

    def test_hub_project_gets_no_workspace(self):
        r = self.claim("hub")
        self.assertIn("workspace: hub uses its live checkout", r.stdout)
        self.assertNotIn("workspace", self.read_board()["tasks"][0])
        self.assertFalse((self.root / "work").exists())

    def test_a_create_failure_leaves_the_claim_intact(self):
        self.assert_ok(self.run_hub("new", "work", "--owner", "Zeus", "--project", "p"))
        board = self.load_module()
        with mock.patch.object(sys, "path", [str(ROOT), *sys.path]):
            import workspace
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"HUB_AGENT": "Zeus", "HOME": str(self.root)}), \
                mock.patch.object(workspace, "create", side_effect=RuntimeError("boom")), \
                contextlib.redirect_stdout(out):
            board.cmd_claim(argparse.Namespace(id="1", as_agent=None, force=False, project=None))
        self.assertIn("workspace: not created (boom); claim stands", out.getvalue())
        t = self.read_board()["tasks"][0]
        self.assertEqual((t["status"], t["owner"]), ("claimed", "Zeus"))
        self.assertNotIn("workspace", t)


class TestBoardConcurrency(BoardHelpers):
    """T-586: a burst of concurrent subprocesses doing new/claim/note/done loses no writes."""

    def test_concurrent_subprocess_burst_preserves_every_write_and_event(self):
        seeded = [
            *(task(f"T-{i:03d}", None, status="open", owner=f"Agent{i}") for i in range(1, 6)),
            *(task(f"T-{i:03d}", None, status="claimed", owner=f"Agent{i}") for i in range(6, 16)),
        ]
        self.write_board({"next_id": 16, "tasks": seeded})
        self.assert_ok(self.run_hub("list", cwd=self.root, timeout=10))

        jobs = [
            *((f"Agent{i}", ("claim", f"T-{i:03d}")) for i in range(1, 6)),
            *((f"Agent{i}", ("note", "T-006", f"concurrent-note-{i}")) for i in range(6, 11)),
            *((f"Agent{i}", ("done", f"T-{i:03d}", "--note", f"done-note-{i}")) for i in range(11, 16)),
            *((f"Agent{i}", ("new", f"burst-new-{i}", "--detail", f"detail-{i}")) for i in range(16, 21)),
        ]
        self.assertEqual(len(jobs), 20)
        start = threading.Barrier(len(jobs))

        def run_job(job):
            agent, args = job
            start.wait(timeout=10)
            return self.run_hub(*args, agent=agent, cwd=self.root, timeout=10)

        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            results = list(pool.map(run_job, jobs))
        for res in results:
            self.assert_ok(res)

        self.assertFalse((self.root / ".board.wal").exists())
        board = self.read_board()
        self.assertEqual(board["next_id"], 21)
        tasks = board["tasks"]
        self.assertEqual(len(tasks), 20)
        self.assertEqual({t["id"] for t in tasks}, {f"T-{i:03d}" for i in range(1, 21)})
        by_id = {t["id"]: t for t in tasks}
        for i in range(1, 6):
            self.assertEqual((by_id[f"T-{i:03d}"]["status"], by_id[f"T-{i:03d}"]["owner"]),
                             ("claimed", f"Agent{i}"))
        self.assertCountEqual(
            [(n["by"], n["text"]) for n in by_id["T-006"]["notes"]],
            [(f"Agent{i}", f"concurrent-note-{i}") for i in range(6, 11)],
        )
        for i in range(11, 16):
            t = by_id[f"T-{i:03d}"]
            self.assertEqual((t["status"], t["owner"]), ("done", f"Agent{i}"))
            self.assertEqual([(n["by"], n["text"]) for n in t["notes"]],
                             [(f"Agent{i}", f"done-note-{i}")])
        created = [by_id[f"T-{i:03d}"] for i in range(16, 21)]
        self.assertCountEqual(
            [(t["created_by"], t["title"], t["detail"], t["status"]) for t in created],
            [(f"Agent{i}", f"burst-new-{i}", f"detail-{i}", "open") for i in range(16, 21)],
        )

        events = self.events()
        self.assertEqual(len(events), 40)
        txids = []
        actions = []
        for idx in range(0, len(events), 2):
            action, commit = events[idx], events[idx + 1]
            self.assertIn(action["event"], ("created", "claimed", "note", "done"))
            self.assertEqual(commit["event"], "commit")
            self.assertEqual(action["txid"], commit["txid"])
            txids.append(commit["txid"])
            actions.append(action)
        self.assertEqual(len(set(txids)), 20)
        self.assertCountEqual(
            [(e["by"], e["event"], e["task"]) for e in actions if e["event"] == "claimed"],
            [(f"Agent{i}", "claimed", f"T-{i:03d}") for i in range(1, 6)],
        )
        self.assertCountEqual(
            [(e["by"], e["event"], e["task"], e["text"]) for e in actions if e["event"] == "note"],
            [(f"Agent{i}", "note", "T-006", f"concurrent-note-{i}") for i in range(6, 11)],
        )
        self.assertCountEqual(
            [(e["by"], e["event"], e["task"], e["note"]) for e in actions if e["event"] == "done"],
            [(f"Agent{i}", "done", f"T-{i:03d}", f"done-note-{i}") for i in range(11, 16)],
        )
        self.assertCountEqual(
            [(e["by"], e["event"], e["title"]) for e in actions if e["event"] == "created"],
            [(f"Agent{i}", "created", f"burst-new-{i}") for i in range(16, 21)],
        )


class TestPhases(BoardHelpers):
    """Living spec §4: the board enforces claim and done_force from each agent's phase."""

    def setUp(self):
        super().setUp()
        live = json.loads((ROOT / "factory.example.json").read_text())
        (self.root / "factory.json").write_text(json.dumps({"agents": [
            {"name": "Iris", "kind": "agy", "phase": "trial"},
            {"name": "Prometheus", "kind": "codex", "phase": "trusted"},
            {"name": "Ghost", "kind": "agy", "phase": "off"}], "autonomy": live["autonomy"]}))

    def test_trial_done_force_refused(self):
        for n, agent in enumerate(("Iris", "Iris", "Prometheus"), 1):
            self.assert_ok(self.run_hub("new", f"work {n}", "--owner", agent))
            self.assert_ok(self.run_hub("claim", str(n), agent=agent))
        note = ("--note", "built it on task/T-1 at abc1234; nothing left")
        for flag in ("--force", "--no-verify"):
            r = self.run_hub("done", "1", flag, *note, agent="Iris")
            self.assertNotEqual(r.returncode, 0, r.stdout)
            self.assertIn(f"{flag} needs done_force; Iris's phase trial has none", r.stderr)
        self.assertEqual(self.read_board()["tasks"][0]["status"], "claimed")
        self.assert_ok(self.run_hub("done", "2", *note, agent="Iris"))
        self.assert_ok(self.run_hub("done", "3", "--force", agent="Prometheus"))  # trusted has done_force

    def test_off_phase_cannot_claim(self):
        self.assert_ok(self.run_hub("new", "work"))
        r = self.run_hub("claim", "1", agent="Ghost")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("Ghost's phase off may not claim", r.stderr)
        self.assertEqual(self.read_board()["tasks"][0]["status"], "open")
        self.assert_ok(self.run_hub("claim", "1", agent="Apollo"))  # not in factory.json: no phase rules

    def test_new_budget_sets_the_tasks_own_budget(self):
        self.assert_ok(self.run_hub("new", "long one", "--budget", "240"))
        self.assertEqual(self.read_board()["tasks"][0]["budget_minutes"], 240)
        self.assertNotEqual(self.run_hub("new", "bad", "--budget", "0").returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
