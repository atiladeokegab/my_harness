"""Skills-parity test: every plugin skill's frontmatter and hub verbs are real (T-585)."""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
SKILLS_DIR = HUB / "plugin" / "skills"
if not SKILLS_DIR.is_dir():  # a checkout keeps skills in claude/skills, an install in plugin/skills
    SKILLS_DIR = HUB.parent / "claude" / "skills"
BAD_FIXTURE = HUB / "tests" / "fixtures" / "bad_skill" / "SKILL.md"


def parse_frontmatter(text: str) -> tuple[str | None, str | None]:
    if not text.startswith("---\n"):
        return None, None
    parts = text.split("\n---\n", 1)
    if len(parts) < 2:
        return None, None
    head = parts[0][4:]
    name_m = re.search(r"(?m)^name:[ \t]*(\S+)[ \t]*$", head)
    desc_m = re.search(r"(?ms)^description:[ \t]*(.*?)(?=^[A-Za-z0-9_-]+:|\Z)", head)
    name = name_m.group(1).strip("\"'") if name_m else None
    desc = None
    if desc_m:
        raw = desc_m.group(1).strip()
        if raw in (">", "|", ">-", "|-"):
            desc = ""
        else:
            desc = " ".join(raw.lstrip(">|-").split()).strip("\"'")
    return name, desc


def load_hub_verbs() -> tuple[set[str], dict[str, set[str]]]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("HUB_DIR", "HUB_AGENT", "HUB_PROJECT", "CLAUDE_CODE_SESSION_NAME")
    }
    out = subprocess.run(
        [sys.executable, str(HUB / "board.py"), "--help"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout
    verbs = set(re.search(r"\{([a-z0-9,_-]+)\}", out).group(1).split(","))
    nested: dict[str, set[str]] = {}
    for parent in ("spec", "ws"):
        if parent in verbs:
            sub_out = subprocess.run(
                [sys.executable, str(HUB / "board.py"), parent, "--help"],
                env=env,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            ).stdout
            m = re.search(r"\{([a-z0-9,_-]+)\}", sub_out)
            if m:
                nested[parent] = set(m.group(1).split(","))
    return verbs, nested


def check_skill_file(
    path: Path, verbs: set[str], nested: dict[str, set[str]]
) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    name, desc = parse_frontmatter(text)
    if not name:
        errors.append(f"{path}: missing frontmatter name")
    elif name != path.parent.name:
        errors.append(
            f"{path}: frontmatter name {name!r} != folder name {path.parent.name!r}"
        )
    if not desc:
        errors.append(f"{path}: missing or empty frontmatter description")
    code_spans = " ".join(re.findall(r"```.*?```|`[^`\n]+`", text, re.S))
    for match in re.finditer(
        r"(?<![\w/.~-])hub ([a-z][a-z0-9-]*)(?: ([a-z][a-z0-9-]*))?", code_spans
    ):
        verb, subverb = match.group(1), match.group(2)
        if verb not in verbs:
            errors.append(f"{path}: unknown hub verb 'hub {verb}'")
        elif verb in nested and subverb and subverb not in nested[verb]:
            errors.append(
                f"{path}: unknown 'hub {verb}' subcommand 'hub {verb} {subverb}'"
            )
    return errors


class SkillsParityTest(unittest.TestCase):
    verbs: set[str] = set()
    nested: dict[str, set[str]] = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.verbs, cls.nested = load_hub_verbs()

    def test_every_plugin_skill_has_valid_frontmatter_and_real_hub_verbs(self) -> None:
        files = sorted(SKILLS_DIR.glob("*/SKILL.md"))
        self.assertTrue(files, "Expected at least one plugin/skills/*/SKILL.md")
        for skill_file in files:
            with self.subTest(skill=skill_file.parent.name):
                self.assertEqual(
                    check_skill_file(skill_file, self.verbs, self.nested), []
                )

    def test_bad_fixture_skill_fails_parity_checks(self) -> None:
        self.assertTrue(BAD_FIXTURE.is_file())
        errors = check_skill_file(BAD_FIXTURE, self.verbs, self.nested)
        joined = "\n".join(errors)
        self.assertIn("frontmatter name 'wrong-name' != folder name 'bad_skill'", joined)
        self.assertIn("missing or empty frontmatter description", joined)
        self.assertIn("unknown hub verb 'hub init'", joined)
        self.assertIn("unknown 'hub spec' subcommand 'hub spec review'", joined)

    def test_missing_frontmatter_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "sample-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("# No frontmatter\n", encoding="utf-8")
            errors = check_skill_file(skill_md, self.verbs, self.nested)
            self.assertEqual(len(errors), 2)


if __name__ == "__main__":
    unittest.main()
