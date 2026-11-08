"""Spec lint catches overlaps before a change is approved or applied."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
FIXTURE = HUB / "tests" / "fixtures" / "spec_lint"


def line(aid, text, test=None):
    return {"id": aid, "v": 1, "text": text,
            "test": test or f"tests/acceptance/test_{aid.replace('-', '_').replace('.', '_')}.py"}


def requirement(rid, title, *lines):
    return {"id": rid, "title": title, "needs": [], "acceptance": list(lines)}


def change(cid, *added):
    return {"id": cid, "base_version": 1, "added": list(added), "modified": [], "removed": []}


class SpecLintTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hub-spec-lint-test-")
        self.addCleanup(self.temp.cleanup)
        self.hub = Path(self.temp.name) / "hub"
        self.spec = self.hub / "projects" / "sample" / "spec"
        (self.spec / "changes").mkdir(parents=True)
        self.repo = Path(self.temp.name) / "repo"
        (self.hub / "board.json").write_text(json.dumps({"next_id": 1, "tasks": []}))
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("HUB_")}
        self.env.update(HUB_DIR=str(self.hub), HUB_AGENT="Zeus")

    def write_spec(self, spec):
        path = self.spec / "requirements.json"
        path.write_text(json.dumps(spec))
        (self.spec / "spec.lock").write_text(json.dumps({
            "version": spec["version"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))

    def write_change(self, item):
        (self.spec / "changes" / f"{item['id']}.json").write_text(json.dumps(item))

    def replay(self, cid, version):
        self.write_spec(json.loads((FIXTURE / f"v{version}.json").read_text()))
        self.write_change(json.loads((FIXTURE / f"{cid}.json").read_text()))

    def run_spec(self, *args):
        return subprocess.run([sys.executable, str(HUB / "board.py"), "spec", *args,
                               "--project", "sample", "--repo", str(self.repo)], check=False, env=self.env,
                              capture_output=True, text=True, timeout=45)

    def make_repo(self):
        self.repo.mkdir()
        origin = Path(self.temp.name) / "origin.git"
        for args in (("init", "-q", "-b", "main", self.repo),
                     ("-C", self.repo, "config", "user.name", "Test"),
                     ("-C", self.repo, "config", "user.email", "test@example.invalid")):
            subprocess.run(["git", *map(str, args)], check=True, capture_output=True)
        (self.repo / "README").write_text("fixture\n")
        for args in (("-C", self.repo, "add", "README"),
                     ("-C", self.repo, "commit", "-qm", "initial"),
                     ("init", "-q", "--bare", "-b", "main", origin),
                     ("-C", self.repo, "remote", "add", "origin", origin),
                     ("-C", self.repo, "push", "-q", "origin", "main")):
            subprocess.run(["git", *map(str, args)], check=True, capture_output=True)

    def test_c003_replay_is_an_error_at_impact(self):
        self.replay("C-003", 3)
        self.make_repo()

        result = self.run_spec("impact", "C-003")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.startswith("lint:\n"), result.stdout)
        self.assertIn("L2", result.stdout)
        self.assertIn("A-6.1", result.stdout)
        self.assertIn("A-2.1", result.stdout)
        self.assertIn("GET /api/uptime", result.stdout)
        self.assertIn("L6", result.stdout)
        self.assertLess(result.stdout.index("L2"), result.stdout.index("C-003: spec v3"))

    def test_real_changes_lint_clean(self):
        for cid, version in (("C-004", 5), ("C-005", 6), ("C-007", 7)):
            with self.subTest(cid=cid):
                self.replay(cid, version)
                result = self.run_spec("lint", cid)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("error ", result.stdout)

    def test_original_c005_duplicate_title_is_an_error(self):
        self.write_spec(json.loads((FIXTURE / "v5.json").read_text()))
        self.write_change(json.loads((FIXTURE / "C-005-original.json").read_text()))

        result = self.run_spec("lint", "C-005")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("error L6", result.stdout)
        self.assertIn("R-8", result.stdout)
        self.assertIn("R-1", result.stdout)

    def test_needs_cycle_is_an_error(self):
        self.write_spec({"version": 1, "requirements": [
            requirement("R-1", "First", line("A-1.1", "do first")),
            requirement("R-2", "Second", line("A-2.1", "do second"))]})
        self.write_change({"id": "C-001", "base_version": 1, "added": [],
                           "modified": [{"id": "R-1", "needs": ["R-2"]},
                                        {"id": "R-2", "needs": ["R-1"]}], "removed": []})

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("needs cycle", result.stdout)

    def test_touches_overlap_warns_with_sequence_note(self):
        spec = {"version": 1, "requirements": [requirement(
            "R-1", "API: first", line("A-1.1", "do first"))]}
        spec["requirements"][0]["touches"] = ["src/api.py"]
        self.write_spec(spec)
        added = {"id": "R-2", "title": "Other: second", "needs": [],
                 "touches": ["src/*.py"], "acceptance": [{"id": "A-2.1", "text": "do second"}]}
        self.write_change(change("C-001", added))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("touches overlap", result.stdout)
        self.assertIn("auto-sequence", result.stdout)

    def test_two_globs_with_possible_shared_file_warn(self):
        spec = {"version": 1, "requirements": [requirement(
            "R-1", "First", line("A-1.1", "do first"))]}
        spec["requirements"][0]["touches"] = ["src/a*.py"]
        self.write_spec(spec)
        added = {"id": "R-2", "title": "Second", "needs": [],
                 "touches": ["src/*b.py"], "acceptance": [{"id": "A-2.1", "text": "do second"}]}
        self.write_change(change("C-001", added))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("touches overlap", result.stdout)

    def test_rank_must_be_unique_and_contiguous_when_ranked(self):
        spec = {"version": 1, "requirements": [requirement(
            "R-1", "First", line("A-1.1", "do first"))]}
        spec["requirements"][0]["rank"] = 1
        self.write_spec(spec)
        added = {"id": "R-2", "title": "Second", "rank": 1, "needs": [],
                 "acceptance": [{"id": "A-2.1", "text": "do second"}]}
        self.write_change(change("C-001", added))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("rank", result.stdout)

    def test_oversized_prd_header_and_requirement_warn(self):
        spec = {"version": 1, "header": {"problem": "\n".join(["long"] * 61)},
                "requirements": [requirement("R-1", "First", line("A-1.1", "do first"))]}
        spec["requirements"][0]["rank"] = 1
        self.write_spec(spec)
        added = {"id": "R-2", "title": "Second", "rank": 2, "why": "\n".join(["long"] * 11),
                 "needs": [], "acceptance": [{"id": "A-2.1", "text": "do second",
                                               "test": "tests/acceptance/test_A_2_1.py"}]}
        self.write_change(change("C-001", added))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("header exceeds", result.stdout)
        self.assertIn("R-2 exceeds", result.stdout)

    def test_new_prd_line_requires_explicit_test_path(self):
        spec = {"version": 1, "header": {"problem": "Example"},
                "requirements": [requirement("R-1", "First", line("A-1.1", "do first"))]}
        spec["requirements"][0]["rank"] = 1
        self.write_spec(spec)
        self.write_change(change("C-001", {"id": "R-2", "title": "Second", "rank": 2,
                                            "needs": [], "acceptance": [{"id": "A-2.1",
                                                                          "text": "do second"}]}))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("A-2.1 has no explicit test path", result.stdout)

    def test_unknown_set_paths_are_lint_errors(self):
        self.write_spec({"version": 1, "requirements": [requirement(
            "R-1", "First", line("A-1.1", "do first"))]})
        self.write_change({"id": "C-001", "base_version": 1, "added": [], "modified": [], "removed": [],
                           "set": {"header.problme": "typo", "requirements.R-1": "forbidden",
                                   "references.unknown": {"path": "x", "sha256": "0" * 64}}})

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("error L17", result.stdout)
        self.assertIn("header.problme", result.stdout)
        self.assertIn("requirements.R-1", result.stdout)
        self.assertIn("references.unknown", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_three_short_acceptance_lines_fit_size_budget(self):
        self.write_spec({"version": 1, "requirements": [requirement(
            "R-1", "First", line("A-1.1", "do first"))]})
        self.write_change(change("C-001", {"id": "R-2", "title": "Second", "needs": [],
                                            "acceptance": [{"id": f"A-2.{n}", "text": f"do case {n}"}
                                                           for n in range(1, 4)]}))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("L14", result.stdout)

    def test_same_requirement_can_use_same_endpoint(self):
        self.write_spec({"version": 1, "requirements": [requirement(
            "R-1", "Stats: summary", line("A-1.1", "GET /stats returns {count} for all users"))]})
        self.write_change(change("C-001", {"id": "A-1.2", "req": "R-1",
                                            "text": "GET /stats returns {count} after login"}))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("L2", result.stdout)

    def test_shape_conflict_fires_inside_one_requirement(self):
        self.write_spec({"version": 1, "requirements": [requirement(
            "R-1", "Stats: summary", line("A-1.1", "GET /stats returns {count}"))]})
        self.write_change(change("C-001", {"id": "A-1.2", "req": "R-1",
                                            "text": "GET /stats returns {total}"}))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("L4", result.stdout)

    def test_endpoint_key_normalizes_query_slash_and_parameter_names(self):
        self.write_spec({"version": 1, "requirements": [requirement(
            "R-1", "Users: lookup", line("A-1.1", "GET /users/<id>/?q=x returns {name}"))]})
        self.write_change(change("C-001", {"id": "R-2", "title": "Lookup: users", "needs": [],
                                            "acceptance": [{"id": "A-2.1",
                                                            "text": "GET /users/{user}/ returns {name}"}]}))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("L2", result.stdout)

    def test_endpoint_key_ignores_case(self):
        self.write_spec({"version": 1, "requirements": [requirement(
            "R-1", "Status: lookup", line("A-1.1", "GET /API/STATUS returns {ok}"))]})
        self.write_change(change("C-001", {"id": "R-2", "title": "Check: status", "needs": [],
                                            "acceptance": [{"id": "A-2.1",
                                                            "text": "get /api/status returns {ok}"}]}))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("L2", result.stdout)

    def test_lint_ok_suppresses_the_named_pair(self):
        self.replay("C-003", 3)
        item = json.loads((FIXTURE / "C-003.json").read_text())
        item["lint_ok"] = [{"rule": "L2", "lines": ["A-6.1", "A-2.1"],
                            "why": "deliberate second version"},
                           {"rule": "L6", "lines": ["R-6", "R-2"],
                            "why": "deliberate second version"}]
        self.write_change(item)

        result = self.run_spec("lint", "C-003")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("allowed L2", result.stdout)

    def test_new_line_without_a_current_heldout_check_warns_l9(self):
        self.write_spec({"version": 1, "requirements": [requirement(
            "R-1", "Ping: health", line("A-1.1", "GET /api/ping returns {pong}"))]})
        self.write_change(change("C-001", {"id": "R-2", "title": "Sum: add numbers", "needs": [], "acceptance": [
            {"id": "A-2.1", "text": "GET /api/sum returns {sum}", "test": "tests/acceptance/test_A_2_1.py"},
            {"id": "A-2.2", "text": "a missing sum parameter is a 400", "test": "tests/acceptance/test_A_2_2.py"}]}))
        heldout = self.hub / "projects" / "sample" / "heldout"
        heldout.mkdir()
        (heldout / "heldout.json").write_text(json.dumps({"A-2.1": {"v": 1, "tests": ["A-2.1/test_neg.py"]},
                                                          "A-2.2": {"v": 2, "tests": ["A-2.2/test_x.py"]}}))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([x.strip() for x in result.stdout.splitlines() if " L9" in x],
                         ["warn L9: A-2.2@1 has no held-out check"])  # A-1.1 is untouched; A-2.1's is current

    def test_same_text_and_same_test_are_errors(self):
        self.write_spec({"version": 1, "requirements": [requirement(
            "R-1", "First: report", line("A-1.1", "produce a weekly report", "tests/report.py"))]})
        self.write_change(change("C-001", {"id": "R-2", "title": "Second: report", "needs": [],
                                            "acceptance": [{"id": "A-2.1", "text": "produce a weekly report",
                                                            "test": "tests/report.py"}]}))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("L1", result.stdout)
        self.assertIn("L3", result.stdout)

    def test_near_text_and_named_file_are_warnings(self):
        self.write_spec({"version": 1, "requirements": [requirement(
            "R-1", "Archive: report", line("A-1.1", "writes daily reports to src/worker.py"))]})
        self.write_change(change("C-001", {"id": "R-2", "title": "Delivery: report", "needs": [],
                                            "acceptance": [{"id": "A-2.1",
                                                            "text": "writes daily report to src/worker.py"}]}))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("L5", result.stdout)
        self.assertIn("L7", result.stdout)

    def test_pending_change_on_same_endpoint_warns(self):
        self.write_spec({"version": 1, "requirements": [requirement(
            "R-1", "Old: endpoint", line("A-1.1", "GET /old returns {ok}"))]})
        self.write_change(change("C-001", {"id": "R-2", "title": "New: endpoint", "needs": [],
                                            "acceptance": [{"id": "A-2.1",
                                                            "text": "GET /new returns {ok}"}]}))
        self.write_change(change("C-002", {"id": "R-3", "title": "Other: endpoint", "needs": [],
                                            "acceptance": [{"id": "A-3.1",
                                                            "text": "GET /new returns {value}"}]}))

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("L8", result.stdout)
        self.assertIn("C-002", result.stdout)

    def test_pending_change_on_removed_line_warns(self):
        self.write_spec({"version": 1, "requirements": [requirement(
            "R-1", "Old: endpoint", line("A-1.1", "GET /old returns {ok}"))]})
        self.write_change({"id": "C-001", "base_version": 1,
                           "added": [], "modified": [], "removed": ["A-1.1"]})
        self.write_change({"id": "C-002", "base_version": 1, "added": [],
                           "modified": [{"id": "A-1.1", "text": "GET /changed returns {ok}"}],
                           "removed": []})

        result = self.run_spec("lint", "C-001")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("L8", result.stdout)
        self.assertIn("A-1.1", result.stdout)

    def test_rewind_dry_run_prints_lint_first(self):
        self.replay("C-003", 3)
        self.make_repo()

        result = self.run_spec("rewind", "C-003", "--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.startswith("lint:\n"), result.stdout)
        self.assertIn("L2", result.stdout)
        self.assertIn("dry run: nothing written", result.stdout)

    def test_apply_refuses_lint_error_without_writing(self):
        self.replay("C-003", 3)
        self.make_repo()
        change_path = self.spec / "changes" / "C-003.json"
        reviews = self.hub / "projects" / "sample" / "reviews"
        reviews.mkdir()
        (reviews / "C-003.json").write_text(json.dumps({
            "decision": "approve", "approved_path": str(change_path),
            "approved_sha256": hashlib.sha256(change_path.read_bytes()).hexdigest()}))
        before = ((self.hub / "board.json").read_bytes(), (self.spec / "requirements.json").read_bytes())

        result = self.run_spec("apply", "C-003")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("L2", result.stdout + result.stderr)
        self.assertEqual(before, ((self.hub / "board.json").read_bytes(),
                                  (self.spec / "requirements.json").read_bytes()))
        branches = subprocess.run(["git", "-C", str(self.repo), "branch", "--list", "change/C-003"],
                                  check=True, capture_output=True, text=True).stdout
        self.assertEqual(branches, "")


if __name__ == "__main__":
    unittest.main()
