"""`snapshot.sh full` must carry everything a lost disk takes with it (T-543).

    uv run python3 -m unittest tests.test_snapshot

The T-539 rehearsal found artifacts/ in neither backup and the git history of projects/
nowhere off the disk. Runs against a scratch hub and a fake `gcloud` that maps gs:// to a
local directory, so nothing touches the live bucket.
"""

import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent

FAKE_GCLOUD = r"""#!/usr/bin/env bash
# gcloud storage, on a local directory: gs://X/... -> $FAKE_GCS/X/...
args=(); for a in "$@"; do args+=("${a/#gs:\/\//$FAKE_GCS/}"); done
set -- "${args[@]}"
[ "$1" = storage ] || exit 1; shift
case "$1" in
buckets) exit 0 ;;
cp) shift; [ "$1" = --quiet ] && shift
    dst="${@: -1}"; mkdir -p "$([[ $dst == */ ]] && echo "$dst" || dirname "$dst")"; cp "$@" ;;
ls) compgen -G "$2" ;;
rm) shift; [ "$1" = --quiet ] && shift; rm "$@" ;;
*) exit 1 ;;
esac
"""


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True, timeout=120).stdout


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hub-snapshot-test-"))
        self.hub = self.tmp / "hub"
        git(self.tmp, "init", "-q", "-b", "main", str(self.hub))
        for k, v in (("user.email", "t@t"), ("user.name", "t")):
            git(self.hub, "config", k, v)
        (self.hub / "projects").mkdir()
        (self.hub / "artifacts").mkdir()
        (self.hub / "projects" / "plan.md").write_text("v1\n")
        (self.hub / "artifacts" / "page.html").write_text("<p>published</p>\n")
        git(self.hub, "add", "-A")
        git(self.hub, "commit", "-qm", "plan v1")
        (self.hub / "projects" / "plan.md").write_text("v2\n")
        git(self.hub, "commit", "-qam", "plan v2")
        (self.hub / "artifacts" / "untracked.png").write_bytes(b"\x89PNG not committed")
        (self.hub / "board.json").write_text("{}\n")
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        (bin_ / "gcloud").write_text(FAKE_GCLOUD)
        (bin_ / "gcloud").chmod(0o755)
        self.gcs = self.tmp / "gcs"
        # Strip every variable that could point this at the live hub or a live session.
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("HUB_", "GIT_")) and k != "CLAUDE_CODE_SESSION_NAME"}
        self.env = {**env, "HUB_DIR": str(self.hub), "FAKE_GCS": str(self.gcs),
                    "PATH": f"{bin_}:{env['PATH']}", "SNAPSHOT_BUCKET": "gs://scratch/t543"}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_nightly_restores_artifacts_and_the_history_of_projects(self):
        r = subprocess.run([str(HUB / "snapshot.sh"), "full"], env=self.env,
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("uploaded gs://scratch/t543/nightly/", r.stdout, r.stdout + r.stderr)
        [tarball] = (self.gcs / "scratch" / "t543" / "nightly").glob("hub-*.tar.gz")

        restore = self.tmp / "restore"
        restore.mkdir()
        with tarfile.open(tarball) as t:
            t.extractall(restore, filter="data")
        self.assertEqual((restore / "artifacts" / "untracked.png").read_bytes(), b"\x89PNG not committed")
        self.assertEqual((restore / "board.json").read_text(), "{}\n")

        # The runbook's history restore: clone the bundle, then the files on top.
        clone = self.tmp / "hub-restored"
        git(self.tmp, "clone", "-q", "--branch", "main", str(restore / "hub.bundle"), str(clone))
        self.assertEqual(git(clone, "log", "--format=%s", "--", "projects/").split("\n")[:2],
                         ["plan v2", "plan v1"])
        self.assertEqual((clone / "artifacts" / "page.html").read_text(), "<p>published</p>\n")


if __name__ == "__main__":
    unittest.main()
