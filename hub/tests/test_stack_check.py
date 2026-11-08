import json
import subprocess
import unittest

import live_merge  # at load: another test module sets sys.modules["live_merge"] to None
import stack_check


class StackCheckTests(unittest.TestCase):
    def test_kind(self):
        self.assertEqual(stack_check.kind("pyproject.toml"), "pyproject")
        self.assertEqual(stack_check.kind("backend/pyproject.toml"), "pyproject")
        self.assertEqual(stack_check.kind("package.json"), "package")
        self.assertEqual(stack_check.kind("frontend/package.json"), "package")
        self.assertEqual(stack_check.kind("Dockerfile"), "docker")
        self.assertEqual(stack_check.kind("Dockerfile.prod"), "docker")
        self.assertEqual(stack_check.kind("deploy/app.Dockerfile"), "docker")
        self.assertEqual(stack_check.kind("ci/Dockerfile.test"), "docker")
        self.assertIsNone(stack_check.kind("Makefile"))
        self.assertIsNone(stack_check.kind("uv.lock"))
        self.assertIsNone(stack_check.kind("docs/stack.md"))
        self.assertIsNone(stack_check.kind("docker-compose.yml"))

    def test_norm(self):
        self.assertEqual(stack_check.norm("OpenTelemetry SDK"), "opentelemetry-sdk")
        self.assertEqual(stack_check.norm("Python 3.12"), "python-3-12")
        self.assertEqual(stack_check.norm("uv"), "uv")
        self.assertEqual(stack_check.norm("--foo__bar--"), "foo-bar")

    def test_deps_pyproject(self):
        content = """
[project]
dependencies = ["requests >= 2.0", "Flask[async]", "opentelemetry-sdk"]

[project.optional-dependencies]
test = ["pytest-cov", "pytest>=8.0"]

[build-system]
requires = ["hatchling>=1.0"]

[tool.uv]
dev-dependencies = ["ruff"]

[dependency-groups]
dev = ["black", {include-group = "test"}]
"""
        d = stack_check.deps("pyproject", content)
        expected = {"requests", "Flask", "opentelemetry-sdk", "pytest-cov", "pytest", "hatchling", "ruff", "black"}
        self.assertEqual(d, expected)
        self.assertEqual(stack_check.deps("pyproject", None), set())
        with self.assertRaises(stack_check.Unreadable):
            stack_check.deps("pyproject", "invalid toml {[[")

    def test_deps_package(self):
        content = json.dumps({
            "dependencies": {"react": "^18.0.0", "axios": "1.0.0"},
            "devDependencies": {"typescript": "^5.0.0"},
            "peerDependencies": {"react-dom": "^18.0.0"},
            "optionalDependencies": {"fsevents": "^2.3.2"},
        })
        d = stack_check.deps("package", content)
        self.assertEqual(d, {"react", "axios", "typescript", "react-dom", "fsevents"})
        self.assertEqual(stack_check.deps("package", None), set())
        with self.assertRaises(stack_check.Unreadable):
            stack_check.deps("package", "{invalid json")

    def test_deps_docker(self):
        content = """
# Dockerfile
FROM --platform=linux/amd64 python:3.12-slim AS builder
RUN pip install ...
FROM ghcr.io/astral-sh/uv:0.5 AS uv-stage
COPY ...
FROM builder AS tester
RUN test ...
FROM scratch
COPY --from=builder /app /app
FROM alpine:3.18
"""
        d = stack_check.deps("docker", content)
        self.assertEqual(d, {"python", "uv", "alpine"})
        self.assertEqual(stack_check.deps("docker", None), set())

    def test_decided_and_declared(self):
        table = """
# Stack Table
| Layer | Choice | Status | Notes |
|---|---|---|---|
| Runtime | Python 3.12 | Decided | standard runtime |
| Tracing | OpenTelemetry SDK | Decided | spans as standard |
| Database | PostgreSQL 16 | Proposed | under review |
| Cache | Redis 7 | Decided | fast caching |
| Rejected | Memcached | Rejected | not needed |
"""
        rows = stack_check.decided(table)
        self.assertEqual(len(rows), 3)
        self.assertTrue(stack_check.declared("python", rows))
        self.assertTrue(stack_check.declared("opentelemetry-sdk", rows))
        self.assertTrue(stack_check.declared("opentelemetry_sdk", rows))
        self.assertTrue(stack_check.declared("redis", rows))
        # PostgreSQL is Proposed, not Decided
        self.assertFalse(stack_check.declared("postgresql", rows))
        # Memcached is Rejected
        self.assertFalse(stack_check.declared("memcached", rows))
        # Word boundaries: 'cat' is not declared on row containing 'category'
        cat_table = "| Tool | ScyllaDB Category | Decided | test |"
        cat_rows = stack_check.decided(cat_table)
        self.assertFalse(stack_check.declared("cat", cat_rows))

    def test_stack_path(self):
        self.assertEqual(stack_check.stack_path(None), "docs/stack.md")
        self.assertEqual(stack_check.stack_path({}), "docs/stack.md")
        self.assertEqual(stack_check.stack_path({"constraints": {}}), "docs/stack.md")
        self.assertEqual(stack_check.stack_path({"constraints": {"stack": "arch/stack.md"}}), "arch/stack.md")
        self.assertEqual(stack_check.stack_path({"constraints": {"stack": "  "}}), "docs/stack.md")
        self.assertEqual(stack_check.stack_path({"constraints": {"stack": "./docs/stack.md"}}), "docs/stack.md")

    def test_dotted_stack_path_still_keeps_the_table_out_of_the_lanes(self):
        pr = {"files": [{"path": "docs/stack.md"}], "changedFiles": 1, "body": "Verified: yes"}
        self.assertFalse(live_merge.docs_only(pr, stack="./docs/stack.md"))
        self.assertFalse(live_merge.fast_lane(pr, "Files: docs/", [], stack="./docs/stack.md"))
        self.assertTrue(live_merge.docs_only({"files": [{"path": "docs/x.md"}], "changedFiles": 1},
                                             stack="./docs/stack.md"))

    def test_message(self):
        msg_single = stack_check.message([("redis", "pyproject.toml")], "docs/stack.md")
        self.assertIn("adds `redis` (pyproject.toml)", msg_single)
        self.assertIn("not on a Decided row of `docs/stack.md`", msg_single)
        self.assertIn("naming it (Layer | Choice | Decided | why)", msg_single)
        self.assertIn("in an earlier PR", msg_single)

        msg_multi = stack_check.message([("axios", "package.json"), ("redis", "pyproject.toml")], "docs/stack.md")
        self.assertIn("adds `axios` (package.json), `redis` (pyproject.toml)", msg_multi)
        self.assertIn("naming each (Layer | Choice | Decided | why)", msg_multi)
        self.assertIn("in an earlier PR", msg_multi)

    def test_undeclared_no_dependency_files_touched(self):
        pr = {"files": [{"path": "src/main.py"}], "headRefOid": "h1"}
        calls = []
        fetch = lambda p, r: calls.append((p, r))
        self.assertEqual(stack_check.undeclared(pr, "main", fetch, "docs/stack.md"), [])
        self.assertEqual(calls, [])

    def test_undeclared_no_stack_table_in_repo(self):
        pr = {"files": [{"path": "pyproject.toml"}], "headRefOid": "h1"}
        fetch = lambda p, r: None
        self.assertEqual(stack_check.undeclared(pr, "main", fetch, "docs/stack.md"), [])

    def test_undeclared_finds_missing_and_allows_declared(self):
        files = {
            ("docs/stack.md", "main"): "| Lib | requests | Decided | http |\n",
            ("docs/stack.md", "h1"): "| Lib | requests | Decided | http |\n",
            ("pyproject.toml", "main"): '[project]\ndependencies = ["requests>=2.0"]\n',
            ("pyproject.toml", "h1"): '[project]\ndependencies = ["requests>=2.0", "httpx>=0.24", "Flask>=3.0"]\n',
        }
        fetch = lambda p, r: files.get((p, r))
        pr = {"files": [{"path": "pyproject.toml"}], "headRefOid": "h1"}
        res = stack_check.undeclared(pr, "main", fetch, "docs/stack.md")
        self.assertEqual(res, [("Flask", "pyproject.toml"), ("httpx", "pyproject.toml")])

    def test_undeclared_dep_plus_row_in_one_pr_is_held(self):
        files = {
            ("docs/stack.md", "main"): "| Lib | requests | Decided | http |\n",
            ("docs/stack.md", "h1"): "| Lib | requests | Decided | http |\n| Lib | httpx | Decided | async http |\n",
            ("pyproject.toml", "main"): '[project]\ndependencies = ["requests>=2.0"]\n',
            ("pyproject.toml", "h1"): '[project]\ndependencies = ["requests>=2.0", "httpx>=0.24"]\n',
        }
        fetch = lambda p, r: files.get((p, r))
        pr = {"files": [{"path": "pyproject.toml"}, {"path": "docs/stack.md"}], "headRefOid": "h1"}
        res = stack_check.undeclared(pr, "main", fetch, "docs/stack.md")
        self.assertEqual(res, [("httpx", "pyproject.toml")])

    def test_undeclared_bump_existing_is_not_added(self):
        files = {
            ("docs/stack.md", "main"): "| Lib | requests | Decided | http |\n",
            ("docs/stack.md", "h1"): "| Lib | requests | Decided | http |\n",
            ("pyproject.toml", "main"): '[project]\ndependencies = ["requests==2.25.0"]\n',
            ("pyproject.toml", "h1"): '[project]\ndependencies = ["requests==2.31.0"]\n',
        }
        fetch = lambda p, r: files.get((p, r))
        pr = {"files": [{"path": "pyproject.toml"}], "headRefOid": "h1"}
        res = stack_check.undeclared(pr, "main", fetch, "docs/stack.md")
        self.assertEqual(res, [])

    def test_undeclared_unreadable_raises(self):
        def fetch(p, r):
            if p == "pyproject.toml" and r == "h1":
                raise stack_check.Unreadable("network failure")
            return "| Lib | requests | Decided | http |\n"
        pr = {"files": [{"path": "pyproject.toml"}], "headRefOid": "h1"}
        with self.assertRaises(stack_check.Unreadable):
            stack_check.undeclared(pr, "main", fetch, "docs/stack.md")

    def test_gh_fetch(self):
        def run(argv):
            cmd = " ".join(argv)
            if "contents/found.txt" in cmd:
                return subprocess.CompletedProcess(argv, 0, "file content", "")
            if "contents/missing.txt" in cmd:
                return subprocess.CompletedProcess(argv, 1, "", "HTTP 404: Not Found")
            return subprocess.CompletedProcess(argv, 1, "", "HTTP 500: Server Error")

        fetch = stack_check.gh_fetch(run, "owner/repo")
        self.assertEqual(fetch("found.txt", "main"), "file content")
        self.assertIsNone(fetch("missing.txt", "main"))
        with self.assertRaises(stack_check.Unreadable):
            fetch("error.txt", "main")


if __name__ == "__main__":
    unittest.main()
