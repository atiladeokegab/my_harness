"""Factory outcomes shown beside each agent on the dashboard."""

import unittest
import json
import tempfile
import threading
import urllib.request
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dashboard import make_server, state
from tests.test_dashboard import needs_sockets


class FactoryDashboardCase(unittest.TestCase):
    def test_claude_launch_tags_metrics_for_local_sink(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            (home / "hub").mkdir()
            bin_dir = home / "bin"
            bin_dir.mkdir()
            log = home / "tmux.jsonl"
            fake = bin_dir / "tmux"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "if sys.argv[1] == 'has-session': sys.exit(1)\n"
                "with open(os.environ['FAKE_TMUX_LOG'], 'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\n"
            )
            fake.chmod(0o755)
            env = {**os.environ, "HOME": str(home), "FAKE_TMUX_LOG": str(log),
                   "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            command = f"source {Path(__file__).resolve().parents[1] / 'shell.sh'}; _hub_enter Zeus ."
            result = subprocess.run(["bash", "-c", command], env=env, cwd=root,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            launch = next(call for call in calls if call[:2] == ["new-session", "-d"]
                          and "hub-zeus" in call)
            self.assertIn("CLAUDE_CODE_ENABLE_TELEMETRY=1", launch)
            self.assertIn("OTEL_METRICS_EXPORTER=otlp", launch)
            self.assertIn("OTEL_RESOURCE_ATTRIBUTES=agent=Zeus", launch)
            self.assertIn("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:8765/v1/metrics", launch)

    def test_agent_outcomes_use_done_events_and_recorded_run_cost(self):
        board = {"tasks": [
            {"id": "T-1", "title": "A", "owner": "Zeus", "status": "done", "attempts": 1},
            {"id": "T-2", "title": "B", "owner": "Apollo", "status": "done"},
            {"id": "T-3", "title": "C", "owner": "Zeus", "status": "open", "attempts": 2},
        ]}
        events = [
            {"at": "2026-10-11T12:00:00+00:00", "by": "Apollo", "event": "done", "task": "T-2"},
            {"at": "2026-10-15T12:00:00+00:00", "by": "Zeus", "event": "done", "task": "T-1"},
            {"at": "2026-10-16T12:00:00+00:00", "by": "Zeus", "event": "note", "task": "T-1",
             "text": 'hub_run: {"kind":"claude","total_cost_usd":0.2,"exit_code":0}'},
        ]
        result = state(board, events, set(), False, {}, datetime(2026, 10, 17, tzinfo=timezone.utc))
        zeus = next(a for a in result["agents"] if a["name"] == "Zeus")
        apollo = next(a for a in result["agents"] if a["name"] == "Apollo")
        self.assertEqual(zeus["done_this_week"], 1)
        self.assertEqual(apollo["done_this_week"], 0)
        self.assertEqual(zeus["attempts"], 3)
        self.assertEqual(zeus["runs"], 1)
        self.assertEqual(zeus["cost_usd"], 0.2)

    @needs_sockets
    def test_local_otlp_metrics_post_is_written_to_daily_file(self):
        with tempfile.TemporaryDirectory() as root:
            server = make_server(root, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = {"resourceMetrics": [{"resource": {"attributes": [
                    {"key": "agent", "value": {"stringValue": "Zeus"}},
                ]}}]}
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}/v1/metrics",
                    data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"},
                    method="POST")
                with urllib.request.urlopen(request, timeout=3) as response:
                    self.assertEqual(response.status, 200)
                files = list((Path(root) / "inbox" / "telemetry").glob("metrics-*.jsonl"))
                self.assertEqual(len(files), 1)
                self.assertEqual(json.loads(files[0].read_text().splitlines()[0]), payload)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    @needs_sockets
    def test_factory_page_shows_current_agent_outcomes(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            path.joinpath("board.json").write_text(json.dumps({"tasks": [
                {"id": "T-1", "title": "Finished", "owner": "Zeus", "status": "done",
                 "attempts": 2, "notes": []},
            ]}))
            today = datetime.now(timezone.utc).isoformat()
            path.joinpath("events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in [
                {"at": today, "by": "Zeus", "event": "done", "task": "T-1"},
                {"at": today, "by": "Zeus", "event": "note", "task": "T-1",
                 "text": 'hub_run: {"kind":"claude","total_cost_usd":0.2,"exit_code":0}'},
            ]))
            server = make_server(root, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{server.server_address[1]}/factory", timeout=3
                ) as response:
                    page = response.read().decode()
                self.assertIn("Tasks done this week", page)
                self.assertIn("PRs merged", page)
                self.assertIn("Zeus", page)
                self.assertIn("$0.20", page)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    @needs_sockets
    def test_merge_ledger_counts_only_unreverted_prs_for_issue_owner(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            tasks = [
                {"id": "T-1", "project": "demo", "issue": 7, "owner": "Hermes", "status": "done"},
                {"id": "T-2", "project": "demo", "issue": 8, "owner": "Apollo", "status": "done"},
            ]
            path.joinpath("board.json").write_text(json.dumps({"tasks": tasks}))
            path.joinpath("events.jsonl").write_text("")
            live = path / "projects" / "demo"
            live.mkdir(parents=True)
            # merges count for the calendar week from Monday 00:00 UTC, so stamp them now, not on a fixed date
            at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            live.joinpath("live-state.json").write_text(json.dumps({"merge_events": [
                {"at": at, "pr": 2, "issue": 7, "event": "merged"},
                {"at": at, "pr": 3, "issue": 8, "event": "merged"},
                {"at": at, "pr": 3, "issue": 8, "event": "reverted"},
                {"at": "bad timestamp", "pr": 4, "issue": 8, "event": "merged"},
            ]}))
            server = make_server(root, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with urllib.request.urlopen(base + "/state.json", timeout=3) as response:
                    agents = json.load(response)["agents"]
                self.assertEqual(next(a for a in agents if a["name"] == "Hermes")["prs_merged"], 1)
                self.assertEqual(next(a for a in agents if a["name"] == "Apollo")["prs_merged"], 0)
                with urllib.request.urlopen(base + "/factory", timeout=3) as response:
                    page = response.read().decode()
                self.assertIn("<td>Hermes</td><td>0</td><td>1</td>", page)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
