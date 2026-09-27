# /// script
# requires-python = ">=3.11"
# dependencies = ["diagrams"]
# ///
"""C4 diagrams for the hackathon kit, drawn from the real code.

    uv run c4.py            # writes context.png ... code.png beside this file
    uv run c4.py context    # just one level

The kit is `hub gh-sync` (gh_sync.py), the `hackathon` skill, and the public template
repo (your copy of hackathon_teamwork) that every event repo is made from.
"""

import shutil
import sys
from functools import partial
from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.c4 import Container, Database, Person, Relationship, System, SystemBoundary
from diagrams.programming.language import Python

Container, Database, Person, System = (partial(f, width="3.3") for f in (Container, Database, Person, System))

SYSTEM = "Hackathon kit"
OUT = Path(__file__).parent
GRAPH = {"splines": "spline", "nodesep": "0.8", "ranksep": "1.1"}


def draw(level, title):
    return Diagram(f"{SYSTEM} - {title}", filename=str(OUT / f"{level}"), outformat="png",
                   show=False, direction="TB", graph_attr=GRAPH)


def context():
    with draw("context", "System Context"):
        lead = Person("Lead", "Plans, grills, assigns, reviews")
        mate = Person("Teammate", "Picks up issues with any AI tool")
        kit = System(SYSTEM, "Turns a pasted brief into assigned GitHub issues and a rulebook every agent follows")
        gh = System("GitHub", "Event repo from the template: issues, milestones, PRs, protection", external=True)
        agents = System("Teammate's AI agent", "Claude Code, Codex, Cursor, Copilot...", external=True)
        lead >> Relationship("pastes brief, approves") >> kit
        kit >> Relationship("gh CLI: repo, issues, milestones") >> gh
        mate >> Relationship("drives") >> agents
        agents >> Relationship("reads AGENTS.md, gh issue develop, PRs") >> gh


def container():
    with draw("container", "Containers"):
        lead = Person("Lead", "")
        agents = System("Teammate's AI agent", "", external=True)
        gh = System("GitHub Issues + PRs", "", external=True)
        with SystemBoundary("Lead's PC: ~/hub (never shipped)"):
            skill = Container("hackathon skill", "claude/skills/hackathon", "Deadlines first, roster, planning, assignment grill, publish, live loop")
            cli = Container("hub gh-sync", "gh_sync.py, stdlib", "--init provisions; sync pulls then pushes; refuses foreign repos; shells out to gh")
            board = Database("Hub board", "board.json", "Tasks with issue, issue_hash, issue_assignee")
            cfg = Database("hackathon.json", "projects/<p>/", "repo, deadlines, roster, seen change-requests")
            inbox = Database("Lead agent inbox", "inbox/<lead>.jsonl", "change-request notices")
        with SystemBoundary("Event repo (from template hackathon_teamwork)"):
            rules = Container("AGENTS.md + CLAUDE.md", "Markdown", "Fixed rulebook: clock, plan first, branch per issue, stay in lane")
            hack = Container("HACKATHON.md", "Markdown", "Brief, deadlines, rules, judging, team")
            ghdir = Container(".github/", "forms + templates", "Task and change-request forms, PR Impact, CODEOWNERS")
        lead >> Relationship("runs") >> skill
        skill >> Relationship("writes") >> cfg
        skill >> Relationship("hub new / assign") >> board
        skill >> Relationship("fills") >> hack
        skill >> Relationship("runs") >> cli
        cli >> Relationship("reads/writes") >> cfg
        cli >> Relationship("snapshot, then one short write") >> board
        cli >> Relationship("deliver") >> inbox
        cli >> Relationship("gh issue create/edit/list") >> gh
        agents >> Relationship("reads") >> rules
        rules >> Relationship("points to") >> hack
        agents >> Relationship("issue forms, PRs 'Closes #N'") >> ghdir
        ghdir >> Relationship("shape") >> gh


def component():
    with draw("component", "Components of hub gh-sync"):
        ghcli = System("gh CLI", "", external=True)
        board = Database("Hub board", "board.json", "")
        cfg = Database("hackathon.json", "", "")
        inbox = Database("Lead agent inbox", "", "")
        with SystemBoundary("gh_sync.py"):
            guard = Container("check_config / repo_state", "functions", "Config checked first; repo named after the project and made from the template; one run at a time")
            wrap = Container("Gh", "class", "Every gh call; --dry-run prints writes; bodies via --body-file; one-line GhError")
            init = Container("init", "function", "Provision only: repo or clone, identity, invites, labels, milestone dates, protection")
            pull = Container("pull", "function", "Closed -> done; reopened -> open; pool pickup -> owner; not planned / missing -> warning; change-request -> inbox once")
            push = Container("push", "function", "New issues; brief, title, deadline, owner, labels follow the hub; GitHub edits kept")
            apply = Container("snapshot / apply", "functions", "Read the board, then record each change the moment GitHub has it; no gh call under the lock")
        guard >> Relationship("reads") >> cfg
        guard >> Relationship("gh repo view") >> wrap
        for c in (init, pull, push):
            c >> Relationship("calls") >> wrap
        wrap >> Relationship("subprocess, 60 s") >> ghcli
        pull >> Relationship("changes") >> apply
        push >> Relationship("each change") >> apply
        apply >> Relationship("board(write=True)") >> board
        pull >> Relationship("hb.deliver") >> inbox


def code():
    global GRAPH
    GRAPH = {**GRAPH, "nodesep": "1.2", "ranksep": "1.4"}  # icon labels are wide
    with draw("code", "Code"):
        with Cluster("gh_sync.py"):
            cmd = Python("cmd_gh_sync(a)\n——\nconfig, lock, repo_state;\n--init: provision only;\nelse pull, then push")
            check = Python("check_config(cfg, project)\n——\n-> [problem lines]")
            state = Python("repo_state(gh, repo)\n——\n-> 'missing' | 'ours'\nelse exit")
            init = Python("init(cfg, gh, repo,\nfailures, exists)")
            pull = Python("pull(tasks, cfg, gh, repo)\n——\n-> (changes, issues)")
            push = Python("push(tasks, cfg, gh, repo,\nfailures, assignable, issues)")
            target = Python("target(owner, cfg)\n——\n-> (handle | None, labels)\ncanon() names, Pool")
            gh = Python("Gh(dry)\n——\n__call__(*args, write, stdin,\ncwd, body) -> str\njson(*args) -> object")
            apply = Python("apply(changes, dry)\n——\none short board(write=True)")
        with Cluster("task fields added"):
            fields = Python("issue, issue_hash,\nissue_assignee, issue_title,\nissue_milestone,\nnotice_pending, closed_by_gh")
        cmd >> Edge(label="1") >> check
        cmd >> Edge(label="2") >> state
        cmd >> Edge(label="--init") >> init
        cmd >> Edge(label="3") >> pull
        cmd >> Edge(label="4") >> push
        push >> Edge(label="uses") >> target
        for f in (state, init, pull, push):
            f >> Edge(label="gh") >> gh
        pull >> Edge(label="records") >> apply
        push >> Edge(label="records") >> apply
        apply >> Edge(label="writes") >> fields


LEVELS = {n: globals()[n] for n in ("context", "container", "component", "code")}

if __name__ == "__main__":
    if not shutil.which("dot"):
        sys.exit("c4: Graphviz is not installed (no `dot` on PATH). Run: sudo apt install -y graphviz")
    for name in sys.argv[1:] or LEVELS:
        LEVELS[name]()
        print(OUT / f"{name}.png")
