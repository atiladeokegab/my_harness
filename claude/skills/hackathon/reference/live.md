# Live duties in detail (§7)

Read when a §7 situation comes up: a gh-sync warning, a change-request, a DONE, a merge, a red smoke, the
code freeze, a question, or hub live being down. hub live does the mechanical duties; Zeus does them by
hand only when hub live is down (SKILL.md §7). Every GitHub command names the repo (`-R <owner>/<p>`).

## Contents
- Running the loop by hand
- Watching the breakdowns
- Change-requests
- gh-sync warnings and board changes
- DONE → PR
- Reviewing and merging by hand
- Merge order and conflicts
- Smoke, then promote or revert
- Zeus's own commits
- Code freeze
- Questions
- Other situations
- Old patterns

## Running the loop by hand

Only when hub live is down (check: `tmux has-session -t hub-live-<p>` and the last line of
`$HUB_DIR/projects/<p>/live.log`). Start
`/loop 5m run scripts/team-inbox.sh --lead (and hub gh-sync --project <p> every other pass), then do the hackathon skill's Live review pass`.

- Scheduled deadline jobs fire only when the session is idle, so they can run late (dry run #1:
  10 minutes). Schedule each deadline job 5 minutes early, and at the start of every pass check whether
  a deadline in HACKATHON.md is due within 10 minutes; if so, do it now.
- A sync is safe to repeat, and an overlapping one refuses to start. Fix any `error:` line it prints,
  then rerun.
- On each loop, check `gh pr list -R <repo>` and each owner's branch for pushes.

## Watching the breakdowns

Sub-issues change live all event: owners add, edit and close their own. `scripts/team-inbox.sh --lead`
(run in Zeus's clone) prints NEW, CHANGED, CLOSED and DRAFT lines per vertical. Check each NEW or
CHANGED one against **the line**: `Files:` inside the vertical's `Files:`, the `Contract:` unchanged,
the design unchanged, and it serves `IDEA.md` (nothing from "What we don't build", the same demo).

- **Inside the line:** nothing to do; the next sync imports it.
- **A problem with a live one:** **one** comment on it that starts with `FLAG:` (the inbox matches on
  that, because on the lead's shared account the author can't tell Zeus from an owner's agent),
  addressed to the owner: the problem, the `IDEA.md` line, contract or design section it breaks, and a
  proposed fix. Their inbox shows it as FLAG; their agent fixes it itself when those decide it, or asks
  its human. If you still disagree after one exchange, show the lead both sides and post the lead's
  call.
- **A DRAFT** (it says `Crosses: …`): decide within 10 minutes. Remove `draft`
  (`gh issue edit <N> -R <repo> --remove-label draft`; their inbox shows READY), or close it as not
  planned with the reason, or re-plan it as a change-request below.

## Change-requests

- **A design change-request** (addressed to the designer): the designer decides, with Zeus. Once
  decided, the designer changes `docs/design.md` or `docs/mockup/` in their own PR, and Zeus runs
  `hub edit` on each affected vertical's `Design:` line so its owner's agent gets "Brief updated".
- **A change-request in the inbox:**
  1. Re-plan the affected tasks, and grill if the change is architectural.
  2. Redraw the C4 and change the briefs with `hub edit N` (Zeus: `hub edit N --detail-file F --yes`;
     the diff is printed either way), each with a dated line under `## Changes since approval`
     ([briefs.md](briefs.md)). `--title` and `--deadline <name>` change those.
  3. Sync. gh-sync posts "Brief updated" on each changed issue.
- **A task added after publishing:** put it in `IDEA.md` ("What we build" and the owners table) and give
  it a box on the C4 diagram *before* syncing. Otherwise its owner's PR has no box to name under Impact.

## gh-sync warnings and board changes

**Source of truth:** the hub owns each brief (title, body, owner, milestone); GitHub owns who picked up
pool work and what got closed. A brief edited on GitHub is never overwritten.

- **`#N was edited on GitHub; not overwriting`** (with a diff), on every sync until you decide:
  - to keep their text: `hub edit N --take-github --yes`, then sync (one "Brief updated");
  - to put the brief back: `hub edit N --keep-hub --yes`, then sync (GitHub is overwritten).
  The issue's title and milestone wait for the decision too.
- **An issue was closed as not planned, or not found:** decide.
  - To drop the task: `hub done <id> --force --note "dropped: #N"`.
  - To keep it: reopen the issue on GitHub (a reopened issue reopens its task by itself, if a sync had
    closed it). Or, if the issue is gone, `hub new` a replacement task, which gets a fresh issue, and
    drop the old one as above. Don't edit `board.json` by hand.
- **An owner edited their own task on GitHub:** gh-sync takes it in by itself (no warning) and Zeus's
  inbox gets `<Owner> edited #N: <diff>`. Check the change still serves IDEA.md; review their PR against
  the new brief. An edit that changes `Files:` still warns: that is a change-request.
- **Someone hasn't accepted the invite:** nudge them. Their issues are already there, unassigned.
- **The board** (GitHub Project, linked to the repo) is updated at the end of every sync: Todo → In
  progress (a branch `N-…` exists) → In review (an open PR says `Closes #N`) → Done. A board error is one
  warning line; the sync itself carries on. A new card can take a few seconds to appear after a sync;
  the next sync never duplicates it.
- **An owner changes:** the next sync updates IDEA.md's "Areas and owners" table itself.

## DONE → PR

hub live does this; by hand only if it's down. A teammate's agent never opens a PR: when it's finished
it comments on the issue, first line `DONE:`, with how it verified the work, Impact and Assumptions. hub
live then runs `gh pr create -R <repo> --base integration --head <N>-<slug>` from the lead's account,
titled `<issue title> (#N)`, its body `Closes #N`, the plan comment's link and the DONE text.

- It acts on each `DONE:` once, only from a roster handle.
- It never opens a second PR for a branch that has one open (a `DONE:` after review fixes); after a
  revert, the next `DONE:` opens the new PR.
- Zeus's builders and Hermes still open their own PRs.

## Reviewing and merging by hand

hub live merges a PR on a green smoke with no review when every changed file is outside
`review_before` and inside its issue's `Files:` and its `DONE:` has `Verified:`; anything else waits for
the reviewers' `LGTM` (hackathon-reviewer): one merges by default, two (Prometheus and Atlas)
for a gate, privacy, delivery or security change. By hand, only when hub live is down, Zeus alone merges, and
reviews every PR first.

1. Read it: `gh pr diff <PR> -R <repo>` and
   `gh pr view <PR> -R <repo> --json title,body,files,reviews,comments,baseRefName,headRefOid`. Plain
   `gh pr view` fails on gh older than 2.77; the `--json` form works on 2.63 and newer.
2. A PR based on `main` gets `gh pr edit <PR> -R <repo> --base integration` first.
3. Review it against its issue, `IDEA.md` and its owner's area (a pool issue: exactly its `Files:`). A
   PR whose diff leaves its owner's area without an accepted change-request: request changes, whatever
   else it does well.
4. Note the full 40-character `headRefOid` you reviewed (GitHub rejects a short one); merging with
   `--match-head-commit <it>` makes a push after the review fail the merge instead of slipping in.
5. Then either:
   - `gh pr review <PR> -R <repo> --approve` and
     `gh pr merge <PR> -R <repo> --squash --delete-branch --match-head-commit <sha>`; or
   - `gh pr review <PR> -R <repo> --request-changes` with exactly what to fix.

GitHub doesn't let an account approve, or request changes on, its own PR, and Zeus's, Hermes's,
the reviewers' and (opened by hub live) every teammate's PRs come from the lead's account. For those, ask for fixes with a
comment whose first line starts `CHANGES:` (hub live relays only those; `FYI:` stays quiet), and merge
with `gh pr merge <PR> -R <repo> --admin --squash --delete-branch --match-head-commit <sha>` after the
same review.

**Re-review on push:** any push to an approved PR cancels the approval (stale-review dismissal). Review
it again before merging.

## Merge order and conflicts

Merge PRs in dependency order (issues say `Depends on: #N`). After each merge, check the others:
`gh pr list -R <repo> --json number,mergeable`. On every `CONFLICTING` PR, comment: "integration moved:
run `git pull --no-rebase origin integration`, fix the conflicts in your area, push."

## Smoke, then promote or revert

After every merge into `integration`. Never in `$HUB_CODE_DIR/<p>` itself: Prometheus works there. Use a
throwaway worktree:

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

Never pipe the smoke (`| tail` etc.): `ok=$?` would then be the pipe's last command, not the smoke.
`ok=setup` means the fetch or checkout failed: fix that and rerun; nobody's merge is at fault.

**Green** (`ok` is 0): `git -C "$P" push origin "$sha:refs/heads/main"`. It promotes exactly the commit
the smoke tested, and fails if `main` moved some other way.

**Red:** find the squash commit, `gh pr view <PR> -R <repo> --json mergeCommit --jq .mergeCommit.oid`,
and revert it in a fresh worktree:

```bash
d=$(mktemp -d) && git -C "$P" worktree add -q --detach "$d" origin/integration &&
  git -C "$d" revert --no-edit <sha> && git -C "$d" push origin HEAD:integration
git -C "$P" worktree remove --force "$d"
```

Then `gh issue reopen <N> -R <repo> --comment "Reverted: the smoke failed after #<PR> merged. <failing output>. Fix it on the same branch, push, and post a new DONE: comment (the lead opens the new PR)."`
Reopening puts the issue back in the owner's open list. Its hub task reopens only if a sync had already
closed it; a revert that comes before any sync leaves the task open, which is the same thing. `main`
never moved.

## Zeus's own commits

Zeus's own commits on the event repo (the IDEA.md table, docs) follow the revert's pattern: a throwaway
worktree on `origin/integration`, commit, `git -C "$d" push origin HEAD:integration`, then smoke and
promote. Never commit in `$HUB_CODE_DIR/<p>` once Prometheus works there.

## Code freeze

Run `hub gh-sync --project <p> --freeze`.

- It tags `freeze` on `main` once (`tagged freeze at <sha>`; a rerun prints
  `freeze tag already set; keeping it`) and re-runs the `freeze-gate` check on every open PR, since a PR
  checked before the freeze carries a stale pass.
- Checks still running are waited for (2 minutes in all) and then re-run. Any gate it could not refresh
  is named and `--freeze` exits non-zero: run it again once those checks finish, until it exits 0. Only
  then is the freeze in force.
- From then on GitHub itself refuses a PR to `integration` unless it is labelled `fix` (`--init` made
  `freeze-gate` a required check and sets the `FREEZE_AT` variable; a moved code freeze in
  hackathon.json re-sets it on the next sync).
- Add `fix` only to real fixes, with `gh api -X POST repos/<repo>/issues/<PR>/labels -f 'labels[]=fix'`
  (`gh pr edit --add-label` fails on gh older than 2.77, like plain `gh pr view`).
- Never `--admin` a PR whose `freeze-gate` failed: `--admin` skips required checks.
- Each fix moves `main` only on a green smoke. The demo and final runs use `main`.

## Questions

Each pass:
`gh issue list -R <repo> --label question --state open --limit 200 --json number,title,body,assignees,createdAt,comments`.

A question's owner is its assignee or, if it has none, the handle @mentioned in its body. An unassigned
one whose owner has since accepted the invite gets `gh issue edit <N> -R <repo> --add-assignee <handle>`.
Skip any that already carry the owner's answer: it's waiting for the asker, not the owner.

- **For the lead** (the core, or a Zeus or Hermes area): show it to the lead at this pass with a
  draft answer. The lead decides; Zeus posts it with `gh issue comment <N> -R <repo> --body-file <file>`
  and leaves the issue open for the asker.
- **For anyone else**, open over 20 minutes with no answer comment: comment
  `@<owner> this is waiting on you`, unless it already carries that comment (read it from `comments`,
  not from memory: a restarted Zeus must not nag twice). Still unanswered 20 minutes after that comment,
  tell the lead.
- **Questions from Hermes, Prometheus or Atlas** arrive by message: open them with
  `--label question --label agent:<name>`, and relay the answer back the same way.
- Zeus never answers for another owner or reroutes a question.

## Other situations

- **Issues a teammate opened in their own area** (AGENTS §6) aren't on the hub board, so gh-sync never
  announces them. Expect PRs that close them: review against the area and `IDEA.md` like any other; the
  sync puts the issue in its IDEA.md row.
- **A secret in a PR or a push** (API key, token, `.env`): don't merge it. Tell the lead at once. The key
  has to be **revoked at its provider**, because the repo is public and deleting the commit doesn't
  un-leak it. Then have the owner remove it from the branch.
- **A branch with no pushes for an hour** while its issue is open: ask its owner in an issue comment
  what's blocking them.
- **A moved deadline** doesn't need `--init`:
  `gh api -X PATCH repos/<repo>/milestones/<number> -f due_on=<UTC time>`.

## Old patterns

A repo made from the template before template b262764 (areas and `integration`) still says `main` in
its own AGENTS.md; one made before b0cb6ac has no Questions section. Before rerunning `--init` on it,
bring in the new AGENTS.md, README.md, HACKATHON.md `Smoke:` line and IDEA.md table, and retarget open
PRs with `gh pr edit <n> -R <repo> --base integration`.
