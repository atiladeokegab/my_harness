"""`hub live --project <p>`: the mechanical half of a hackathon's Live loop.

Every tick (5 minutes) it checks the clock, syncs, opens a PR for each teammate's `DONE:`, hands
each new item to whoever judges it (PRs and sub-issue changes to Hermes; DRAFTs, change-requests,
the lead's questions and errors to Zeus), merges at most one approved PR through live_merge, runs
the freeze and the reminders, and nudges. It never judges anything itself.
The hackathon skill's §7 says who handles what.
"""

import fcntl
import fnmatch
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import board as hb
import gh_sync
from live_merge import CLOSES, DETACHED_SH, EVIDENCE, docs_only, fast_lane, lead_changes, protected, req_problem, req_text, secret_files

REVIEWER = os.environ.get("HUB_REVIEWER") or "Hermes"
LEAD_AGENT = os.environ.get("HUB_LEAD") or "Zeus"
# gh's words for GitHub throttling ("API rate limit exceeded", "secondary rate limit", HTTP 429,
# Retry-After). A plain 403 is a permissions error, not a throttle.
# shortcut/ponytail notes only after a comment marker, so `shortcut: "⌘K"` in UI code is not a limitation
LIMITS = r"(#|//|/\*|--|<!--) *(shortcut|ponytail):"
THROTTLE = re.compile(r"rate limit|HTTP 429|retry-after", re.I)
BIG_DIFF = 800  # changed lines; unmerged agent PRs are the larger ones (R1 practice 3)
NO_EVIDENCE = ("Held: this PR body has no `## Evidence` block (or `Verified:` line), so it is not sent for "
               "review and will not merge. Add one to the body: the commands you ran in a clean checkout, their "
               "exit codes and the last lines of output, and screenshot links for anything visible.")


class Throttled(Exception):
    """GitHub throttled a gh call: the rest of the pass is skipped."""


def run(args, cwd=None, timeout=60):
    """Run a command; a non-zero exit is returned, never raised."""
    return subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def send(agent, text):
    # Sign as hub-live, not "Unknown" (dry run #4), unless the caller set an identity.
    subprocess.run(["hubmsg", agent, text], capture_output=True, text=True, timeout=30,
                   env={**os.environ, "HUB_AGENT": os.environ.get("HUB_AGENT") or "hub-live"})


def owned_files(detail):
    """The paths a task's brief owns: its OWNS: or Files owned: line, else its Files: line."""
    for name in ("OWNS", "Files owned"):
        value = gh_sync.field_line(detail, name)
        if value:  # "OWNS: live.py, tests/test_live.py. Starts after ...": the list ends at the sentence
            value = re.split(r"\.(?:\s|$)", value.replace("`", ""))[0]
            return [p for p in re.split(r"[,\s]+", value) if "/" in p or "." in p]
    return gh_sync.file_paths(detail)


def when(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class Live:
    def __init__(self, project, run=run, send=send, now=None):
        self.project = project
        self.dir = Path(hb.HUB_DIR) / "projects" / project
        self.cfg = json.loads((self.dir / "hackathon.json").read_text())
        self.repo = self.cfg["repo"]
        self.clone = Path(os.environ.get("HUB_CODE_DIR") or os.path.expanduser("~/code")) / project
        self.lead = next(p["github"] for p in self.cfg["roster"] if p.get("lead"))
        self.deadlines = {d["name"]: when(d["at"]) for d in self.cfg["deadlines"]}
        self._run, self._send, self.now = run, send, now or (lambda: datetime.now(timezone.utc))
        self.interval = 300  # cmd_live sets --interval; a throttle doubles it, up to 10 min
        self.state_file = self.dir / "live-state.json"
        self.state = json.loads(self.state_file.read_text()) if self.state_file.is_file() else {}
        self.state.setdefault("sent", [])
        self._prs, self._branches, self._branch_work, self._commits, self._pushes = None, None, None, {}, None
        self._prs_error = self._branch_error = self._branch_work_error = False

    def log(self, line):
        with open(self.dir / "live.log", "a") as f:
            f.write(f"{self.now().isoformat(timespec='seconds')} {line}\n")

    def once(self, key, agent, text):
        """Send `text` to `agent` the first time `key` is seen, ever."""
        if key in self.state["sent"]:
            return
        self.state["sent"].append(key)
        self._send(agent, text)
        self.log(f"sent {agent}: {text}")

    def run(self, args, cwd=None, timeout=60):
        """Every command hub live and live_merge run comes through here, so one check sees every throttle."""
        r = self._run(args, cwd=cwd, timeout=timeout)
        if r.returncode and str(args[0]) in ("gh", "hub") and THROTTLE.search(r.stderr or ""):
            raise Throttled((r.stderr or "").strip()[:200])
        return r

    def paused(self):
        """~/hub/PAUSE stops every pass, merges and nudges included, until `hub resume`."""
        reason = hb.paused()
        if reason:
            self.log(f"paused: {reason}")
            self.save()
        return bool(reason)

    def throttled(self):
        until = self.state.get("throttled_until")
        return bool(until) and self.now() < when(until)

    def throttle(self, why):
        """Back off: the next pass waits twice as long (up to 10 min). Zeus hears once per episode,
        which ends at the first pass that finishes clean."""
        now = self.now()
        backoff = self.state["backoff"] = min(600, 2 * self.state.get("backoff", self.interval))
        until = now + timedelta(seconds=backoff)
        self.state["throttled_until"] = until.isoformat(timespec="seconds")
        since = self.state.setdefault("throttled_since", now.isoformat(timespec="seconds"))
        self.log(f"throttled by GitHub ({why}); next pass in {backoff} s")
        local = until.astimezone(ZoneInfo(self.cfg.get("timezone") or "UTC")).strftime("%H:%M")
        self.once(f"throttle:{since}", LEAD_AGENT, f"{self.project}: hub live throttled by GitHub until ~{local}")

    def gh_json(self, *args, timeout=60):
        r = self.run(["gh", *args], timeout=timeout)
        if r.returncode:
            self.log(f"gh {' '.join(args[:3])} failed: {(r.stderr or '').strip()[:200]}")
            return None
        return json.loads(r.stdout or "null")

    def save(self):
        self.state_file.write_text(json.dumps(self.state, indent=1) + "\n")

    # --- the tick ------------------------------------------------------------------

    def tick(self):
        """One pass. Returns False once submit has passed (the loop stops)."""
        if self.now() >= self.deadlines["submit"]:
            self.once("submit", LEAD_AGENT, f"{self.project}: submit has passed; hub live stopped.")
            self.save()
            return False
        if self.paused():
            return True
        # The full gh-sync takes minutes and blocks the quick PR checks, so it runs every other
        # pass; the inbox, PR and merge steps run on every pass (dry run #4, F11).
        self.state["ticks"] = self.state.get("ticks", 0) + 1
        self.state.setdefault("rollcall_at", self.now().isoformat())
        self._prs, self._branches, self._branch_work, self._commits, self._pushes = None, None, None, {}, None
        self._prs_error = self._branch_error = self._branch_work_error = False
        steps = (self.sync,) if self.state["ticks"] % 2 == 1 else ()
        for step in steps + (self.inbox, self.done, self.agent_labels, self.prs, self.ci_failures, self.issues,
                             self.merge, self.hand_merges, self.merge_shas, self.reverts, self.deploy,
                             self.ci_reports, self.timers, self.nudges, self.roll_call):
            try:
                step()
            except Throttled as e:
                self.throttle(e)
                break
            except Exception as e:  # one broken step never stops the loop
                self.log(f"{step.__name__} failed: {e}")
        else:
            for key in ("backoff", "throttled_until", "throttled_since"):
                self.state.pop(key, None)
        self.save()
        return True

    def sync(self):
        if self.cfg.get("factory"):
            return  # a factory repo: the factory poll owns its GitHub link, and gh-sync refuses non-template repos
        r = self.run(["hub", "gh-sync", "--project", self.project], timeout=600)
        for line in (r.stdout + r.stderr).splitlines():
            if line.startswith("error:"):
                self.once(f"error:{line}", LEAD_AGENT, f"{self.project} gh-sync: {line}")

    def inbox(self):
        """team-inbox --lead prints only what is new since its last run, so every line goes on."""
        script = self.clone / "scripts" / "team-inbox.sh"
        if not script.is_file():
            return
        r = self.run([script, "--lead"], cwd=self.clone, timeout=180)
        for line in r.stdout.splitlines():
            kind = line.split(" ", 1)[0]
            if kind in ("NEW", "CHANGED") and " in #" in line:  # sub-issue activity: FLAG if it drifts
                self._send(REVIEWER, f"{self.project} {line}")
                self.log(f"sent {REVIEWER}: {line}")
            elif kind == "DRAFT":
                self._send(LEAD_AGENT, f"{self.project} {line} (decide within 10 min)")
                self.log(f"sent {LEAD_AGENT}: {line}")

    def done(self):
        """Teammates' agents never open PRs (they got stuck on the mechanics): a `DONE:` comment on
        the issue is the signal, and the PR is opened here from the lead's account. Each DONE: is
        acted on once, and a branch that already has an open PR (a DONE: after review fixes) gets none.
        A DONE: with no `Verified:` line gets one comment saying so and no PR: its text becomes the PR
        body, and the merge queue reads `Verified:` there."""
        team = {x["github"].lower() for p in self.cfg["roster"] for x in [p, *p.get("agents", [])] if x.get("github")}
        heads = None
        for issue in self.gh_json("issue", "list", "-R", self.repo, "--state", "open", "--limit", "200",
                                  "--json", "number,title,comments") or []:
            n, comments = issue["number"], issue.get("comments") or []
            said = [c for c in comments if (c.get("body") or "").startswith("DONE:")
                    and (c.get("author") or {}).get("login", "").lower() in team]
            if not said:
                continue
            key = f"done:{n}:{said[-1]['createdAt']}"
            if key in self.state["sent"]:
                continue
            if not re.search(r"(?m)^Verified:", said[-1]["body"]):
                self.state["sent"].append(key)
                self.run(["gh", "issue", "comment", n, "-R", self.repo, "--body",
                          "No PR yet: this DONE: has no `Verified:` line. Post a new DONE: with `Verified:` "
                          "(the commands you ran in a clean checkout, `git worktree add --detach ../verify-<N> HEAD` "
                          "then `make -C ../verify-<N> check`, and their counts) and `Not verified:` (what you didn't check, or \"nothing\")."])
                self.log(f"refused DONE: on #{n}: no Verified:")
                continue
            refs = self.gh_json("api", f"repos/{self.repo}/git/matching-refs/heads/{n}-", "--jq", "[.[].ref]")
            if not refs:
                continue  # not pushed yet: try again next pass
            if heads is None:
                heads = self.gh_json("pr", "list", "-R", self.repo, "--state", "open", "--limit", "200",
                                     "--json", "headRefName")
                if heads is None:
                    return  # unsure which branches have a PR: never risk a second one
                heads = {pr["headRefName"] for pr in heads}
            self.state["sent"].append(key)
            branch = refs[0].removeprefix("refs/heads/")
            if branch in heads:
                continue
            plan = next((c.get("url") for c in comments if (c.get("body") or "").lstrip().startswith("Plan:")), None)
            body = f"Closes #{n}\n\n- [x] Plan comment: {plan or 'none posted'}\n\n{said[-1]['body']}\n"
            task = self.task_for({"body": f"Closes #{n}"})  # a task hub spec apply generated builds on its change branch
            base = (gh_sync.change_branch(task) if task and task.get("generated_from") else None) or "integration"
            r = self.run(["gh", "pr", "create", "-R", self.repo, "--base", base, "--head", branch,
                          "--title", f"{issue['title']} (#{n})", "--body", body])
            if r.returncode:
                self.state["sent"].remove(key)  # retry this DONE: on the next pass
                self.once(f"donefail:{key}", LEAD_AGENT, f"{self.project} cannot open the PR for #{n} from "
                          f"{branch}: {(r.stderr or '').strip()[:200]}")
            else:
                self.log(f"opened PR for #{n} from {branch}")

    def prs(self):
        # gh's default limit of 30 dropped the 31st PR. Commits come per PR, as in live_merge: on a
        # 100-PR list they exceed GitHub's 500,000-node GraphQL limit.
        self._prs = self.gh_json("pr", "list", "-R", self.repo, "--state", "open", "--limit", "100", "--json",
                                "number,title,headRefOid,headRefName,isDraft,author,body,reviews,comments,files,changedFiles,additions,deletions")
        if not isinstance(self._prs, list):
            self._prs, self._prs_error = [], True
            hour = self.now().strftime("%Y-%m-%dT%H")
            self.once(f"prlist:{hour}", LEAD_AGENT, f"{self.project}: PR list failed; review routing and roll call are incomplete.")
            return
        self._prs_error = False
        lines = gh_sync.current_lines(self.project)  # re-read each pass: hub spec apply moves it
        fixes = self.ci_fix_tasks() if lines is not None else {}
        for pr in self._prs:
            if pr["isDraft"]:
                continue
            n, sha = pr["number"], pr["headRefOid"]
            if ((pr.get("author") or {}).get("login", "").lower() == self.lead.lower()
                    and any((note.get("body") or "").strip().startswith("CHANGES:")
                            for note in (pr.get("comments") or []) + (pr.get("reviews") or []))):
                view = self.gh_json("pr", "view", str(n), "-R", self.repo, "--json", "commits")
                if not isinstance(view, dict):
                    continue  # logged by gh_json; retried next pass
                pr["commits"] = view.get("commits")
            key = f"pr:{n}:{sha}"
            if lines is not None and self.spec_hold(pr, lines, fixes):
                pass
            elif key in self.state["sent"]:
                pass
            elif not EVIDENCE.search(pr.get("body") or ""):
                self.hold(pr)  # not reviewed until it proves its work; live_merge never merges it
            elif self.fast(pr):
                self.state["sent"].append(key)  # the "merged without review:" digest covers it
            else:
                task = self.task_for(pr)
                text = f"{self.project} PR #{n} ready for review at {sha[:12]}: {pr['title']}{self.scope(pr, task)}"
                if self.builder(task) == REVIEWER:  # live_merge ignores Hermes's LGTM on its own PR
                    self.once(key, LEAD_AGENT, f"{text}\nBuilt by {REVIEWER}, so its LGTM does not count: "
                              "review it and merge it by hand.")
                else:
                    self.once(key, REVIEWER, text)
            if (pr.get("author") or {}).get("login", "").lower() == self.lead.lower():
                self.fixes(pr)

    def hold(self, pr):
        """One comment per PR saying what is missing; a failed comment is retried next pass."""
        key = f"evidence:{pr['number']}"
        if key not in self.state["sent"] and not self.run(
                ["gh", "pr", "comment", pr["number"], "-R", self.repo, "--body", NO_EVIDENCE]).returncode:
            self.state["sent"].append(key)
            self.log(f"held PR #{pr['number']}: no Evidence")

    def ci_fix_tasks(self):
        with hb.board() as (data, _):
            return {t["id"]: t["issue"] for t in data["tasks"] if t.get("project") == self.project
                    and "ci-fix" in (t.get("tags") or []) and t.get("issue")}

    def spec_hold(self, pr, lines, ci_fix_tasks=None):
        """In a project with a spec: a PR whose Req: is missing or not current gets one comment per problem
        and no review; one touching spec/ or tests/acceptance/ goes to Zeus, never Hermes or the fast lane.
        True when held; live_merge applies the same rules and never merges either."""
        n, sha = pr["number"], pr["headRefOid"]
        text = req_text(pr, self.repo, lambda args: self.gh_json(*args[1:]))
        if text is None:
            return True  # commits unreadable: logged by gh_json, retried next pass
        problem = req_problem(text, lines, ci_fix_tasks)
        if problem:
            key = f"req:{n}:{problem}"
            if key not in self.state["sent"] and not self.run(
                    ["gh", "pr", "comment", n, "-R", self.repo, "--body",
                     f"Held: {problem}. In this project every PR cites the acceptance lines it implements, at "
                     "their current versions, as `Req: A-3.2@2` lines in its body or a commit message (the current "
                     "lines are in the issue). Push a commit whose message carries them; nothing is reviewed or "
                     "merged until then."]).returncode:
                self.state["sent"].append(key)
                self.log(f"held PR #{n}: {problem}")
            return True
        if protected(pr):
            self.once(f"protected:{n}:{sha}", LEAD_AGENT,
                      f"{self.project} PR #{n} at {sha[:12]} touches spec/ or tests/acceptance/ (or gh cut its file "
                      f"list short): protected, so not sent to {REVIEWER} and never merged by hub live. Review it and "
                      "merge it by hand.")
            return True
        return False

    def task_for(self, pr):
        """The hub task whose issue the PR closes, or None."""
        m = CLOSES.search(pr.get("body") or "")
        if not m:
            return None
        with hb.board() as (data, _):
            return next((t for t in data["tasks"]
                         if t.get("project") == self.project and t.get("issue") == int(m[1])), None)

    def builder(self, task):
        """Who built the task's PR: its agent, else Zeus; None for a teammate, who reads GitHub."""
        t = task or {}
        if t.get("agent"):
            return hb.canon(t["agent"])
        teammates = {hb.canon(p["name"]) for p in self.cfg["roster"] if not p.get("lead")}
        return None if hb.canon(t.get("owner")) in teammates else LEAD_AGENT

    def scope(self, pr, task):
        """Lines for Hermes: changed paths outside the task's owned files, and a diff over BIG_DIFF lines."""
        detail = (task or {}).get("detail")
        # Zeus may widen a factory issue's Files: after the task is made. Not for untrusted tasks: their issue's
        # author is the outsider, who can always edit the body; only the board detail is ours.
        if (task or {}).get("kind") == "factory" and task.get("issue") and "untrusted" not in (task.get("tags") or []):
            issue = self.gh_json("issue", "view", str(task["issue"]), "-R", self.repo, "--json", "body")
            detail = issue.get("body") if isinstance(issue, dict) else detail
        owned = owned_files(detail)
        extra = [f["path"] for f in pr.get("files") or [] if owned and not any(
            f["path"] == a or f["path"].startswith(a.rstrip("/") + "/") or fnmatch.fnmatchcase(f["path"], a)
            for a in owned)]
        size = (pr.get("additions") or 0) + (pr.get("deletions") or 0)
        return ((f"\nOutside {task['id']}'s owned files: {', '.join(extra)}" if extra else "")
                + (f"\n{size} changed lines (over {BIG_DIFF}): check it should not be split" if size > BIG_DIFF else ""))

    def ci_failures(self):
        """A required check failed on an open PR's head: the failed run's log tail goes to the builder as a
        fix request and counts an attempt on its hub task. From hb.MAX_ATTEMPTS on, the builder hears
        nothing more and Zeus decides (R1 practices 2 and 10). Once per head sha."""
        required = set(self.cfg.get("checks", ["freeze-gate"])) | {"smoke", "image"}
        for pr in self._prs or []:
            n, sha = pr["number"], pr["headRefOid"]
            key = f"cifail:{n}:{sha}"
            if pr.get("isDraft") or key in self.state["sent"]:
                continue
            r = self.run(["gh", "pr", "checks", n, "-R", self.repo, "--json", "name,bucket,link"])
            try:  # gh may exit non-zero because a check failed; the JSON still says which
                failed = [c for c in json.loads(r.stdout or "[]") if c.get("name") in required and c.get("bucket") == "fail"]
            except (TypeError, ValueError):
                continue
            if not failed:
                continue
            self.state["sent"].append(key)
            names = ", ".join(c["name"] for c in failed)
            run_id = re.search(r"/actions/runs/(\d+)", failed[0].get("link") or "")
            log = run_id and self.run(["gh", "run", "view", run_id[1], "-R", self.repo, "--log-failed"], timeout=120)
            tail = ("\n".join(log.stdout.splitlines()[-60:]) if log and not log.returncode else "") or \
                f"(no Actions log: {failed[0].get('link') or 'see the PR checks'})"
            task = self.task_for(pr)
            tries = task and hb.bump_attempts(task["id"], "hub-live", f"CI {names} failed on PR #{n} at {sha[:12]}", tail)
            if tries and tries >= hb.MAX_ATTEMPTS:
                self.once(f"cistop:{n}", LEAD_AGENT,
                          f"{self.project} PR #{n} ({task['id']}) has failed CI {tries} times, now {names} at {sha[:12]}: "
                          f"no more fix requests to its builder; decide it. The log tail is on the task (hub show {task['id']}).")
                continue
            text = (f"{self.project} CI failed on PR #{n} at {sha[:12]}: {names}. Fix it on the same branch "
                    f"(attempt {tries or '?'} of {hb.MAX_ATTEMPTS}). Failed log, last 60 lines:\n{tail}")
            builder = self.builder(task)
            if builder:
                self._send(builder, text)
                self.log(f"sent {builder}: CI fix request for PR #{n} at {sha[:12]}")
            else:
                self.run(["gh", "pr", "comment", n, "-R", self.repo, "--body", text])

    def fast(self, pr):
        """True when live_merge would merge this PR without review (its fast lane, no secret in
        the diff, no CHANGES: pending). Anything unknown is False: Hermes hears of it."""
        m = CLOSES.search(pr.get("body") or "")
        review_before = self.cfg.get("review_before")
        if (not m or lead_changes(pr, self.lead)
                or (pr.get("author") or {}).get("login", "").lower() != self.lead.lower()):
            return False
        if review_before is None:  # factory repo: rule F2, docs, READMEs and media need no review
            if not docs_only(pr):
                return False
        else:  # hackathon: the fast lane alone, so review_before and the issue's Files: still gate docs
            issue = self.gh_json("issue", "view", m[1], "-R", self.repo, "--json", "body")
            if not isinstance(issue, dict) or not fast_lane(pr, issue.get("body"), review_before):
                return False
        diff = self.run(["gh", "pr", "diff", str(pr["number"]), "-R", self.repo])
        return not diff.returncode and not secret_files(diff.stdout)

    def fixes(self, pr):
        """A PR from the lead's account can only get comments, not a changes-requested review, so a
        note from the lead's account after the last push that starts `CHANGES:` asks for a fix. Only
        that prefix: authors comment from the same account, and 12 of 17 relays at real-world-agents
        were their own "Review fix in <sha>" echoes. It goes to the agent that built it (the issue's
        agent:<name> label), which has stopped watching."""
        n, sha = pr["number"], pr["headRefOid"]
        asks = [body for _, body in lead_changes(pr, self.lead)]
        if not asks:
            return
        agent = LEAD_AGENT
        m = re.search(r"\b(?:closes|fixes|resolves)\s+#(\d+)", pr.get("body") or "", re.I)
        issue = m and self.gh_json("issue", "view", m[1], "-R", self.repo, "--json", "labels,assignees")
        owners = [a["login"].lower() for a in (issue or {}).get("assignees") or []]
        if owners and self.lead.lower() not in owners:
            return  # a teammate's PR that done() opened: their inbox shows the review
        for label in (issue or {}).get("labels") or []:
            if label["name"].startswith("agent:"):
                agent = label["name"].split(":", 1)[1].capitalize()
        key = f"fix:{n}:{sha}"
        if key not in self.state["sent"]:
            rounds = self.state.setdefault("fix_rounds", {}).setdefault(str(n), [])
            rounds.append(sha)
            if len(rounds) >= 3:  # a review loop: the brief is probably the problem, not the code
                self.once(f"loop:{n}", LEAD_AGENT,
                          f"{self.project} PR #{n} is on its {len(rounds)}rd round of requested changes: "
                          "check the brief or decide it")
        self.once(key, agent,
                  f"{self.project} changes requested on PR #{n} at {sha[:12]}: {asks[-1].splitlines()[0][:200]}"
                  f" (fix it on the same branch; a {LEAD_AGENT} sub-agent: resume it by name)")

    def issues(self):
        for cr in self.gh_json("issue", "list", "-R", self.repo, "--label", "change-request",
                               "--state", "open", "--json", "number,title") or []:
            self.once(f"cr:{cr['number']}", LEAD_AGENT, f"{self.project} change-request #{cr['number']}: {cr['title']}")

    def merge(self):
        hold = self.dir / ".merge-hold"
        if hold.is_file():
            since = hold.read_text().strip() or "?"
            self.log(f"merges held since {since}")
            try:
                if self.now() - when(since) >= timedelta(minutes=15):
                    self.once(f"hold:{since}", LEAD_AGENT,
                              f"{self.project}: merges held by {REVIEWER} since {since} (15 min+). "
                              f"Resume: hub live --project {self.project} --resume-merges")
            except ValueError:
                pass
            return
        try:
            import live_merge
        except ImportError:
            self.log("live_merge missing: no merges this tick")
            return
        def send(agent, text):  # live.log keeps what live_merge tells Zeus too (reverts, failures)
            self._send(agent, text)
            self.log(f"sent {agent}: {text}")
        lines, spec = gh_sync.current_lines(self.project), {}
        if lines is not None:  # a change branch waits for every unfinished task generated from the PRD
            with hb.board() as (data, _):
                spec = {"req_lines": lines, "change_tasks": [
                    t["id"] for t in data["tasks"] if t.get("project") == self.project and t.get("generated_from")
                    and t.get("status") != "done" and "stale" not in (t.get("tags") or [])]}
                issues = {}
                for task in data["tasks"]:
                    if task.get("project") == self.project and task.get("issue") and (branch := gh_sync.change_branch(task)):
                        issues.setdefault(branch, []).append(task["issue"])
                spec["change_issues"] = issues
            spec["acceptance"], spec["acceptance_timeout"] = gh_sync.acceptance_checks(self.project)
            spec["ci_fix_tasks"] = self.ci_fix_tasks()
            spec["change_timeout"] = gh_sync.factory_entry(self.project).get("change_timeout", 1800)
            spec["gate_dir"] = self.dir
        live_merge.merge_tick(self.repo, self.clone, self.cfg["smoke"], self.lead, self.state,
                              self.run, send, self.cfg.get("review_before"), **spec)
        now, since = self.now(), self.state.setdefault("gated_since", {})
        for n in self.state.get("gated", []):
            if now - when(since.setdefault(str(n), now.isoformat())) > timedelta(minutes=10):
                self.once(f"gatewait:{n}", LEAD_AGENT,
                          f"{self.project} PR #{n} has waited 10+ min for LGTM: review it "
                          f"(a sub-agent can load hub:hackathon-reviewer) or chase {REVIEWER}.")

    def hand_merges(self):
        """A PR merged into integration by someone other than live_merge (Zeus merging a Hermes-built PR)
        gets the merged merge_event live_merge would have written, once: the dashboard counts from these."""
        events = self.state.setdefault("merge_events", [])
        prs = self.gh_json("pr", "list", "-R", self.repo, "--state", "merged", "--base", "integration",
                           "--limit", "20", "--json", "number,body,mergedAt,mergeCommit")
        if not self.state.get("hand_merges_seeded"):  # merges before this step existed are not hand merges
            if prs is None:
                return  # a failed first call must not seed an empty set
            self.state["hand_merges_seen"] = [pr["number"] for pr in prs]
            self.state["hand_merges_seeded"] = True
            return
        known = {e["pr"] for e in events if e.get("event") == "merged"} | set(self.state.get("hand_merges_seen", []))
        for pr in prs or []:
            if pr["number"] in known:
                continue
            m = CLOSES.search(pr.get("body") or "")
            task = re.search(r"(?mi)^Task:[ \t]*(T-\d+)", pr.get("body") or "")
            events.append({"at": pr.get("mergedAt"), "pr": pr["number"], "issue": m and int(m[1]),
                           "event": "merged", "by": "hand", "sha": (pr.get("mergeCommit") or {}).get("oid"),
                           "task": task and task[1]})
            self.log(f"recorded hand merge of #{pr['number']}")

    def merge_shas(self):
        """Each merged PR's squash commit goes on the board task it closes (by issue, then by its Task:
        trailer) as merge_sha, a list once a task has more than one, for spec.py's history(). Once per merge."""
        for e in self.state.get("merge_events", []):
            key = f"mergesha:{e.get('pr')}:{e.get('sha')}"
            if e.get("event") != "merged" or not e.get("sha") or key in self.state["sent"]:
                continue
            with hb.board(write=True) as (data, events):
                mine = [x for x in data["tasks"] if x.get("project") == self.project]
                t = (next((x for x in mine if e.get("issue") and x.get("issue") == e["issue"]), None)
                     or next((x for x in mine if e.get("task") and x["id"] == hb.norm_id(e["task"])), None))
                if t is not None:
                    had = t.get("merge_sha")
                    t["merge_sha"] = e["sha"] if had is None else [*([had] if isinstance(had, str) else had), e["sha"]]
                    t["updated"] = hb.now()
                    hb.log(events, "hub-live", "merge_sha", t["id"], pr=e["pr"], sha=e["sha"])
            self.state["sent"].append(key)  # after the write: a failed one is retried next tick
            self.log(f"merge_sha {e['sha'][:12]} on {t['id']}" if t else f"merge of #{e['pr']}: no task for its sha")

    def factory_tasks(self):
        with hb.board() as (data, _):
            return [t for t in data["tasks"] if t.get("project") == self.project and t.get("kind") == "factory"]

    def agent_labels(self):
        """A factory task's builder is on the board only (hub claim sets its agent); live_merge's own-LGTM
        check and fixes() read the issue's agent:<name> label. One gh call per change, cached in state."""
        labelled, made = self.state.setdefault("labelled", {}), self.state.setdefault("labels_made", [])
        for t in self.factory_tasks():
            if not t.get("agent") or not t.get("issue"):
                continue
            n, want, had = str(t["issue"]), f"agent:{t['agent'].lower()}", labelled.get(str(t["issue"]))
            if had == want:
                continue
            if want not in made:  # once per label: gh issue edit fails on a label the repo lacks
                if self.run(["gh", "label", "create", want, "-R", self.repo, "--force"]).returncode:
                    continue
                made.append(want)
            r = self.run(["gh", "issue", "edit", n, "-R", self.repo, "--add-label", want,
                          *(["--remove-label", had] if had else [])])
            if r.returncode:
                self.log(f"label {want} on #{n} failed: {(r.stderr or '').strip()[:200]}")
                continue
            labelled[n] = want
            self.log(f"labelled #{n} {want}")

    def reverts(self):
        """live_merge reverted a merge after a red smoke and reopened its issue: reopen the board task
        too, keeping its owner and agent, and wake that agent. Once per revert."""
        for e in self.state.get("merge_events", []):
            if e.get("event") != "reverted":
                continue  # before the key: a change-merged event has no pr
            key = f"reopen:{e['pr']}:{e['at']}"
            if key in self.state["sent"]:
                continue
            note = f"reverted after smoke: {e.get('why') or 'see the reopened issue'}"
            with hb.board(write=True) as (data, events):
                # factory tasks only: in an event, gh-sync and the reopened issue tell the owner
                t = next((x for x in data["tasks"] if x.get("project") == self.project
                          and x.get("issue") == e.get("issue") and x.get("kind") == "factory"), None)
                if t is not None:
                    t["status"], t["updated"] = "open", hb.now()
                    t["notes"].append({"at": hb.now(), "by": "hub-live", "text": note})
                    hb.log(events, "hub-live", "reopened", t["id"], pr=e["pr"], why=note)
            self.state["sent"].append(key)  # after the write: a failed one is retried next tick
            if t is None:
                self.log(f"revert of #{e['pr']}: no factory task for #{e.get('issue')}")
                continue
            who = hb.actor(t) or LEAD_AGENT
            self._send(who, f"{self.project} PR #{e['pr']} was reverted after a red smoke; {t['id']} (#{e['issue']}) "
                            f"is open again for you: {note}. Fix it on the same branch and post a new DONE:.")
            self.log(f"reopened {t['id']} after the revert of #{e['pr']}")

    def deploy(self):
        """After a green promote, hackathon.json's deploy.command runs detached in a throwaway worktree
        of the promoted sha, one deploy at a time; a later pass reads how it ended. Success records
        the last https:// URL and Cloud Run revision it printed and tells Zeus for the lead in one
        release-record line (sha, revision, URL); a failure alerts Zeus once.
        Nothing here touches main: a failed deploy leaves the last good one serving."""
        spec = self.cfg.get("deploy") or {}
        if not spec.get("command"):
            return
        d, log, exit_file = self.state.get("deploy") or {}, self.dir / "deploy.log", self.dir / "deploy.exit"
        if d and "exit" not in d:
            if exit_file.is_file():
                d["exit"] = exit_file.read_text().strip()
            elif self.now() - when(d["started"]) > timedelta(minutes=35):
                d["exit"] = "lost"  # past the 30-minute cap with no exit file: hub live or the machine restarted
            else:
                return  # still running
            out, sha = (log.read_text(errors="replace") if log.is_file() else ""), d["sha"]
            if d["exit"] == "0":
                urls = re.findall(r"https://\S+", out)
                d["url"] = urls[-1].rstrip(".,;)'\"") if urls else None
                # Cloud Run names revisions <service>-<5 digits>-<3 chars>; gcloud prints "revision [name]"
                revs = re.findall(r"\b[a-z][a-z0-9-]*-\d{5}-[a-z0-9]{3}\b", out)
                d["revision"] = revs[-1] if revs else None
                self.once(f"deployed:{sha}", LEAD_AGENT,  # the release record: commit, revision, URL
                          f"{self.project} deployed {sha[:12]}: revision {d['revision'] or 'unknown'}, "
                          f"{d['url'] or 'no https:// URL in its output'}")
            else:
                tail = "\n".join(out.strip().splitlines()[-15:])
                self.once(f"deployfail:{sha}", LEAD_AGENT,
                          f"{self.project} deploy failed at {sha[:12]} (exit {d['exit']}); main is unchanged and the "
                          f"last good deploy still serves. For {spec.get('owner') or 'the deploy owner'}; log {log}:\n{tail}")
        sha = self.state.get("promoted")
        if not sha or sha == d.get("sha"):
            return
        exit_file.unlink(missing_ok=True)
        with open(log, "w") as out:
            subprocess.Popen(["sh", "-c", DETACHED_SH, "deploy", str(self.clone), sha, spec["command"], str(exit_file), "1800"],
                             stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        self.state["deploy"] = {"sha": sha, "started": self.now().isoformat(timespec="seconds")}
        self.log(f"deploy started at {sha[:12]}")

    def ci_reports(self):
        """Once, after the first merge: every check named in hackathon.json "checks" (default
        freeze-gate) reported on that PR's head. One that never reports means its workflow is not
        wired, and nothing else would say so. A failed lookup is retried next pass."""
        sha = self.state.get("first_merge")
        if not sha or self.state.get("ci_checked"):
            return
        names = self.gh_json("api", f"repos/{self.repo}/commits/{sha}/check-runs?per_page=100",
                             "--jq", "[.check_runs[].name]")
        if names is None:
            return
        self.state["ci_checked"] = sha
        missing = [c for c in self.cfg.get("checks", ["freeze-gate"]) if c not in names]
        if missing:
            self.once(f"ci-missing:{sha}", LEAD_AGENT,
                      f"{self.project}: CI never reported {', '.join(missing)} on the first merged PR's head "
                      f"{sha[:12]}: check the repo's .github/workflows, or drop the name from \"checks\" in hackathon.json.")

    def quick(self):
        """Between passes: notice DONE:s and new PRs (and review asks on the lead's) within a minute, not five."""
        if self.throttled() or hb.paused():
            return
        try:
            self.done()
            self.prs()
        except Throttled as e:
            self.throttle(e)
        except Exception as e:
            self.log(f"quick failed: {e}")
        self.save()

    def merge_now(self):
        """A merge pass on request (Hermes's --merge-now), outside the 5-minute rhythm."""
        if self.throttled() or hb.paused():
            return
        try:
            self.merge()
            self.deploy()
        except Throttled as e:
            self.throttle(e)
        except Exception as e:
            self.log(f"merge_now failed: {e}")
        self.save()

    def fast_tick(self):
        """Handle a finished gate or deploy without waiting for the next full tick."""
        self.merge_now()

    def roll_call_now(self):
        if self.throttled():
            return
        try:
            self._prs, self._branches, self._branch_work, self._commits, self._pushes = None, None, None, {}, None
            self._prs_error = self._branch_error = self._branch_work_error = False
            self.roll_call(force=True)
        except Throttled as e:
            self.throttle(e)
        except Exception as e:
            self.log(f"roll_call_now failed: {e}")
        self.save()

    def timers(self):
        now = self.now()
        freeze = self.deadlines.get("code freeze")
        if freeze and now >= freeze and not self.state.get("frozen"):
            r = self.run(["hub", "gh-sync", "--project", self.project, "--freeze"], timeout=600)
            self.state["frozen"] = r.returncode == 0
            self.log(f"freeze exit {r.returncode}")
        if self.state.get("frozen") and not self.state.get("freeze_sha"):
            self.freeze_report()
        if freeze and freeze - timedelta(minutes=45) <= now < freeze:
            merged = ", ".join(f"#{n}" for n in self.state.get("unreviewed", [])) or "none"
            self.once("release-review", REVIEWER,
                      f"{self.project} release review: code freeze in 45 min, run it now (hub:hackathon-reviewer): "
                      "the runner at main's head on 5 practice cases, per-tool error counts, the final-state mix, "
                      f"and these PRs merged without review, each reviewed: {merged}.")
        start = self.deadlines.get("build start")
        spine = self.deadlines.get("spine") or (start and start + timedelta(hours=2))
        if spine and now >= spine:
            self.once("spine", LEAD_AGENT,
                      f"{self.project}: spine deadline. Smoke must pass on one sample case and make deploy must "
                      "have a URL before the verticals build on it; if not, decide what to cut now.")
        for n, minutes in ((1, 30), (2, 60)):
            if start and now >= start + timedelta(minutes=minutes):
                self.once(f"unseen:{n}", LEAD_AGENT,
                          f"{self.project}: build start +{minutes} min: drop unseen sample set {n}.")

    def freeze_report(self):
        """Once the freeze tag is set: record its sha in live-state.json for the lead, check the
        runner is in it, and hand Zeus its `shortcut:` and `ponytail:` comments as Known limitations. A failed
        lookup is retried next pass."""
        tag = self.gh_json("api", f"repos/{self.repo}/git/ref/tags/freeze")
        if not isinstance(tag, dict):
            return
        sha = tag["object"]["sha"]
        if self.run(["git", "-C", self.clone, "fetch", "-q", "origin", "main"], timeout=120).returncode:
            self.log("freeze report: cannot fetch main; retrying next pass")
            return
        self.state["freeze_sha"] = sha
        runner = self.cfg.get("runner")
        missing = bool(runner) and self.run(["git", "-C", self.clone, "cat-file", "-e", f"{sha}:{runner}"]).returncode
        # say the runner check passed too, so a silent message is never mistaken for a pass (rehearsal 2026-10-18)
        self.once(f"freeze-sha:{sha}", LEAD_AGENT,
                  f"{self.project}: code freeze is {sha} on main. Tell the lead: the final runs and the demo "
                  "come from this commit." + (f" The runner {runner} is in it." if runner and not missing else ""))
        if missing:
            self.once(f"no-runner:{sha}", LEAD_AGENT,
                      f"{self.project}: the runner {runner} is not in the frozen commit {sha[:12]}, so the "
                      "answers cannot come from the freeze. Decide now.")
        hits = self.run(["git", "-C", self.clone, "grep", "-n", "-E", LIMITS, sha]).stdout
        self.once(f"ponytail:{sha}", LEAD_AGENT,
                  f"{self.project} Known limitations at the freeze ({sha[:12]}), from its shortcut: and ponytail: comments:\n"
                  + (hits.replace(f"{sha}:", "").strip() or "none marked"))

    def branches(self):
        if self._branches is None:
            r = self.run(["gh", "api", f"repos/{self.repo}/branches?per_page=100", "--paginate",
                          "--jq", ".[].name"])
            self._branches = r.stdout.splitlines() if r.returncode == 0 else []
            if not self._branches:
                self._branch_error = True
                self.log(f"branch list failed: {(r.stderr or '').strip()[:200]}")
                hour = self.now().strftime("%Y-%m-%dT%H")
                self.once(f"branchlist:{hour}", LEAD_AGENT,
                          f"{self.project}: branch list failed; nudges and roll call are incomplete.")
        return self._branches

    def branch_work(self):
        if self._branch_work is None:
            self._branch_work = []
            merged_heads = None
            for name in self.branches():
                if name in ("main", "integration"):
                    continue
                compare = self.gh_json("api", f"repos/{self.repo}/compare/integration...{quote(name, safe='')}")
                if not isinstance(compare, dict) or not isinstance(compare.get("ahead_by"), int):
                    self._branch_work_error = True
                    self.once(f"branchwork:{self.now().strftime('%Y-%m-%dT%H')}", LEAD_AGENT,
                              f"{self.project}: branch work check failed; nudges and roll call are incomplete.")
                    continue
                if not compare["ahead_by"]:
                    continue
                last = self._commits.get(name)
                if last is None:
                    last = self.gh_json("api", f"repos/{self.repo}/commits/{quote(name, safe='')}",
                                        "--jq", "{sha: .sha, at: .commit.committer.date, author: .author.login}")
                    self._commits[name] = last
                if isinstance(last, dict) and last.get("sha"):
                    if merged_heads is None:
                        merged = self.gh_json("pr", "list", "-R", self.repo, "--state", "merged",
                                              "--limit", "200", "--json", "headRefName,headRefOid")
                        if not isinstance(merged, list):
                            self._branch_work_error = True
                            self.once(f"branchwork:{self.now().strftime('%Y-%m-%dT%H')}", LEAD_AGENT,
                                      f"{self.project}: branch work check failed; nudges and roll call are incomplete.")
                            self._branch_work = []  # unknown merge state must not trigger a false nudge
                            return self._branch_work
                        # shortcut: only the newest 200 merged PRs are checked; widen this for long-lived repos.
                        merged_heads = {(p.get("headRefName"), p.get("headRefOid")) for p in merged}
                    if (name, last["sha"]) in merged_heads:
                        continue  # squash merges leave compare.ahead_by positive for the old branch
                    self._branch_work.append((name, last))
        return self._branch_work

    def pushes(self):
        if self._pushes is None:
            events = self.gh_json("api", f"repos/{self.repo}/events?per_page=100")
            self._pushes = {}
            for event in events if isinstance(events, list) else []:
                if event.get("type") == "PushEvent":
                    branch = (event.get("payload") or {}).get("ref", "").removeprefix("refs/heads/")
                    self._pushes.setdefault(branch, event.get("created_at"))
        return self._pushes

    def roll_call(self, force=False):
        now = self.now()
        if not force and now - when(self.state.get("rollcall_at", now.isoformat())) < timedelta(minutes=30):
            return
        if getattr(self, "_prs", None) is None:
            self.prs()
        issues = self.gh_json("issue", "list", "-R", self.repo, "--state", "all", "--limit", "200",
                              "--json", "number,state,assignees,comments")
        if not isinstance(issues, list):
            return  # retry at the next tick; an empty issue list would falsely look like no work
        by_number = {i["number"]: i for i in issues}
        rows = {p["github"].lower(): {"name": p["name"], "issues": [], "branches": [],
                                      "prs": [], "done": None, "unreviewed": []}
                for p in self.cfg["roster"] if p.get("github")}
        untied = []

        def owners(issue):
            return [a["login"].lower() for a in (issue or {}).get("assignees") or []
                    if a.get("login", "").lower() in rows]

        def issue_number(pr):
            m = re.match(r"(\d+)-", pr.get("headRefName") or "") or re.search(
                r"\b(?:closes|fixes|resolves)\s+#(\d+)\b", pr.get("body") or "", re.I)
            return int(m[1]) if m else None

        for issue in issues:
            if issue.get("state") == "OPEN":
                for login in owners(issue):
                    rows[login]["issues"].append(f"#{issue['number']}")
            for comment in issue.get("comments") or []:
                login = (comment.get("author") or {}).get("login", "").lower()
                if login in rows and (comment.get("body") or "").startswith("DONE:"):
                    latest = rows[login]["done"]
                    stamp = comment.get("createdAt") or ""
                    if latest is None or stamp > latest[0]:
                        rows[login]["done"] = (stamp, issue["number"])

        work = self.branch_work()
        pushes = self.pushes() if work else {}
        for name, last in work:
            n = int(m[1]) if (m := re.match(r"(\d+)-", name)) else None
            commit_author = last.get("author") or ""
            if isinstance(commit_author, dict):
                commit_author = commit_author.get("login") or ""
            people = ([commit_author.lower()] if commit_author.lower() in rows else owners(by_number.get(n)))
            stamp = pushes.get(name) or last.get("at") or ""
            clock = when(stamp).strftime("%H:%M") if stamp else "?"
            item = f"{name}{'' if n in by_number else ' (no issue)'} ({'push' if name in pushes else 'commit'} {clock})"
            if people:
                for login in people:
                    rows[login]["branches"].append(item)
            else:
                untied.append(item)

        for pr in self._prs or []:
            n = issue_number(pr)
            people = owners(by_number.get(n)) or [(pr.get("author") or {}).get("login", "").lower()]
            for login in people:
                if login in rows:
                    rows[login]["prs"].append(f"#{pr['number']}")
        new = [n for n in self.state.get("unreviewed", []) if f"digest:{n}" not in self.state["sent"]]
        for n in self.state.get("unreviewed", []):
            pr = self.gh_json("pr", "view", str(n), "-R", self.repo, "--json", "headRefName,body,author")
            if not isinstance(pr, dict):
                untied.append(f"merged without review #{n}")
                continue
            people = owners(by_number.get(issue_number(pr))) or [(pr.get("author") or {}).get("login", "").lower()]
            if not any(login in rows for login in people):
                untied.append(f"merged without review #{n}")
            for login in people:
                if login in rows:
                    rows[login]["unreviewed"].append(f"#{n}")

        lines = [f"{self.project} roll call {now.strftime('%Y-%m-%d %H:%M UTC')}"]
        for p in self.cfg["roster"]:
            login = p.get("github", "").lower()
            if login not in rows:
                continue
            row = rows[login]
            last_done = row["done"]
            done_text = f"#{last_done[1]} {when(last_done[0]).strftime('%H:%M')}" if last_done else "none"
            lines.append(f"{row['name']} (@{login}): issues {', '.join(row['issues']) or 'none'}; "
                         f"branches {', '.join(row['branches']) or 'none'}; PRs {', '.join(row['prs']) or 'none'}; "
                         f"last DONE {done_text}; merged without review {', '.join(row['unreviewed']) or 'none'}")
        if untied:
            lines.append(f"Unassigned: {', '.join(untied)}")
        if getattr(self, "_prs_error", False):
            lines.append("PR list unavailable; PR rows may be incomplete")
        if self._branch_error:
            lines.append("branch list unavailable; branch rows may be incomplete")
        if self._branch_work_error:
            lines.append("branch work check unavailable; ahead rows may be incomplete")
        message = "\n".join(lines)
        # The clock changes every check; compare only the work details.
        body = "\n".join(lines[1:])
        has_work = (any(any(row[k] for k in ("issues", "branches", "prs", "done", "unreviewed"))
                        for row in rows.values()) or bool(untied) or
                    self._prs_error or self._branch_error or self._branch_work_error)
        if not self.cfg.get("factory") or (has_work and body != self.state.get("rollcall_last")):
            self._send(LEAD_AGENT, message)
            self.log(f"sent {LEAD_AGENT}: {message}")
            if self.cfg.get("factory"):
                self.state["rollcall_last"] = body
        self.state["rollcall_at"] = now.isoformat()
        if new:
            self.state["sent"] += [f"digest:{n}" for n in new]
            digest = f"{self.project} merged without review: {', '.join(f'#{n}' for n in new)}. Review each with gh pr diff <n>.\n{message}"
            self._send(REVIEWER, digest)
            self.log(f"sent {REVIEWER}: {digest}")

    def nudges(self):
        now = self.now()
        nudged = self.state.setdefault("nudged", {})
        for q in self.gh_json("issue", "list", "-R", self.repo, "--label", "question", "--state", "open",
                              "--limit", "200", "--json", "number,title,body,assignees,createdAt,comments") or []:
            n = q["number"]
            owner = (q["assignees"][0]["login"] if q["assignees"]
                     else next(iter(re.findall(r"@([A-Za-z0-9-]+)", q.get("body") or "")), None))
            if not owner:
                continue
            if owner.lower() == self.lead.lower():
                self.once(f"q:{n}", LEAD_AGENT, f"{self.project} question #{n} for the lead: {q['title']}")
                continue
            comments = q.get("comments") or []
            if any(c["author"]["login"].lower() == owner.lower() for c in comments):
                continue  # answered: waiting for the asker, not the owner
            reminder = next((c for c in comments if "this is waiting on you" in c["body"]), None)
            if reminder is None and now - when(q["createdAt"]) >= timedelta(minutes=20):
                body = f"@{owner} this is waiting on you"
                self.run(["gh", "issue", "comment", n, "-R", self.repo, "--body", body])
                self.log(f"nudged #{n} @{owner}")
            elif reminder and now - when(reminder["createdAt"]) >= timedelta(minutes=20):
                self.once(f"qlate:{n}", LEAD_AGENT,
                          f"{self.project} question #{n} to @{owner} unanswered 20 min after the reminder: {q['title']}")
        work = self.branch_work()
        pushes = self.pushes() if work else {}
        for name, last in work:
            if self._prs_error:
                break  # unknown PR state must not trigger a false nudge
            pr = next((p for p in self._prs or [] if p.get("headRefName") == name), None)
            if pr and not pr.get("isDraft"):
                nudged.pop(name, None)
                continue  # review and smoke gates already track this PR
            stamp = pushes.get(name) or last.get("at")
            if not stamp:
                continue
            seen = nudged.get(name)
            if isinstance(seen, str):  # live-state.json from before branch tracking
                seen = {"sha": seen, "push_at": stamp, "at": now.isoformat()}
            if seen and (seen["sha"] != last["sha"] or seen.get("push_at") != stamp):
                seen = None
            if now - when(stamp) < timedelta(minutes=45):
                nudged.pop(name, None)
                continue
            if seen:
                nudged[name] = seen
                if now - when(seen["at"]) >= timedelta(minutes=45) and not seen.get("alerted"):
                    self.once(f"branchlate:{name}:{last['sha']}:{stamp}", LEAD_AGENT,
                              f"{self.project}: {name} is still silent 45 min after the branch nudge; check with its owner.")
                    seen["alerted"] = True
                continue
            body = f"No push to `{name}` for 45 min. What's blocking it?"
            m = re.match(r"(\d+)-", name)
            if m:
                result = self.run(["gh", "issue", "comment", m[1], "-R", self.repo, "--body", body])
            elif pr:
                result = self.run(["gh", "pr", "comment", pr["number"], "-R", self.repo, "--body", body])
            else:
                result = self.run(["gh", "api", "-X", "POST",
                                   f"repos/{self.repo}/commits/{last['sha']}/comments", "-f", f"body={body}"])
            if result.returncode:
                self.log(f"branch nudge failed for {name}: {(result.stderr or '').strip()[:200]}")
                continue
            nudged[name] = {"sha": last["sha"], "push_at": stamp, "at": now.isoformat()}
            self.log(f"idle branch {name}")
        pending = self.gh_json("api", f"repos/{self.repo}/invitations", "--jq", "[.[].invitee.login]") or []
        if pending:
            hour = now.strftime("%Y-%m-%dT%H")
            self.once(f"invites:{hour}", LEAD_AGENT,
                      f"{self.project}: not accepted the invite yet: {', '.join(pending)}")


def cmd_live(a):
    project = a.project or os.environ.get("HUB_PROJECT")
    if not project:
        sys.exit("live: --project is required")
    live = Live(project)
    now_file, hold_file, call_file, tick_file = (live.dir / ".merge-now", live.dir / ".merge-hold",
                                                live.dir / ".roll-call-now", live.dir / ".tick-now")
    if getattr(a, "roll_call", False):
        call_file.touch()
        return print("roll call requested")
    if a.merge_now:  # Hermes, right after an approval: the running hub live merges within ~10 s
        now_file.touch()
        return print("merge requested")
    if a.hold_merges:
        hold_file.write_text(live.now().isoformat(timespec="seconds") + "\n")
        return print("merges held (hub live --resume-merges to go on)")
    if a.resume_merges:
        hold_file.unlink(missing_ok=True)
        now_file.touch()
        return print("merges resumed")
    lock = open(live.dir / ".live.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit("hub live already running")
    live.interval = a.interval
    while live.tick() and not a.once:
        for i in range(1, max(1, live.state.get("backoff", a.interval) // 10) + 1):  # between passes: merge requests ~10 s, new PRs ~60 s
            time.sleep(10)
            if i % 6 == 0:
                live.quick()
            if now_file.is_file():
                now_file.unlink(missing_ok=True)
                live.merge_now()
            if tick_file.is_file():
                tick_file.unlink(missing_ok=True)
                live.fast_tick()
            if call_file.is_file():
                call_file.unlink(missing_ok=True)
                live.roll_call_now()


def register(sub):
    p = sub.add_parser("live", help="the mechanical Live loop for a hackathon (sync, merges, smoke, timers, nudges)")
    p.add_argument("--project", help="the hackathon's project tag (default: $HUB_PROJECT)")
    p.add_argument("--once", action="store_true", help="run one tick and exit")
    p.add_argument("--interval", type=int, default=300, help="seconds between ticks (default 300)")
    p.add_argument("--merge-now", action="store_true", help="ask the running hub live to merge now (the reviewer, after approving)")
    p.add_argument("--roll-call", action="store_true", help="ask the running hub live for an immediate roll call")
    p.add_argument("--hold-merges", action="store_true", help="stop merging until --resume-merges (Zeus hears after 15 min)")
    p.add_argument("--resume-merges", action="store_true", help="lift a hold and merge now")
    p.set_defaults(fn=cmd_live)
