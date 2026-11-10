"""Nightly cleanup of recoverable scratch checkouts and old test directories."""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

DAY = 86400
GIT_ENV = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], env=GIT_ENV,
                          capture_output=True, check=True).stdout


def raise_walk_error(error):
    raise error


def newest_mtime(path):
    newest = path.lstat().st_mtime
    for root, dirs, files in os.walk(path, followlinks=False, onerror=raise_walk_error):
        for name in dirs + files:
            newest = max(newest, (Path(root) / name).lstat().st_mtime)
    return newest


def size(path):
    total = path.lstat().st_blocks * 512
    for root, dirs, files in os.walk(path, followlinks=False, onerror=raise_walk_error):
        for name in dirs + files:
            total += (Path(root) / name).lstat().st_blocks * 512
    return total


def checkouts(tmp):
    found = []
    for root, dirs, files in os.walk(tmp, followlinks=False):
        if ".git" in dirs or ".git" in files:
            found.append(Path(root))
            if ".git" in dirs:
                dirs.remove(".git")
        dirs[:] = [name for name in dirs if name not in ("node_modules", ".venv")]
    return sorted(found, key=lambda path: len(path.parts), reverse=True)


def contains_checkout(path, removed=frozenset()):
    for root, dirs, files in os.walk(path, followlinks=False, onerror=raise_walk_error):
        if Path(root) in removed:
            dirs[:] = []
            continue
        if removed:
            dirs[:] = [name for name in dirs if Path(root, name) not in removed]
        if ".git" in dirs or ".git" in files:
            return True
    return False


def contains_nested_checkout(repo):
    for root, dirs, files in os.walk(repo, followlinks=False, onerror=raise_walk_error):
        if Path(root) == repo:
            dirs[:] = [name for name in dirs if name != ".git"]
        elif ".git" in dirs or ".git" in files:
            return True
    return False


def origin_has_commits(repo):
    try:
        origin = git(repo, "remote", "get-url", "origin").decode().strip()
    except subprocess.CalledProcessError as error:
        if error.returncode == 2:  # no origin remote: keep the checkout
            return False
        raise
    if not origin:
        return False
    if "://" in origin or origin.startswith("git@") or ":" in origin:
        if not git(repo, "for-each-ref", "--format=%(refname)", "refs/remotes/origin").strip():
            return False
        return not git(repo, "rev-list", "--all", "--reflog", "HEAD", "--not",
                       "--remotes=origin").strip()
    local = Path(origin)
    if not local.is_absolute():
        local = repo / local
    if not local.is_dir():
        return False
    origin_commits = set(git(local, "rev-list", "--all").splitlines())
    checkout_commits = set(git(repo, "rev-list", "--all", "--reflog", "HEAD").splitlines())
    return checkout_commits <= origin_commits


def save_wip(repo, hub):
    """Archive tracked edits and non-ignored untracked files before deleting a checkout."""
    # shortcut: ignored files are omitted, archive them if scratch repos store unique work there.
    patch = git(repo, "diff", "--binary", "HEAD")
    untracked = git(repo, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    if not patch and not any(untracked):
        raise ValueError("dirty checkout has no recoverable diff")
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    day = hub / "artifacts" / "wip-patches" / date
    day.mkdir(parents=True, exist_ok=True, mode=0o700)
    digest = hashlib.sha256(str(repo).encode()).hexdigest()[:12]
    target = Path(tempfile.mkdtemp(prefix=f"{repo.name}-{digest}-", dir=day))
    try:
        with (target / "changes.patch").open("wb") as output:
            output.write(patch)
            output.flush()
            os.fsync(output.fileno())
        (target / "source.txt").write_text(f"{repo}\n")
        if any(untracked):
            with tarfile.open(target / "untracked.tar.gz", "w:gz") as archive:
                for name in filter(None, untracked):
                    relative = Path(os.fsdecode(name))
                    archive.add(repo / relative, arcname=str(relative), recursive=False)
        for item in target.iterdir():
            item.chmod(0o600)
            with item.open("rb") as source:
                os.fsync(source.fileno())
        return target
    except Exception:
        shutil.rmtree(target)
        raise


def remove_checkout(repo):
    if (repo / ".git").is_dir():
        shutil.rmtree(repo)
    else:
        if git(repo, "rev-parse", "--show-superproject-working-tree").strip():
            raise ValueError("submodule checkout")
        git(repo, "worktree", "remove", "--force", str(repo))


def cache_prune(command):
    before = shutil.disk_usage("/").free
    subprocess.run(command, capture_output=True, check=True, timeout=180)
    return max(0, shutil.disk_usage("/").free - before)


def report_error(item, error):
    print(f"disk-gc skip {str(item)!r}: {type(error).__name__}: "
          f"{' '.join(str(error).splitlines())}", file=sys.stderr)


def collect(tmp, hub, dry_run=False):
    resolved = tmp.resolve()
    if not tmp.is_dir() or not resolved.is_relative_to("/tmp") or resolved.is_relative_to(Path.home().resolve()):
        report_error(tmp, ValueError("unsafe TMPDIR"))
        print("disk-gc git=0.0MB tmp=0.0MB uv=0.0MB docker=0.0MB errors=1")
        return 1
    now = time.time()
    cutoff = now - DAY
    old_tmp = []
    freed_git = freed_tmp = errors = 0
    planned_git = set()
    for path in tmp.iterdir():
        try:
            if (path.is_dir() and not path.is_symlink() and path.name.startswith("tmp")
                    and path.stat().st_uid == os.getuid() and path.stat().st_mtime < cutoff
                    and newest_mtime(path) < cutoff):
                old_tmp.append(path)
        except OSError as error:
            errors += 1
            report_error(path, error)
    for repo in checkouts(tmp):
        try:
            if (repo.is_symlink() or not repo.exists() or repo.stat().st_uid != os.getuid()
                    or repo.stat().st_mtime >= cutoff or newest_mtime(repo) >= cutoff):
                continue
            if "scratchpad" in repo.parts:
                scratchpad = next((parent for parent in repo.parents if parent.name == "scratchpad"), None)
                if scratchpad and newest_mtime(scratchpad.parent) >= cutoff:
                    continue
            if contains_nested_checkout(repo) or not origin_has_commits(repo):
                continue
            dirty = bool(git(repo, "status", "--porcelain", "--untracked-files=all").strip())
            if dirty:
                if newest_mtime(repo) >= now - 7 * DAY:
                    continue
                if dry_run:
                    print(f"disk-gc would archive {repo}", file=sys.stderr)
                else:
                    save_wip(repo, hub)
            amount = size(repo)
            if dry_run:
                planned_git.add(repo)
                print(f"disk-gc would remove {repo}", file=sys.stderr)
            else:
                remove_checkout(repo)
            freed_git += amount
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as error:
            errors += 1
            report_error(repo, error)
    for path in old_tmp:
        try:
            if path.exists() and path not in planned_git and not contains_checkout(path, planned_git):
                amount = size(path)
                if dry_run:
                    print(f"disk-gc would remove {path}", file=sys.stderr)
                else:
                    shutil.rmtree(path)
                freed_tmp += amount
        except OSError as error:
            errors += 1
            report_error(path, error)
    docker_ready = bool(shutil.which("docker") and shutil.which("sudo"))
    if docker_ready:
        try:
            docker_ready = subprocess.run(["sudo", "-n", "true"], capture_output=True,
                                          check=False, timeout=10).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            docker_ready = False
    freed_cache = []
    commands = (["uv", "cache", "prune"],
                ["sudo", "-n", "docker", "builder", "prune", "-f"] if docker_ready else None)
    for cache_name, command in zip(("uv cache", "docker builder cache"), commands):
        if command is None:
            freed_cache.append(0)
            continue
        try:
            if dry_run:
                print(f"disk-gc would prune {cache_name}", file=sys.stderr)
                freed_cache.append(0)
            else:
                freed_cache.append(cache_prune(command))
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            freed_cache.append(0)
            errors += 1
            report_error(" ".join(command), error)
    amounts = (freed_git, freed_tmp, *freed_cache)
    print("disk-gc " + ("dry-run " if dry_run else "") + " ".join(f"{name}={amount / 1048576:.1f}MB"
                                for name, amount in zip(("git", "tmp", "uv", "docker"), amounts))
          + f" errors={errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report removals without changing files")
    args = parser.parse_args()
    sys.exit(collect(Path(os.environ.get("TMPDIR", "/tmp")), Path.home() / "hub", args.dry_run))
