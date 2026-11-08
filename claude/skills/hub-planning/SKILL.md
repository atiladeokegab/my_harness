---
name: hub-planning
description: >
  Use when substantial work needs planning and assignment to hub agents: it says where
  the spec and plan go ($HUB_DIR/projects/<repo>/, never the repo) and turns an approved plan
  into hub board tasks with owners, instead of executing it in one session. Also use for
  a new project, "put this on the board", "who should build this", or waking workers.
  Not for a one-line fix, or for work one session will finish alone.
---

# Planning on this hub

This workflow is self-contained. Small, clear fixes go straight to implementation and
an appropriate check under the `development` skill; they need no design document or extra
approval. For substantial work, use the relevant steps below. An explicit instruction
to proceed is authorization: do not ask the user to approve the same decision again.

## The workflow

Before assigning substantial work, inspect the relevant code and requirements, settle
the approach and risks, then decompose it into reviewable tasks. Ask only for missing
decisions that materially change the result. Recommend an approach and explain its
tradeoff when there is a real choice; resolve routine details yourself.

1. **Design.** State the goal, scope, constraints, approach and testable success criteria.
2. **Grill it.** New or multi-agent work only: the `grilling` skill, one question per prompt (step 0).
3. **Draw it.** C4 levels 1 to 3 from `c4_template.py` (step 0b), then the reviewer
   (`$HUB_REVIEWER`) rates the architecture out of 6 and the lead revises once before
   approval 1 (step 0c).
4. **Approval 1** in a `hub review` window, not the terminal.
5. **Spec** to `$HUB_DIR/projects/<repo>/`, then **approval 2**.
6. **Plan**: write concrete steps, owned files, dependencies and verification, same place.
7. **Board**: tasks with one owner per file, then **approval 3**.
8. **Wake the workers.**
9. **Review each result before committing it.** Code, tests, config and dependencies are
   reviewed first; a docs, README or media-only diff commits on its pasted evidence and is
   reviewed after. The last task always puts real C4 in the README.

Keep review pages lean: pictures and a few lines. Run `hub review` in the background; its
exit carries the decision.

## 0. Grill the design before it is approved (architectural work only)

For a new project, a new subsystem, or anything that will become several tasks: once
the design is concrete and **before** the spec is written, load the
`grilling` skill and run it on that design, until every decision in the tree is
settled. Keep its logic (look facts up yourself, only ask what is unblocked) but NOT its
batched-round format: the user wants **one question per prompt**, through
AskUserQuestion where the tool exists, recommended option first and marked
"(Recommended)", with room to type their own answer. The design approval is given
at the end of grilling: "grilled and agreed", not "looks fine".

This exists because the most common failure is an agent making a wrong design decision
midway through building. The cheapest place to catch it is before any spec exists.

Bounded work skips this; ask for a decision only when existing authorization leaves a
material choice unresolved. The user can ask for a grilling on anything, any time.

**A product with a UI** also runs `init`, `shape` and `new-work` through `designing-products`
(gate G1) on a fresh sub-agent before approval 1. The
approval-1 page shows `PRODUCT.md`'s positioning line, the chosen specimen with the blind judge's
scores and the standard card, and the first-screen mockup at both sizes. No question to the user about the look.

## 0b. Draw it before it is approved (architectural work only)

After grilling, draw the planned system so the user approves a picture, not only prose.
Copy `c4_template.py` from this skill's directory to `$HUB_DIR/projects/<repo>/c4.py`,
replace the example nodes with the planned system, and run `uv run c4.py context
container component`. Show the user the three PNGs next to the spec. Skip level 4 while
planning: classes that do not exist yet are a guess. If it exits saying Graphviz is
missing, ask the user to run `sudo apt install -y graphviz`; do not switch tools.

## 0c. The reviewer rates the architecture (every project)

No design reaches approval 1 until the reviewer (`$HUB_REVIEWER`; a Codex agent such as
Prometheus is a good choice, since a second model family has different blind spots) has
reviewed its C4 diagrams. Put a `review` task on the board for the reviewer naming the three
PNGs, `c4.py` and the design doc, and send it with `hubmsg <Reviewer> "..." --task T-NNN`.
The reviewer answers in the task note with a score out of 6 (6: build it as drawn; 4: sound
with named fixes; 2 or below: rethink) and a short list: missing boxes or flows, a wrong
boundary, a single point of failure, a contract nobody owns, a cheaper shape. The lead revises
the design and diagrams once, then shows the score, the list and what changed on the
approval-1 page. Spend real thinking here: an architecture mistake found now costs minutes,
found mid-build it costs the day. The closing "Architecture diagrams" task gets the same
review against the real code.

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

Only create planning files when the scope warrants them. Keep them outside the project
(keeping them in the repo once left 93 tracked plan files in a product repo that no code
ever read):

- spec → `$HUB_DIR/projects/<repo>/YYYY-MM-DD-<topic>-design.md`
- plan → `$HUB_DIR/projects/<repo>/YYYY-MM-DD-<feature>-plan.md`

Commit both in `$HUB_DIR` (keep it a git repo). Never in the project repo. See `clean-repo`.

**Lessons applied** (event or demo work): the spec and the plan each carry a `Lessons applied`
table listing every lesson in your lessons ledger (for example
`$HUB_DIR/projects/lessons.md`) by number, with the task or
check that applies it, or `n/a: <why>`. Read the ledger fresh each time; cite it, don't copy it.
- isolation → use the workspace `hub claim` provides. Reuse an existing isolated
  checkout; if a worktree is needed, `.worktrees/` is ignored by `hub init-repo` per
  clone. Never add it to a shared `.gitignore`.
- executing with several agents → its tasks become hub tasks (section 2). A single
  session follows its steps directly; no extra execution skill is required.

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
<repo> --repo .'`. **The check-writer task comes first on the board** (owner: the reviewer,
never a builder: it writes every `tests/acceptance/` file,
from first principles and not only the given dataset, until `hub spec check` is green), and every build task `--dep`s it. `hub spec converge` reopens drift weekly.

## 2. The plan becomes the board

Work assigned to hub agents goes through the board. Do not launch a second scheduling
system inside one session to bypass ownership and dependencies.

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
question was underwritten. It also names the **PRD line** it serves (`--req A-x.y`, or the
`PRODUCT.md` or `IDEA.md` line): the reviewer's PRD-fit lens checks the change against it.
On an event or demo board it also quotes, by number and line, the ledger lessons that bear on
that task, so the builder meets them without opening the ledger.
A UI task's `--detail` carries `Design: PRODUCT.md, .impeccable/surfaces/<surface>.md, DESIGN.md`
and its `Verify:` includes `make check-design` (`designing-products` gate G2).

```bash
hub new "<title>" --owner <Agent> --project <repo> --detail '<the whole brief>'
```

**Always pass `--project <repo>`.** Without it a task is tagged with the project this
session *started* in, so a new repo's board lands in another project's queue. If that
happens, recreate the task with `--project`.

For a repo with other committers, paste the "In a repo you do not own" rules from the
`clean-repo` skill into every `--detail`, **except for a repo whose own AGENTS.md is the
rulebook for agents** (a team hackathon repo, say): the house rules ("do not push", "no edits to existing files") contradict it. `--dep` only what genuinely blocks.

**Present the board to the user and get a yes before waking anyone.** That is the third
approval, after the design and the spec.

## 3. Who does it

`hub agents` lists the roster and each agent's phase (`factory.json` is the source of truth);
`hub brief` gives the reviewer routing. The Codex agents (`$HUB_CODEX_AGENTS`, default
Prometheus) have no Claude slash commands, `SendMessage` or `ListAgents`, so reach them only
with `hubmsg`.

## A new project

After the design is approved: create the repo, set its commit identity, and put the
`clean-repo` ignore rules in `.git/info/exclude`. Then the spec, the plan, the board.

## Closing a cycle

Before anything is pushed, list what the push would add (`git diff --stat @{u}..HEAD`) and
check it against `clean-repo`. A harness file in that list is a blocker, not a note.
