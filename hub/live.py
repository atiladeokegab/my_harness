"""`hub live --project <p>`: the mechanical half of a hackathon's Live loop.

Every tick (5 minutes) it checks the clock, syncs, hands each new item to whoever judges it
(PRs and sub-issue changes to Hermes; DRAFTs, change-requests, the lead's questions and errors to
Zeus), merges at most one approved PR through live_merge, runs the freeze and the reminders, and
nudges. It never judges anything itself. The hackathon skill's §7 says who handles what.
"""

import fcntl
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import board as hb

REVIEWER = os.environ.get("HUB_REVIEWER") or "Hermes"
LEAD_AGENT = os.environ.get("HUB_LEAD") or "Zeus"


def run(args, cwd=None, timeout=60):
    """Run a command; a non-zero exit is returned, never raised."""
    return subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def send(agent, text):
    # Sign as hub-live, not "Unknown" (dry run #4), unless the caller set an identity.
    subprocess.run(["hubmsg", agent, text], capture_output=True, text=True, timeout=30,
                   env={**os.environ, "HUB_AGENT": os.environ.get("HUB_AGENT") or "hub-live"})


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
        self.run, self._send, self.now = run, send, now or (lambda: datetime.now(timezone.utc))
        self.state_file = self.dir / "live-state.json"
        self.state = json.loads(self.state_file.read_text()) if self.state_file.is_file() else {}
        self.state.setdefault("sent", [])

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
        # The full gh-sync takes minutes and blocks the quick PR checks, so it runs every other
        # pass; the inbox, PR and merge steps run on every pass (dry run #4, F11).
        self.state["ticks"] = self.state.get("ticks", 0) + 1
        steps = (self.sync,) if self.state["ticks"] % 2 == 1 else ()
        for step in steps + (self.inbox, self.prs, self.issues, self.merge, self.timers, self.nudges):
            try:
                step()
            except Exception as e:  # one broken step never stops the loop
                self.log(f"{step.__name__} failed: {e}")
        self.save()
        return True

    def sync(self):
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

    def prs(self):
        for pr in self.gh_json("pr", "list", "-R", self.repo, "--state", "open", "--json",
                               "number,title,headRefOid,isDraft,author,body,reviews,comments,commits") or []:
            if pr["isDraft"]:
                continue
            n, sha = pr["number"], pr["headRefOid"]
            self.once(f"pr:{n}:{sha}", REVIEWER, f"{self.project} PR #{n} ready for review at {sha[:12]}: {pr['title']}")
            if (pr.get("author") or {}).get("login", "").lower() == self.lead.lower():
                self.fixes(pr)

    def fixes(self, pr):
        """A PR from the lead's account can only get comments, not a changes-requested review, so any
        note from the lead's account after the last push that isn't `LGTM <head>` asks for a fix.
        It goes to the agent that built it (the issue's agent:<name> label), which has stopped watching."""
        n, sha = pr["number"], pr["headRefOid"]
        pushed = max((c.get("committedDate") or "" for c in pr.get("commits") or []), default="")
        notes = [(r.get("submittedAt") or "", r.get("body") or "", r.get("author") or {}) for r in pr.get("reviews") or []]
        notes += [(c.get("createdAt") or "", c.get("body") or "", c.get("author") or {}) for c in pr.get("comments") or []]
        asks = [body for at, body, who in notes
                if at > pushed and who.get("login", "").lower() == self.lead.lower()
                and body.strip() and not body.strip().startswith(("LGTM ", "FYI:"))]
        if not asks:
            return
        agent = LEAD_AGENT
        m = re.search(r"\b(?:closes|fixes|resolves)\s+#(\d+)", pr.get("body") or "", re.I)
        issue = m and self.gh_json("issue", "view", m[1], "-R", self.repo, "--json", "labels")
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
                  " (fix it on the same branch; a Zeus sub-agent: resume it by name)")

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
                              f"{self.project}: merges held by Hermes since {since} (15 min+). "
                              f"Resume: hub live --project {self.project} --resume-merges")
            except ValueError:
                pass
            return
        try:
            import live_merge
        except ImportError:
            self.log("live_merge missing: no merges this tick")
            return
        live_merge.merge_tick(self.repo, self.clone, self.cfg["smoke"], self.lead, self.state,
                              self.run, self._send)

    def quick(self):
        """Between passes: notice new PRs (and review asks on the lead's) within a minute, not five."""
        try:
            self.prs()
        except Exception as e:
            self.log(f"quick failed: {e}")
        self.save()

    def merge_now(self):
        """A merge pass on request (Hermes's --merge-now), outside the 5-minute rhythm."""
        try:
            self.merge()
        except Exception as e:
            self.log(f"merge_now failed: {e}")
        self.save()

    def timers(self):
        now = self.now()
        freeze = self.deadlines.get("code freeze")
        if freeze and now >= freeze and not self.state.get("frozen"):
            r = self.run(["hub", "gh-sync", "--project", self.project, "--freeze"], timeout=600)
            self.state["frozen"] = r.returncode == 0
            self.log(f"freeze exit {r.returncode}")
        start = self.deadlines.get("build start")
        for n, minutes in ((1, 30), (2, 60)):
            if start and now >= start + timedelta(minutes=minutes):
                self.once(f"unseen:{n}", LEAD_AGENT,
                          f"{self.project}: build start +{minutes} min: drop unseen sample set {n}.")

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
        for name in (self.gh_json("api", f"repos/{self.repo}/branches", "--paginate", "--jq", "[.[].name]") or []):
            m = re.match(r"(\d+)-", name)
            if not m:
                continue
            last = self.gh_json("api", f"repos/{self.repo}/commits/{name}",
                                "--jq", "{sha: .sha, at: .commit.committer.date}")
            if not last or now - when(last["at"]) < timedelta(hours=1) or nudged.get(name) == last["sha"]:
                continue
            issue = self.gh_json("issue", "view", m[1], "-R", self.repo, "--json", "state")
            if issue and issue["state"] == "OPEN":
                self.run(["gh", "issue", "comment", m[1], "-R", self.repo, "--body",
                          f"No push to `{name}` for an hour. What's blocking it?"])
                nudged[name] = last["sha"]
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
    now_file, hold_file = live.dir / ".merge-now", live.dir / ".merge-hold"
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
    while live.tick() and not a.once:
        for i in range(1, max(1, a.interval // 10) + 1):  # between passes: merge requests ~10 s, new PRs ~60 s
            time.sleep(10)
            if i % 6 == 0:
                live.quick()
            if now_file.is_file():
                now_file.unlink(missing_ok=True)
                live.merge_now()


def register(sub):
    p = sub.add_parser("live", help="the mechanical Live loop for a hackathon (sync, merges, smoke, timers, nudges)")
    p.add_argument("--project", help="the hackathon's project tag (default: $HUB_PROJECT)")
    p.add_argument("--once", action="store_true", help="run one tick and exit")
    p.add_argument("--interval", type=int, default=300, help="seconds between ticks (default 300)")
    p.add_argument("--merge-now", action="store_true", help="ask the running hub live to merge now (the reviewer, after approving)")
    p.add_argument("--hold-merges", action="store_true", help="stop merging until --resume-merges (Zeus hears after 15 min)")
    p.add_argument("--resume-merges", action="store_true", help="lift a hold and merge now")
    p.set_defaults(fn=cmd_live)
