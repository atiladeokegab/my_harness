# Board, projects and commands

Part of the hub manual. Index: `$HUB_DIR/HUB.md` (default `~/hub/HUB.md`).

## The two task boards

**`hub` (the hub directory's `board.json`)** is the durable source of truth. It survives
restarts, is readable by any tool, and is what you should trust. Read it through `hub list`,
`hub show` and `hub events`, never by opening `board.json` or `events.jsonl` directly.

**Native `TaskCreate`/`TaskList`/`TaskUpdate`** tools also exist when agent teams are
enabled. They're convenient in-session but experimental: status can lag and in-process
teammates don't resume. Use them freely for scratch coordination, but anything that
matters gets written to `hub`.

## Projects

The board is one shared list for the whole machine; it is not per-repo. A task can carry a
`project` tag so agents working in one codebase are not handed another's work.

```bash
hub new "..." --project webapp      # tag at creation
hub list --project webapp           # only that project
hub next --project webapp           # only that project
```

`$HUB_PROJECT` is the default for all three, mirroring how `--as` defaults to `$HUB_AGENT`.

**You normally never set it.** `_hub_enter` derives it from the directory you launch the
agent in (the basename of that directory's git root) and passes it into the tmux session
alongside `HUB_AGENT`. Start `apollo` inside `$HUB_CODE_DIR/webapp` and it is scoped to
`webapp` for the life of that session. The launch line tells you:

```
started Apollo in ~/code/webapp  (account: ...)  project: webapp
```

Two deliberate exceptions, both resolving to no scope (whole board): the hub directory
itself, because the lead plans across every project; and any directory that is not a git repo.

Override per shell with `export HUB_PROJECT=...`, or per call with `--project`.

**Scoping is strict.** With a project in scope, `hub next` will not offer untagged tasks
either. That is deliberate: the leak worth closing is an agent that clears its own queue
and falls through to unrelated work. With no project in scope, everything is visible, so
the lead keeps a whole-board view by default.

Tags are free-form: no registry, no setup. `hub list` shows each task's tag in `[brackets]`.

## Commands

```bash
hub new "title" --detail "full plan"    # create a task
hub new "title" --dep T-001             # ...that waits on another
hub new "title" --owner Hermes          # ...assigned up front
hub new "title" --tag read              # ...a read or research task: the reader first
hub edit T-003 --tag headless           # change a task's title, brief, deadline or tags
hub tag T-003 standing [--rm read]     # add tags, or remove one
hub list                                # active tasks (add --all for done)
hub next                                # next task available to you
hub show T-003 [--full]                 # detail and the 5 newest notes (--full: every note)
hub claim T-003                         # claim it; prints the workspace path to work in
hub claim T-003 --force                 # override assignment/deps (audited)
hub done T-003 --note "what happened"   # finish it; runs verify (default make check) in the workspace
hub block T-003 "why it's stuck"        # flag a blocker
hub note T-003 "progress update"        # leave a note
hub release T-003                       # put it back
hub assign T-003 <owner|pool>           # hand a task to a person (or the pool)
hub delegate T-003 <agent>              # ...and to one of that person's agents
hub pause "reason" | hub resume         # the kill switch (see the factory, in dispatch.md)
hub notify Hermes "text" --task T-003   # queue a durable message
hub review --name approval-1 --title "Idea + C4" c4_*.png IDEA.md   # approval window built from files
hub review page.html                    # ...or a hand-written page (needs #approve/#changes/#note/#status)
hub approve <owner/repo>#<N> <sha>      # record a review approval of a PR's head on the board
hub changes <owner/repo>#<N> <sha> "why"   # ...or a request for changes
hub gh-sync --project <p> [--init|--freeze|--dry-run]   # hackathon: board ↔ GitHub Issues
hub live --project <p> [--once]         # the mechanical Live loop (runs as systemd hub-live@<p>)
hub live --project <p> --merge-now|--hold-merges|--resume-merges   # the reviewer sets the merge pace
hub brief                               # where you stand: inbox, your work, phase, what peers hold
hub inbox [--all] [--clear]             # a count plus the latest 20 messages; --all for every one
hub receive --pending                   # reveal every unreceived message once (what a wake asks for)
hub receive <message-id>                # reveal one message once (v1 wakes)
hub sh [--tail N] [--name x] -- <cmd>   # run a long or noisy command: full log on disk, tail on screen
hub ws path T-003 | hub ws gc [--dry-run]   # a task's workspace; remove finished, merged ones
hub events [--tail 50] [--task T-003]   # the append-only ledger
hub new-project <name>                  # a new repo with the commit identity and guards set
hub init-repo <path> | hub ship-check | hub scrub <path>   # keep harness files out of shared repos
hub dashboard                           # who is doing what, and each project's build phases
hub map <project> callers|callees|explain|path <symbol>   # code call graph (needs graphify)
hub trace <target>                      # provenance: trace requirement, task, PR, commit, or acceptance check
hub agents                              # each agent's autonomy phase, budget, and live record
hub agent phase <name> <phase> --why "..."   # promote or demote an agent's autonomy phase (lead only)
hub prd show|render|check|grill <p>     # view, validate, render HTML, or grill gaps in the PRD
hub spec check|lint|impact|rewind|apply|correct|propose|revert|approve|converge  # living PRD tree (living-spec.md)
```

Agents identify themselves automatically via `$HUB_AGENT`, falling back to
`$CLAUDE_CODE_SESSION_NAME`; `--as Name` overrides. `$HUB_AGENT` is set for every agent
including Prometheus, which is why the board needed no changes to take a Codex worker.
A task whose dependencies aren't done can't be claimed without `--force`.

Task state and ownership are enforced: claim before block/done, only the owner may
release/block/finish, and an assigned task cannot be taken by someone else without
`--force`. Overrides are recorded in `events.jsonl`. `hub note` remains deliberately
open to peers because notes are additive and attributed. Dependencies are normalized and
must exist; self-dependencies and cycles are rejected.
