# Roles in detail

Read when starting a builder sub-agent, delegating to Hermes, relaunching Prometheus for an event,
or setting up the deploy owner. `hub agents` (factory.json) is the source of truth;
the current task and phase decide authorization. The summary is in SKILL.md "Current roles and boundaries".

## Contents
- Zeus's builder sub-agents
- Hermes
- Prometheus and Atlas, the reviewers
- Rules for every agent on the lead's account
- The deploy owner

## Zeus's builder sub-agents

Zeus builds the lead's bigger tasks through background sub-agents (the lead's decision, 2026-09-29),
and never in its own session, so it can always answer the lead and the queue.

- One sub-agent per task, in its own worktree:
  `git -C ~/code/<p> worktree add .worktrees/<N>-<slug> -b <N>-<slug> origin/integration`.
  It follows AGENTS.md like any agent on the lead's account: label `agent:zeus`, plan comment first,
  one commit per step, a PR that says `Closes #N`. The reviewers review those PRs like any other, so
  nobody reviews their own work.
- **Use available runtime capacity** and current assignments; the old three-builder cap is retired.
- Label the issue `agent:zeus` first. Then start it with the `builder` agent type
  (`~/.claude/agents/builder.md` holds its rules and current model default).
  `name` lets Zeus resume the same sub-agent later:
  ```
  Agent(description: "Build #N <slug>", subagent_type: "builder", name: "build-N",
        prompt: "Build issue #N in <owner>/<p>. First read ~/.claude/agents/builder.md and follow it
                 exactly: it overrides AGENTS.md §5 (worktree, never the shared clone).")
  ```
  The prompt names the rules file because a session loads agent definitions only when it starts: a
  Zeus started before `builder.md` existed gets a plain sub-agent that never sees them (builder test,
  2026-09-29: it checked out in the shared clone and skipped the smoke). The builder test on
  2026-09-29 (issue #12) passed every step with this prompt.
- When a reviewer asks for changes, hub live tells the agent in the issue's label: for a Zeus
  sub-agent, Zeus resumes `build-N` by name with the review's text; Hermes fixes its own.
- Lessons: Zeus names the lessons that bear on the task (SKILL.md §0 "Where the lessons bite").
  builder.md makes the builder read `$HUB_DIR/projects/hackathon-lessons.md` and end its plan comment with
  `Lessons applied:`; a plan comment without that line goes back before the build.
- A sub-agent can't ask the lead anything: it reports back, and Zeus asks.
- When a builder's issue closes, remove its worktree:
  `git -C ~/code/<p> worktree remove .worktrees/N-<slug> && git -C ~/code/<p> branch -D N-<slug>`.

## Hermes

Hermes builds the lead's smaller, self-contained tasks delegated to it (`hub delegate N Hermes`, label
`agent:hermes`). It is Claude on its own Pro account's usage, acting on GitHub as the lead. It follows
AGENTS.md like any agent on the lead's shared account: finds its work with `--label agent:hermes`,
posts its own plan comment (ending `Lessons applied:`), branches `<N>-<slug>`, pushes, and opens the
PR itself. Its PRs go to the reviewers like any other.

## Prometheus and Atlas, the reviewers

Prometheus reviews first and Atlas second, both with the `hackathon-reviewer` skill: PRs touching a
`review_before` path before they merge, the rest after (hub live's digest), every sub-issue change, and
the release review at freeze minus 45.

- **One `LGTM` merges by default; two (Prometheus and Atlas) for a gate, privacy, delivery or security
  change.**
- Either reviewer may push a small fix (about 20 lines or fewer) on a PR it reviews; the other reviewer
  then checks those lines before the merge.
- A reviewer never builds what it reviews.
- Prometheus also owns every test task (SKILL.md §3) and scores the C4 at approval 1.
- Both work on GitHub **with the lead's token** (the lead's decision, 2026-09-28 for Prometheus), so to
  GitHub their work is the lead's. The event repo's AGENTS.md does not name them; these are their rules.
- **Relaunch Prometheus in the event repo** before giving it event work: `hubkill prometheus`, then
  `prometheus <event>`, and leave its window with `Ctrl-b d` (never `Ctrl-c` or `/quit`, which end the
  session). Launched from a script, detach the client it leaves behind
  (`tmux detach-client -s hub-prometheus`), or every wake waits. Its `gh` must be logged in with the
  lead's token. Do this after §6 step 5 has pushed.
- Prometheus owns the starter's deploy files (`Dockerfile`, `.dockerignore`, `scripts/deploy.sh`,
  `docs/deploy.md`): a failed `make deploy` goes to it by hubmsg, with the output.
- When both reviewers are out, or a gated PR waits more than 10 minutes, Zeus starts a backup reviewer
  sub-agent with the same skill (its "Backup reviewer").

Hephaestus can build or review when assigned within its current phase; never review its own work.

## Rules for every agent on the lead's account

These apply to every assigned agent on the lead's account, including Hephaestus.

- No pool issues: a shared account can't tell who claimed one. The lead claims and delegates.
- Their PRs come from the lead's account, so a reviewer can only comment, not approve: the reviewer
  comments exactly `LGTM <head sha>`, and hub live then merges with `--admin --match-head-commit <that sha>`,
  never past a failed `freeze-gate`.
- **Never `hub done` on a task that has an issue** (`hub done` refuses it). The task closes when gh-sync
  sees its issue close, so a smoke revert that reopens the issue reopens the task too.
- Their questions arrive by message: see [live.md](live.md) "Questions".

## The deploy owner

One deploy owner: `deploy.owner` in hackathon.json, Zeus by default, named under IDEA.md's areas table.

- After each green promote, hub live runs `deploy.command` itself, detached, in a throwaway worktree of
  `main`, and tells Zeus `<p> deployed <sha12>: <url>`. A failure goes to Zeus once, for the owner, and
  `main` stays where it was.
- Nobody else deploys: two laptops deploying undo each other.
- It needs the lead's `gcloud auth login` on this machine.
- Without a `deploy` key nothing deploys by itself: the owner runs `make deploy` from a clean checkout
  of `main`.
- Every deploy copies `.env` into its worktree first, and fails unless `/health` afterwards shows the
  live provider and voice on (A11y 7 Nov: three deploys silently went out with no keys).
- Every live deploy messages the lead the URL and sha, so the lead never has to ask
  "is it deployed". Batch fixes: one deploy per 10 minutes at most, not one per fix.
