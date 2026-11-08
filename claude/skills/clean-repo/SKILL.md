---
name: clean-repo
description: "Keeps harness output out of repos other people work in. Load BEFORE creating any file in a shared repo that is not code or a test — plans, roadmaps, reviews, audits, handoffs, summaries, CLAUDE.md/AGENTS.md, .claude/, debate transcripts, scratch scripts — and before any commit or push to a repo with teammates. Triggers on: 'write up', 'make a plan', 'make a .md', 'document this', 'add a doc', 'commit', 'push', 'PR', 'hackathon', 'my team', 'teammate', 'shared repo', 'don't touch their work'. Not for a repo only the user works in, and not for docs a teammate actually asked for."
---

# Don't ship the harness

## The test

> **Would a teammate who never used Claude Code open this file on purpose?**

No → it does not go in the repo. This applies to good files too. A useful roadmap nobody
asked for is still a cost to everyone who clones.

## Three buckets — decide before writing, not before committing

**Product — belongs in the repo.** Code, tests, `README.md`, one decision record, one demo
script, docs a teammate will open.

**Harness — never enters the repo.** `CLAUDE.md`, `AGENTS.md`, `.claude/`, skills, hooks,
settings, plans, roadmaps, reviews, audits, debate transcripts, handoffs, task write-ups,
"what I did" summaries, reproduction harnesses, scratch scripts.

**Working notes — local only.** Anything written to think with.

## Default output medium

The answer goes **in the terminal reply**. A file is created only when the human asks for
one, or a named teammate will open it in the repo.

"Write it up" does not mean "add it to the repo" — ask *where*, in one line.

## Where harness output goes instead

`$HUB_DIR/projects/<repo-name>/` — plans, reviews, roadmaps, audits. Same content, outside
the tree, still under version control when `$HUB_DIR` is a git repo.

Per-project agent instructions belong at `~/.claude/projects/<slug>/`, never as a
`CLAUDE.md` in a shared repo root unless the human put it there for the team.

## In a repo you do not own

1. Ask who owns which files this hour. Put the map in the task detail, not in a repo file.
2. **New files only**, unless asked. It prevents every merge conflict and costs nothing.
3. **Never push unless asked.** Commit freely; pushing is the human's call.
4. Leave their bugs alone. A pre-existing lint error in their file is theirs — report it.
5. Zero new dependencies without asking. A `package.json` diff is everyone's build.
6. Don't rename their things. Their vocabulary wins, including in commit messages.

## Ignore files: `.git/info/exclude`, never `.gitignore`

Editing a shared `.gitignore` is itself a harness edit to their repo.
`.git/info/exclude` is per-clone, uncommitted, invisible to teammates.

```
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
scratch/
```

## The commands

```bash
git -C <path> rev-parse --git-path info/exclude   # the per-clone ignore file: append the list above
git diff --stat @{u}..HEAD                        # what a push would add: check each path's bucket
```

Fill the exclude file at hour zero of any shared repo, and read the push diff before reporting
done. A harness path in that diff is a blocker, not a note.

## Before handing back — verify, don't assert

```bash
git diff --stat --diff-filter=M <their-last-commit>..HEAD   # empty = touched nothing of theirs
git diff <base>..HEAD -- package.json package-lock.json      # empty = no new dependency
git log --oneline <base>..HEAD                               # what you are actually proposing
```

Report the output, not the intention. "I didn't touch anything" is not evidence; an empty
`--diff-filter=M` is.
