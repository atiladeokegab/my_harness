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
gh repo create <you>/hackathon_teamwork --template atiladeokegab/hackathon_teamwork --public --clone
cd hackathon_teamwork
echo "* @<you>" > .github/CODEOWNERS
git commit -am "chore: I own this template" && git push
gh repo edit <you>/hackathon_teamwork --template
```

Then every event's `hackathon.json` names it as `"template"`.

## Roles

- **The lead agent thinks** (`$HUB_LEAD`, Zeus by default; "Zeus" below). It owns the
  idea, `IDEA.md`, the plan, every task brief, every PR review and every merge. Run it on
  your strongest model.
- **Other hub agents build** only the tasks they are assigned, on the lead's GitHub
  account (their issues are labelled `agent:<name>`). A Claude agent works like a
  teammate. A **Codex agent** (Prometheus by default) is sandboxed: it can write only the
  directory it was launched in (plus the hub), and it has **no GitHub access**. So:
  - Before giving it event tasks, relaunch it in the event repo:
    `hubkill prometheus`, then `prometheus <event>`.
  - **Plan first, through Zeus.** It sends its plan to Zeus by hubmsg; Zeus posts it as the
    issue's plan comment (`gh issue comment <N> -R <repo> --body-file <file>`) and replies
    with the comment's URL. Only then does it write code.
  - It works on a local branch named `<N>-<slug>`, commits, and messages Zeus.
  - Zeus pushes that branch and opens the PR for it
    (`gh pr create -R <repo> --head <branch> --base integration --body-file <file>`, from the
    PR template), then reviews it like any other and relays review comments by hubmsg.
  - **It never runs `hub done` on a task that has an issue.** The task closes when gh-sync
    sees its issue close, so a smoke revert that reopens the issue reopens the task too.
- **Teammates** build in their own areas, push to their branches after every commit, and
  never merge.

## The planning session: the team at the lead's laptop

Everything from §0 to §6 happens with the whole team in the room, in front of the lead's
screen. Zeus asks one question at a time, as always, and **the room answers**:

- Each teammate answers the roster questions about themselves.
- **Pitch round, before Zeus proposes anything.** Once the track and deadlines are settled,
  first ask one question: is everyone round the lead's laptop, or should Zeus collect ideas
  from each person separately? Recommend "round one laptop"; that is the usual case.
  - **Round one laptop:** one open question to the room: "Every idea on the table, one per
    line, with whose it is." No suggestions to choose from. The room talks; the lead types.
  - **Separately:** one question per person, "What would you build, in one line?",
    showing only that person's strengths.

  Then Zeus adds at most one pitch of its own, labelled as Zeus's. The room shortlists, and
  the brainstorm and design continue together from the chosen pitch. Only after that are
  builds and tasks handed out by strengths (§4). Without this round every option comes from
  Zeus and the room only picks between them. The spec names whose pitch it grew from.
- In the brainstorm and the grill, a teammate's own idea is an answer: it comes in as
  "Other", and Zeus weighs it like any option.
- Every approval is the team's decision. The lead gives it, and records "team agreed"
  (or the disagreement) with it.
- In the assignment grill, people claim tasks aloud; the recommendation is still shown first.
- Nobody leaves until §6 has published: every teammate has accepted the invite, logged in
  with `gh auth login`, and seen their own issues assigned to them.

**Timebox: the session ends by build start + 60 minutes**, publish included. Grill only the
decisions that change scope, ownership or acceptance; every smaller assumption goes into an
`Assumptions` section of the spec instead of a question. At build start + 45 minutes, say how
much is left and cut to it.

The plans, specs and reviews on the lead's screen still live only in the hub's `projects/` folder, never in the team repo.

## 0. Deadlines first

When the lead pastes the event brief, before any design, extract:

- every date and time: submission, code freeze, judging, check-ins, mentor sessions
- the rules and the judging criteria

Show them as one table with absolute ISO 8601 times and a timezone, and confirm with one
AskUserQuestion. There is always a `code freeze` and a `submit`; if the brief names no
freeze, recommend submit minus 60 minutes.

## 1. Project and roster

- Pick a lowercase project tag (e.g. `lablab-oct26`) and make `~/hub/projects/<project>/`.
  **The event repo is named exactly the tag** (`<you>/lablab-oct26`). gh-sync
  refuses anything else, and refuses any repo not created from the template, so a typo
  can never point it at a real repo.
- For each teammate, ask name, GitHub handle, strengths and AI tool, one question at a
  time. Mark the lead `"lead": true`. The roster `name` is the one-word name you'll assign
  tasks to: for "Sam Lee", use `SamLee` or their GitHub handle.
- Roster names become hub task owners, so each is **one word** (letters, digits, `_`, `-`),
  unique, and not a hub agent's name or `Pool`. The hub capitalises them (`deshawn` →
  `Deshawn`), and gh-sync matches either spelling. gh-sync checks the whole file and names
  anything wrong before it touches GitHub.
- Write `~/hub/projects/<project>/hackathon.json`:

```json
{"repo": "<you>/<event-repo>", "template": "<you>/hackathon_teamwork", "timezone": "Europe/London",
 "deadlines": [{"name": "code freeze", "at": "..."}, {"name": "submit", "at": "..."}],
 "roster": [{"name": "...", "github": "...", "lead": true, "strengths": "...", "tool": "..."}]}
```

## 2. Design, spec, plan

Plan it the way you plan any multi-agent project: agree the design with the room
(brainstorm it, challenge every decision, draw it), write the spec and the plan, then put
each task on the board with `hub new --project <project>`.

**The idea is fixed when the design is approved, not at the end.** Zeus then writes the
hub's `projects/<project>/IDEA.md`: the problem, the idea, what we build, what we don't
build, the demo in one line, and the "Areas and owners" table with the areas and their
directories filled in and the Owner and Issues cells left as `—`. The lead approves IDEA.md
together with the design drawings; the spec, plan and board build on it.

The design names the **areas** (a set of directories each, split by strength) and the
**core** (shared contracts; Zeus owns it), and one **smoke command**: the unit tests plus one
end-to-end run on a few sample inputs, under 2 minutes. It runs in a clean checkout with only
`.env` copied in, so it includes its own install step (`uv run …` installs; `npm ci && …`).
Until the pipeline exists, the smoke is the tests alone. Every task's `Files:` is its area's
directories.

Every task `--detail` carries these headings, one per line, because teammates' agents rely
on them:

```
Context:
Files:        <the area's directories: the owner may change anything inside them>
Approach:
Acceptance:
Verify:
Deadline:     <a deadline name from hackathon.json>
```

Write `Verify:` commands that run on any teammate's machine: `python3`, not `python`.

## 3. Submission track

Always add three tasks:

- the demo script, `Deadline: code freeze` for the first draft, then adjusted after the final
  run, so the recording is a rehearsal and not a discovery
- the recording, `Deadline: submit` (or the demo-video deadline if the event has one)
- the submission form, `Deadline: submit`

## 4. Assignment grill

Assign **areas first**: one question per area, recommendation first, based on strengths
and balanced load; a teammate claiming an area overrides. An area's owner is a roster name,
or a hub agent on your roster as the lead's hands. Every task in an area inherits its owner.
Ask per task only for the core (always Zeus) and for work outside any area, which may go to
`pool`: unassigned, whoever finishes early takes it (submission, docs, diagrams). Then
`hub assign <id> <name>` (or `hub assign <id> pool`), then the lead's approval of the whole
board.

## 5. IDEA.md: the gate

IDEA.md was approved with the design (§2). After the board is approved, fill in its **Areas
and owners** table from the assignment: owners and hub task IDs. That is bookkeeping, not a
new approval. Re-open IDEA.md for approval only if the spec, plan or board changed what we
build or don't build since then; say which lines changed.
**No issue is synced until `IDEA.md` is approved.** Issue numbers replace the task IDs in
the owners table after the first sync.

## 6. Publish

0. **Visibility.** `--init` makes a **public** repo. Check the event rules (and sponsor
   IP terms) allow that, and that every teammate is fine with public code. If public is
   not allowed, stop and tell the lead: the kit needs a private-repo variant, and private
   repos on a free account lose branch protection.
1. Run `hub gh-sync --project <p> --init --dry-run` and read what it would do.
2. Run `hub gh-sync --project <p> --init`. This creates the repo from the template, invites
   the roster, and sets up labels, milestones and branch protection.
3. `--init` only provisions. No issue exists until step 6. In the new clone, fill in
   every placeholder:
   - `IDEA.md`: the approved text, with the "Areas and owners" table
   - `HACKATHON.md`: from `hackathon.json`, both the event-time and the **UTC** column
     (agents check the clock against UTC), and the `Smoke:` command from the design
   - `README.md`: the title, the intro, the real `gh repo clone <you>/<p>` line,
     and the C4 PNGs in Architecture
4. Check that nothing is left:
   `grep -n "<[A-Za-z]\|<!--" README.md IDEA.md HACKATHON.md` must print nothing, and
   every C4 image README links must exist in the clone:
   ```bash
   imgs=$(grep -o 'docs/architecture/c4_[a-z]*\.png' README.md | sort -u)
   [ -n "$imgs" ] && for f in $imgs; do [ -s "$f" ] || echo "missing $f"; done
   ```
   must print nothing and exit 0 (no link at all exits 1). A teammate who follows a
   placeholder literally gets a shell error, and an empty Architecture section leaves
   their agent with no boxes to name. Until the Architecture task redraws them from real
   code, copy the approved planning PNGs from the hub's `projects/<p>/` to
   `docs/architecture/`.
5. Commit on `integration` and push, after confirming with the lead: pushing is
   outward-facing. `--init` cloned before `integration` existed, and Zeus runs from `~/hub`,
   so name the repo on every command:
   ```bash
   P="${HUB_CODE_DIR:-$HOME/code}/<p>"
   git -C "$P" fetch origin && git -C "$P" checkout integration
   git -C "$P" add IDEA.md HACKATHON.md README.md docs/architecture
   git -C "$P" commit -m "docs: fill in the event"
   git -C "$P" push origin integration && git -C "$P" push origin integration:main
   ```
   Do this before a Codex agent is relaunched in that checkout.
6. Run `hub gh-sync --project <p>`. Every task becomes an issue.
7. Put the real issue numbers into `IDEA.md`'s "Areas and owners" table. Check each
   number against `gh issue list` (the title must fit the area), then commit it as
   **Zeus's own commits** in §7 describes.
8. Give the lead the repo URL to share with the team, and list who hasn't accepted the
   invite yet:
   `gh api repos/<repo>/invitations --jq '.[].invitee.login'`.
   GitHub can't assign an issue to someone who hasn't accepted. gh-sync creates their
   issues unassigned, warns, and assigns them on the first sync after they accept. Tell
   each teammate to accept before they tell their agent to pick up work, and to log in with
   `gh auth login` (browser). A fine-grained personal access token (`github_pat_…`) can't
   accept the invite, and fails in a repo it doesn't own with "Resource not accessible by
   personal access token".

## 7. Live

**Every pass starts with the clock**, the same rule the teammates' agents follow:
`date -u` against the UTC column of `HACKATHON.md`.
- **Before code freeze:** everything below.
- **After code freeze:** no new feature tasks, no feature replans, no feature merges.
  Only fixes, demo and submission work.
- **After submit:** stop the loop. Nothing more is merged or synced.

**Source of truth:** the hub owns each brief (title, body, owner, milestone); GitHub owns who
picked up pool work and what got closed. A brief edited on GitHub is never overwritten: Zeus
folds the edit into the hub task, then syncs.

**Every GitHub command names the repo** (`-R <owner>/<p>`) and a number: Zeus runs from
`~/hub`, where a bare `gh pr list` finds no repo, and from any other checkout it would act on
the wrong one. **One integration pass at a time:** finish one merge's smoke and its promote
or revert before merging the next.

**If Zeus is down, the lead is the backup.** All state lives on the board and on GitHub, so the
lead relaunches `zeus` in the event repo and it picks up from `hub brief` and `gh pr list`. In
the last 30 minutes before a deadline, the lead may merge a PR Zeus has already reviewed, or
one with green checks that matches its issue, with `gh pr merge <PR> -R <repo> --admin
--squash --delete-branch --match-head-commit <reviewed sha>`, rather than wait, then smoke and promote as the Live loop does: the demo
runs from `main`, so a merge that never reaches it is missing from the demo.

- **Keep the board in step:** start
  `/loop 10m run hub gh-sync --project <p>, then do the hackathon skill's Live review pass`.
  A sync is safe to repeat, and an overlapping one refuses to start. Fix any `error:` line
  it prints, then rerun.
- **A change-request in the inbox:**
  1. Re-plan the affected tasks, and challenge the design again if it is architectural.
  2. Redraw the C4 and edit the hub tasks.
  3. Sync. gh-sync posts "Brief updated" on each changed issue.
- **gh-sync warns that an issue was edited on GitHub:** fold the edit into the hub task,
  then sync. The issue's title and milestone wait for the brief too.
- **gh-sync warns that an issue was closed as not planned, or not found:** decide.
  - To drop the task: `hub claim <id> --force`, then `hub done <id> --note "dropped: #N"`.
  - To keep it: reopen the issue on GitHub (a reopened issue reopens its task by itself,
    if a sync had closed it). Or, if the issue is gone, `hub new` a replacement task,
    which gets a fresh issue, and drop the old one as above. Don't edit `board.json` by
    hand.
- **An owner changes:** update `IDEA.md`'s "Areas and owners" table to match, as one of
  **Zeus's own commits** (below).
- **A task is added after publishing:** put it in `IDEA.md` ("What we build" and the owners
  table) and give it a box on the C4 diagram *before* syncing. Otherwise its owner's PR
  has no box to name under Impact.
- **Branches and PRs:** Zeus alone merges. On each loop, check `gh pr list -R <repo>` and
  each owner's branch for pushes. Read each PR with `gh pr diff <PR> -R <repo>` and
  `gh pr view <PR> -R <repo> --json title,body,files,reviews,comments,baseRefName,headRefOid`.
  Plain `gh pr view` fails on gh older than 2.77; the `--json` form works on 2.63 and newer.
  A PR based on `main` gets `gh pr edit <PR> -R <repo> --base integration` first. Review it
  against its issue, `IDEA.md` and its owner's area (a pool issue: exactly its `Files:`).
  Note the `headRefOid` you reviewed; merging with `--match-head-commit <it>` makes a push
  after the review fail the merge instead of slipping in. Then either:
  - `gh pr review <PR> -R <repo> --approve` and
    `gh pr merge <PR> -R <repo> --squash --delete-branch --match-head-commit <sha>`; or
  - `gh pr review <PR> -R <repo> --request-changes` with exactly what to fix.

  GitHub doesn't let an account approve, or request changes on, its own PR, and hub
  agents' PRs come from the lead's account. For those, ask for fixes with
  `gh pr review <PR> -R <repo> --comment`, and merge with `gh pr merge <PR> -R <repo>
  --admin --squash --delete-branch --match-head-commit <sha>` after the same review.
- **Merge order:** merge PRs in dependency order (issues say `Depends on: #N`). After each
  merge, check the others: `gh pr list -R <repo> --json number,mergeable`. On every
  `CONFLICTING` PR, comment: "integration moved: run `git pull --no-rebase origin
  integration`, fix the conflicts in your area, push."
- **After every merge into `integration`: smoke, then promote or revert.** Never in
  the event checkout itself: a Codex agent may be building there. Use a throwaway worktree:
  ```bash
  P="${HUB_CODE_DIR:-$HOME/code}/<p>"
  git -C "$P" fetch -q origin && d=$(mktemp -d) &&
    git -C "$P" worktree add -q --detach "$d" origin/integration &&
    sha=$(git -C "$d" rev-parse HEAD) && {
      cp "$P/.env" "$d"/ 2>/dev/null
      (cd "$d" && timeout 300 sh -c '<Smoke command from HACKATHON.md>'); ok=$?
    } || ok=setup
  git -C "$P" worktree remove --force "$d" 2>/dev/null
  ```
  `ok=setup` means the fetch or checkout failed: fix that and rerun; nobody's merge is at fault.
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
  back in the owner's open list and reopens its hub task. `main` never moved.
- **Zeus's own commits on the event repo** (the IDEA.md table, docs) follow the revert's
  pattern: a throwaway worktree on `origin/integration`, commit, `git -C "$d" push origin
  HEAD:integration`, then smoke and promote. Never commit in the event checkout once a Codex agent
  works there.
- **At code freeze**, once (a rerun keeps the first tag):
  `P="${HUB_CODE_DIR:-$HOME/code}/<p>"; git -C "$P" fetch -q origin && { git -C "$P" ls-remote --exit-code --tags origin freeze >/dev/null || { git -C "$P" tag freeze origin/main && git -C "$P" push origin freeze; }; }`.
  After it, only
  fixes merge, and each moves `main` only on a green smoke. The demo and final runs use `main`.
- **A repo made from an older copy of the template** (before areas and `integration`) still
  says `main` in its own AGENTS.md, and may have no Questions section. Before rerunning `--init` on it, bring in the new AGENTS.md, README.md,
  HACKATHON.md `Smoke:` line and IDEA.md table, and retarget open PRs with
  `gh pr edit <n> -R <repo> --base integration`. A moved deadline alone doesn't need `--init`:
  `gh api -X PATCH repos/<repo>/milestones/<number> -f due_on=<UTC time>`.
- **Issues a teammate opened in their own area** (AGENTS §6) aren't on the hub board, so
  gh-sync never announces them. Expect PRs that close them: review against the area and
  `IDEA.md` like any other, and add the issue to IDEA.md's "Areas and owners" row as one of
  Zeus's own commits.
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
  - **For the lead** (the core, or a hub agent's area): show it to the lead at
    this pass with a draft answer. The lead decides; Zeus posts it with
    `gh issue comment <N> -R <repo> --body-file <file>` and leaves the issue open for the asker.
  - **For anyone else**, open over 20 minutes with no answer comment: comment
    `@<owner> this is waiting on you`, unless it already carries that comment (read it from
    `comments`, not from memory: a restarted Zeus must not nag twice). Still unanswered 20
    minutes after that comment, tell the lead.
  - **A Codex agent's questions** arrive by hubmsg: open them with
    `--label question --label agent:<its name>`, and relay the answer back by hubmsg.
  - Zeus never answers for another owner or reroutes a question.
- **A branch with no pushes for an hour** while its issue is open: ask its owner in an
  issue comment what's blocking them.

## Never

- Fork the template. Use `gh repo create --template`, which `--init` does.
- Put plans, specs or reviews in the team repo. They go to `~/hub/projects/<project>/`.
- Edit `AGENTS.md` for one event. Event details go in `HACKATHON.md`.
- Merge a PR that doesn't match its issue, `IDEA.md` or its owner's area, or that
  contains a secret.
