"""Every hub skill is findable and points at things that exist.

    uv run python tests/test_skills.py
"""

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
SKILLS = HUB / "plugin" / "skills"
if not SKILLS.is_dir():  # a checkout keeps skills in claude/skills, an install in plugin/skills
    SKILLS = HUB.parent / "claude" / "skills"


def frontmatter(text):
    """name and description from a SKILL.md header; description may be quoted or a `>` block."""
    head = text.split("---", 2)[1]
    name = re.search(r"(?m)^name:[ \t]*(\S+)", head)
    desc = re.search(r"(?ms)^description:[ \t]*(.*?)(?=^\S|\Z)", head)
    return name and name[1], desc and " ".join(desc[1].lstrip(">|").split()).strip('"')


class SkillLint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = {k: v for k, v in os.environ.items() if k not in ("HUB_DIR", "HUB_AGENT", "HUB_PROJECT")}
        out = subprocess.run([sys.executable, str(HUB / "board.py"), "--help"], env=env,
                             capture_output=True, text=True, timeout=30).stdout
        cls.subcommands = set(re.search(r"\{([a-z,-]+)\}", out)[1].split(","))

    def test_every_skill(self):
        files = sorted(SKILLS.glob("*/SKILL.md"))
        self.assertTrue(files)
        for f in files:
            with self.subTest(skill=f.parent.name):
                text = f.read_text()
                name, desc = frontmatter(text)
                self.assertEqual(name, f.parent.name)
                self.assertTrue(desc and len(desc) <= 1024, f"description is {len(desc or '')} chars")
                self.assertRegex(desc, r"\b(Use|Load)\b")
                self.assertIn("Not for", desc, "the description says when to use it but not when not to")
                for ref in re.findall(r"\bhub:([a-z][a-z-]*)", text):
                    self.assertTrue((SKILLS / ref).is_dir(), f"hub:{ref} is not a skill")
                # Only in code spans and blocks: prose says "the hub owns", "hub agents".
                code = " ".join(re.findall(r"```.*?```|`[^`\n]+`", text, re.S))
                for sub in re.findall(r"(?<![\w/.~-])hub ([a-z][a-z-]*)", code):
                    self.assertIn(sub, self.subcommands, f"`hub {sub}` is not a hub subcommand")


if __name__ == "__main__":
    unittest.main()
