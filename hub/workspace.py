"""Fresh, disposable worktrees for hub tasks."""

import copy
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import board as hb
from gh_sync import change_branch


def git(cwd, *args, check=True):
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
    try:
        result = subprocess.run(["git", "-C", str(cwd), *args], env=env, capture_output=True,
                                text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"git {' '.join(args)}: {exc}") from exc
    if check and result.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip() or result.returncode}")
    return result


def _git_path(worktree, name):
    path = Path(git(worktree, "rev-parse", "--git-path", name).stdout.strip())
    return path if path.is_absolute() else worktree / path


def _same_repo(a, b):
    def common(path):
        value = Path(git(path, "rev-parse", "--git-common-dir").stdout.strip())
        return (value if value.is_absolute() else path / value).resolve()
    return common(a) == common(b)


def code_dir(home):
    """Where the project clones live: $HUB_CODE_DIR, else <home>/code."""
    return Path(os.environ.get("HUB_CODE_DIR") or Path(home) / "code")


def create(task, home=Path.home()):
    project, tid = task.get("project"), task.get("id")
    if project == "hub":
        print("workspace: hub uses its live checkout")
        return None
    if not isinstance(project, str) or not hb.PROJECT_RE.fullmatch(project) or not re.fullmatch(r"T-\d+", tid or ""):
        print("workspace: invalid project or task id")
        return None
    home = Path(home)
    clone = code_dir(home) / project
    if not (clone / ".git").exists():
        print(f"workspace: no clone at {clone}; claim continues without one")
        return None
    path = home / "work" / project / tid
    fetched = f"fetched {time.strftime('%H:%MZ', time.gmtime())}"
    for attempt in range(3):
        try:
            git(clone, "fetch", "-q", "--prune", "origin")
            break
        except RuntimeError as exc:
            if attempt == 2:
                # Prometheus's sandbox has no DNS: build from the local refs and say how old they are.
                print(f"workspace: fetch failed after 3 tries: {exc}")
                fetch_head = _git_path(clone, "FETCH_HEAD")
                fetched = ("UNFETCHED, last fetch "
                           + (f"{(time.time() - fetch_head.stat().st_mtime) / 60:.0f} min ago" if fetch_head.exists()
                              else "never"))
            else:
                time.sleep(1)
    try:
        if path.exists():
            if not _same_repo(clone, path):
                print(f"workspace: {path} is not a worktree of {clone}")
                return None
            print(f"workspace: reusing {path}\n{git(path, 'status', '-sb').stdout.strip()}")
            return path
        branch = change_branch(task)
        base = f"origin/{branch}" if branch else "origin/integration"
        if not branch and git(clone, "show-ref", "--verify", "--quiet", "refs/remotes/origin/integration",
                              check=False).returncode:
            base = "origin/HEAD"
        sha = git(clone, "rev-parse", "--verify", base).stdout.strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        git(clone, "worktree", "add", "--detach", str(path), sha)
        _git_path(path, "hub-base").write_text(f"{sha} {base}\n")
        if (clone / ".env").is_file():
            shutil.copy2(clone / ".env", path / ".env")
        try:  # fast checks in a fresh worktree; a failed install must not fail the claim
            subprocess.run([str(Path(__file__).parent / "bin" / "ws-node-modules"), str(path)], timeout=900)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"workspace: node_modules not prepared: {exc}")
        print(f"workspace: {path} (detached at {base} {sha[:7]}, {fetched})")
        print(f"create your branch there: git switch -c <issue>-<slug> | task/{tid}")
        return path
    except (RuntimeError, OSError) as exc:
        print(f"workspace: could not prepare {path}: {exc}")
        return None


def _safe(path, task):
    """HEAD's commits survive removing the worktree: merged, unchanged from base, or on origin."""
    # hub live squash-merged it, so HEAD never reaches origin; live.reverts reopens a task and keeps merge_sha
    if task.get("merge_sha") and task.get("status") == "done":
        return True
    head = git(path, "rev-parse", "HEAD").stdout.strip()
    base_file = _git_path(path, "hub-base")
    sha, base = ([*base_file.read_text().split(), "", ""] if base_file.exists() else ["", ""])[:2]
    if head == sha or git(path, "for-each-ref", "--contains", head, "refs/remotes/origin").stdout.strip():
        return True
    for upstream in {base, "origin/integration", "origin/main"} - {""}:
        r = git(path, "cherry", upstream, head, check=False)
        if r.returncode == 0 and "+" not in r.stdout:
            return True
    return False


def _still_removable(task):
    """The board now, not the snapshot gc started from: a re-claim may have reused the worktree."""
    with hb.board() as (data, _):
        now = next((t for t in data["tasks"] if t.get("id") == task["id"]), None)
        return bool(now) and now.get("status") in ("done", "open") and now.get("workspace") == task["workspace"]


def gc(tasks, dry_run):
    root = (Path.home() / "work").resolve()
    kept = []
    for task in tasks:
        if task.get("status") not in ("done", "open") or not task.get("workspace"):
            continue
        project, tid = task.get("project"), task.get("id")
        if project == "hub" or not isinstance(project, str) or not hb.PROJECT_RE.fullmatch(project) \
                or not re.fullmatch(r"T-\d+", tid or ""):
            continue
        path = Path(task["workspace"]).resolve()
        if path != root / project / tid or not path.exists():
            continue
        clone = code_dir(Path.home()) / project
        try:
            if not _same_repo(clone, path):
                raise RuntimeError("not a worktree of its project clone")
            if git(path, "status", "--porcelain").stdout.strip():
                raise RuntimeError("dirty")
            if not _safe(path, task):
                raise RuntimeError("unmerged local commits")
            if dry_run:
                print(f"workspace: would remove {path}")
            else:
                if not _still_removable(task):
                    raise RuntimeError("re-claimed since gc read the board")
                git(clone, "worktree", "remove", str(path))
                print(f"workspace: removed {path}")
        except (RuntimeError, OSError) as exc:
            kept.append(str(path))
            old = task.get("status") == "done" and path.stat().st_mtime < time.time() - 14 * 86400
            print(f"workspace: kept {path} ({exc})" + ("; done over 14 days ago" if old else ""))
    return kept


def cmd_path(args):
    with hb.board() as (data, _):
        task = hb.resolve(data, args.id, hb.which_project(getattr(args, "project", None)))
    print(task.get("workspace") or "no workspace")


def cmd_gc(args):
    # Copy under the lock, run git without it: gc takes minutes on a big board and writes nothing back.
    with hb.board() as (data, _):
        tasks = copy.deepcopy(data["tasks"])
    gc(tasks, args.dry_run)


def register(sub):
    parser = sub.add_parser("ws", help="per-task workspaces")
    commands = parser.add_subparsers(dest="ws_cmd", required=True)
    path = commands.add_parser("path", help="show a task's workspace")
    path.add_argument("id")
    path.add_argument("--project")
    path.set_defaults(fn=cmd_path)
    clean = commands.add_parser("gc", help="remove safe finished workspaces")
    clean.add_argument("--dry-run", action="store_true")
    clean.set_defaults(fn=cmd_gc)
