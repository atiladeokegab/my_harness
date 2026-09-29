---
name: hackathon
description: >
  The lead's flow for a team hackathon: from a pasted event brief to a team repo whose
  GitHub Issues every teammate's AI agent picks up under the hackathon_teamwork rulebook.
  Use when the user says "hackathon", "new hackathon", "event brief", "team repo",
  "hackathon teamwork", or pastes an event description to plan with a team. Orchestrates
  your planning flow and hub gh-sync; it does not replace them.
---

# Running a hackathon from this PC

The whole team plans together at the lead's laptop (§1–§6); teammates never touch the hub
themselves. Each event repo is made from your
copy of the `hackathon_teamwork` template, whose `AGENTS.md` makes every agent plan before
coding, branch per issue, stay in its area and raise change-requests. This skill gets
the plan onto GitHub as Issues. `hub gh-sync` is the bridge.

## One-time setup: your template repo

The template's `CODEOWNERS` names the lead, so make your own copy once:

```bash
gh repo create <you>/hackathon_teamwork --template <you>/hackathon_teamwork --public --clone
cd hackathon_teamwork
echo "* @<you>" > .github/CODEOWNERS
git commit -am "chore: I own this template" && git push
gh repo edit <you>/hackathon_teamwork --template
```

Then every event's `hackathon.json` names it as `"template"`.

Also make one GitHub Project board titled **Hackathon board (template)** on your account, once:
a `Status` field (Todo, In progress, In review, Done), text fields `Agent` and `Deadline`, and a
**By vertical** table view grouped by Parent issue (add views in the browser: the API can't).
`--init` copies it for every event; without it gh-sync warns and carries on with no board.

The names below (Zeus, Hermes, Prometheus) are the defaults: Zeus is `$HUB_LEAD`, the reviewer is
`$HUB_REVIEWER` (default Hermes), and Prometheus is any Codex agent in `$HUB_CODEX_AGENTS`.

## Roles

- **Zeus thinks and builds, and stays free for the lead.** It owns the idea, `IDEA.md`, the plan,
  every task brief, every `DRAFT`, change-request and question for the lead, and anything Hermes
  escalates. It is on the biggest subscription, so it also **builds most of the lead's areas,
  through background sub-agents** (the kit's default): one sub-agent per task, in
  its own worktree (`git -C $HUB_CODE_DIR/<p> worktree add .worktrees/<N>-<slug> -b <N>-<slug>
  origin/integration`), following AGENTS.md like any agent on the lead's account (label
  `agent:zeus`, plan comment first, one commit per step, PR that says `Closes #N`). Zeus never
  builds in its own session, so it can always answer the lead and the queue; Hermes reviews those
  PRs like any other, so nobody reviews their own work. **At most 3 builder sub-agents at once**
  (the kit's default): start the next only when one reports back. The call, one per task,
  uses the `builder` agent type (`~/.claude/agents/builder.md` holds its rules; default model Sonnet,
  pass `model: "opus"` for a hard task); `name` lets Zeus resume the same sub-agent later:
  ```
  Agent(description: "Build #N <slug>", subagent_type: "builder", name: "build-N",
        prompt: "Build issue #N in <owner>/<p>. First read ~/.claude/agents/builder.md and follow it
                 exactly: it overrides AGENTS.md §5 (worktree, never the shared clone).")
  ```
  The prompt names the rules file because a session only loads agent definitions when it starts:
  a Zeus started before `builder.md` existed gets a plain sub-agent that never sees them (builder
  test, 2026-09-29: it checked out in the shared clone and skipped the smoke).
  When a builder's issue closes, remove its worktree:
  `git -C $HUB_CODE_DIR/<p> worktree remove .worktrees/N-<slug> && git -C $HUB_CODE_DIR/<p> branch -D N-<slug>`.
  The builder test on 2026-09-29 (issue #12) passed every step with this prompt.
  Label the issue `agent:zeus` first. When Hermes asks for changes, hub live tells the agent in
  that label (a Zeus sub-agent: Zeus resumes `build-N` by name with the review's text; Prometheus
  fixes its own). A sub-agent can't ask the lead anything: it reports back, and Zeus asks.
- **Hermes reviews** (Claude, on its own Pro account's usage, acting on GitHub as the lead). Every PR
  and every sub-issue change comes to it by hubmsg from hub live. See "Reviewer (Hermes)" below.
  With nothing to review it may build one small task of the lead's delegated to it
  (`hub delegate N Hermes`, label `agent:hermes`), never a pool issue (a shared account can't
  claim pool work), and never one it would then review: its PRs go to Zeus for review.
- **hub live merges and keeps time** (`hub live --project <p>`, a script, no model): sync, the
  merge queue, smoke → promote or revert, the freeze, reminders and nudges, every 5 minutes. It
  never judges; it hands each item once to Hermes or Zeus.
- **Prometheus builds** the lead's smaller, self-contained tasks delegated to it (`hub delegate N
  Prometheus`): its Codex budget is the smallest and runs out first. It
  works on GitHub **with the lead's token** (the kit's default), so to GitHub its
  work is the lead's. The event repo's AGENTS.md does not name it; this section is where its
  rules live:
  - Before giving it event tasks, relaunch it in the event repo:
    `hubkill prometheus`, then `prometheus <event>`, and leave its window with `Ctrl-b d`
    (never `Ctrl-c` or `/quit`, which end the session). Launched from a script, detach the client
    it leaves behind (`tmux detach-client -s hub-prometheus`), or every wake waits. Its `gh` must be logged in with the
    lead's token.
  - It follows AGENTS.md like any agent on the lead's shared account: finds its work with
    `--label agent:prometheus`, posts its own plan comment, branches `<N>-<slug>`, pushes,
    and opens the PR itself.
  - It doesn't take pool issues (a shared account can't tell who claimed one): the lead
    claims and delegates.
  - Its PRs come from the lead's account, so the reviewer can only comment, not approve: Hermes
    comments exactly `LGTM <head sha>`, and hub live then merges with `--admin
    --match-head-commit <that sha>`, never past a failed `freeze-gate`.
  - **It never runs `hub done` on a task that has an issue.** The task closes when gh-sync
    sees its issue close, so a smoke revert that reopens the issue reopens the task too.
- **Teammates** build in their own areas, push to their branches after every commit, and
  never merge.

Give hub work only to agents on a paid account: by default Zeus (with its sub-agents), Prometheus
and Hermes. In `hackathon.json` the lead's `agents` are Zeus, Prometheus and Hermes, so gh-sync makes
an `agent:<name>` label for each.

## Reviewer (Hermes)

Hermes is started at the end of planning (§6 step 10) with one line: "You are the reviewer for
<p>. Read the hackathon skill's Reviewer section, then run hub inbox." Then, for each hubmsg:
1. **`PR #N ready for review at <sha>`:** read `gh pr diff N -R <repo>` and
   `gh pr view N -R <repo> --json title,body,files,headRefOid,baseRefName`. Check it against its
   issue, the owner's area (IDEA.md "Areas and owners"; a pool issue: exactly its `Files:`) and
   IDEA.md. Then either approve (`gh pr review N -R <repo> --approve`; for a PR from the lead's
   account, comment exactly `LGTM <headRefOid>` instead), or request changes with exactly what to
   fix (`--request-changes`, or `--comment` on a lead-account PR). A push after that comes back as
   a new hubmsg. Hermes never merges, but **it sets the pace**: right after an approval or
   `LGTM`, run `hub live --project <p> --merge-now` and hub live merges within about 10 seconds
   (one PR at a time, each smoke-checked; the 5-minute pass is only a backstop).
   **Hold** merges with `hub live --project <p> --hold-merges` while `integration` is red (a
   revert just happened), during a demo run-through, or to land related PRs in a set order;
   `--resume-merges` lifts it and merges at once. A hold longer than 15 minutes is reported to Zeus.
   **Two rounds, then Zeus.** After requesting changes twice on the same PR, don't ask a third time:
   escalate to Zeus with what keeps coming back. A PR that won't converge usually means the brief
   is unclear or wrong, and only Zeus re-plans. (hub live also tells Zeus on a third round it relays.)
2. **`NEW` / `CHANGED #n in #v …`:** read the sub-issue. If it drifts from IDEA.md, the contract or
   the design while staying inside its vertical, comment once, starting `FLAG:`: the problem, the
   line it breaks, a fix. Otherwise nothing.
3. **Escalate to Zeus** (`hubmsg Zeus "…"`) instead of deciding when: unsure; the PR or sub-issue
   touches scope, IDEA.md, the contract or the design; its diff leaves the owner's area without an
   accepted change-request (request changes too); or it contains a secret (never approve it; say
   so to Zeus at once: the key must be revoked).
Hermes never merges, never edits code, briefs or `IDEA.md`, and never answers questions for an owner.
- **Findings-only comments start `FYI:`**, so hub live doesn't relay them as change requests.
- **The design PR is never LGTM'd by Hermes:** it posts `FYI:` findings and the lead approves the design
  in its window (§2a); Zeus merges it.
- **Hermes's permissions** must allow `gh pr comment`, `gh pr review` and `hub live` (the lead adds them
  in Hermes's `/permissions`; dry run #4: without them its auto mode blocked every LGTM and
  `--merge-now`). If they're blocked anyway, Hermes sends its verdict to Zeus by message, the lead
  approves, and Zeus merges by hand (§7's fallback), which is what dry run #4 did.

## The planning session: the team at the lead's laptop

Everything from §0 to §6 happens with the whole team in the room, in front of the lead's
screen. Zeus asks one question at a time, as always, and **the room answers**:

- Each teammate answers the roster questions about themselves.
- **Pitch round, before Zeus proposes anything.** Once the track and deadlines are settled,
  first ask one question: is everyone round the lead's laptop, or should Zeus collect ideas
  from each person separately? Recommend "round one laptop"; that is the usual case.
  - **Round one laptop:** one open question to the room: "Every idea on the table, one per
    line, with whose it is." No suggestions to choose from. The room talks; the lead types.
  - **Separately:** one multiple-choice question per person, "What would you build, in one line?",
    showing only that person's strengths.

  Then Zeus adds at most one pitch of its own, labelled as Zeus's. The room shortlists, and
  the brainstorm and design continue together from the chosen pitch. Only after that are
  builds and tasks handed out by strengths (§4). Without this round every option comes from
  Zeus and the room only picks between them. That happened in the 2026-09-28 rehearsal: 14
  questions, all answered with the recommendation. The spec names whose pitch it grew from.
  If the room offers no ideas, say so in the spec ("grew from Zeus's pitch; the room offered
  none") and continue from Zeus's pitch rather than asking again (dry run #1, 2026-09-28).
- In the brainstorm and the grill, a teammate's own idea is an answer: it comes in as
  "Other", and Zeus weighs it like any option.
- Every approval window is the team's decision. Zeus never writes the page by hand:
  `hub review --name <approval-N> --title "<what>" --note "team agreed" <files…>` builds it from
  the files (pictures side by side, `.md` as text, `.html` embedded) and waits for the click. The
  lead edits the note only for a disagreement, so the saved review always records one or the other.
- In the assignment grill, people claim tasks aloud; the recommendation is still shown first.
- Nobody leaves until §6 has published: every teammate has accepted the invite, logged in
  with `gh auth login`, and seen their own issues assigned to them; **every vertical has its
  first sub-issues on GitHub** (§6 step 9); and the design PR is merged, or, if the mockup is
  late, `docs/design.md` is approved (§2a).

**Timebox: the session ends by build start + 60 minutes**, publish included. Grill only the
decisions that change scope, ownership or acceptance; every smaller assumption goes into an
`Assumptions` section of the spec instead of a question. At build start + 45 minutes, say how
much is left and cut to it.

The plans, specs and reviews on the lead's screen still live only in `$HUB_DIR/projects/`.

## 0. Deadlines first

When the lead pastes the event brief, before any design, extract:

- every date and time: submission, code freeze, judging, check-ins, mentor sessions
- the rules and the judging criteria

Show them as one table with absolute ISO 8601 times and a timezone, and confirm with one
multiple-choice question. There is always a `code freeze` and a `submit`; if the brief names no
freeze, recommend submit minus 60 minutes. GitHub milestones keep only the date, so the UTC
column of HACKATHON.md is the clock everyone checks, never the milestone.

## 1. Project and roster

- Pick a lowercase project tag (e.g. `lablab-oct26`) and make `$HUB_DIR/projects/<project>/`.
  **The event repo is named exactly the tag** (`<you>/lablab-oct26`). gh-sync
  refuses anything else, and refuses any repo not created from the template, so a typo
  can never point it at a real repo.
- For each teammate, ask name, GitHub handle, strengths and AI tool, one question at a
  time. Mark the lead `"lead": true`. Then ask once: **who is the designer?** (default: the
  lead) and mark them `"designer": true`; gh-sync refuses more than one, and refuses a designer
  with no AI `tool`: the designer's agent builds the mockup (§2a). When the lead is the designer,
  Zeus is that agent. The roster `name` is the one-word name you'll assign
  tasks to: for "Sam Lee", use `SamLee` or their GitHub handle.
- Roster names become hub task owners, so each is **one word** (letters, digits, `_`, `-`),
  unique, and not a hub agent's name or `Pool`. The hub capitalises them (`deshawn` →
  `Deshawn`), and gh-sync matches either spelling. gh-sync checks the whole file and names
  anything wrong before it touches GitHub.
- **Owners are humans; agents are delegates.** Each person may list the agents that work for
  them under `agents`. The lead's are Zeus and Prometheus; both act on GitHub as the lead
  (Prometheus with the lead's token), so they have no `github`. A teammate's agent with its
  own GitHub account gets a `github` handle, which must not be any person's handle.
- Write `$HUB_DIR/projects/<project>/hackathon.json`:

```json
{"repo": "<you>/<event-repo>", "template": "<you>/hackathon_teamwork", "timezone": "Europe/London",
 "deadlines": [{"name": "code freeze", "at": "..."}, {"name": "submit", "at": "..."}],
 "roster": [{"name": "...", "github": "...", "lead": true, "strengths": "...", "tool": "...",
             "agents": [{"name": "Zeus"}, {"name": "Prometheus"}]},
            {"name": "...", "github": "...", "strengths": "...", "tool": "...",
             "agents": [{"name": "cursor"}]}],
 "event": "<event name>", "title": "<product name>", "summary": "<one paragraph: what, which track>",
 "smoke": "<the smoke command>", "rules": "<link or 'the event brief'>", "judging": ["..."]}
```
`event`, `title`, `summary` and `smoke` are needed before `--init` (§2): gh-sync writes
HACKATHON.md and README.md from them and refuses to publish without them. `title`, `summary` and
`smoke` come from the brainstorm; fill them in when approval 1 is agreed.

## 2. Design, spec, plan

Plan it the way you plan any multi-agent project (brainstorm, challenge every decision, draw it), with `--project <project>` on every `hub new`, and two hackathon cuts:
**no separate plan document** and **no approval 2**. The vertical and task briefs
are the plan. Write one short spec (contract, smoke, assumptions) to `$HUB_DIR/projects/<p>/`; it is
approved together with the board at approval 3.

**The idea is fixed at approval 1, not at the end.** Once the grill is agreed, Zeus writes
`$HUB_DIR/projects/<project>/IDEA.md`: the problem, the idea, what we build, what we don't
build, the demo in one line, and the "Areas and owners" table with the areas and their
directories filled in and the Owner and Issues cells left as `—`. The approval-1 window shows IDEA.md
beside the C4 diagrams, and the lead approves both together. The spec, plan and board then
build on an idea the lead has already signed.

**Publish the repo at approval 1**, not at the end: run §6 steps 0–5 straight after it, so the
designer's agent has a repo to work in (§2a) while Zeus writes the spec, plan and board. The
issues for the verticals still wait for approval 3 (§6 step 6).

The design names the **areas** (a set of directories each, split by strength) and the
**core** (shared contracts; Zeus owns it), and one **smoke command**: the unit tests plus one
end-to-end run on a few sample inputs, under 2 minutes. It runs in a clean checkout with only
`.env` copied in, so it includes its own install step (`uv run …` installs; `npm ci && …`).
Until the pipeline exists, the smoke is the tests alone. Until the first test exists there is
nothing to smoke: publish promotes `main` directly (§6 step 5), and the first code task (usually
the core) adds the test package, e.g. `tests/__init__.py`, so the tests-only smoke can pass.
Every task's `Files:` is its area's directories.

Every task
`--detail` carries these headings, one per line, because teammates' agents rely on them:

```
Context:
Files:        <the area's directories: the owner may change anything inside them>
Approach:
Acceptance:
Verify:
Deadline:     <a deadline name from hackathon.json>
```

Write `Verify:` commands that run on any teammate's machine: `python3`, not `python`.

## 2a. The designer's mockup (in parallel with the spec)

No multiple-choice design grill (dry run #3: the designer didn't know the questions were theirs,
and a look can't be chosen from words). Straight after the repo is published (§2):
1. `hub new "Design: design.md + clickable mockup" --owner <designer> --project <p>` with a brief:
   `Files: docs/design.md, docs/mockup/`; `Acceptance:` references first (described and linked,
   never someone else's images committed), `docs/design.md` in the template's shape with the look,
   and `docs/mockup/index.html` (static, fake data, every screen and state clickable, exact copy);
   `Verify:` the placeholder grep on `docs/design.md` prints nothing and the mockup opens in a
   browser; `Deadline:` a deadline named `design`, set to when approval 3 is expected. Then
   `hub gh-sync --project <p>`: it becomes the first issue.
2. Say it to the room **by name**: "<Designer>, as designer, you're up: your agent has issue #N."
   Their agent follows AGENTS.md "If your human is the designer". **When the lead is the designer,
   Prometheus builds it** (`hub delegate <N> Prometheus`), so Zeus keeps planning: Prometheus asks
   for references by hubmsg, Zeus puts each to the lead and relays the answer.
3. Zeus writes the spec, plan and board meanwhile.
4. The design PR: check it out in a throwaway worktree `$d`, copy its design into the project
   folder (the page and the saved decision go next to the first file, and the worktree is thrown
   away): `cp "$d/docs/design.md" $HUB_DIR/projects/<p>/design.md`, then run
   `hub review --name design --title "Design + mockup" --note "team agreed" $HUB_DIR/projects/<p>/design.md "$d/docs/mockup/index.html"`
   (the design shown as text, the mockup embedded). Keep the worktree until the window closes. Before approving, check that nothing private leaks: no private text, URLs
   or images in the mockup or `docs/design.md`. On approve, merge it like any PR (§7), then smoke
   and promote.
5. **Late:** if the mockup PR isn't ready at approval 3, the room approves `docs/design.md` alone
   (Zeus commits it as one of its own commits, §7), the verticals start on it, and the mockup
   follows on the designer's issue: their PR pulls `integration` first and adds only the mockup
   and approved refinements; when it merges, `hub edit` the affected verticals so their
   owners get "Brief updated".

Every vertical's brief then gets a `Design:` line naming the sections and the mockup it must
follow (`Design: docs/design.md §Flow, §States; docs/mockup/` or `Design: none`). The web page's
vertical says in `Approach:` that its first sub-issue copies `docs/mockup/` into its area.

## 3. Submission track

Always add three tasks:

- the demo script, `Deadline: code freeze` for the first draft, then adjusted after the final
  run, so the recording is a rehearsal and not a discovery
- the recording, `Deadline: submit` (or the demo-video deadline if the event has one)
- the submission form, `Deadline: submit`

The **sample data** task is owned by someone other than the owner of the rules it exercises:
a sample written by the rules' author only tests what the author already thought of. And Zeus
drops a small unseen set on the team at build start + 30 minutes and a second one at build start
+ 60, not only at the reality test (dry run #1's reality test found the gaps an hour too late;
in dry run #2 the first early set caught two gaps and the reality test still found two more).

## 4. Assignment grill

**The board holds verticals, not tasks.** Each area becomes one vertical for its owner
(`hub new "<area>: <what it delivers>" --vertical --owner <person> --project <p>`), whose brief says
`Files:` (the area), `Acceptance:` (what the vertical must deliver), `Contract:` (interfaces it
consumes and provides) and `Deadline:`. Owners break their own vertical into sub-issues
in the room, then live (§6 step 9, §7 "Watching the breakdowns"). The core and the submission track stay ordinary tasks.

Assign **areas first**: one multiple-choice question per area, recommendation first, based on
strengths and balanced load; a teammate claiming an area overrides. An area's owner is
always a **person** on the roster; the lead's areas are built by Zeus or Prometheus as
delegates. Every task in an area inherits its owner. Ask per task only for the core (the
lead, delegated to Zeus) and for work outside any area, which may go to `pool`: unassigned,
whoever finishes early takes it (submission, docs, diagrams). Then `hub assign <id> <person>`
(or `hub assign <id> pool`), and for the lead's own tasks `hub delegate <id> Zeus|Prometheus`
(`hub assign` refuses an agent as owner and says which two commands to run instead). Then
approval 3: `hub review --name approval-3 --title "Spec + board" --note "team agreed" <spec.md>
<board.md>`, where `board.md` lists each task by **title**, owner, deadline and `Design:` line:
tasks have no issue number yet, and a T-id never reaches the repo.

## 5. IDEA.md: the gate

IDEA.md was approved with the design (§2). Its **Areas and owners** table is kept by gh-sync:
every sync fills each row's Owner and Issues from the issues whose `Files:` fall in that row's
directories, and commits the change to `integration` (Zeus promotes it after the next green smoke). Re-open IDEA.md for approval only if the spec, plan or board changed
what we build or don't build since approval 1; say which lines changed.
**No issue is synced until `IDEA.md` is approved.**

## 6. Publish

0. **Visibility.** `--init` makes a **public** repo. Check the event rules (and sponsor
   IP terms) allow that, and that every teammate is fine with public code. If public is
   not allowed, stop and tell the lead: the kit needs a private-repo variant, and private
   repos on a free account lose branch protection.
1. Run `hub gh-sync --project <p> --init --dry-run` and read what it would do.
2. Run `hub gh-sync --project <p> --init`. This creates the repo from the template, invites
   the roster, and sets up labels, milestones and branch protection.
3. Before step 1, `hackathon.json` must have `event`, `title`, `summary` and `smoke` (§1).
   `--init` then fills the clone itself: IDEA.md from `$HUB_DIR/projects/<p>/`, HACKATHON.md (both
   time columns, the team table, the lead's agents, the board link), README.md (title, intro, the
   clone line, the planning C4 PNGs in Architecture). `docs/design.md` is left for the designer's
   PR (§2a). It runs the placeholder and image check; any leftover `<…>` stops it before a push.
4. Read what step 1's `--dry-run` said it would write and push, and **confirm with the lead**:
   the push is outward-facing.
5. Step 2 commits "docs: fill in the event" on `integration` and pushes `integration` and `main`.
   Do this before Prometheus is relaunched in that checkout.
6. After approval 3, run `hub gh-sync --project <p>`. Every task becomes an issue. (Steps 0–5 ran
   at approval 1, §2.)
7. gh-sync ends with an `owners (for IDEA.md):` block and, when the table changed, "IDEA.md owners
   table updated": it has already committed the table to `integration`. An issue that fits no row
   prints a warning: add a row (or fix the issue's `Files:`). From now on, in
   this project, every hub command takes the issue number: `hub show 5`, `hub edit 5`,
   `hub claim 5` (`T-…` ids still work).
8. Give the lead the repo URL and the board URL (`--init` printed `board: <url>`, also on
   HACKATHON.md's `Board:` line) to share with the team. The board is public:
   a column per status, a lane per owner. List who hasn't accepted the
   invite yet:
   `gh api repos/<repo>/invitations --jq '.[].invitee.login'`.
   GitHub can't assign an issue to someone who hasn't accepted. gh-sync creates their
   issues unassigned, warns, and assigns them on the first sync after they accept. Tell
   each teammate to accept before they tell their agent to pick up work, and to log in with
   `gh auth login` (browser), and to start their agent with only "Read AGENTS.md, then pick up
   my issue": it keeps itself going with `scripts/team-inbox.sh`. The board has a **By vertical**
   view (grouped by Parent issue): show that one in the room. It comes from the template board; if
   it's missing there, add it once by hand (the GitHub API can't create views). Until then, show
   each vertical's sub-issues: `gh api repos/<repo>/issues/<V>/sub_issues --jq '.[] | "#\(.number) \(.title)"'`. A fine-grained personal access token (`github_pat_…`) can't
   accept the invite, and fails in a repo it doesn't own with "Resource not accessible by
   personal access token".
9. **Breakdowns, in the room.** Each owner starts their agent on their own laptop; it opens 2–6
   sub-issues under their vertical (AGENTS.md "Break down your vertical, live"). The room watches
   the By vertical view on the lead's screen. Zeus does the lead's verticals the same way and the
   lead okays them in the terminal. Check each against the line (§7) as it appears. The session
   ends when every vertical has its first sub-issues and §2a's design is in.
10. **Start the live crew** before the room breaks up: `tmux new -d -s hub-live-<p> "hub live --project <p>"`,
   and `hermes <p>` with its one line (Reviewer section); leave it with `Ctrl-b d`, never `Ctrl-c`.

## 7. Live

**Who does the Live work.** hub live (a script, every 5 minutes) does the mechanical duties below:
the sync, merges in dependency order at an approved head sha, the smoke → promote or revert, the
conflict comments, the freeze (retried until it exits 0), the unseen-set reminders, the question
nudge (20 min, then Zeus), the idle-branch comment (1 h) and the invite reminder. Hermes reviews
every PR and FLAGs drifting sub-issues. Zeus gets, by hubmsg: `DRAFT`s, change-requests, questions
for the lead, escalations from Hermes, gh-sync errors, smoke reverts and the unseen-set reminders.
**The rest of this section is how each duty is done; Zeus does the mechanical ones by hand only
if hub live is down** (check: `tmux has-session -t hub-live-<p>` and the last line of
`$HUB_DIR/projects/<p>/live.log`), in which case start the `/loop` below.

**Never state a time from memory:** run `date` first, every time you tell the lead a time or a
countdown (dry run #4: Zeus narrated from a clock an hour stale; a builder's clock check caught it).

**Every pass starts with the clock**, the same rule the teammates' agents follow:
`date -u` against the UTC column of `HACKATHON.md`.
- **Before code freeze:** everything below.
- **After code freeze:** no new feature tasks, no feature replans, no feature merges.
  Only fixes, demo and submission work.
- **After submit:** stop the loop. Nothing more is merged or synced.

**Watching the breakdowns.** Sub-issues change live all event: owners add, edit and close their
own. `scripts/team-inbox.sh --lead` (run in Zeus's clone) prints NEW, CHANGED, CLOSED and DRAFT
lines per vertical. Check each NEW or CHANGED one against **the line**: `Files:` inside the
vertical's `Files:`, the `Contract:` unchanged, the design unchanged, and it serves `IDEA.md`
(nothing from "What we don't build", the same demo).
- Inside the line: nothing to do; the next sync imports it.
- A problem with a live one: **one** comment on it that starts with `FLAG:` (the inbox matches on
  that, because on the lead's shared account the author can't tell Zeus from an owner's agent),
  addressed to the owner: the problem, the
  `IDEA.md` line, contract or design section it breaks, and a proposed fix. Their inbox shows it
  as FLAG; their agent fixes it itself when those decide it, or asks its human. If you still
  disagree after one exchange, show the lead both sides and post the lead's call.
- A DRAFT (it says `Crosses: …`): decide within 10 minutes. Remove `draft`
  (`gh issue edit <N> -R <repo> --remove-label draft`; their inbox shows READY), or close it as not
  planned with the reason, or re-plan it as a change-request below.

**Never relay through a human.** Every request to a teammate goes on GitHub as a review, a
question or a brief change; their agent runs `scripts/team-inbox.sh` after each push and every
5 minutes and acts on it (AGENTS.md §3). If a teammate's agent seems idle, say so to that
teammate, but don't send them text to paste.

**Source of truth:** the hub owns each brief (title, body, owner, milestone); GitHub owns who
picked up pool work and what got closed. A brief edited on GitHub is never overwritten: every
sync warns until the lead decides with `hub edit N --take-github` or `hub edit N --keep-hub`.

**Every GitHub command names the repo** (`-R <owner>/<p>`) and a number: Zeus runs from
the hub folder, where a bare `gh pr list` finds no repo, and from any other checkout it would act on
the wrong one. **One integration pass at a time:** finish one merge's smoke and its promote
or revert before merging the next.

**If Zeus is down, the lead is the backup.** All state lives on the board and on GitHub, so the
lead relaunches `zeus` in the event repo and it picks up from `hub brief` and `gh pr list`. In
the last 30 minutes before a deadline, the lead may merge a PR Zeus has already reviewed, or
one with green checks that matches its issue, with `gh pr merge <PR> -R <repo> --admin
--squash --delete-branch --match-head-commit <reviewed sha>`, rather than wait, then smoke and promote as the Live loop does: the demo
runs from `main`, so a merge that never reaches it is missing from the demo.

- **Keep the board in step** (hub live; by hand only if it's down): start
  `/loop 5m run scripts/team-inbox.sh --lead (and hub gh-sync --project <p> every other pass), then do the hackathon skill's Live review pass`.
  Scheduled deadline jobs fire only when the session is idle, so they can run late (dry run #1:
  10 minutes). Schedule each deadline job 5 minutes early, and at the start of every pass check
  whether a deadline in HACKATHON.md is due within 10 minutes; if so, do it now.
  A sync is safe to repeat, and an overlapping one refuses to start. Fix any `error:` line
  it prints, then rerun.
- **A design change-request** (addressed to the designer): the designer decides, with Zeus.
  Once decided, the designer changes `docs/design.md` or `docs/mockup/` in their own PR, and Zeus runs `hub edit`
  on each affected vertical's `Design:` line so its owner's agent gets "Brief updated".
- **A change-request in the inbox:**
  1. Re-plan the affected tasks, and grill if the change is architectural.
  2. Redraw the C4 and change the briefs with `hub edit N` (Zeus: `hub edit N --detail-file F
     --yes`; the diff is printed either way). `--title` and `--deadline <name>` change those.
  3. Sync. gh-sync posts "Brief updated" on each changed issue.
- **gh-sync warns that an issue was edited on GitHub** (`#N was edited on GitHub; not
  overwriting`, with a diff), on every sync until you decide:
  - to keep their text: `hub edit N --take-github --yes`, then sync (one "Brief updated");
  - to put the brief back: `hub edit N --keep-hub --yes`, then sync (GitHub is overwritten).
  The issue's title and milestone wait for the decision too.
- **gh-sync warns that an issue was closed as not planned, or not found:** decide.
  - To drop the task: `hub claim <id> --force`, then `hub done <id> --note "dropped: #N"`.
  - To keep it: reopen the issue on GitHub (a reopened issue reopens its task by itself,
    if a sync had closed it). Or, if the issue is gone, `hub new` a replacement task,
    which gets a fresh issue, and drop the old one as above. Don't edit `board.json` by
    hand.
- **An owner edited their own task on GitHub:** gh-sync takes it in by itself (no warning) and
  Zeus's inbox gets `<Owner> edited #N: <diff>`. Check the change still serves IDEA.md; review
  their PR against the new brief. An edit that changes `Files:` still warns: that is a
  change-request.
- **The board** (GitHub Project, linked to the repo) is updated at the end of every sync:
  Todo → In progress (a branch `N-…` exists) → In review (an open PR says `Closes #N`) → Done.
  A board error is one warning line; the sync itself carries on. A new card can take a few
  seconds to appear on the board after a sync; the next sync never duplicates it.
- **An owner changes:** the next sync updates IDEA.md's "Areas and owners" table itself.
- **A task is added after publishing:** put it in `IDEA.md` ("What we build" and the owners
  table) and give it a box on the C4 diagram *before* syncing. Otherwise its owner's PR
  has no box to name under Impact.
- **Branches and PRs:** Hermes reviews (Reviewer section) and hub live merges; by hand, only when hub live is down, Zeus alone merges. On each loop, check `gh pr list -R <repo>` and
  each owner's branch for pushes. Read each PR with `gh pr diff <PR> -R <repo>` and
  `gh pr view <PR> -R <repo> --json title,body,files,reviews,comments,baseRefName,headRefOid`.
  Plain `gh pr view` fails on gh older than 2.77; the `--json` form works on 2.63 and newer.
  A PR based on `main` gets `gh pr edit <PR> -R <repo> --base integration` first. Review it
  against its issue, `IDEA.md` and its owner's area (a pool issue: exactly its `Files:`).
  Note the full 40-character `headRefOid` you reviewed (GitHub rejects a short one); merging with
  `--match-head-commit <it>` makes a push
  after the review fail the merge instead of slipping in. Then either:
  - `gh pr review <PR> -R <repo> --approve` and
    `gh pr merge <PR> -R <repo> --squash --delete-branch --match-head-commit <sha>`; or
  - `gh pr review <PR> -R <repo> --request-changes` with exactly what to fix.

  GitHub doesn't let an account approve, or request changes on, its own PR, and Zeus's
  and Prometheus's PRs come from the lead's account. For those, ask for fixes with
  `gh pr review <PR> -R <repo> --comment`, and merge with `gh pr merge <PR> -R <repo>
  --admin --squash --delete-branch --match-head-commit <sha>` after the same review.
- **Merge order:** merge PRs in dependency order (issues say `Depends on: #N`). After each
  merge, check the others: `gh pr list -R <repo> --json number,mergeable`. On every
  `CONFLICTING` PR, comment: "integration moved: run `git pull --no-rebase origin
  integration`, fix the conflicts in your area, push."
- **After every merge into `integration`: smoke, then promote or revert.** Never in
  `$HUB_CODE_DIR/<p>` itself: Prometheus builds there. Use a throwaway worktree:
  ```bash
  P=$HUB_CODE_DIR/<p>
  git -C "$P" fetch -q origin && d=$(mktemp -d) &&
    git -C "$P" worktree add -q --detach "$d" origin/integration &&
    sha=$(git -C "$d" rev-parse HEAD) && {
      cp "$P/.env" "$d"/ 2>/dev/null
      (cd "$d" && timeout 300 sh -c '<Smoke command from HACKATHON.md>'); ok=$?   # never pipe this
    } || ok=setup
  git -C "$P" worktree remove --force "$d" 2>/dev/null
  ```
  Never pipe the smoke (`| tail` etc.): `ok=$?` would then be the pipe's last command, not the
  smoke. `ok=setup` means the fetch or checkout failed: fix that and rerun; nobody's merge is at fault.
  **Green** (`ok` is 0): `git -C "$P" push origin "$sha:refs/heads/main"`. It promotes exactly
  the commit the smoke tested, and fails if `main` moved some other way.
  **Red:** find the squash commit, `gh pr view <PR> -R <repo> --json mergeCommit --jq .mergeCommit.oid`,
  and revert it in a fresh worktree:
  ```bash
  d=$(mktemp -d) && git -C "$P" worktree add -q --detach "$d" origin/integration &&
    git -C "$d" revert --no-edit <sha> && git -C "$d" push origin HEAD:integration
  git -C "$P" worktree remove --force "$d"
  ```
  Then `gh issue reopen <N> -R <repo> --comment "Reverted: the smoke failed after #<PR> merged.
  <failing output>. Fix it on the same branch and open a new PR."` Reopening puts the issue
  back in the owner's open list. Its hub task reopens only if a sync had already closed it; a
  revert that comes before any sync leaves the task open, which is the same thing. `main` never
  moved.
- **Zeus's own commits on the event repo** (the IDEA.md table, docs) follow the revert's
  pattern: a throwaway worktree on `origin/integration`, commit, `git -C "$d" push origin
  HEAD:integration`, then smoke and promote. Never commit in `$HUB_CODE_DIR/<p>` once Prometheus
  works there.
- **At code freeze:** `hub gh-sync --project <p> --freeze`. It tags `freeze` on `main` once
  (`tagged freeze at <sha>`; a rerun prints `freeze tag already set; keeping it`) and re-runs the
  `freeze-gate` check on every open PR, since a PR checked before the freeze carries a stale
  pass. Checks still running are waited for (2 minutes in all) and then re-run. Any gate it
  could not refresh is named and `--freeze` exits non-zero: run it again once those checks finish,
  until it exits 0. Only then is the freeze in force. From then on GitHub itself refuses a PR to `integration` unless it is labelled `fix`
  (`--init` made `freeze-gate` a required check and sets the `FREEZE_AT` variable; a moved code
  freeze in hackathon.json re-sets it on the next sync). Add `fix` only to real fixes, with
  `gh api -X POST repos/<repo>/issues/<PR>/labels -f 'labels[]=fix'` (`gh pr edit --add-label`
  fails on gh older than 2.77, like plain `gh pr view`). Never
  `--admin` a PR whose `freeze-gate` failed: `--admin` skips required checks. Each fix moves
  `main` only on a green smoke. The demo and final runs use `main`.
- **A repo made from the template before template b262764** (areas and `integration`) still
  says `main` in its own AGENTS.md; one made before b0cb6ac has no Questions section. Before rerunning `--init` on it, bring in the new AGENTS.md, README.md,
  HACKATHON.md `Smoke:` line and IDEA.md table, and retarget open PRs with
  `gh pr edit <n> -R <repo> --base integration`. A moved deadline alone doesn't need `--init`:
  `gh api -X PATCH repos/<repo>/milestones/<number> -f due_on=<UTC time>`.
- **Issues a teammate opened in their own area** (AGENTS §6) aren't on the hub board, so
  gh-sync never announces them. Expect PRs that close them: review against the area and
  `IDEA.md` like any other; the sync puts the issue in its IDEA.md row.
- **A PR whose diff leaves its owner's area** without an accepted change-request: request
  changes, whatever else it does well.
- **Re-review on push:** any push to an approved PR cancels the approval (stale-review
  dismissal). Review it again before merging.
- **A secret in a PR or a push** (API key, token, `.env`): don't merge it. Tell the lead at
  once. The key has to be **revoked at its provider**, because the repo is public and
  deleting the commit doesn't un-leak it. Then have the owner remove it from the branch.
- **gh-sync warns that someone hasn't accepted the invite:** nudge them. Their issues are
  already there, unassigned.
- **Questions**, each pass:
  `gh issue list -R <repo> --label question --state open --limit 200 --json number,title,body,assignees,createdAt,comments`.
  A question's owner is its assignee or, if it has none, the handle @mentioned in its body.
  An unassigned one whose owner has since accepted the invite gets
  `gh issue edit <N> -R <repo> --add-assignee <handle>`. Skip any that already carry the
  owner's answer: it's waiting for the asker, not the owner.
  - **For the lead** (the core, or a Zeus or Prometheus area): show it to the lead at
    this pass with a draft answer. The lead decides; Zeus posts it with
    `gh issue comment <N> -R <repo> --body-file <file>` and leaves the issue open for the asker.
  - **For anyone else**, open over 20 minutes with no answer comment: comment
    `@<owner> this is waiting on you`, unless it already carries that comment (read it from
    `comments`, not from memory: a restarted Zeus must not nag twice). Still unanswered 20
    minutes after that comment, tell the lead.
  - **Prometheus's questions** arrive by hubmsg: open them with
    `--label question --label agent:prometheus`, and relay the answer back by hubmsg.
  - Zeus never answers for another owner or reroutes a question.
- **A branch with no pushes for an hour** while its issue is open: ask its owner in an
  issue comment what's blocking them.

## Never

- Fork the template. Use `gh repo create --template`, which `--init` does.
- Put plans, specs or reviews in the team repo. They go to `$HUB_DIR/projects/<project>/`.
- Edit `AGENTS.md` for one event. Event details go in `HACKATHON.md`.
- Merge a PR that doesn't match its issue, `IDEA.md` or its owner's area, or that
  contains a secret.
