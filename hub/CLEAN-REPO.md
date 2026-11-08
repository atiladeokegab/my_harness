# Don't ship the harness

How agents on this hub work inside a repo other people also work in.

Companion to `HUB.md` — that file covers coordination between agents, this one covers
what we are allowed to leave behind in somebody else's tree.

## The problem

Agents write a lot of files about *how they worked*: dated plans, specs, reviews, handoffs,
roadmaps. Committed, they look like documentation, but nobody outside your machine ever needs
one. In one real repo, half the tracked Markdown was this kind of file and no code referenced
any of it. A roadmap nobody asked for, added to a four-person repo, is the same problem at
small scale; it only cost nothing because it was never pushed.

## The rule

Three buckets. Decide which one a file is in **before** writing it, not before committing it.

**1. Product — belongs in the repo.**
Code. Tests. `README.md`. One decision record (`PRODUCT.md`). One demo script (`DEMO.md`).
Docs a *teammate* will open. Nothing else.

**2. Harness — never enters the repo.**
`CLAUDE.md`, `AGENTS.md`, `.claude/`, skills, hooks, settings, plans, roadmaps, reviews,
audits, debate transcripts, handoffs, task write-ups, "what I did" summaries,
reproduction harnesses, agent scratch scripts.

**3. Working notes — local, and they stay local.**
Anything an agent writes to think. Evidence extracts, scratch analysis, screenshots.

> The test: **would a teammate who never used Claude Code open this file on purpose?**
> No → it is not product. That includes files that are genuinely good. `roadmap.md` was
> good. It was still slop, because nobody on that team asked for a roadmap.

### Default output medium

An agent's answer belongs **in the terminal reply**, not in a new file. A file is created
only when the human asks for one, or a named teammate will read it in the repo.

"Write it up" does not mean "add it to the repo" — ask *where*.

## Where harness output goes instead

```
~/hub/projects/<repo-name>/
```

Plans, reviews, roadmaps, audits, debate transcripts. Same content, outside the tree.
`~/hub` is itself a git repo, so nothing is lost and nothing is shipped.

Per-project agent instructions stay at `~/.claude/projects/<slug>/` where they already
live — never `CLAUDE.md` in the repo root, unless the human puts it there for the team.

## Enforcement — four layers, cheapest first

### 1. `.git/info/exclude`, never `.gitignore`

The key move. Adding harness patterns to a shared `.gitignore` is *itself* a harness edit
to somebody's repo. `.git/info/exclude` is per-clone, uncommitted and invisible to
teammates.

```
# harness — per clone, never committed
CLAUDE.md
AGENTS.md
.claude/
roadmap.md
plan.md
docs/plans/
docs/specs/
docs/superpowers/
docs/reviews/
debate/
*.handoff.md
scratch/
```

### 2. A pre-commit hook that refuses harness paths

`.git/hooks/pre-commit` is also per-clone and uncommitted. It blocks the staged file
rather than trusting an agent to remember under deadline.

```sh
#!/bin/sh
bad=$(git diff --cached --name-only | grep -iE \
  '^(CLAUDE|AGENTS)\.md$|^\.claude/|superpowers/|/(roadmap|handoff)\.md$|^debate/|^scratch/')
[ -z "$bad" ] || { echo "harness files blocked:"; echo "$bad"; \
  echo "move them to ~/hub/projects/, or commit with --no-verify if the human asked"; exit 1; }
```

### 3. `hub ship-check` — show what a push would add

One command, run before any push to a shared repo. Lists every file the push would add
that the human did not ask for, grouped by bucket. Cheap to write, and it makes the
question visible at the only moment it matters.

### 4. `hub scrub <repo>` — retrofit

Lists tracked harness files in an existing repo and offers `git rm --cached` for each.

## Working in a repo you do not own

Beyond files. These habits keep a shared repo calm.

1. **Ask what is shared before touching anything.** Who owns which files, this hour.
2. **New files only, unless asked.** *"Don't touch my teammates' work"* costs nothing and
   prevents most merge conflicts.
3. **Never push without being asked.** Commit freely; pushing is the human's call.
4. **Leave their bugs alone.** A pre-existing lint error in a teammate's file is theirs.
   Report it, don't fix it.
5. **Zero new dependencies** without asking. A `package.json` diff is a decision about
   everyone's build.
6. **Don't rename their things.** Their vocabulary wins, including in commit messages.
7. **Verify the claim, don't assert it.** `git diff --stat --diff-filter=M <base>..HEAD`
   returning empty is proof you touched nothing; "I didn't touch anything" is not.

## Hour zero of a shared-repo project

Do this before any agent writes a line. About five minutes.

- [ ] `hub init-repo <path>` — writes `.git/info/exclude` and the pre-commit hook
- [ ] `mkdir -p ~/hub/projects/<repo>` — the destination for every plan and review
- [ ] Agree the ownership map, and put it in the task `--detail`, not in a repo file
- [ ] Confirm with the human: push, or never push?
- [ ] Tell every agent, in the task detail: **new files only, terminal answers by default**

At the end, before handing back:

- [ ] `hub ship-check` and read the list out loud
- [ ] `git diff --stat --diff-filter=M <their-last-commit>..HEAD` — should be empty
- [ ] `git diff <base>..HEAD -- package.json` — should be empty

## Task `--detail` boilerplate

Paste into every task that touches a repo with other committers. A worker who never saw
the conversation needs the rule in front of it, not a link to it.

```
HOUSE RULES. New files only -- zero edits to any file that already exists, unless this
task names one. Do not push; commit only. Zero new dependencies without asking. Leave
pre-existing lint errors and bugs in their files alone -- report, do not fix. Plans,
reviews and write-ups go to ~/hub/projects/<repo>/, never into the tree; the answer to a
question goes in your reply. Before reporting done, run `hub ship-check` and paste the
verdict, plus `git diff --stat --diff-filter=M <base>..HEAD` (should be empty).
```

`hub init-repo` writes each glob case-insensitively (`[cC][lL]...`) because exclude is case-sensitive on Linux, and the hook greps with `-i`. The hook blocks new, renamed and copied harness paths, never edits to one already tracked: a file the human kept (`scrub --keep`) stays editable. The hook is copied into each clone, so re-run `hub init-repo` after changing it.

Implementation is `clean_repo.py` in the hub, wired into `hub` as three subcommands. Its
pattern list is paired `(regex, glob)` entries — the regex drives the hook and the checks,
the glob drives the ignore file — because converting one to the other is lossy and a
silently-wrong ignore line is worse than none.

## The rest of the setup

| Piece | What it is for |
|---|---|
| `hub new-project <name>` | New repo with the commit identity (`HUB_GIT_NAME`, `HUB_GIT_EMAIL`, else your global git config) and these guards already installed |
| `hub init-repo <path>` | Retrofit the guards onto an existing repo |
| `hub ship-check` | What a push would add, bucketed. Non-zero if harness would land |
| `hub scrub <path>` | Move tracked harness files out, then untrack them |
| `hub done` | Nudges when a finished task leaves harness files behind |
| `development` skill | Focused debugging, behavior tests, review and verification in Hub |
| `hub-planning` skill | Self-contained team planning: spec and plan to `~/hub/projects/`, plan → board |
| `ponytail` skill | Fewer lines. This file is fewer files. Same instinct, other axis |
| `/ponytail-audit` | Ranked list of code to delete. Pairs with `hub scrub` |

## The line to remember

**A file is a cost to everyone who clones the repo. Pay it only when a teammate gets
something back.**
