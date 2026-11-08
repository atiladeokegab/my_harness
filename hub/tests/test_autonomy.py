"""Autonomy phases (living spec §4, T-576): hub agents, hub agent phase, hub approve / hub changes, and the
weekly promote/demote pass, against a throwaway hub. Never touches the live board or factory.json.

    env -u HUB_DIR -u HUB_AGENT -u HUB_PROJECT -u CLAUDE_CODE_SESSION_NAME uv run python -m unittest tests.test_autonomy
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# factory.example.json's autonomy table with a fuller roster: two codex reviewers, an agy seat, a lead.
LIVE = json.loads((ROOT / "factory.example.json").read_text())
LIVE["agents"] = [{"name": "Prometheus", "kind": "codex", "session": "hub-prometheus", "phase": "reviewer"},
                  {"name": "Orion", "kind": "codex", "session": "hub-orion", "phase": "reviewer"},
                  {"name": "Iris", "kind": "agy", "session": "hub-iris", "phase": "trusted", "reads": True},
                  {"name": "Hermes", "kind": "claude", "session": "hub-hermes", "phase": "trusted"},
                  {"name": "Zeus", "kind": "claude", "session": "hub-zeus", "phase": "lead"}]
LIVE["autonomy"]["known_kinds"] = ["claude", "codex", "agy"]
# Phases are pinned so a roster change cannot break these tests.
# The phase tests exercise trial on Iris; LIVE runs it trusted (see test below).
FIXTURE = json.loads(json.dumps(LIVE))
PHASES = {"Prometheus": "reviewer", "Iris": "trial", "Hermes": "trusted", "Zeus": "lead"}
FIXTURE["agents"] = [a for a in FIXTURE["agents"] if a["name"] in PHASES]
for _a in FIXTURE["agents"]:
    _a["phase"] = PHASES[_a["name"]]
HEAD = "abc1234def5678abc1234def5678abc1234def56"
# gh pr view stub: prints $GH_PR, or fails like an offline sandbox when it is unset.
GH = '#!/bin/sh\n[ -n "$GH_PR" ] && exec printf %s "$GH_PR"; echo offline >&2; exit 1\n'


def task(tid, owner, status="done", **extra):
    return {"id": tid, "title": f"Task {tid}", "detail": "", "status": status, "owner": owner, "deps": [],
            "notes": [], "project": "fs", "created_by": "Zeus", "created": "2026-10-19T00:00:00+00:00",
            "updated": "2026-10-19T00:00:00+00:00", **extra}


class Hub(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hub-autonomy-test-")
        self.addCleanup(self.temp.cleanup)
        self.hub = Path(self.temp.name)
        self.factory(FIXTURE)
        self.board([])
        (self.hub / "bin").mkdir()
        (self.hub / "bin" / "gh").write_text(GH)
        (self.hub / "bin" / "gh").chmod(0o755)

    def factory(self, cfg):
        (self.hub / "factory.json").write_text(json.dumps(cfg, indent=2) + "\n")

    def read_factory(self):
        return json.loads((self.hub / "factory.json").read_text())

    def board(self, tasks):
        (self.hub / "board.json").write_text(json.dumps({"next_id": 50, "tasks": tasks}))

    def ledger(self, *events):
        with open(self.hub / "events.jsonl", "a") as f:
            for e in events:
                f.write(json.dumps({"at": "2026-10-19T00:00:00+00:00", **e}) + "\n")

    def events(self, name=None):
        p = self.hub / "events.jsonl"
        out = [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
        return [e for e in out if name is None or e["event"] == name]

    def env(self, agent, **extra):
        env = {k: v for k, v in os.environ.items()
               if k not in ("HUB_DIR", "HUB_AGENT", "HUB_PROJECT", "CLAUDE_CODE_SESSION_NAME", "GH_PR")}
        return {**env, "HUB_DIR": str(self.hub), "HOME": str(self.hub), "HUB_AGENT": agent,
                "PATH": f"{self.hub / 'bin'}:{env['PATH']}", **extra}

    def hub_cmd(self, *args, agent="Zeus", **extra):
        return subprocess.run([sys.executable, str(ROOT / "board.py"), *args], env=self.env(agent, **extra),
                              text=True, capture_output=True, timeout=60)

    def ok(self, r):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout


class AgentsTest(Hub):
    def test_live_codex_roles_keep_a_dedicated_reviewer_and_atlas_available(self):
        self.factory(LIVE)
        out = self.ok(self.hub_cmd("agents"))
        self.assertRegex(out, r"(?m)^Prometheus\s+reviewer\b")
        self.assertRegex(out, r"(?m)^Orion\s+reviewer\b")

    def test_brief_reports_current_phase_dispatch_and_reviewer(self):
        out = self.ok(self.hub_cmd("brief", agent="Prometheus"))
        self.assertIn("phase reviewer; build dispatch off; reset off", out)
        self.assertIn("Reviewer: Prometheus", out)
        self.assertIn("factory.json", out)
        self.factory({**FIXTURE, "agents": [{"name": "Orion", "kind": "codex", "phase": "trusted"}]})
        out = self.ok(self.hub_cmd("brief", agent="Orion"))
        self.assertIn("phase trusted; build dispatch on; reset per-task", out)

    def test_iris_shows_as_trial(self):
        """The acceptance line for the whole living-spec set, on the live factory.json."""
        out = self.ok(self.hub_cmd("agents"))
        for name, phase in PHASES.items():
            self.assertRegex(out, rf"(?m)^{name}\s+{phase}\b")
        self.assertRegex(out, r"(?m)^\| phase \| dispatch \| reset \| budget \| may \|$")
        self.assertRegex(out, r"(?m)^\| trial \| yes \| no \| 90 min \| claim, push, open_pr \|$")

    def test_live_iris_is_trusted_and_can_close_with_no_verify(self):
        """Overnight it closes scratch-branch tasks with --no-verify and lands branches."""
        self.factory(LIVE)
        self.board([task("T-001", "Iris", status="claimed")])
        r = self.hub_cmd("done", "T-001", "--no-verify", "--note", "closed on its scratch branch, sha abc1234",
                         agent="Iris")
        self.assertNotIn("needs done_force", r.stderr)
        self.ok(r)

    def test_record_reads_the_last_done_tasks_from_the_ledger(self):
        self.board([task(f"T-00{n}", "Prometheus") for n in range(1, 8)])
        self.ledger(
            {"by": "Prometheus", "event": "done", "task": "T-001", "verify": "passed"},  # outside the last 5
            {"by": "Prometheus", "event": "verify_failed", "task": "T-001"},
            {"by": "Prometheus", "event": "done", "task": "T-002", "verify": "passed"},
            {"by": "Prometheus", "event": "verify_failed", "task": "T-003"},
            {"by": "Prometheus", "event": "done", "task": "T-003", "verify": "passed"},
            {"by": "Prometheus", "event": "override", "task": "T-004", "verb": "done"},
            {"by": "Prometheus", "event": "done", "task": "T-004", "verify": "passed"},
            {"by": "Prometheus", "event": "done", "task": "T-005", "verify": "skipped"},
            {"by": "Watchdog", "event": "over_budget", "task": "T-006", "level": 1},
            {"by": "Prometheus", "event": "done", "task": "T-006", "verify": "passed"},
            {"by": "Prometheus", "event": "done", "task": "T-007", "verify": "passed"},
            {"by": "hub-live", "event": "reopened", "task": "T-007", "why": "reverted after smoke: red"},
            {"by": "Hermes", "event": "done", "task": "T-002", "verify": "passed"},  # someone else's done
        )
        out = self.ok(self.hub_cmd("agents"))
        line = next(x for x in out.splitlines() if x.startswith("Prometheus"))
        self.assertIn("record 0/5 clean", line)
        for flag in ("T-003 verify failed", "T-004 override", "T-005 no verify", "T-006 over budget",
                     "T-007 reverted"):
            self.assertIn(flag, line)
        self.assertNotIn("T-001", line)
        self.assertNotIn("T-002", line)  # clean tasks are counted, not listed

    def test_a_dead_dispatch_or_reset_field_is_warned_about(self):
        cfg = json.loads(json.dumps(FIXTURE))
        cfg["agents"][0].update(dispatch=True, reset="per-task")
        self.factory(cfg)
        out = self.ok(self.hub_cmd("agents"))
        self.assertIn("warning: Prometheus: dispatch, reset ignored; phase reviewer decides them", out)
        self.assertNotIn("warning: Hermes", out)


class PhaseTest(Hub):
    def test_the_lead_changes_a_phase_and_it_is_logged(self):
        cfg = json.loads(json.dumps(FIXTURE))
        cfg["agents"][1]["reset"] = "per-task"  # a dead field goes with the change
        self.factory(cfg)
        out = self.ok(self.hub_cmd("agent", "phase", "iris", "trusted", "--why", "five clean tasks"))
        self.assertIn("Iris: trial -> trusted", out)
        after = self.read_factory()
        heph = after["agents"][1]
        self.assertEqual(heph["phase"], "trusted")
        self.assertNotIn("reset", heph)
        self.assertEqual(heph["reads"], True)
        self.assertEqual({k: v for k, v in after.items() if k != "agents"},
                         {k: v for k, v in FIXTURE.items() if k != "agents"})
        [e] = self.events("phase")
        self.assertEqual({k: e[k] for k in ("by", "agent", "from", "to", "why")},
                         {"by": "Zeus", "agent": "Iris", "from": "trial", "to": "trusted",
                          "why": "five clean tasks"})

    def test_only_the_lead_phase_changes_phases_and_as_does_not_help(self):
        before = (self.hub / "factory.json").read_text()
        for args in ((), ("--as", "Zeus")):
            r = self.hub_cmd(*args, "agent", "phase", "Hermes", "trusted", "--why", "x", agent="Hermes")
            self.assertNotEqual(r.returncode, 0, r.stdout)
            self.assertIn("only the lead phase", r.stderr)
        self.assertEqual((self.hub / "factory.json").read_text(), before)
        self.assertEqual(self.events("phase"), [])

    def test_unknown_phase_or_agent_is_refused(self):
        r = self.hub_cmd("agent", "phase", "Hermes", "boss", "--why", "x")
        self.assertIn("no phase 'boss'", r.stderr)
        r = self.hub_cmd("agent", "phase", "Apollo", "trial", "--why", "x")
        self.assertIn("Apollo is not in factory.json", r.stderr)
        self.assertEqual(self.events("phase"), [])


class ApproveTest(Hub):
    def setUp(self):
        super().setUp()
        self.board([task("T-001", "Prometheus", "claimed", agent="Prometheus", kind="factory", issue=12)])
        self.factory({**FIXTURE, "repos": [{"repo": "o/fs"}]})
        self.pr = {"GH_PR": json.dumps({"headRefName": "task/T-001", "headRefOid": HEAD, "body": "Closes #12"})}

    def test_a_reviewer_approval_is_recorded_with_both_identities(self):
        out = self.ok(self.hub_cmd("approve", "o/fs#13", HEAD[:12], agent="Hermes", **self.pr))
        self.assertIn("approval recorded", out)
        self.ok(self.hub_cmd("approve", "fs#13", HEAD, "--as", "Zeus", agent="Hermes", **self.pr))
        first, second = self.events("approved")
        self.assertEqual({k: first[k] for k in ("by", "env", "repo", "pr", "sha", "builder", "task")},
                         {"by": "Hermes", "env": "Hermes", "repo": "o/fs", "pr": 13, "sha": HEAD,
                          "builder": "Prometheus", "task": "T-001"})
        self.assertEqual((second["by"], second["env"]), ("Zeus", "Hermes"))  # the mismatch shows in the ledger

    def test_the_builder_cannot_approve_its_own_pr_even_with_as(self):
        for args in ((), ("--as", "Hermes")):
            r = self.hub_cmd("approve", "o/fs#13", HEAD, *args, agent="Prometheus", **self.pr)
            self.assertNotEqual(r.returncode, 0, r.stdout)
            self.assertIn("Prometheus built o/fs#13", r.stderr)
        self.assertEqual(self.events("approved"), [])

    def test_the_builder_is_found_from_closes_when_the_branch_is_not_a_task(self):
        pr = {"GH_PR": json.dumps({"headRefName": "12-time", "headRefOid": HEAD, "body": "Closes #12"})}
        r = self.hub_cmd("approve", "o/fs#13", HEAD, agent="Prometheus", **pr)
        self.assertIn("Prometheus built o/fs#13", r.stderr)

    def test_changes_are_recorded_with_why(self):
        self.ok(self.hub_cmd("changes", "o/fs#13", HEAD[:7], "the test never goes red", agent="Hermes", **self.pr))
        [e] = self.events("changes")
        self.assertEqual((e["by"], e["sha"], e["why"], e["task"]), ("Hermes", HEAD, "the test never goes red", "T-001"))

    def test_refusals(self):
        cases = {
            "not the head": (("approve", "o/fs#13", "0000000"), "Hermes", self.pr, "is not the head of o/fs#13"),
            "gh unreachable": (("approve", "o/fs#13", HEAD), "Hermes", {}, "cannot read o/fs#13"),
            "phase without review": (("approve", "o/fs#13", HEAD), "Iris", self.pr,
                                     "Iris's phase trial has no review"),
            "bad ref": (("approve", "13", HEAD), "Hermes", self.pr, "<owner/repo>#<pr>"),
        }
        for label, (args, agent, extra, msg) in cases.items():
            with self.subTest(label):
                r = self.hub_cmd(*args, agent=agent, **extra)
                self.assertNotEqual(r.returncode, 0, label)
                self.assertIn(msg, r.stderr, label)
        self.assertEqual(self.events("approved"), [])


class WeeklyTest(Hub):
    def weekly(self):
        env = self.env("Dispatch")
        r = subprocess.run([sys.executable, str(ROOT / "dispatch.py"), "weekly"], env=env, text=True,
                           capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def done(self, agent, *tids, **extra):
        self.ledger(*({"by": agent, "event": "done", "task": t, "verify": "passed", **extra} for t in tids))

    def test_a_clean_trial_record_opens_one_promote_task_for_zeus(self):
        self.done("Iris", *(f"T-00{n}" for n in range(1, 6)))
        self.weekly()
        self.weekly()
        promote = [t for t in json.loads((self.hub / "board.json").read_text())["tasks"]
                   if t["title"] == "Promote Iris to trusted?"]
        self.assertEqual(len(promote), 1)
        self.assertEqual(promote[0]["owner"], "Zeus")
        self.assertEqual(self.read_factory()["agents"][1]["phase"], "trial")  # promotion is Zeus's call

    def test_a_short_record_opens_nothing(self):
        self.done("Iris", "T-001", "T-002")
        self.weekly()
        self.assertFalse(any(t["title"].startswith("Promote Iris")
                             for t in json.loads((self.hub / "board.json").read_text())["tasks"]))

    def test_a_revert_demotes_a_trusted_agent_and_tells_zeus(self):
        self.done("Hermes", "T-001")
        self.ledger({"by": "hub-live", "event": "reopened", "task": "T-001", "why": "reverted after smoke: x"})
        out = self.weekly()
        self.assertIn("Hermes: trusted -> trial", out)
        self.assertEqual(self.read_factory()["agents"][2]["phase"], "trial")
        [e] = self.events("phase")
        self.assertEqual((e["by"], e["to"]), ("Dispatch", "trial"))
        self.assertIn("T-001 reverted", e["why"])
        self.assertIn("Hermes", (self.hub / "inbox" / "Zeus.jsonl").read_text())

    def test_two_double_overruns_in_a_row_demote(self):
        self.done("Hermes", "T-001")
        self.ledger({"by": "Watchdog", "event": "over_budget", "task": "T-002", "level": 2},
                    {"by": "Watchdog", "event": "over_budget", "task": "T-003", "level": 2})
        self.done("Hermes", "T-002", "T-003")
        self.weekly()
        self.assertEqual(self.read_factory()["agents"][2]["phase"], "trial")

    def test_one_double_overrun_does_not_demote(self):
        self.ledger({"by": "Watchdog", "event": "over_budget", "task": "T-002", "level": 2})
        self.done("Hermes", "T-002", "T-003")
        self.weekly()
        self.assertEqual(self.read_factory()["agents"][2]["phase"], "trusted")


if __name__ == "__main__":
    unittest.main()
