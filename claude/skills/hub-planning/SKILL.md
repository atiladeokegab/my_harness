---
name: hub-planning
description: >
  The hub's layer on top of superpowers planning. Use with superpowers:brainstorming and
  superpowers:writing-plans whenever the work will be done by hub agents: it says where
  the spec and plan go ($HUB_DIR/projects/<repo>/, never the repo) and turns an approved plan
  into hub board tasks with owners, instead of executing it in one session. Also use for
  a new project, "put this on the board", "who should build this", or waking workers.
  Not for a one-line fix, or for work one session will finish alone.
---

# Planning on this hub

**superpowers does the thinking; this skill does the hub.** Design with
`superpowers:brainstorming` (its questions, approaches and HARD-GATE apply unchanged),
plan with `superpowers:writing-plans`. This skill changes three things, and adds three steps.

## 0. Grill the design before it is approved (architectural work only)

For a new project, a new subsystem, or anything that will become several tasks: once
brainstorming has presented its design and **before** the spec is written, grill that
design (a `grilling` skill if you have one installed), until every decision in the tree is
settled. Keep its logic (look facts up yourself, only ask what is unblocked) but NOT its
batched-round format: the user wants **one question per prompt**, through
AskUserQuestion where the tool exists, recommended option first and marked
"(Recommended)", with room to type their own answer. The design approval is given
at the end of grilling: "grilled and agreed", not "looks fine".

This exists because the most common failure is an agent making a wrong design decision
midway through building. The cheapest place to catch it is before any spec exists.

Bounded work skips this and keeps the single short design and one yes. The user can ask for
a grilling on anything, any time.

## 0b. Draw it before it is approved (architectural work only)

After grilling, draw the planned system so the user approves a picture, not only prose.
Copy `c4_template.py` from this skill's directory to `$HUB_DIR/projects/<repo>/c4.py`,
replace the example nodes with the planned system, and run `uv run c4.py context
container component`. Show the user the three PNGs next to the spec. Skip level 4 while
planning: classes that do not exist yet are a guess. If it exits saying Graphviz is
missing, ask the user to run `sudo apt install -y graphviz`; do not switch tools.

**The board always ends with an "Architecture diagrams" task**, depending on every
build task: move `c4.py` to `docs/architecture/c4.py` in the repo, redraw it from the
real code with level 4 included, render all four PNGs beside it, and add an
Architecture section to `README.md` that shows them. That is product documentation a
teammate opens, so it belongs in the repo; the planning copy stays in `$HUB_DIR/projects`.
The same closing task also:
- refreshes the README stub (below) and writes its `Known limitations` from a grep of
  `shortcut:`/`ponytail:` comments (live.py's LIMITS pattern) plus one run against the real target, when the board deploys or ships an artefact. Anything
  not tried is "not tested", and a failure is listed as a failure.
- moves the rules agents broke twice this cycle into the repo's AGENTS.md (for a shared repo,
  into `$HUB_DIR/projects/<repo>/`, per `clean-repo`), with the incident in the commit body.

**A README stub comes with the first working code.** The first task that makes the repo run
also writes a README stub: what it is, how to run it, and its status. Nobody opening the repo
mid-cycle should find nothing.

## Approvals happen in a window, not the terminal

Every approval (design with its diagrams, spec, board) goes on a **lean** review page:
the pictures or three to five short lines, a comment box pre-filled with `agreed` (so the saved
review records the decision even when the user just clicks), Approve / Request changes. The
user found a text-heavy page worse. Write it as plain HTML in `$HUB_DIR/projects/<repo>/`
with elements `#approve`, `#changes`, `#note` and `#status` (no script of your own), then
run, **in the background**:

```bash
hub review $HUB_DIR/projects/<repo>/<page>.html --name approval-1
```

It opens a browser window, and exits when the user clicks. It prints
the decision as one JSON line and saves it to `reviews/approval-1.json` beside the page.
Its exit is what wakes you; do not ask the user to type "decided". Images next to the
page (the C4 PNGs) can be referenced by bare filename. Act only on `"decision":
"approve"`; on `"changes"`, the note says what to fix.

## 1. Where the files go

Upstream defaults to `docs/superpowers/specs/` and `docs/superpowers/plans/` in the
project repo. That default is what once left 93 tracked plan files in a product repo that no
code ever read. Both skills allow a user preference to override it, and this is it:

- spec → `$HUB_DIR/projects/<repo>/YYYY-MM-DD-<topic>-design.md`
- plan → `$HUB_DIR/projects/<repo>/YYYY-MM-DD-<feature>-plan.md`

Commit both in `$HUB_DIR` (keep it a git repo). Never in the project repo. See `clean-repo`.

## 1b. Seed the spec at approval 2

The approved spec's acceptance criteria become the project's PRD, the root every later
change rewinds from (HUB.md, "Spec Tree"). Write them as `R-<n>` requirements, each line
one testable sentence numbered `A-<n>.<m>` and naming one test path
(`tests/acceptance/test_A_3_2.py`), then:

```bash
hub spec init <repo> --from seed.json     # v1 and its lock; commit spec/ in $HUB_DIR
```

A line nobody could write a test for goes back to the lead, never into the seed. From
here plain `hub new` refuses this project; board tasks go in with `--from-spec
--generated-from v1 --req A-3.2@1` and `--verify 'make check && hub spec check --project
<repo> --repo .'`. **The check-writer task comes first on the board** (a Zeus sub-agent,
never a builder: it writes every `tests/acceptance/` file until `hub spec check` is
green), and every build task `--dep`s it. `hub spec converge` reopens drift weekly.

## 2. The plan becomes the board

When writing-plans asks how to execute, the answer for hub work is: **neither of its
options.** `subagent-driven-development` and `executing-plans` run the plan inside one
session and bypass the board. Instead:

**Map the files**, then **assign one owner per file for the whole cycle** and write it
into every task. Two agents editing one file lose work silently.

**A new repo starts with a spine.** For a repo with no code yet, the first task is the
spine: one agent in one session builds the thinnest version that runs end to end, with one
test, and every other task `--dep`s it. Parallel tasks then build on running code, not on a
spec. Existing repos keep the normal split.

**One hub task per reviewable unit.** Split where a reviewer could reject one and approve
its neighbour; fold setup, config and docs into the task that needs them.

**Write each task for someone who never saw this conversation.** `--detail` carries the
context, the files it owns, the approach (paste the plan's steps for that task, not a
link to them), acceptance criteria and how to verify. A task that needs a follow-up
question was underwritten.

```bash
hub new "<title>" --owner <Agent> --project <repo> --detail '<the whole brief>'
```

**Always pass `--project <repo>`.** Without it a task is tagged with the project this
session *started* in, so a new repo's board lands in another project's queue. If that
happens, recreate the task with `--project`.

For a repo with other committers, paste the "In a repo you do not own" rules from the
`clean-repo` skill into every `--detail`, **except for a hackathon event repo**: its AGENTS.md is the rulebook,
and the house rules ("do not push", "no edits to existing files") contradict it. `--dep` only what genuinely blocks.

**Present the board to the user and get a yes before waking anyone.** That is the third
approval, after the design and the spec.

## 3. Who does it

`apollo`, `hermes`, `athena` (Claude) and `prometheus` (Codex). Prometheus has the same
skills (hub, ponytail and superpowers are installed on Codex too) but no slash commands,
`SendMessage` or `ListAgents`: reach it only with `hubmsg`. A Codex plugin's hooks need
trusting once per new thread via `/hooks`.

## A new project

After the design is approved: create the repo, set its commit identity, and put the
`clean-repo` ignore rules in `.git/info/exclude`. Then the spec, the plan, the board.

## Closing a cycle

Before anything is pushed, list what the push would add (`git diff --stat @{u}..HEAD`) and
check it against `clean-repo`. A harness file in that list is a blocker, not a note.
