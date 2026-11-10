Paths and commands below resolve from the [skill root](../SKILL.md). Read only the current stage.

## 7. Live

**Who does what.** hub live (a script, every 5 minutes) does the mechanical duties: the sync, a PR for
each teammate's `DONE:`, merges in dependency order at an approved head sha, the smoke → promote or
revert, the conflict comments, the freeze (retried until it exits 0), the unseen-set reminders, the
question nudge (20 min, then Zeus), the idle-branch comment (1 h) and the invite reminder. Prometheus
reviews every PR first and Atlas second (one `LGTM` merges; two for a gate, privacy, delivery or
security change), and they FLAG drifting sub-issues. Zeus gets, by hubmsg: `DRAFT`s, change-requests,
questions for the lead, escalations from the reviewers, gh-sync errors, smoke reverts and the unseen-set
reminders. Zeus does the mechanical duties by hand only if hub live is down (check:
`tmux has-session -t hub-live-<p>` and the last line of `$HUB_DIR/projects/<p>/live.log`), starting the
loop in [live.md](live.md) "Running the loop by hand".

**Never state a time from memory:** run `date` first, every time you tell the lead a time or a
countdown (dry run #4: Zeus narrated from a clock an hour stale; a builder's clock check caught it).

**Every pass starts with the clock**, the same rule the teammates' agents follow: `date -u` against the
UTC column of `HACKATHON.md`.
- **Before code freeze:** everything below.
- **After code freeze:** no new feature tasks, no feature replans, no feature merges. Only fixes, demo
  and submission work.
- **After submit:** stop the loop. Nothing more is merged or synced.

At each checkpoint, re-read the plan's `Lessons applied` table; at freeze minus 45, walk it against
what shipped, beside Prometheus's release review (§0 "Where the lessons bite"). The reviewers enforce
the ledger on every PR, plan and spec with hackathon-reviewer check 13 (a missing `Lessons applied`
table or line, or a repeated ledger failure, is `CHANGES:`).
By build + 60 the first screen is live and judged (`designing-products` G4; lessons 25, 26), then `document` writes `DESIGN.md`.

**Never relay through a human.** Every request to a teammate goes on GitHub as a review, a question or
a brief change; their agent runs `scripts/team-inbox.sh` after each push and every 5 minutes and acts
on it (AGENTS.md §3). If a teammate's agent seems idle, say so to that teammate, but don't send them
text to paste.

**Source of truth:** the hub owns each brief (title, body, owner, milestone); GitHub owns who picked up
pool work and what got closed. A brief edited on GitHub is never overwritten: every sync warns until
the lead decides with `hub edit N --take-github` or `hub edit N --keep-hub`.

**Every GitHub command names the repo** (`-R <owner>/<p>`) and a number: Zeus runs from `$HUB_DIR`, where
a bare `gh pr list` finds no repo, and from any other checkout it would act on the wrong one. **One
integration pass at a time:** finish one merge's smoke and its promote or revert before merging the
next.

**If Zeus is down, the lead is the backup.** All state lives on the board and on GitHub, so the lead
relaunches `zeus` in the event repo and it picks up from `hub brief` and `gh pr list`. In the last 30
minutes before a deadline, the lead may merge a PR Zeus has already reviewed, or one with green checks
that matches its issue, with
`gh pr merge <PR> -R <repo> --admin --squash --delete-branch --match-head-commit <reviewed sha>`,
rather than wait, then smoke and promote as the Live loop does: the demo runs from `main`, so a merge
that never reaches it is missing from the demo.

**The film, in the take window:** the lead records; the render machine builds; Zeus watches each take's
message and routes a red gate per your film pipeline's notes (not shipped) "In the take window". Before
submit, someone who did not cut it frame-checks the last-green film.

**Each situation, in [live.md](live.md):** watching the breakdowns against the line (`FLAG:`,
DRAFTs within 10 minutes), change-requests, gh-sync warnings, `DONE:` → PR, reviewing and merging by
hand, merge order and conflicts, smoke then promote or revert, Zeus's own commits, the code freeze
(`hub gh-sync --project <p> --freeze`), questions, a secret in a PR (never merge; revoke at the
provider), idle branches, moved deadlines and repos from an old template.
