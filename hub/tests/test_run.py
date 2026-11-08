"""Behavior checks for the headless task runner using fake agent CLIs."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run  # noqa: E402


class RunCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hub-run-test-")
        self.addCleanup(self.temp.cleanup)
        self.hub = Path(self.temp.name)
        self.bin = self.hub / "bin"
        self.bin.mkdir()
        self.log = self.hub / "invocation.json"
        self.task = {
            "id": "T-001", "title": "Check a small thing", "detail": "Read the README and report.",
            "status": "open", "owner": "Prometheus", "project": "hub", "notes": [],
        }
        self.write_board()
        fake = self.bin / "agent-fake"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys, time\n"
            "if '--help' in sys.argv:\n"
            "    print('--max-turns --max-budget-usd')\n"
            "    sys.exit(0)\n"
            "pathlib.Path(os.environ['FAKE_LOG']).write_text(json.dumps({\n"
            "    'argv': sys.argv[1:], 'cwd': os.getcwd(),\n"
            "    'api_keys': [key for key in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY') if key in os.environ],\n"
            "}))\n"
            "time.sleep(float(os.environ.get('FAKE_SLEEP', '0')))\n"
            "print(os.environ['FAKE_OUTPUT'])\n"
            "sys.exit(int(os.environ.get('FAKE_EXIT', '0')))\n"
        )
        fake.chmod(0o755)
        (self.bin / "claude").symlink_to(fake)
        (self.bin / "codex").symlink_to(fake)
        self.env = {**{k: v for k, v in os.environ.items() if not k.startswith("HUB_")},
                    "HUB_DIR": str(self.hub), "HUB_AGENT": "Prometheus", "HUB_LEAD": "Zeus",
                    "HUB_CLAUDE_AGENTS": "Zeus Hermes", "HUB_CODEX_AGENTS": "Prometheus",
                    "HUB_PROJECT": "", "FAKE_LOG": str(self.log),
                    "PATH": f"{self.bin}:{os.environ['PATH']}",
                    "ANTHROPIC_API_KEY": "must-not-leak", "OPENAI_API_KEY": "must-not-leak"}

    def write_board(self):
        (self.hub / "board.json").write_text(json.dumps({"next_id": 2, "tasks": [self.task]}))

    def board_task(self):
        return json.loads((self.hub / "board.json").read_text())["tasks"][0]

    def run_hubrun(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "run.py"), "T-001", *args],
                              env=self.env, text=True, capture_output=True, timeout=20)

    def result_note(self):
        note = self.board_task()["notes"][-1]["text"]
        self.assertTrue(note.startswith("hub_run: "), note)
        return json.loads(note.removeprefix("hub_run: "))

    def test_claude_run_records_cost_without_claiming_or_finishing_task(self):
        self.task["owner"] = "Zeus"
        self.write_board()
        self.env["FAKE_OUTPUT"] = json.dumps({
            "session_id": "claude-session", "num_turns": 3, "total_cost_usd": 0.42,
            "result": "Read it.",
        })
        result = self.run_hubrun("--max-turns", "4", "--budget-usd", "1.5")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        invocation = json.loads(self.log.read_text())
        self.assertEqual(invocation["cwd"], str(self.hub))
        self.assertIn("--max-turns", invocation["argv"])
        self.assertIn("--max-budget-usd", invocation["argv"])
        self.assertIn("Read the README and report.", " ".join(invocation["argv"]))
        self.assertEqual(invocation["api_keys"], [])
        self.assertEqual(self.board_task()["status"], "open")
        self.assertEqual(self.result_note()["session_id"], "claude-session")
        self.assertEqual(self.result_note()["num_turns"], 3)
        self.assertEqual(self.result_note()["total_cost_usd"], 0.42)

    def test_claude_default_budget_is_10_for_zeus_and_2_for_others(self):
        self.env["FAKE_OUTPUT"] = json.dumps({"session_id": "s", "num_turns": 1, "result": "ok"})
        for owner, budget in (("Zeus", "10.0"), ("Hermes", "2.0")):
            self.task["owner"] = owner
            self.write_board()
            result = self.run_hubrun()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            argv = json.loads(self.log.read_text())["argv"]
            self.assertEqual(argv[argv.index("--max-budget-usd") + 1], budget)

    def test_codex_run_records_thread_and_marks_cost_unknown(self):
        self.env["FAKE_OUTPUT"] = "\n".join([
            json.dumps({"type": "thread.started", "thread_id": "codex-thread"}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 9}}),
        ])
        result = self.run_hubrun()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        invocation = json.loads(self.log.read_text())
        self.assertEqual(invocation["argv"][:2], ["exec", "--json"])
        self.assertEqual(invocation["api_keys"], [])
        note = self.result_note()
        self.assertEqual(note["session_id"], "codex-thread")
        self.assertEqual(note["num_turns"], 1)
        self.assertIsNone(note["total_cost_usd"])
        self.assertEqual(note["exit_code"], 0)

    def test_pause_refuses_before_start_and_leaves_no_note(self):
        (self.hub / "PAUSE").touch()
        self.env["FAKE_OUTPUT"] = "{}"
        result = self.run_hubrun()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.board_task()["notes"], [])

    def test_claimed_task_refuses_without_starting_or_recording_note(self):
        self.task["status"] = "claimed"
        self.write_board()
        result = self.run_hubrun()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("claimed", result.stderr)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.board_task()["notes"], [])

    def test_lock_exists_during_run_and_is_removed_afterward(self):
        self.env["FAKE_OUTPUT"] = "{}"
        self.env["FAKE_SLEEP"] = "1"
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "run.py"), "T-001"],
            env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        lock = self.hub / "run" / "T-001.lock"
        deadline = time.monotonic() + 3
        while not self.log.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.log.exists(), "fake CLI never started")
        self.assertTrue(lock.exists(), "task lock missing during run")
        self.assertEqual(lock.read_text(), f"{process.pid}\n")
        second = self.run_hubrun()
        self.assertEqual(second.returncode, 2, second.stdout + second.stderr)
        self.assertIn("locked", second.stderr)
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertFalse(lock.exists(), "task lock remained after run")

    def test_dead_pid_lock_is_recovered(self):
        self.env["FAKE_OUTPUT"] = "{}"
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait(timeout=3)
        lock_dir = self.hub / "run"
        lock_dir.mkdir()
        lock = lock_dir / "T-001.lock"
        lock.write_text(f"{child.pid}\n")
        result = self.run_hubrun()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(lock.exists())
        self.assertEqual(self.result_note()["exit_code"], 0)

    def test_pause_stops_a_run_already_in_progress(self):
        self.env["FAKE_OUTPUT"] = json.dumps({"type": "thread.started", "thread_id": "paused"})
        self.env["FAKE_SLEEP"] = "5"
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "run.py"), "T-001", "--timeout-seconds", "10"],
            env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 3
        while not self.log.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.log.exists(), "fake CLI never started")
        (self.hub / "PAUSE").touch()
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 125, stdout + stderr)
        self.assertEqual(self.result_note()["stopped"], "paused")

    def test_timeout_kills_run_and_records_exit_code(self):
        self.env["FAKE_OUTPUT"] = "{}"
        self.env["FAKE_SLEEP"] = "5"
        result = self.run_hubrun("--timeout-seconds", "1")
        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
        self.assertEqual(self.result_note()["exit_code"], 124)
        self.assertEqual(self.board_task()["status"], "open")

    def test_stop_group_waits_ten_seconds_before_kill(self):
        process = Mock(pid=123)
        process.wait.side_effect = [subprocess.TimeoutExpired("agent", 10), 0]
        with patch.object(run.os, "killpg") as kill, \
                patch.object(run.time, "monotonic", side_effect=[0, 11]):
            run.stop_group(process)
        self.assertEqual(process.wait.call_args_list[0].kwargs, {"timeout": 10})
        self.assertEqual(kill.call_count, 2)

    def test_stop_group_kills_descendants_when_leader_exits(self):
        process = Mock(pid=123)
        with patch.object(run.os, "killpg") as kill, \
                patch.object(run.time, "monotonic", side_effect=[0, 11]), \
                patch.object(run.time, "sleep"):
            run.stop_group(process)
        self.assertEqual(kill.call_args_list[-1].args, (123, run.signal.SIGKILL))

    def test_stale_recovery_serializes_contenders(self):
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait(timeout=3)
        lock_dir = self.hub / "run"
        lock_dir.mkdir()
        lock = lock_dir / "T-001.lock"
        lock.write_text(f"{dead.pid}\n")
        with patch.object(run.fcntl, "flock", wraps=run.fcntl.flock) as flock:
            fd = run.acquire_lock(lock, "T-001")
        os.close(fd)
        lock.unlink()
        self.assertTrue(flock.called)

    def test_rate_limit_records_backoff_and_distinct_exit(self):
        self.env["FAKE_OUTPUT"] = '{"error":"429 rate limit; resets at 21:00 UTC"}'
        self.env["FAKE_EXIT"] = "1"
        result = self.run_hubrun()
        self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
        state = json.loads((self.hub / "state" / "Prometheus.limit.json").read_text())
        self.assertGreater(state["until"], time.time())
        self.assertIn("line", state)
        self.assertIn("limited until", "\n".join(n["text"] for n in self.board_task()["notes"]))
        self.assertFalse((self.hub / "run" / "T-001.lock").exists())

    def test_rate_limit_uses_explicit_reset_when_available(self):
        self.env["FAKE_OUTPUT"] = "usage limit resets at 2099-01-01T00:00:00Z"
        self.env["FAKE_EXIT"] = "1"
        result = self.run_hubrun()
        self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
        state = json.loads((self.hub / "state" / "Prometheus.limit.json").read_text())
        self.assertEqual(state["until"], 4070908800)

    def test_successful_report_about_rate_limits_does_not_back_off(self):
        self.env["FAKE_OUTPUT"] = '{"result":"Done: dispatch.py now backs off on a rate limit."}'
        result = self.run_hubrun()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.hub / "state" / "Prometheus.limit.json").exists())

    def test_existing_backoff_skips_agent_until_limit_passes(self):
        state = self.hub / "state"
        state.mkdir()
        (state / "Prometheus.limit.json").write_text('{"until":4070908800}')
        self.env["FAKE_OUTPUT"] = "{}"
        result = self.run_hubrun()
        self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.hub / "run" / "T-001.lock").exists())

    def test_concurrent_stale_recovery_only_starts_one_runner(self):
        self.env["FAKE_OUTPUT"] = "{}"
        self.env["FAKE_SLEEP"] = "1"
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait(timeout=3)
        lock_dir = self.hub / "run"
        lock_dir.mkdir()
        (lock_dir / "T-001.lock").write_text(f"{dead.pid}\n")
        processes = [subprocess.Popen(
            [sys.executable, str(ROOT / "run.py"), "T-001"], env=self.env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        outputs = [p.communicate(timeout=10) for p in processes]
        self.assertEqual(sorted(p.returncode for p in processes), [0, 2], outputs)
        self.assertFalse((lock_dir / "T-001.lock").exists())


if __name__ == "__main__":
    unittest.main()
