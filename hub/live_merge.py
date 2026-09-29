"""One safe merge and smoke cycle for hub live."""

import os

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


PROJECT_FILES = ("pyproject.toml", "package.json", "go.mod", "Cargo.toml", "Makefile")


def is_lgtm(body, sha):
    """The reviewer's approval on a lead-account PR: the first line is exactly `LGTM <sha>`;
    notes may follow on later lines."""
    lines = (body or "").strip().splitlines()
    return bool(lines) and lines[0].strip() == f"LGTM {sha}"


def merge_tick(repo: str, clone: Path, smoke: str, lead_login: str, state: dict,
               run, send) -> None:
    """Merge at most one eligible PR, then smoke and promote or revert integration."""
    clone = Path(clone)

    def call(args, cwd=None, timeout=60):
        try:
            return run(args, cwd=cwd, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"live merge: {args[0]} failed: {exc}")
            return subprocess.CompletedProcess(args, 1, "", str(exc))

    def data(args):
        result = call(args)
        if result.returncode:
            print(f"live merge: {' '.join(args[:3])} failed: {result.stderr}")
            return None
        try:
            return json.loads(result.stdout)
        except (TypeError, ValueError):
            print(f"live merge: invalid JSON from {' '.join(args[:3])}")
            return None

    def fail(message):
        print(f"live merge: {message}")
        send(os.environ.get("HUB_LEAD") or "Zeus", message)

    def git(*args):
        return call(["git", "-C", str(clone), *args])

    def smoke_head(merged_pr=None, issue=None):
        fetched = git("fetch", "-q", "origin", "integration")
        if fetched.returncode:
            fail("Smoke setup failed: cannot fetch integration")
            return
        head = git("rev-parse", "origin/integration")
        if head.returncode or not head.stdout.strip():
            fail("Smoke setup failed: cannot read integration head")
            return
        sha = head.stdout.strip()
        if merged_pr is None and sha == state.get("smoked"):
            return
        with tempfile.TemporaryDirectory(prefix="hub-live-smoke-") as directory:
            path = Path(directory)
            added = git("worktree", "add", "-q", "--detach", str(path), "origin/integration")
            if added.returncode:
                fail("Smoke setup failed: cannot create worktree")
                return
            try:
                try:
                    if (clone / ".env").is_file():
                        shutil.copy2(clone / ".env", path / ".env")
                except OSError as exc:
                    fail(f"Smoke setup failed: cannot copy .env: {exc}")
                    return
                tested = call(["git", "-C", str(path), "rev-parse", "HEAD"])
                if tested.returncode or tested.stdout.strip() != sha:
                    fail("Smoke setup failed: integration head changed during checkout")
                    return
                if not any((path / f).exists() for f in PROJECT_FILES):
                    # Nothing to smoke before the first code lands (dry run #4: the design PR and
                    # the owners table were "red" on an empty repo). Green, so main still moves.
                    result = subprocess.CompletedProcess([], 0, "no project yet: nothing to smoke", "")
                else:
                    result = call(["timeout", "300", "sh", "-c", smoke], cwd=path, timeout=310)
            finally:
                git("worktree", "remove", "--force", str(path))

        previous_smoked = state.get("smoked")
        state["smoked"] = sha
        if result.returncode == 0:
            pushed = git("push", "origin", f"{sha}:refs/heads/main")
            if pushed.returncode:
                if previous_smoked is None:
                    state.pop("smoked", None)
                else:
                    state["smoked"] = previous_smoked
                fail(f"Smoke passed at {sha}, but main push failed")
            return
        if merged_pr is None:
            fail(f"Smoke failed on integration at {sha}")
            return
        merged = data(["gh", "pr", "view", str(merged_pr), "-R", repo, "--json", "mergeCommit"])
        commit = (merged or {}).get("mergeCommit") or {}
        if not commit.get("oid"):
            fail(f"Smoke failed after #{merged_pr}; cannot find squash commit to revert")
            return
        with tempfile.TemporaryDirectory(prefix="hub-live-revert-") as directory:
            path = Path(directory)
            added = git("worktree", "add", "-q", "--detach", str(path), "origin/integration")
            if added.returncode:
                fail(f"Smoke failed after #{merged_pr}; revert worktree setup failed")
                return
            try:
                reverted = call(["git", "-C", str(path), "revert", "--no-edit", commit["oid"]])
                if reverted.returncode:
                    fail(f"Smoke failed after #{merged_pr}; revert failed")
                    return
                pushed = call(["git", "-C", str(path), "push", "origin", "HEAD:refs/heads/integration"])
                if pushed.returncode:
                    fail(f"Smoke failed after #{merged_pr}; revert push failed")
                    return
            finally:
                git("worktree", "remove", "--force", str(path))
        lines = (str(result.stdout or "") + "\n" + str(result.stderr or "")).splitlines()[-30:]
        body = (f"Reverted: the smoke failed after #{merged_pr} merged.\n"
                + "\n".join(lines)
                + "\nFix it on the same branch and open a new PR.")
        reopened = call(["gh", "issue", "reopen", str(issue), "-R", repo, "--comment", body])
        if reopened.returncode:
            fail(f"Smoke failed after #{merged_pr}; issue #{issue} reopen failed")
        else:
            fail(f"Smoke failed after #{merged_pr}; reverted integration and reopened issue #{issue}")

    prs = data(["gh", "pr", "list", "-R", repo, "--state", "open", "--limit", "100",
                "--json", "number,body,author,headRefOid,baseRefName,isDraft,mergeable,comments"])
    if prs is None:
        fail("Merge queue failed: cannot list PRs")
        return
    chosen = None
    issue = None
    for pr in sorted(prs, key=lambda item: item["number"]):
        if pr.get("isDraft") or pr.get("mergeable") == "CONFLICTING":
            continue
        body = pr.get("body") or ""
        match = re.search(r"\b(?:closes|fixes|resolves)\s+#(\d+)", body, re.I)
        if not match:
            continue
        issue_number = int(match.group(1))
        linked_issue = data(["gh", "issue", "view", str(issue_number), "-R", repo,
                             "--json", "state,body"])
        if linked_issue is None:
            continue
        dependencies = [number for line in re.findall(r"(?im)^Depends on:[^\n]*",
                                                    linked_issue.get("body") or "")
                        for number in re.findall(r"#(\d+)", line)]
        if any((item := data(["gh", "issue", "view", number, "-R", repo, "--json", "state"])) is None
               or item.get("state") != "CLOSED" for number in dependencies):
            continue
        sha = pr.get("headRefOid")
        if not sha:
            continue
        author = (pr.get("author") or {}).get("login")
        if author == lead_login:
            approved = any(is_lgtm(comment.get("body"), sha)
                           and (comment.get("author") or {}).get("login") == lead_login
                           for comment in pr.get("comments") or [])
        else:
            owner, name = repo.split("/", 1)
            reviews = data(["gh", "api", f"repos/{owner}/{name}/pulls/{pr['number']}/reviews"])
            approved = reviews is not None and any(
                review.get("state") == "APPROVED" and review.get("commit_id") == sha
                for review in reviews)
        if not approved:
            continue
        if pr.get("baseRefName") == "main":
            edited = call(["gh", "pr", "edit", str(pr["number"]), "-R", repo,
                           "--base", "integration"])
            if edited.returncode:
                print(f"live merge: cannot retarget #{pr['number']}")
                continue
        checks = data(["gh", "pr", "checks", str(pr["number"]), "-R", repo,
                       "--json", "name,bucket,state"])
        if checks is None or not any(check.get("name") == "freeze-gate" and
                                     check.get("bucket") == "pass" for check in checks):
            continue
        chosen, issue = pr, issue_number
        break

    if chosen is None:
        smoke_head()
        return
    number, sha = chosen["number"], chosen["headRefOid"]
    command = ["gh", "pr", "merge", str(number), "-R", repo, "--squash", "--delete-branch",
               "--match-head-commit", sha]
    if (chosen.get("author") or {}).get("login") == lead_login:
        command.append("--admin")
    merged = call(command)
    if merged.returncode:
        print(f"live merge: cannot merge #{number}: {merged.stderr}")
        return
    smoke_head(number, issue)
    open_prs = data(["gh", "pr", "list", "-R", repo, "--state", "open", "--limit", "100",
                     "--json", "number,mergeable"])
    noted = state.setdefault("conflict_noted", [])
    if open_prs is not None:
        for item in open_prs:
            number = item["number"]
            if item.get("mergeable") == "CONFLICTING" and number not in noted:
                commented = call(["gh", "pr", "comment", str(number), "-R", repo,
                                  "--body", "integration moved: run `git pull --no-rebase origin integration`, "
                                           "fix the conflicts in your area, push."])
                if commented.returncode == 0:
                    noted.append(number)
                else:
                    print(f"live merge: cannot comment on conflicting PR #{number}")
