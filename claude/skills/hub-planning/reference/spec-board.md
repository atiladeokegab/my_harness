Paths and commands below resolve from the [skill root](../SKILL.md). Read only the current stage.

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
