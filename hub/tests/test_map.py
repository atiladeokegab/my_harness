"""Tests for `hub map`: offline code-only graphify wrapper with edge filtering and commit-keyed cache."""

import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import board as hb  # noqa: E402
import map as hub_map  # noqa: E402


FAKE_GRAPH = {
    "directed": True,
    "multigraph": False,
    "nodes": [
        {
            "id": "live_Live_merge",
            "label": "Live.merge()",
            "source_file": "live.py",
            "source_location": "L530",
            "file_type": "code",
            "_callable": True,
        },
        {
            "id": "live_merge_merge_tick",
            "label": "merge_tick()",
            "source_file": "live_merge.py",
            "source_location": "L50",
            "file_type": "code",
            "_callable": True,
        },
        {
            "id": "live_merge_worker_step",
            "label": "worker_step()",
            "source_file": "live_merge.py",
            "source_location": "L90",
            "file_type": "code",
            "_callable": True,
        },
        {
            "id": "clean_repo_register",
            "label": "register()",
            "source_file": "clean_repo.py",
            "source_location": "L450",
            "file_type": "code",
            "_callable": True,
        },
        {
            "id": "clean_repo_cmd_scrub",
            "label": "cmd_scrub()",
            "source_file": "clean_repo.py",
            "source_location": "L306",
            "file_type": "code",
            "_callable": True,
        },
        {
            "id": "board_cmd_done",
            "label": "cmd_done()",
            "source_file": "board.py",
            "source_location": "L740",
            "file_type": "code",
            "_callable": True,
        },
        {
            "id": "live_merge_rationale_51",
            "label": "Run one tick of the merge queue.",
            "source_file": "live_merge.py",
            "source_location": "L51",
            "file_type": "rationale",
        },
    ],
    "links": [
        # Kept: EXTRACTED cross-file call
        {
            "source": "live_Live_merge",
            "target": "live_merge_merge_tick",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "source_file": "live.py",
            "source_location": "L538",
        },
        # Kept: EXTRACTED same-file call
        {
            "source": "live_merge_merge_tick",
            "target": "live_merge_worker_step",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "source_file": "live_merge.py",
            "source_location": "L62",
        },
        # Kept: INFERRED same-file indirect_call (e.g. argparse set_defaults)
        {
            "source": "clean_repo_register",
            "target": "clean_repo_cmd_scrub",
            "relation": "indirect_call",
            "confidence": "INFERRED",
            "source_file": "clean_repo.py",
            "source_location": "L478",
        },
        # Dropped: INFERRED cross-file false-positive edge
        {
            "source": "board_cmd_done",
            "target": "live_merge_merge_tick",
            "relation": "indirect_call",
            "confidence": "INFERRED",
            "source_file": "board.py",
            "source_location": "L744",
        },
        # Kept: EXTRACTED docstring rationale edge
        {
            "source": "live_merge_rationale_51",
            "target": "live_merge_merge_tick",
            "relation": "rationale_for",
            "confidence": "EXTRACTED",
            "source_file": "live_merge.py",
            "source_location": "L51",
        },
    ],
}


class MapTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hub-map-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.hub = self.root / "hub"
        self.hub.mkdir()
        self.code = self.home / "code"
        self.code.mkdir()
        self.repo = self.code / "demo"
        self.repo.mkdir()
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.calls_log = self.root / "graphify_calls.jsonl"
        self.fixture_file = self.root / "fixture_graph.json"
        self.fixture_file.write_text(json.dumps(FAKE_GRAPH), encoding="utf-8")

        self._init_git_repo(self.repo)
        self._init_git_repo(self.hub)
        self._install_fake_graphify()

        env_patch = unittest.mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "HUB_DIR": str(self.hub),
                "PATH": f"{self.bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            },
        )
        env_patch.start()
        self.addCleanup(env_patch.stop)

        hub_dir_patch = unittest.mock.patch.object(hb, "HUB_DIR", str(self.hub))
        hub_dir_patch.start()
        self.addCleanup(hub_dir_patch.stop)

    def _init_git_repo(self, path: Path):
        env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
        subprocess.run(["git", "-C", str(path), "init", "-q"], env=env, check=True)
        subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], env=env, check=True)
        subprocess.run(["git", "-C", str(path), "config", "user.email", "t@e.st"], env=env, check=True)
        (path / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(path), "add", "app.py"], env=env, check=True)
        subprocess.run(["git", "-C", str(path), "commit", "-qm", "initial"], env=env, check=True)

    def _install_fake_graphify(self):
        script = self.bin_dir / "graphify"
        script.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env python3
                import json, os, subprocess, sys
                from pathlib import Path

                argv = sys.argv[1:]
                if not argv or argv[0] != "extract":
                    sys.stderr.write(f"unexpected graphify command: {{argv}}\\n")
                    sys.exit(2)
                target = Path(argv[1]).resolve()
                out_idx = argv.index("--out")
                out_dir = Path(argv[out_idx + 1]).resolve() / "graphify-out"
                out_dir.mkdir(parents=True, exist_ok=True)
                head = subprocess.check_output(["git", "-C", str(target), "rev-parse", "HEAD"], text=True).strip()
                graph = json.loads(Path({str(self.fixture_file)!r}).read_text(encoding="utf-8"))
                graph["built_at_commit"] = head
                (out_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")

                record = {{
                    "argv": argv,
                    "env": {{
                        k: os.environ.get(k)
                        for k in (
                            "GRAPHIFY_BACKEND",
                            "GRAPHIFY_NO_AUTO_REFRESH",
                            "GRAPHIFY_NO_CTA",
                            "GRAPHIFY_NO_TIPS",
                        )
                    }},
                }}
                with open({str(self.calls_log)!r}, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\\n")
                """
            ),
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)

    def _read_calls(self):
        if not self.calls_log.exists():
            return []
        return [json.loads(line) for line in self.calls_log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _run_map(self, *args):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            hub_map.run_cli(list(args))
        return out.getvalue(), err.getvalue()

    def test_extract_runs_offline_code_only_and_caches_by_built_at_commit(self):
        out1, _ = self._run_map("demo", "callers", "live_merge.py::merge_tick")
        self.assertIn("live.py:L538", out1)
        self.assertIn("Live.merge()", out1)

        calls = self._read_calls()
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(call["argv"][0], "extract")
        self.assertIn("--code-only", call["argv"])
        self.assertIn("--out", call["argv"])
        out_arg = Path(call["argv"][call["argv"].index("--out") + 1])
        self.assertEqual(out_arg, self.hub / "state" / "graph" / "demo")
        self.assertEqual(
            call["env"],
            {
                "GRAPHIFY_BACKEND": "none",
                "GRAPHIFY_NO_AUTO_REFRESH": "1",
                "GRAPHIFY_NO_CTA": "1",
                "GRAPHIFY_NO_TIPS": "1",
            },
        )

        # Second run at the same HEAD must reuse graph.json without invoking graphify again
        out2, _ = self._run_map("demo", "callers", "merge_tick")
        self.assertEqual(len(self._read_calls()), 1)
        self.assertEqual(out1, out2)

        # Advancing repo HEAD triggers a fresh extract
        (self.repo / "app.py").write_text("def main():\n    return 2\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qam", "advance"], check=True)
        self._run_map("demo", "callers", "merge_tick")
        self.assertEqual(len(self._read_calls()), 2)

    def test_keeps_extracted_and_same_file_inferred_but_drops_cross_file_inferred(self):
        # Cross-file INFERRED caller (board.py:L744 cmd_done -> live_merge.py::merge_tick) must be dropped
        callers_out, _ = self._run_map("demo", "callers", "live_merge.py::merge_tick")
        self.assertIn("live.py:L538", callers_out)
        self.assertIn("Live.merge()", callers_out)
        self.assertNotIn("board.py", callers_out)
        self.assertNotIn("cmd_done", callers_out)

        # Same-file INFERRED callee (clean_repo.py::register -> clean_repo.py::cmd_scrub) must be kept
        callees_out, _ = self._run_map("demo", "callees", "clean_repo.py::register")
        self.assertIn("clean_repo.py:L306", callees_out)
        self.assertIn("cmd_scrub()", callees_out)

        # Cross-file INFERRED callee from board.py::cmd_done must be dropped
        done_callees, _ = self._run_map("demo", "callees", "board.py::cmd_done")
        self.assertNotIn("merge_tick", done_callees)

    def test_explain_and_path_subcommands_and_board_registration(self):
        explain_out, _ = self._run_map("demo", "explain", "live_merge.py::merge_tick")
        self.assertIn("live_merge.py:L50", explain_out)
        self.assertIn("merge_tick()", explain_out)
        self.assertIn("Run one tick of the merge queue.", explain_out)
        self.assertIn("live.py:L538", explain_out)
        self.assertIn("live_merge.py:L90", explain_out)
        self.assertNotIn("cmd_done", explain_out)

        # Valid directed path across kept edges
        path_out, _ = self._run_map("demo", "path", "Live.merge", "worker_step")
        self.assertIn("live.py:L530", path_out)
        self.assertIn("live_merge.py:L50", path_out)
        self.assertIn("live_merge.py:L90", path_out)

        # Path across dropped cross-file INFERRED edge must not exist and must print caveat
        no_path_out, _ = self._run_map("demo", "path", "cmd_done", "worker_step")
        self.assertIn("no path", no_path_out.lower())
        self.assertIn("subprocess", no_path_out.lower())

        # Subprocess invocation via `board.py map ...` works and writes no dotfiles or hooks
        proc = subprocess.run(
            [sys.executable, str(ROOT / "board.py"), "map", "hub", "callers", "live_merge.merge_tick"],
            env={
                **os.environ,
                "HOME": str(self.home),
                "HUB_DIR": str(self.hub),
                "PATH": f"{self.bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            },
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("live.py:L538", proc.stdout)
        for forbidden in (".claude", ".gemini", ".codex", "AGENTS.md", "CLAUDE.md"):
            self.assertFalse((self.home / forbidden).exists())
            self.assertFalse((self.hub / forbidden).exists())

    def test_timeout_exits_cleanly_without_traceback_and_help_mentions_head_cache(self):
        real_run = subprocess.run

        def timeout_on_extract(cmd, *args, **kwargs):
            if len(cmd) >= 2 and cmd[1] == "extract":
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=300)
            return real_run(cmd, *args, **kwargs)

        err = io.StringIO()
        with unittest.mock.patch.object(hub_map.subprocess, "run", side_effect=timeout_on_extract):
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                hub_map.run_cli(["demo", "callers", "merge_tick"])
        self.assertNotEqual(ctx.exception.code, 0)
        self.assertIn("timed out", err.getvalue().lower())
        self.assertNotIn("Traceback", err.getvalue())

        help_out = io.StringIO()
        with contextlib.redirect_stdout(help_out), self.assertRaises(SystemExit) as help_ctx:
            hub_map.run_cli(["--help"])
        self.assertEqual(help_ctx.exception.code, 0)
        self.assertIn("HEAD", help_out.getvalue())
        self.assertIn("uncommitted", help_out.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
