"""One safe merge and smoke cycle for hub live."""

import fnmatch
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import gh_sync

LEAD_AGENT = os.environ.get("HUB_LEAD") or "Zeus"
REVIEWER = os.environ.get("HUB_REVIEWER") or "Hermes"

PROJECT_FILES = ("pyproject.toml", "package.json", "go.mod", "Cargo.toml", "Makefile")
# The reviewer skill's must-catch 1, minus its broad `password =` net: these block the fast lane.
SECRET = re.compile(r"sk-ant-|sk_live|AKIA[0-9A-Z]{16}|ghp_|github_pat_|AIza|xox[bp]-"
                    r"|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:@]+:[^/\s@]+@")
# A PR body proves its work with an `## Evidence` block or a `Verified:` line (R1 practice 6).
EVIDENCE = re.compile(r"(?m)^(## Evidence\b|Verified:)")
# Runs detached: $1 clone, $2 sha, $3 command, $4 exit file, $5 cap in seconds. A throwaway worktree of
# the sha, .env copied in, the command capped, then its exit code ("setup" if no worktree). hub live's
# deploy and the change-branch gate both run in it.
DETACHED_SH = """d=$(mktemp -d)
if git -C "$1" worktree add -q --detach "$d" "$2"; then
  cp "$1/.env" "$d/" 2>/dev/null
  (cd "$d" && timeout "$5" sh -c "$3"); code=$?
  git -C "$1" worktree remove --force "$d"
else code=setup; fi
echo "$code" > "$4.tmp" && mv "$4.tmp" "$4" && touch "$(dirname "$4")/.tick-now"
"""
MEDIA = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".mp4", ".mov", ".webm", ".pdf")


# A project with a spec (T-517): PRs carry `Req: A-3.2@2` trailers, and these paths are Zeus's alone.
REQ = re.compile(r"(?mi)^Req:[ \t]*(.*)$")
CLOSES = re.compile(r"\b(?:closes|fixes|resolves)\s+#(\d+)", re.I)
PROTECTED = ("spec/", "tests/acceptance/")
TRAILERS = re.compile(r"(?mi)^(?:Req|Task):[ \t]*\S.*$")
COAUTHOR = re.compile(r"(?i)^co-authored-by:")


def req_text(pr, repo, fetch):
    """The PR body, plus its commit messages when the body has no Req: (one call); None if unreadable."""
    body = pr.get("body") or ""
    if REQ.search(body):
        return body
    view = fetch(["gh", "pr", "view", str(pr["number"]), "-R", repo, "--json", "commits"])
    if not isinstance(view, dict):
        return None
    return body + "".join(f"\n{c.get('messageHeadline') or ''}\n{c.get('messageBody') or ''}"
                          for c in view.get("commits") or [])


def req_problem(text, lines, ci_fix_tasks=None):
    """Why a PR's Req: trailers keep it out, or None. lines: {"A-3.2": 2}, the current PRD. `Req: ci-fix`
    passes only when `Task: T-n` names a ci-fix task and the PR closes that task's issue."""
    cites = [c for line in REQ.findall(text or "") for c in re.split(r"[,\s]+", line) if c]
    if not cites:
        return "no `Req:` trailer"
    bad = []
    issue = CLOSES.search(text or "")
    task = re.search(r"(?mi)^Task:[ \t]*(T-\d+)", text or "")
    fix = bool(issue and task and (ci_fix_tasks or {}).get(task.group(1)) == int(issue.group(1)))
    for c in cites:
        if c.lower() == "ci-fix":
            if not fix:
                bad.append("ci-fix (the PR must `Closes #` its `Task:` ci-fix issue)")
            continue
        m = re.fullmatch(r"(A-[\w.]+)@(\d+)", c)
        if not m or lines.get(m[1]) != int(m[2]):
            bad.append(f"{c} (current: {m[1]}@{lines[m[1]]})" if m and m[1] in lines else f"{c} (not in the PRD)")
    return f"`Req:` cites a line that is not current: {', '.join(bad)}" if bad else None


def protected(pr):
    """True when the PR touches spec/ or tests/acceptance/, or gh did not list all its files."""
    files = [f.get("path") or "" for f in pr.get("files") or []]
    return len(files) != pr.get("changedFiles") or any(f.startswith(PROTECTED) for f in files)


def secret_files(diff):
    """The files whose added lines look like a secret. Never the matched text: it goes in a message."""
    hits, path = [], None
    for line in (diff or "").splitlines():
        if line.startswith("+++ "):
            path = line[4:].removeprefix("b/")
        elif line.startswith("+") and SECRET.search(line) and path not in hits:
            hits.append(path)
    return hits


def fast_lane(pr, issue_body, review_before):
    """True when a PR may merge on green smoke without LGTM: every changed file is outside
    review_before and inside the issue's Files:, and the DONE: text in its body has `Verified:`.
    Anything unknown (no files, a list gh cut short, no Files: line) is gated."""
    files = [f.get("path") or "" for f in pr.get("files") or []]
    areas = [posixpath.normpath(a) for a in gh_sync.file_paths(issue_body)]
    return (bool(files) and len(files) == pr.get("changedFiles")
            and bool(re.search(r"(?m)^Verified:", pr.get("body") or ""))
            and all(not any(fnmatch.fnmatchcase(f, g) for g in review_before)
                    and any(f == a or f.startswith(a + "/") for a in areas) for f in files))


def docs_only(pr):
    """Factory rule F2: a diff of only docs/, READMEs and media merges on its evidence alone.
    No files, or a list gh cut short, is not docs-only."""
    files = [f.get("path") or "" for f in pr.get("files") or []]
    return bool(files) and len(files) == pr.get("changedFiles") and all(
        f.startswith("docs/") or posixpath.basename(f).upper().startswith("README")
        or f.lower().endswith(MEDIA) for f in files)


def is_lgtm(body, sha):
    """The reviewer's approval on a lead-account PR: the first line is exactly `LGTM <sha>`;
    notes may follow on later lines."""
    lines = (body or "").strip().splitlines()
    words = lines[0].split() if lines else []
    # hub live's review request shows a 12-character head, so a prefix of 12+ hex characters of the
    # CURRENT head counts too (T-506 run 2); an LGTM on an older head still never matches.
    return (len(words) == 2 and words[0] == "LGTM" and 12 <= len(words[1]) <= 40
            and re.fullmatch(r"[0-9a-f]+", words[1]) is not None and sha.startswith(words[1]))


def lead_changes(pr, lead_login):
    """The `CHANGES:` notes from the lead's account after the PR's last push, as (time, body),
    oldest first. Authors comment from the same account, so only that prefix asks for a fix."""
    pushed = max((c.get("committedDate") or "" for c in pr.get("commits") or []), default="")
    notes = [(r.get("submittedAt") or "", r.get("body") or "", r.get("author") or {}) for r in pr.get("reviews") or []]
    notes += [(c.get("createdAt") or "", c.get("body") or "", c.get("author") or {}) for c in pr.get("comments") or []]
    return sorted((at, body) for at, body, who in notes
                  if at > pushed and (who.get("login") or "").lower() == lead_login.lower()
                  and body.strip().startswith("CHANGES:"))


def squash_body(commits, trailers):
    """GitHub's default squash body (one commit: its body; more: each as a `* headline` item), with the
    Req:/Task: trailers and every Co-Authored-By: line together in one final trailer block."""
    parts, block = [], list(trailers)
    for c in commits:
        lines = (c.get("messageBody") or "").splitlines()
        block += [line.strip() for line in lines if COAUTHOR.match(line)]
        body = "\n".join(line for line in lines if not (TRAILERS.match(line) or COAUTHOR.match(line))).strip()
        parts.append(body if len(commits) == 1 else "\n\n".join(filter(None, [f"* {c.get('messageHeadline') or ''}", body])))
    return "\n\n".join(filter(None, parts + ["\n".join(dict.fromkeys(block))]))


def spawn(argv, out):
    """Start argv detached from hub live (its own session), output to the open file out."""
    subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def merge_tick(repo: str, clone: Path, smoke: str, lead_login: str, state: dict,
               run, send, review_before=None, req_lines=None, change_tasks=(),
               acceptance=(), acceptance_timeout=300, ci_fix_tasks=None, change_timeout=1800,
               gate_dir=None, spawn=spawn, change_issues=None) -> None:
    """Merge at most one eligible PR, then smoke and promote or revert integration.
    Records in state the PRs merged without review ("unreviewed") and the PRs waiting
    for review this pass ("gated"), for hub live's digest and alerts.
    req_lines: the current PRD's {"A-3.2": 2} in a project with a spec, else None (no spec rules).
    change_tasks: its unfinished generated tasks; a change branch waits for them.
    acceptance: the argv of every current PRD line's acceptance check (factory.json acceptance_cmd), each run
    under acceptance_timeout seconds on a change branch's head before it may join integration.
    ci_fix_tasks: {task id: issue number} for the project's ci-fix tasks with published issues.
    change_timeout: seconds for the smoke and make check on a change head, which run whole product suites.
    gate_dir: where a change gate's exit file and log go (hub live passes the project dir).
    spawn: starts the detached change gate; tests pass a fake.
    change_issues: {"change/C-NNN": [issue, ...]} of its generated tasks, closed once that change lands."""
    clone = Path(clone)
    gate_dir = Path(gate_dir or tempfile.gettempdir())
    spec = req_lines is not None
    # No "review_before" in hackathon.json: everything waits for LGTM (fail closed). The one
    # default list lives in the hackathon-reviewer skill, which the hackathon skill copies in.
    factory = review_before is None  # no hackathon config: factory rule F2 (docs_only) applies instead
    review_before = ["*"] if factory else review_before

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
        send(LEAD_AGENT, message)

    def git(*args):
        return call(["git", "-C", str(clone), *args])

    def close_change_issues():
        """Close the issues of a landed change's generated tasks: GitHub only auto-closes on the default
        branch. gh exits 0 on an already-closed issue; a failed close stays pending for the next pass."""
        pending = state.get("change_issue_pending", {})
        for branch, record in list(pending.items()):
            for issue in list(record["issues"]):  # no closed-forever list: a revert may reopen one for a later change
                result = call(["gh", "issue", "close", str(issue), "-R", repo, "-c",
                               f"Landed with {branch} at {record['sha'][:12]}"])
                if result.returncode:
                    print(f"live merge: {branch}: issue #{issue} close failed: {result.stderr.strip()}")
                    continue
                record["issues"].remove(issue)
            if not record["issues"]:
                del pending[branch]

    def merge_changes():
        """change/C-NNN joins integration as one unit once its tasks are done, no PR into it is open, and on
        its head every current acceptance check, the smoke and `make check` (when the Makefile has one) are
        green, which proves the rebuild matches the new PRD; smoke_head then promotes it to main like any merge.
        That gate runs detached (DETACHED_SH, as hub live's deploy), one at a time, recorded per branch in
        state["change_gates"]; a later pass reads how it ended, so a long suite never holds the live pass."""
        if change_tasks:
            return
        heads = git("ls-remote", "--heads", "origin")
        tried = state.setdefault("change_tried", {})  # the head whose gate result was acted on, per branch
        gates = state.setdefault("change_gates", {})
        busy = False
        for g in gates.values():
            if "exit" in g:
                continue
            exit_file = gate_dir / f"change-gate-{g['sha'][:12]}.exit"
            if exit_file.is_file():
                g["exit"] = exit_file.read_text().strip()
                exit_file.unlink()
            elif datetime.now(timezone.utc) - datetime.fromisoformat(g["started"]) > timedelta(seconds=g["cap"] + 300):
                g["exit"] = "lost"  # past its cap with no exit file: hub live or the machine restarted
            else:
                busy = True  # still running
                continue
            g["finished"] = now_iso()
        for line in heads.stdout.splitlines() if not heads.returncode else []:
            sha, _, ref = line.partition("\t")
            branch = ref.removeprefix("refs/heads/")
            if (not branch.startswith("change/") or tried.get(branch) == sha
                    or any(p.get("baseRefName") == branch for p in prs)):
                continue
            gate = gates.get(branch) or {}
            if gate.get("sha") == sha and "exit" not in gate:
                continue  # running
            if gate.get("sha") == sha and gate["exit"] != "lost":
                land_change(branch, sha, gate)
                continue
            if busy:
                continue
            if gate.get("exit") == "lost":  # its worktree died with it: prune the registration first
                print(f"live merge: {branch}: the gate at {gate['sha'][:12]} never finished; starting it again")
                git("worktree", "prune")
            if git("fetch", "-q", "origin", "integration", ref).returncode:
                print(f"live merge: {branch}: cannot fetch it with integration")  # transient: retried next pass
                continue
            if not git("merge-base", "--is-ancestor", sha, "origin/integration").returncode:
                git("push", "origin", "--delete", branch)  # merged on an earlier pass
                continue
            # hub env stripped from the checks, as spec.py and board.run_verify do
            steps = [(" ".join(argv), ["env", "-u", "HUB_DIR", "-u", "HUB_AGENT", "timeout",
                                       str(acceptance_timeout), *argv]) for argv in acceptance]
            steps += [("smoke", ["timeout", str(change_timeout), "sh", "-c", smoke]),
                      ("make check", ["timeout", str(change_timeout), "sh", "-c",
                                      "if make -n check >/dev/null 2>&1; then make check; fi"])]
            # the gate exits with the number of its first red step, so the result names it
            command = "\n".join(f"{shlex.join(argv)} || exit {n}" for n, (_, argv) in enumerate(steps, 1))
            cap = acceptance_timeout * len(acceptance) + 2 * change_timeout + 60
            exit_file = gate_dir / f"change-gate-{sha[:12]}.exit"
            exit_file.unlink(missing_ok=True)
            with open(gate_dir / "change-gate.log", "w") as out:
                spawn(["sh", "-c", DETACHED_SH, "change-gate", str(clone), sha, command, str(exit_file), str(cap)], out)
            gates[branch] = {"sha": sha, "started": now_iso(), "cap": cap, "steps": [name for name, _ in steps]}
            busy = True

    def land_change(branch, sha, gate):
        """Act once on a finished gate: tell Zeus the first red step, or merge the green head --no-ff."""
        tried = state["change_tried"]
        tried[branch] = sha
        code = gate["exit"]
        if code == "setup":
            fail(f"{branch}: cannot create a worktree at {sha[:12]}")
            return
        if code != "0":
            steps = gate["steps"]
            red = steps[int(code) - 1] if code.isdigit() and 0 < int(code) <= len(steps) else f"exit {code}"
            fail(f"{branch} is red at {sha[:12]} ({red}): not merged into integration")
            return
        if git("fetch", "-q", "origin", "integration").returncode:
            tried.pop(branch)  # transient: retried next pass, on the same green result
            print(f"live merge: {branch}: cannot fetch integration")
            return
        with tempfile.TemporaryDirectory(prefix="hub-live-change-") as directory:
            path = Path(directory)
            if git("worktree", "add", "-q", "--detach", str(path), sha).returncode:
                fail(f"{branch}: cannot create a worktree at {sha[:12]}")
                return
            inside = lambda *args: call(["git", "-C", str(path), *args])
            try:
                if (inside("checkout", "-q", "-f", "--detach", "origin/integration").returncode
                        or inside("merge", "--no-ff", "-m", f"Merge {branch}: its suite is green", sha).returncode):
                    fail(f"{branch} is green at {sha[:12]} but does not merge cleanly into integration: rebase it")
                    return
                if inside("push", "origin", "HEAD:refs/heads/integration").returncode:
                    tried.pop(branch)  # integration moved meanwhile: retried next pass, on the same green result
                    print(f"live merge: {branch}: integration push failed")
                    return
            finally:
                git("worktree", "remove", "--force", str(path))
        git("push", "origin", "--delete", branch)
        state.setdefault("merge_events", []).append(
            {"at": now_iso(), "event": "change-merged", "branch": branch, "sha": sha})
        issues = list(dict.fromkeys((change_issues or {}).get(branch, [])))
        if issues:
            state.setdefault("change_issue_pending", {})[branch] = {"sha": sha, "issues": issues}
            close_change_issues()
        send(LEAD_AGENT, f"{branch} is green at {sha[:12]}: merged into integration; the smoke promotes it to main")

    def smoke_head(merged_pr=None, issue=None, branch=None, branch_sha=None):
        # ponytail: retry covers lock contention from builder worktrees sharing the clone
        for attempt in range(3):
            fetched = git("fetch", "-q", "origin", "integration")
            if not fetched.returncode:
                break
            time.sleep(5 * (attempt + 1))
        if fetched.returncode:
            fail(f"Smoke setup failed: cannot fetch integration: {fetched.stderr.strip()[:200]}")
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
            else:
                state["promoted"] = sha  # hub live deploys it
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
                if merged_pr in state.get("unreviewed", []):
                    state["unreviewed"].remove(merged_pr)  # reverted: nothing for Hermes' digest to review
                output = (str(result.stdout or "") + "\n" + str(result.stderr or "")).splitlines()
                state.setdefault("merge_events", []).append(  # why: the smoke's last line, for the task note
                    {"at": now_iso(), "pr": merged_pr, "issue": issue, "event": "reverted",
                     "why": next((line.strip() for line in reversed(output) if line.strip()), "")})
            finally:
                git("worktree", "remove", "--force", str(path))
        restored = (call(["gh", "api", f"repos/{repo}/git/refs", "-f", f"ref=refs/heads/{branch}",
                          "-f", f"sha={branch_sha}"]) if branch and branch_sha else
                    subprocess.CompletedProcess([], 1, "", "missing PR head"))
        restore_error = restored.stderr or ""
        restored_ok = restored.returncode == 0 or ("HTTP 422" in restore_error and "already exists" in restore_error.lower())
        if not restored_ok:
            fail(f"Smoke failed after #{merged_pr}; branch {branch or '?'} restore failed at {branch_sha or '?'}: "
                 f"{restore_error.strip()[:200]}")
        lines = (str(result.stdout or "") + "\n" + str(result.stderr or "")).splitlines()[-30:]
        body = (f"Reverted: the smoke failed after #{merged_pr} merged.\n"
                + "\n".join(lines)
                + ("\nFix it on the same branch, push, and post a new DONE: comment (the lead opens the new PR)."
                   if restored_ok else
                   f"\nBranch {branch or '?'} could not be restored at {branch_sha or '?'}. Ask the lead to restore it before fixing."))
        reopened = call(["gh", "issue", "reopen", str(issue), "-R", repo, "--comment", body])
        if reopened.returncode:
            fail(f"Smoke failed after #{merged_pr}; issue #{issue} reopen failed")
        else:
            fail(f"Smoke failed after #{merged_pr}; reverted integration and reopened issue #{issue}")

    close_change_issues()
    prs = data(["gh", "pr", "list", "-R", repo, "--state", "open", "--limit", "100",
                "--json", "number,body,author,headRefOid,headRefName,baseRefName,isDraft,mergeable,comments,reviews,files,changedFiles"])
    if prs is None:
        fail("Merge queue failed: cannot list PRs")
        return
    chosen = None
    issue = None
    unreviewed = False
    gated = state["gated"] = []
    for pr in sorted(prs, key=lambda item: item["number"]):
        if pr.get("isDraft") or pr.get("mergeable") == "CONFLICTING":
            continue
        body = pr.get("body") or ""
        match = CLOSES.search(body)
        if not match or not EVIDENCE.search(body):
            continue  # no Evidence: hub live has asked for it, and it never merges without
        if spec:  # hub live comments on a bad Req: and sends spec/ and tests/acceptance/ PRs to Zeus
            text = req_text(pr, repo, data)
            if text is None or req_problem(text, req_lines, ci_fix_tasks) or protected(pr):
                continue
        to_change = spec and (pr.get("baseRefName") or "").startswith("change/")
        issue_number = int(match.group(1))
        linked_issue = data(["gh", "issue", "view", str(issue_number), "-R", repo,
                             "--json", "state,body,labels"])
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
        builder = next((label["name"][6:].lower() for label in linked_issue.get("labels") or []
                        if label["name"].startswith("agent:")), None)
        fast = False
        if author == lead_login:
            # Hermes posts its LGTM from the lead's account, so on a PR Hermes built the LGTM is the
            # builder's and never counts (R1 practice 4); Zeus merges that one by hand.
            # shortcut: any agent can post from the lead's account; signed LGTMs would close that.
            lgtms = [] if builder == REVIEWER.lower() else [
                comment.get("createdAt") or "" for comment in pr.get("comments") or []
                if is_lgtm(comment.get("body"), sha)
                and (comment.get("author") or {}).get("login") == lead_login]
            # A CHANGES: since the last push holds the PR (fast lane too) until a later LGTM. Commits
            # come per PR: on the list call they exceed GitHub's 500,000-node GraphQL limit.
            if any((note.get("body") or "").strip().startswith("CHANGES:")
                   for note in (pr.get("comments") or []) + (pr.get("reviews") or [])):
                view = data(["gh", "pr", "view", str(pr["number"]), "-R", repo, "--json", "commits"])
                if view is None:
                    gated.append(pr["number"])
                    continue
                pr["commits"] = view.get("commits")
            asks = lead_changes(pr, lead_login)
            if asks and not any(at > asks[-1][0] for at in lgtms):
                gated.append(pr["number"])
                continue
            approved = bool(lgtms)
            # Only lead-account PRs: they merge with --admin, so no GitHub review is needed.
            # With a hackathon config, fast_lane already covers ungated in-area docs; docs_only would
            # bypass review_before (docs/CONTRACT.md) and the issue's Files: (Hermes review of 4ac34c0).
            fast = not approved and (docs_only(pr) if factory else fast_lane(pr, linked_issue.get("body"), review_before))
            if fast:  # a hard extra condition: no secret in the added lines, and the diff was read
                diff = call(["gh", "pr", "diff", str(pr["number"]), "-R", repo])
                hits = secret_files(diff.stdout)
                fast = not diff.returncode and not hits
                noted = state.setdefault("secret_noted", [])
                if hits and f"{pr['number']}:{sha}" not in noted:
                    noted.append(f"{pr['number']}:{sha}")
                    send(LEAD_AGENT, f"SECRET? PR #{pr['number']} {', '.join(hits)}: gated until a reviewer reads it; "
                                 "if it is real, revoke it at its provider")
            approved = approved or fast
        else:
            owner, name = repo.split("/", 1)
            reviews = data(["gh", "api", f"repos/{owner}/{name}/pulls/{pr['number']}/reviews"])
            approved = reviews is not None and any(
                review.get("state") == "APPROVED" and review.get("commit_id") == sha
                and (review.get("user") or {}).get("login") != author  # the builder never approves
                for review in reviews)
        if not approved:
            gated.append(pr["number"])
            continue
        if to_change:  # CI runs on PRs into integration only; the change's own suite gates it (merge_changes)
            chosen, issue, unreviewed = pr, issue_number, fast
            break
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
        # GitHub's smoke ran on the PR merged into integration as it was then; the local smoke
        # below still runs on the real merge before main moves. No smoke check at all means
        # Actions is not reporting it, and the local smoke alone decides.
        ci_smoke = [check.get("bucket") for check in checks if check.get("name") == "smoke"]
        if any(bucket != "pass" for bucket in ci_smoke):
            continue
        if any(check.get("name") == "image" and check.get("bucket") == "fail" for check in checks):
            continue  # the image build failed; absent or pending (no Dockerfile yet) does not hold
        if not ci_smoke:
            print(f"live merge: #{pr['number']} has no smoke check (Actions not reporting); the local smoke alone decides")
        chosen, issue, unreviewed = pr, issue_number, fast
        break

    if chosen is None:
        if spec:
            merge_changes()
        smoke_head()
        return
    to_change = spec and (chosen.get("baseRefName") or "").startswith("change/")
    number, sha = chosen["number"], chosen["headRefOid"]
    command = ["gh", "pr", "merge", str(number), "-R", repo, "--squash", "--delete-branch",
               "--match-head-commit", sha]
    # The squash commit keeps the PR's Req: and Task: trailers (body or commits), for spec.py's history()
    view = data(["gh", "pr", "view", str(number), "-R", repo, "--json", "commits"])
    if view is None:
        print(f"live merge: #{number}: cannot read its commits; not merged this pass")
        return
    commits = view.get("commits") or []
    text = "\n".join([chosen.get("body") or ""] + [c.get("messageBody") or "" for c in commits])
    trailers = list(dict.fromkeys(t.strip() for t in TRAILERS.findall(text)))
    if trailers:
        command += ["--body", squash_body(commits, trailers)]
    if (chosen.get("author") or {}).get("login") == lead_login:
        command.append("--admin")
    merged = call(command)
    if merged.returncode:
        print(f"live merge: cannot merge #{number}: {merged.stderr}")
        return
    if not to_change:
        state.setdefault("first_merge", sha)  # hub live checks CI reported on it
    # The dashboard counts merged-not-reverted PRs per agent from these (issue -> board task -> owner);
    # hub live sets the task's merge_sha from sha, found by issue, then by the Task: trailer.
    view = data(["gh", "pr", "view", str(number), "-R", repo, "--json", "mergeCommit"])
    task = re.search(r"(?mi)^Task:[ \t]*(T-\d+)", text)
    state.setdefault("merge_events", []).append(  # base: a change branch's merge commit is these tasks' too
        {"at": now_iso(), "pr": number, "issue": issue, "event": "merged", "base": chosen.get("baseRefName"),
         "sha": ((view or {}).get("mergeCommit") or {}).get("oid"), "task": task and task[1]})
    if unreviewed:
        state.setdefault("unreviewed", []).append(number)
    if to_change:
        return  # integration is untouched: nothing to smoke or promote
    smoke_head(number, issue, chosen.get("headRefName"), sha)
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
