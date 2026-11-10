#!/usr/bin/env bash
# Hub VM disk janitor (T-1100): keep / under 75% automatically
set -euo pipefail

exec /usr/bin/python3 - "$@" << 'EOF'
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

DAY = 86400

TARGET_PCT = int(os.environ.get("TARGET_PCT", "75"))
ALERT_PCT = int(os.environ.get("ALERT_PCT", "85"))
HUB_DIR = Path(os.environ.get("HUB_DIR", str(Path.home() / "hub"))).resolve()
WORK_DIR = Path(os.environ.get("WORK_DIR", str(Path.home() / "work"))).resolve()
TMP_DIR = Path(os.environ.get("TMP_DIR", "/tmp")).resolve()
CLAUDE_TMP_DIR = Path(os.environ.get("CLAUDE_TMP_DIR", "/tmp/claude-1001")).resolve()
LOG_DIR = Path(os.environ.get("LOG_DIR", str(HUB_DIR / "logs" / "janitor"))).resolve()

PROTECTED_EXACT_OR_ANCESTORS = [
    Path.home() / "private",
    HUB_DIR / "projects",
    Path.home() / "code",
    Path.home() / "penpot",
]


def is_protected(path: Path) -> bool:
    """Rule 4: Never touch ~/private, ~/hub/projects, ~/code/*, ~/penpot, or incoming < 30 days old."""
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path
    for p in PROTECTED_EXACT_OR_ANCESTORS:
        try:
            target = p.resolve()
            if resolved == target or resolved.is_relative_to(target):
                return True
        except Exception:
            pass
    incoming = (Path.home() / "incoming").resolve()
    try:
        if resolved == incoming or resolved.is_relative_to(incoming):
            cutoff_30d = time.time() - 30 * DAY
            if resolved.stat().st_mtime >= cutoff_30d:
                return True
    except Exception:
        pass
    return False


def get_disk_pct() -> int:
    """Return root filesystem use percentage."""
    if "MOCK_DISK_PCT" in os.environ:
        try:
            return int(os.environ["MOCK_DISK_PCT"])
        except ValueError:
            pass
    try:
        out = subprocess.check_output(["df", "--output=pcent", "/"], text=True)
        val = "".join(c for c in out.splitlines()[-1] if c.isdigit())
        return int(val) if val else 0
    except Exception:
        return 0


def make_logger(log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    log_file = log_dir / f"{today}.log"

    def log(msg: str):
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"[{now_str}] {msg}"
        print(line, flush=True)
        try:
            with open(log_file, "a") as f:
                f.write(line + "\n")
        except Exception:
            pass

    return log


def get_open_paths() -> set[str]:
    """Collect open file paths and process cwds across all running processes via /proc/*/fd and /proc/*/cwd."""
    open_paths = set()
    proc = Path("/proc")
    if proc.is_dir():
        try:
            for pid_dir in proc.iterdir():
                if not pid_dir.name.isdigit():
                    continue
                # cwd
                try:
                    cwd_target = os.readlink(pid_dir / "cwd")
                    open_paths.add(cwd_target)
                except OSError:
                    pass
                # fd
                fd_dir = pid_dir / "fd"
                try:
                    for fd in fd_dir.iterdir():
                        try:
                            target = os.readlink(fd)
                            open_paths.add(target)
                        except OSError:
                            pass
                except OSError:
                    pass
        except OSError:
            pass
    return open_paths


def is_held_open(path: Path, open_paths: set[str]) -> bool:
    """Check if file or directory has an active file handle or is a cwd of any running process."""
    try:
        resolved_str = str(path.resolve())
    except Exception:
        resolved_str = str(path)

    if resolved_str in open_paths:
        return True

    if path.is_dir():
        prefix = resolved_str.rstrip("/") + "/"
        for op in open_paths:
            if op == resolved_str or op.startswith(prefix):
                return True

    # Candidate-specific fallback to fuser/lsof
    if shutil.which("fuser"):
        try:
            res = subprocess.run(["fuser", str(path)], capture_output=True, timeout=5)
            if res.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, PermissionError):
            return True
        except Exception:
            pass
    elif shutil.which("lsof"):
        try:
            res = subprocess.run(["lsof", str(path)], capture_output=True, timeout=5)
            if res.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, PermissionError):
            return True
        except Exception:
            pass
    return False


def newest_mtime(path: Path) -> float:
    """Get newest mtime for path and its contents."""
    try:
        newest = path.lstat().st_mtime
    except Exception:
        return time.time()
    if path.is_dir() and not path.is_symlink():
        try:
            for root, dirs, files in os.walk(path, followlinks=False):
                for name in dirs + files:
                    try:
                        newest = max(newest, (Path(root) / name).lstat().st_mtime)
                    except Exception:
                        pass
        except Exception:
            pass
    return newest


def run_rule1(dry_run: bool, log):
    """Rule 1: uv cache prune and docker image prune -f (dangling images only)."""
    if "SKIP_RULE1" in os.environ:
        log("Rule 1 skipped via SKIP_RULE1.")
        return
    log("Rule 1: Pruning uv cache and dangling docker images...")
    if shutil.which("uv"):
        if dry_run:
            log("[dry-run] would run uv cache prune")
        else:
            try:
                res = subprocess.run(["uv", "cache", "prune"], capture_output=True, text=True, timeout=60)
                msg = res.stdout.strip() or res.stderr.strip() or "done"
                log(f"uv cache prune: {msg}")
            except Exception as e:
                log(f"uv cache prune error: {e}")

    if shutil.which("docker"):
        if dry_run:
            log("[dry-run] would run docker image prune -f (dangling images only)")
        else:
            try:
                res = subprocess.run(["docker", "image", "prune", "-f"], capture_output=True, text=True, timeout=60)
                msg = res.stdout.strip() or "done"
                log(f"docker image prune: {msg}")
            except Exception as e:
                log(f"docker image prune error: {e}")


def run_rule2(dry_run: bool, log, target_pct: int, force: bool) -> bool:
    """Rule 2: /tmp/* and /tmp/claude-1001/* entries owned by hub, untouched 3+ days (1+ day for playwright/chromium)."""
    log(f"Rule 2: Cleaning old tmp entries in {TMP_DIR} and {CLAUDE_TMP_DIR}...")
    now = time.time()
    cutoff_3d = now - 3 * DAY
    cutoff_1d = now - DAY
    cutoff_24h = now - DAY
    user_uid = os.getuid()
    open_paths = get_open_paths()

    candidates = []
    for base in (TMP_DIR, CLAUDE_TMP_DIR):
        if not base.is_dir():
            continue
        try:
            for entry in base.iterdir():
                # For claude-1001 project dirs like -home-you-code-refinery, inspect individual session dirs
                if base == CLAUDE_TMP_DIR and entry.is_dir() and entry.name.startswith("-home-"):
                    try:
                        for sub_entry in entry.iterdir():
                            candidates.append(sub_entry)
                    except Exception:
                        pass
                else:
                    candidates.append(entry)
        except Exception:
            pass

    for path in candidates:
        try:
            st = path.lstat()
            if st.st_uid != user_uid:
                continue

            if is_protected(path):
                continue

            # Playwright / chromium profile dirs: older than 1 day; other tmp entries: 3+ days
            is_pw_chrom = (
                "playwright" in path.name.lower() or
                "chromium" in path.name.lower()
            )
            cutoff = cutoff_1d if is_pw_chrom else cutoff_3d
            mtime = newest_mtime(path)
            if mtime >= cutoff:
                continue

            # Skip scratchpads modified in the last 24h
            if "scratchpad" in path.name.lower() and mtime >= cutoff_24h:
                continue

            if is_held_open(path, open_paths):
                continue

            if dry_run:
                log(f"[dry-run] would remove tmp entry: {path}")
            else:
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
                log(f"Removed tmp entry: {path}")

            if not force and get_disk_pct() < target_pct:
                log(f"Disk is now below {target_pct}%; stopping.")
                return True
        except (FileNotFoundError, OSError):
            continue
        except Exception as e:
            log(f"Error checking tmp entry {path}: {e}")
    return False


def get_claimed_and_open_workspaces(hub_dir: Path) -> set[str] | None:
    """Retrieve claimed and open workspaces from board.json. Returns None if board is unreadable or schema-invalid."""
    claimed = set()
    board_path = hub_dir / "board.json"
    if not board_path.is_file():
        return None
    try:
        with open(board_path) as f:
            data = json.load(f)
        if not isinstance(data, dict) or "tasks" not in data or not isinstance(data.get("tasks"), list):
            return None
        for t in data["tasks"]:
            if not isinstance(t, dict):
                continue
            status = t.get("status")
            if status not in ("done", "closed", "released", "superseded", "cancelled"):
                ws = t.get("workspace")
                if ws:
                    try:
                        claimed.add(str(Path(ws).resolve()))
                    except Exception:
                        claimed.add(str(ws))
                tid = t.get("id")
                if tid:
                    claimed.add(tid)
        return claimed
    except Exception:
        return None


def find_worktrees(work_dir: Path) -> list[Path]:
    """Find all git worktrees under work_dir (both direct work_dir/<wt> and nested work_dir/<repo>/<wt>)."""
    worktrees = []
    if not work_dir.is_dir():
        return worktrees
    try:
        for p in work_dir.iterdir():
            if not p.is_dir() or is_protected(p):
                continue
            if (p / ".git").is_file():
                worktrees.append(p)
            else:
                try:
                    for sub in p.iterdir():
                        if sub.is_dir() and not is_protected(sub) and (sub / ".git").is_file():
                            worktrees.append(sub)
                except Exception:
                    pass
    except Exception:
        pass
    return worktrees


def run_rule3(dry_run: bool, log, target_pct: int, force: bool) -> bool:
    """Rule 3: Worktrees clean, unclaimed, untouched (2+ days if merged to origin/main, 7+ days if pushed to remote)."""
    log(f"Rule 3: Cleaning old unneeded worktrees in {WORK_DIR}...")
    now = time.time()
    cutoff_7d = now - 7 * DAY
    cutoff_2d = now - 2 * DAY
    claimed = get_claimed_and_open_workspaces(HUB_DIR)
    if claimed is None:
        log("WARNING: board.json is missing or unreadable; skipping worktree removal to protect claimed tasks.")
        return False

    open_paths = get_open_paths()

    if not WORK_DIR.is_dir():
        return False

    for wt in find_worktrees(WORK_DIR):
        if is_protected(wt):
            continue

        # Must not be the workspace of any claimed or open Hub task
        if str(wt.resolve()) in claimed or wt.name in claimed:
            continue

        # Must not have any active open files or process handles
        if is_held_open(wt, open_paths):
            continue

        try:
            # Clean: no uncommitted or untracked files
            res = subprocess.run(
                ["git", "-C", str(wt), "status", "--porcelain", "--untracked-files=all"],
                capture_output=True, text=True, timeout=30
            )
            if res.returncode != 0 or res.stdout.strip():
                continue

            head_sha = subprocess.check_output(
                ["git", "-C", str(wt), "rev-parse", "HEAD"],
                text=True, timeout=10
            ).strip()
            head_branch = subprocess.check_output(
                ["git", "-C", str(wt), "rev-parse", "--abbrev-ref", "HEAD"],
                text=True, timeout=10
            ).strip()

            # Check if branch is fully merged into origin/main
            mb = subprocess.run(
                ["git", "-C", str(wt), "merge-base", "--is-ancestor", "HEAD", "origin/main"],
                capture_output=True, timeout=15
            )
            is_merged = (mb.returncode == 0)

            if is_merged:
                cutoff = cutoff_2d
            else:
                # HEAD reachable from a remote branch
                remotes = subprocess.check_output(
                    ["git", "-C", str(wt), "branch", "-r", "--contains", head_sha],
                    text=True, timeout=15
                ).strip()
                if not remotes:
                    continue
                cutoff = cutoff_7d

            # Check mtime against cutoff
            if newest_mtime(wt) >= cutoff:
                continue

            # Find main repo
            common_dir = subprocess.check_output(
                ["git", "-C", str(wt), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                text=True, timeout=10
            ).strip()
            main_repo = Path(common_dir).parent

            if dry_run:
                log(f"[dry-run] would remove worktree: {wt} (branch: {head_branch}, sha: {head_sha}, merged={is_merged})")
            else:
                subprocess.run(
                    ["git", "-C", str(main_repo), "worktree", "remove", str(wt)],
                    check=True, capture_output=True, text=True, timeout=30
                )
                log(f"Removed worktree: {wt} (branch: {head_branch}, sha: {head_sha}, merged={is_merged})")

            if not force and get_disk_pct() < target_pct:
                log(f"Disk is now below {target_pct}%; stopping.")
                return True
        except Exception as e:
            log(f"Error checking worktree {wt}: {e}")
    return False


def run_rule4(dry_run: bool, log, target_pct: int, force: bool) -> bool:
    """Rule 4: Remove duplicate .venv dirs in worktrees older than 2 days (recreated by uv sync)."""
    log(f"Rule 4: Looking for duplicate .venv dirs in worktrees older than 2 days in {WORK_DIR}...")
    now = time.time()
    cutoff_2d = now - 2 * DAY
    claimed = get_claimed_and_open_workspaces(HUB_DIR)
    if claimed is None:
        log("WARNING: board.json is missing or unreadable; skipping .venv removal to protect claimed tasks.")
        return False
    open_paths = get_open_paths()

    if not WORK_DIR.is_dir():
        return False

    candidates = find_worktrees(WORK_DIR)
    try:
        for p in WORK_DIR.iterdir():
            if p.is_dir() and p not in candidates and not is_protected(p):
                candidates.append(p)
    except Exception:
        pass

    for wt in candidates:
        venv_path = wt / ".venv"
        if not venv_path.is_dir() or venv_path.is_symlink():
            continue
        if is_protected(venv_path) or is_protected(wt):
            continue
        if str(wt.resolve()) in claimed or wt.name in claimed:
            continue
        try:
            mtime = newest_mtime(wt)
            if mtime >= cutoff_2d:
                continue
            if is_held_open(venv_path, open_paths):
                continue

            if dry_run:
                log(f"[dry-run] would remove duplicate .venv: {venv_path}")
            else:
                shutil.rmtree(venv_path, ignore_errors=True)
                log(f"Removed duplicate .venv: {venv_path}")

            if not force and get_disk_pct() < target_pct:
                log(f"Disk is now below {target_pct}%; stopping.")
                return True
        except Exception as e:
            log(f"Error checking .venv in {wt}: {e}")
    return False


def check_alert(current_pct: int, alert_pct: int, dry_run: bool, log):
    """If / is still over alert threshold after all rules, log it with the biggest dirs. Not the lead's WhatsApp:
    the lead asked for no disk-space messages there (2026-11-09)."""
    if current_pct > alert_pct:
        log(f"WARNING: Root disk is at {current_pct}% (>{alert_pct}%) after all janitor rules.")
        top_dirs = "Top dirs unavailable"
        try:
            top_dirs = subprocess.check_output(
                "du -hx --max-depth=2 /home /tmp 2>/dev/null | sort -rh | head -n 10",
                shell=True, text=True, timeout=30
            ).strip()
        except Exception as e:
            top_dirs = f"Could not determine top dirs: {e}"
        log(f"Top 10 dirs:\n{top_dirs}")


def main():
    parser = argparse.ArgumentParser(prog="janitor.sh", description="Hub VM disk janitor: keep / under 75%% automatically")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be freed without deleting anything")
    parser.add_argument("--force", action="store_true", help="Run cleanup rules even if disk is already under 75%%")
    args = parser.parse_args()

    log = make_logger(LOG_DIR)
    current_pct = get_disk_pct()
    log(f"Starting Hub disk janitor (dry_run={args.dry_run}, force={args.force}). Root disk at {current_pct}%.")

    if current_pct < TARGET_PCT and not args.force:
        log(f"Root disk is at {current_pct}%, which is under target {TARGET_PCT}%. Nothing to do.")
        return 0

    # Rule 1: uv cache and docker images
    run_rule1(args.dry_run, log)
    current_pct = get_disk_pct()
    if current_pct < TARGET_PCT and not args.force:
        log(f"Root disk is now at {current_pct}% (<{TARGET_PCT}%); stopping.")
        return 0

    # Rule 2: old tmp files
    stopped = run_rule2(args.dry_run, log, TARGET_PCT, args.force)
    if stopped:
        return 0

    current_pct = get_disk_pct()
    if current_pct < TARGET_PCT and not args.force:
        log(f"Root disk is now at {current_pct}% (<{TARGET_PCT}%); stopping.")
        return 0

    # Rule 3: old clean worktrees
    stopped = run_rule3(args.dry_run, log, TARGET_PCT, args.force)
    if stopped:
        return 0

    current_pct = get_disk_pct()
    if current_pct < TARGET_PCT and not args.force:
        log(f"Root disk is now at {current_pct}% (<{TARGET_PCT}%); stopping.")
        return 0

    # Rule 4: duplicate .venv dirs in worktrees older than 2 days
    stopped = run_rule4(args.dry_run, log, TARGET_PCT, args.force)
    if stopped:
        return 0

    current_pct = get_disk_pct()
    log(f"Completed janitor rules. Root disk is now at {current_pct}%.")

    # Alert if still > 85%
    check_alert(current_pct, ALERT_PCT, args.dry_run, log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
EOF
