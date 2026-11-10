"""The generic starter uses the existing intent, design-pin and spec workflow."""
import json
from pathlib import Path
import sys
from unittest import mock

from tests.test_board import BoardHelpers as BoardTestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import gh_sync
import prd
import prd_grill

TEMPLATE = ROOT / "templates" / "prd" / "project.json"
ANSWERS = {
    "header.problem": "Operators cannot collect local incident files into one portable bundle",
    "header.users": "Support operator: collect a bundle from a local directory",
    "header.goals[+]": "Collect a portable support bundle | incident evidence travels together | CLI writes an archive and manifest",
    "header.non_goals": "Web UI | Hosted storage",
    "constraints.stack": "Python standard library",
    "constraints.limits": "Never archive files outside the supplied directory",
    "constraints.offline_tests": "yes",
    "requirements[+]": "Collect a support bundle",
    "requirements[R-1].why": "Operators need portable incident evidence",
    "requirements[R-1].touches": "bundle.py",
    "requirements[R-1].acceptance[+]": "The bundle CLI writes an archive and manifest for a valid directory; a missing directory exits nonzero without an archive",
    "requirements[R-1].rank": "1",
}


class GenericProjectPRD(BoardTestCase):
    def draft(self):
        return json.loads(TEMPLATE.read_text())

    def filled(self):
        doc = self.draft()
        for path, answer in ANSWERS.items():
            self.assertEqual(prd_grill.next_gap(doc)["path"], path)
            prd_grill.set_field(doc, path, answer)
        return doc

    def test_starter_requires_real_intent_instead_of_inventing_a_project(self):
        doc = self.draft()
        self.assertEqual(prd.validate(doc)[0], [])
        self.assertFalse(prd_grill.ready(doc))
        self.assertEqual(prd_grill.next_gap(doc)["path"], "header.problem")
        self.assertEqual(doc["requirements"], [])

    def test_non_hackathon_goal_bootstraps_into_the_existing_tracker(self):
        doc = self.filled()
        self.assertTrue(prd_grill.ready(doc))
        seed = self.root / "seed.json"
        seed.write_text(json.dumps(doc))
        self.assert_ok(self.run_hub("spec", "init", "support-bundle", "--from", seed))
        with mock.patch.object(prd.hb, "HUB_DIR", str(self.root)):
            loaded = prd.load("support-bundle")
            self.assertEqual(loaded["header"]["goals"], doc["header"]["goals"])
            self.assertEqual(gh_sync.current_lines("support-bundle"), {"A-1.1": 1})

    def test_approved_design_is_pinned_and_later_drift_is_rejected(self):
        doc = self.filled()
        design = self.root / "design.md"
        design.write_text("Approved UI: one action, readable tokens, measured blind review.\n")
        bases = [str(self.root)]
        prd_grill.set_field(doc, "references.design", "design.md", bases=bases)
        self.assertEqual(prd.validate(doc, bases)[0], [])
        design.write_text("Unreviewed replacement direction.\n")
        self.assertTrue(any("sha256 does not match" in error for error in prd.validate(doc, bases)[0]))

    def test_grilled_canonical_draft_can_become_the_initial_live_spec(self):
        draft = self.root / "projects" / "support-bundle" / "spec" / "prd.json"
        draft.parent.mkdir(parents=True)
        draft.write_text(json.dumps(self.draft()))
        for path, answer in ANSWERS.items():
            result = self.run_hub("prd", "grill", "support-bundle", "--answer", f"{path}={answer}", "--json")
            self.assert_ok(result)
        self.assertTrue(json.loads(result.stdout)["ready"])
        self.assert_ok(self.run_hub("spec", "init", "support-bundle", "--from", draft))
        self.assertEqual(json.loads((draft.parent / "spec.lock").read_text())["version"], 1)
        self.assertEqual(json.loads(draft.read_text())["header"]["goals"], self.filled()["header"]["goals"])
        blocked = self.run_hub("new", "manual", "--project", "support-bundle")
        self.assertNotEqual(blocked.returncode, 0)

    def test_draft_promotion_does_not_replace_locked_or_unapproved_state(self):
        cases = [
            ("locked", "prd.json", 1, True, False, True),
            ("different-seed", "prd.json", 1, False, True, True),
            ("older-version", "prd.json", 2, False, False, True),
            ("unfinished", "prd.json", 1, False, False, False),
            ("legacy-doc", "requirements.json", 1, False, False, True),
            ("dual-docs", "prd.json", 1, False, False, True),
            ("orphan-lock", None, 1, True, True, True),
        ]
        for project, filename, version, locked, other_seed, ready in cases:
            with self.subTest(project=project):
                directory = self.root / "projects" / project / "spec"
                directory.mkdir(parents=True)
                doc = self.filled() if ready else self.draft()
                doc["version"] = version
                draft = directory / filename if filename else None
                if draft:
                    draft.write_text(json.dumps(doc))
                if project == "dual-docs":
                    (directory / "requirements.json").write_text(json.dumps(doc))
                if locked:
                    (directory / "spec.lock").write_text('{"version":1,"sha256":"preserve"}')
                source = self.root / f"{project}-seed.json" if other_seed else draft
                if other_seed:
                    source.write_text(json.dumps(self.filled()))
                before = {p.name: p.read_bytes() for p in directory.iterdir()}
                result = self.run_hub("spec", "init", project, "--from", source)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir()}, before)

    def test_draft_promotion_checks_project_design_and_spine_pins(self):
        for reference in ("design", "spine"):
            for state in ("unchanged", "missing", "drifted"):
                with self.subTest(reference=reference, state=state):
                    project = f"{reference}-{state}"
                    directory = self.root / "projects" / project
                    draft = directory / "spec" / "prd.json"
                    draft.parent.mkdir(parents=True)
                    pinned = directory / f"{reference}.md"
                    pinned.write_text("Approved project contract.\n")
                    doc = self.filled()
                    prd_grill.set_field(doc, f"references.{reference}", pinned.name, bases=[str(directory)])
                    draft.write_text(json.dumps(doc))
                    if state == "missing":
                        pinned.unlink()
                    elif state == "drifted":
                        pinned.write_text("Unreviewed replacement.\n")
                    before = draft.read_bytes()
                    grilled = self.run_hub("prd", "grill", project, "--json")
                    self.assert_ok(grilled)
                    self.assertEqual(json.loads(grilled.stdout)["ready"], state == "unchanged")
                    result = self.run_hub("spec", "init", project, "--from", draft)
                    self.assertEqual(result.returncode == 0, state == "unchanged", result.stdout + result.stderr)
                    self.assertEqual((draft.parent / "spec.lock").exists(), state == "unchanged")
                    if state != "unchanged":
                        self.assertEqual(draft.read_bytes(), before)

    def test_draft_alias_promotes_the_canonical_source_without_creating_legacy_file(self):
        draft = self.root / "projects" / "aliased" / "spec" / "prd.json"
        draft.parent.mkdir(parents=True)
        draft.write_text(json.dumps(self.filled()))
        alias = self.root / "seed.json"
        alias.symlink_to(draft)
        self.assert_ok(self.run_hub("spec", "init", "aliased", "--from", alias))
        self.assertTrue((draft.parent / "spec.lock").exists())
        self.assertFalse((draft.parent / "requirements.json").exists())


class ProjectPRDReminder(BoardTestCase):
    def tasks(self, rows):
        self.write_board({"next_id": len(rows) + 1, "tasks": [
            {"id": f"T-{i:03}", "title": "existing", "project": project, "status": status,
             "owner": None, "deps": [], "notes": []}
            for i, (project, status) in enumerate(rows, 1)]})

    def test_reminder_starts_at_four_active_tasks_without_blocking_creation(self):
        for existing in range(4):
            with self.subTest(existing=existing):
                self.tasks([("p", "open")] * existing)
                result = self.run_hub("new", "next", "--project", "p", "--detail", "bounded work")
                self.assert_ok(result)
                self.assertEqual("no live PRD" in result.stdout, existing == 3)
                self.assertEqual(len(self.read_board()["tasks"]), existing + 1)
                if existing == 3:
                    self.assertIn("hub prd grill p", result.stdout)
                    self.assertIn(str(TEMPLATE), result.stdout)

    def test_counts_are_project_local_and_ignore_finished_tasks(self):
        self.tasks([("p", "done")] * 4 + [("other", "open")] * 4)
        result = self.run_hub("new", "next", "--project", "p")
        self.assert_ok(result)
        self.assertNotIn("no live PRD", result.stdout)
        self.tasks([("p", status) for status in ("open", "claimed", "blocked")])
        result = self.run_hub("new", "next", "--project", "p")
        self.assert_ok(result)
        self.assertIn("no live PRD", result.stdout)

    def test_draft_reminds_and_live_spec_keeps_existing_gate(self):
        self.tasks([("p", "open")] * 3)
        directory = self.root / "projects" / "p" / "spec"
        directory.mkdir(parents=True)
        (directory / "prd.json").write_text('{"version":1,"requirements":[]}')
        draft = self.run_hub("new", "next", "--project", "p")
        self.assert_ok(draft)
        self.assertIn("no live PRD", draft.stdout)
        (directory / "spec.lock").write_text('{"version":1}')
        live = self.run_hub("new", "manual", "--project", "p")
        self.assertNotEqual(live.returncode, 0)
        self.assertIn("tasks for p come from hub spec apply", live.stderr)
        generated = self.run_hub("new", "generated", "--project", "p", "--from-spec", "--generated-from", "v1")
        self.assert_ok(generated)
        self.assertNotIn("no live PRD", generated.stdout)

    def test_unscoped_tasks_keep_the_existing_project_hint(self):
        self.tasks([(None, "open")] * 4)
        result = self.run_hub("new", "next")
        self.assert_ok(result)
        self.assertNotIn("no live PRD", result.stdout)
        self.assertIn("pass --project", result.stdout)
