# Learnings

Engineering lessons from running several agents in parallel on real repos. Each one cost
time at least once; the mechanism is what to remember.

## Prove a check can go red before you trust green

**Lesson.** An automated check is believed too early in both directions: it passes on
nothing, or fails on correct code.

**Why.** Probes measured pages in an error state, a page served with no CSS from a stale
build, or a width property that reports the unclipped box. Others fired on a carousel whose
track is wide by design, on decoration clipped on purpose, or on the wrong element because
a selector matched first.

**How to apply.** Inject the defect and require the check to catch it, then remove it and
require the check to go quiet. When a check goes red, find the element or line it is
actually pointing at before changing any code.

## Confirm the named check is what caught a passing case

**Lesson.** A benchmark class at 100% is not evidence that the check it is named after works.

**Why.** One class scored green only because a separate false-positive bug flagged every
case indiscriminately; fixing the false positive exposed the real hole. Another generator
emitted invalid input, so every case was skipped and reported "incomplete" for months
instead of failing.

**How to apply.** For a green class, check which rule produced each detection. Treat a
rise in skipped or incomplete results as an error, not a neutral outcome. Running code
proves only what it did on the inputs tried; a path nobody drove needs a static rule.

## Strip exported hub variables when testing hub tooling

**Lesson.** Changing `HOME` does not isolate a test from variables already exported in your
shell.

**Why.** A "throwaway HOME" installer test honoured the exported `HUB_DIR`, overwrote
tracked files in the live `~/hub` and put a stray task on the live board.

**How to apply.** Run tests of hub tooling as
`env -u HUB_DIR -u HUB_PROJECT -u HUB_AGENT HOME=$(mktemp -d) ...`,
then check `git -C ~/hub status` is clean.

## Unset git's variables in hooks that run git elsewhere

**Lesson.** Hooks run from a linked worktree get an absolute `GIT_DIR` and `GIT_INDEX_FILE`;
the main checkout passes neither.

**Why.** A post-commit hook that cloned the repo and rewrote the clone with git-filter-repo
acted on the real repo instead, and pruned history that could not be recovered.

**How to apply.** Any hook script that runs git in another repo starts with
`unset $(git rev-parse --local-env-vars)` and refuses to rewrite anything but a temp clone.
Before committing from a worktree, check what the repo's hooks do. Runbook:
`runbooks/worktree-hooks-leak-git-dir.md`.

## Never git stash beside other agents

**Lesson.** `git stash` keeps one stack per repository, shared by every worktree.

**Why.** Two agents in sibling worktrees stashed at the same time; one `git stash pop`
applied the other agent's edits.

**How to apply.** To show tests fail without a change, copy the files aside or
`git show origin/main:<path> > <path>`, then restore them. If a pop goes wrong, find the
"WIP on <branch>" commit with `git fsck --unreachable` and check your paths out of it.

## Never pipe a merge into a restart

**Lesson.** A pipeline's exit status is its last command's, and `pipefail` is off by default.

**Why.** `git merge ... | tail -1 && systemctl --user restart <service>` restarted a live
service on a file full of conflict markers, because `tail` exited 0.

**How to apply.** Run the merge on its own, and check
`git diff --name-only --diff-filter=U` is empty before any restart. Better, merge main into
the branch first so the landing merge is a clean fast-forward.

## Give every worktree its own environment

**Lesson.** A worktree using another worktree's `.venv` tests the other worktree's code,
because uv installs the project editable.

**Why.** Red and green results for a fix were meaningless until the worktree got its own
environment; a review verdict on that basis can be silently wrong.

**How to apply.** Run `uv sync` in each worktree. Before a verdict run, check
`uv run python -c "import <pkg>,os;print(os.path.dirname(<pkg>.__file__))"` prints this
worktree.

## Check a PR's base is main before merging

**Lesson.** A stacked PR can merge into a branch that already went to main.

**Why.** The merge succeeds and reports green, so the code sits on a dead branch until
something downstream stays red.

**How to apply.** Before any `gh pr merge`, check `gh pr view <n> --json baseRefName` says
`main`. When a stacked base merges, open fresh PRs to main for its children. Put the check in
every reviewer brief.

## Test an emptiness guard on something you know is there

**Lesson.** A guard of the form `[ -z "$(cmd 2>/dev/null)" ]` passes silently when `cmd`
errors.

**Why.** In some agent shells `find` is a wrapper around bfs, which rejects
`-newermt '-60 minutes'`. The age guard of a cleanup sweep was dead, so it deleted files
younger than its own rule allowed.

**How to apply.** Use `-mmin -60` (works in GNU find and bfs) or `command find`. Before
trusting an emptiness check, run it on something you know is recent and see it non-empty.

## Write tests from the goal, not from the dataset

**Lesson.** Tests drawn only from the data you were given measure fit to that data, not
whether the goal is met.

**Why.** A build tested only on its given dataset passed everything and still undershot the
goal by a wide margin; a bolder approach won.

**How to apply.** Acceptance tests cover held-out, adversarial and production-shaped cases.
At every milestone ask "if every test passed, would we hit the goal?" and treat a "no" as a
finding, the same as a bug. When the plan is "safe", ask whether a bolder approach beats it
before building. Measure how long work takes, but do not set time targets in briefs; work
expands to fill them.

## Merge the approved SHA, not the branch name

**Lesson.** A branch can move after review; merging it by name pulls in unreviewed commits.

**Why.** A fast-forward by branch name took one commit past the approved one. It happened to
be harmless, but it skipped review.

**How to apply.** `git merge --ff-only <approved-sha>`. If main has moved,
`git merge --no-ff <approved-sha>` instead of rebasing, so the approved SHA stays in history,
and check `git diff <approved-sha> HEAD` shows only approved work. Anything past the approved
commit, even a one-line docs change, goes back for review.

## Append to shared files, never overwrite them

**Lesson.** A bare `>` or a full-file write on a shared file erases whatever another agent
put there.

**Why.** An agent wrote a shared notes file with a redirect and erased another agent's
tables. The `ls | head` it ran first cut off just before that file, and the file was
untracked, so git could not recover it.

**How to apply.** Check the exact path with `test -e <path>` or `ls -la <path>`, never a
truncated listing. Add a section headed with the author, revision and UTC time using `>>` or
an edit tool.

## Keep harness output out of shared repos

**Lesson.** Plans, reviews, roadmaps, audits, handoffs, summaries, `CLAUDE.md`, `AGENTS.md`
and `.claude/` do not belong in a repo other people work in.

**Why.** One repo carried about half its tracked Markdown as agent plans that no code
referenced. Another shipped agent instruction files to human teammates who never asked for
them.

**How to apply.** The test: would a teammate who never used an agent open this file on
purpose? If not, it goes to `~/hub/projects/<repo>/`. Ignore agent files per clone in
`.git/info/exclude`, never a shared `.gitignore`, and add a pre-commit hook that refuses them:
`hub init-repo` does both, `hub ship-check` reports what would leak, and `hub scrub` untracks it.
"Write it up" means answer in the reply or ask where. Skill: `clean-repo`.

## Pick the cheapest worker that has the context it needs

**Lesson.** A forked sub-agent starts with the parent's whole conversation and re-reads it
every turn; that is where tokens go.

**Why.** A dozen builders started as forks each carried hundreds of thousands of tokens of
context they did not need, and every worker draws on the same allowance.

**How to apply.** Default to a fresh sub-agent with a self-contained brief for short builds;
a hub session (`hub claim`, its own worktree, a tmux pane) for long work or anything that must
survive the lead being cleared; a fork only when explaining the context would cost more than
copying it. Put standing rules in the brief or a skill, not in conversation history.

## Build habits for every board

**Lesson.** A few board-level habits prevent most late surprises.

**Why.** They were adopted after studying how a well-run agent factory shipped, and each
answers a failure seen more than once.

**How to apply.**
- A new repo ships a README stub with its first working code.
- A new repo's first task is a spine that every other task depends on.
- Docs, README and media-only diffs commit on pasted evidence and are reviewed after; code,
  tests, config and dependencies are reviewed before they merge.
- The closing task moves any rule agents broke twice into `AGENTS.md`, and writes "Known
  limitations" as the failures each shortcut can cause, found by a grep plus one real run.
- A skill change reaches sessions only once it is reinstalled (re-run `./install.sh`) and the
  sessions restart.

## Take the extra round on foundations

**Lesson.** Work every later build reuses (shared skills, design tokens, checkers) is paid for
on every build if it is wrong.

**Why.** A shortcut in a foundation multiplies; a shortcut in a one-off build does not.

**How to apply.** No deadline pressure on foundation tasks. Ask for evidence (exit codes,
captures, blind scores), take the extra review round, and pilot it on one real build before
declaring it done. Event builds still run at event pace.

## Run Python through uv

**Lesson.** One tool for every Python environment avoids "works in my venv" drift.

**Why.** Repos that used uv stayed consistent; the hub itself drifted to bare `python3` in
its tests and docs until the rule was made machine-wide.

**How to apply.** `uv run python script.py`, `uv run pytest`, `uv sync`, `uv add <pkg>`;
never bare `python3`, `pip install` or a hand-made venv. New projects start with a
`pyproject.toml` and `.python-version`. Keep the hub stdlib-only: a dependency that fails to
resolve takes down what every agent coordinates through. The exception is the `hub` entry
point, which keeps a `python3` shebang because it runs from every directory and hook, and a uv
shebang would make it depend on uv being on `PATH` in every sandbox.
