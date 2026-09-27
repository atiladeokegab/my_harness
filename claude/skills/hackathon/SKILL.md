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

The lead plans here; teammates never touch the hub. Each event repo is made from your
copy of the `hackathon_teamwork` template, whose `AGENTS.md` makes every agent plan before
coding, branch per issue, stay in its files and raise change-requests. This skill gets
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
  - It works on a local branch named `<N>-<slug>`, commits, and messages Zeus.
  - Zeus pushes that branch and opens the PR for it (`gh pr create`, with the PR
    template), then reviews it like any other.
- **Teammates** build their own sections, push to their branches after every commit, and
  never merge.

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

Plan it the way you plan any multi-agent project: agree the design with the lead
(brainstorm it, challenge every decision, draw it), write the spec and the plan, then put
each task on the board with `hub new --project <project>`. Every task `--detail` carries
these headings, one per line, because teammates' agents rely on them:

```
Context:
Files:        <the only files this task may touch>
Approach:
Acceptance:
Verify:
Deadline:     <a deadline name from hackathon.json>
```

Write `Verify:` commands that run on any teammate's machine: `python3`, not `python`.

## 3. Submission track

Always add three tasks with `Deadline: submit`:

- the demo script
- the recording
- the submission form

## 4. Assignment grill

For each task, recommend one owner:

- a roster name
- a hub agent on your roster, as the lead's hands
- `pool`: unassigned; whoever finishes early takes it

Base the recommendation on strengths, balanced load, and one owner per file. Ask with one
AskUserQuestion per task, recommendation first. Then `hub assign <id> <name>` (or
`hub assign <id> pool`), then the lead's approval of the whole board.

## 5. IDEA.md: the gate

Before anything reaches GitHub, Zeus writes `IDEA.md` from the approved spec: the problem,
the idea, what we build, what we don't build, the demo in one line, and the **sections and
owners** table from the assignment grill. The lead approves it.
**No issue is synced until `IDEA.md` is approved.** Issue numbers go into the owners table
after the first sync.

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
   - `IDEA.md`: the approved text
   - `HACKATHON.md`: from `hackathon.json`, both the event-time and the **UTC** column
     (agents check the clock against UTC)
   - `README.md`: the title, the intro, the real `gh repo clone <you>/<p>` line,
     and the C4 PNGs in Architecture
4. Check that nothing is left:
   `grep -n "<[A-Za-z]\|<!--" README.md IDEA.md HACKATHON.md` must print nothing. A
   teammate who follows a placeholder literally gets a shell error, and an empty
   Architecture section leaves their agent with no boxes to name.
5. Commit and push, after confirming with the lead: pushing is outward-facing.
6. Run `hub gh-sync --project <p>`. Every task becomes an issue.
7. Put the real issue numbers into `IDEA.md`'s sections-and-owners table. Check each
   number against `gh issue list` (the title must match the section), then commit and push.
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
- **An owner changes:** update `IDEA.md`'s sections-and-owners table to match, then commit
  and push.
- **A task is added after publishing:** put it in `IDEA.md` ("What we build" and the owners
  table) and give it a box on the C4 diagram *before* syncing. Otherwise its owner's PR
  has no box to name under Impact.
- **Branches and PRs:** Zeus alone merges. On each loop, check `gh pr list` and each
  owner's branch for pushes. Read each PR with `gh pr diff <PR>` and
  `gh pr view <PR> --json title,body,files,reviews,comments`. Plain `gh pr view` fails on
  gh older than 2.77; the `--json` form works on 2.63 and newer. Review it against its
  issue, `IDEA.md` and the task's `Files:`. Then either:
  - `gh pr review --approve` and `gh pr merge --squash --delete-branch`; or
  - `gh pr review --request-changes` with exactly what to fix.

  GitHub doesn't let an account approve, or request changes on, its own PR, and hub
  agents' PRs come from the lead's account. For those, ask for fixes with
  `gh pr review --comment`, and merge with `gh pr merge --admin --squash --delete-branch`
  after the same review.
- **Merge order:** merge PRs in dependency order. After each merge, check the others:
  `gh pr list --json number,mergeable`. On every `CONFLICTING` PR, comment: "main moved:
  run `git pull --no-rebase origin main`, fix the conflicts in your files, push."
- **Re-review on push:** any push to an approved PR cancels the approval (stale-review
  dismissal). Review it again before merging.
- **A secret in a PR or a push** (API key, token, `.env`): don't merge it. Tell the lead at
  once. The key has to be **revoked at its provider**, because the repo is public and
  deleting the commit doesn't un-leak it. Then have the owner remove it from the branch.
- **gh-sync warns that someone hasn't accepted the invite:** nudge them. Their issues are
  already there, unassigned.
- **A branch with no pushes for an hour** while its issue is open: ask its owner in an
  issue comment what's blocking them.

## Never

- Fork the template. Use `gh repo create --template`, which `--init` does.
- Put plans, specs or reviews in the team repo. They go to `~/hub/projects/<project>/`.
- Edit `AGENTS.md` for one event. Event details go in `HACKATHON.md`.
- Merge a PR that doesn't match its issue, `IDEA.md` or its `Files:` list, or that
  contains a secret.
