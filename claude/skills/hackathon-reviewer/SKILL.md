---
name: hackathon-reviewer
description: >
  Runs the reviewer's routine for an event run with hackathon: gated PRs before they merge,
  the after-merge digest of everything else, FLAG: on drifting sub-issues, and the release review
  at freeze minus 45. Use when the session is the hub's reviewer (the factory.json agent in phase
  reviewer, or `$HUB_REVIEWER`) reviewing an event repo, when hub live sends "PR #N ready for review", "merged without
  review:" or "release review:", or when Zeus starts a backup reviewer sub-agent; its "Rule
  candidates" section also applies to every factory review the reviewer does. Not for planning or
  building (hackathon), not for merging or reverting (hub live and Zeus do that), and never for
  a PR the reviewer built.
---

# Reviewing a hackathon

The reviewer is `$HUB_REVIEWER`, or the factory.json agent in phase `reviewer` if you run the factory.
The names here are the author's roster: read Prometheus (and the older Hermes) as your reviewer, Atlas
as a second reviewer if you have one, and Zeus as your lead (`$HUB_LEAD`); hackathon SKILL.md maps the rest.

You review; hub live merges; Zeus decides. You never revert, edit code (except a small fix, below),
briefs or `IDEA.md`, never merge or change merge controls,
and never answer a question for an owner. What you check against: `$HUB_DIR/projects/<p>/hackathon.json`,
the repo's `IDEA.md` (areas, `Ceilings`, `Deploy owner`), `docs/CONTRACT.md`, and the issue the PR
closes. Every `gh` command names the repo (`-R <repo>`). `P=$HUB_CODE_DIR/<p>` below.

## Choose the review

For every review, read the relevant risks in [checks](reference/checks.md): secrets,
ownership, trust boundaries, contracts, claims, dependencies, async lifecycle and UI
evidence. Event-only runner/holdout/trace instructions apply when those paths exist.

| Trigger | Read |
|---|---|
| Gated PR or a factory commit review | [operations](reference/operations.md) §1; exact-head verdict and board receipt |
| After-merge digest | [operations](reference/operations.md) §2 |
| New/changed sub-issue | [operations](reference/operations.md) §3 |
| Release review | [operations](reference/operations.md) §4 plus [direction](reference/direction.md) |
| Full review, acceptance checks or direction check | [direction](reference/direction.md), including the required first-principles skill and PRD coverage table |
| Backup reviewer or merge gating rules | [operations](reference/operations.md) |

## Conventions (hub live and every agent's inbox match on these)

- `LGTM <40-char headRefOid>` approves exactly that commit; a later push cancels it.
- `CHANGES: <what to fix, where, and the line it breaks>` is the **only** way to ask for changes.
  hub live relays only these; the author's agent sees them as REVIEW.
- `FYI: <finding>` blocks nothing. A finding that should block is a `CHANGES:`, never an FYI
  (#69: the claim linter was "the biggest lever on our score", posted as FYI; the Reality Test
  then landed 0 DONE / 19 ESCALATED).
- `FLAG: <problem, the line it breaks, a fix>` once, on a drifting sub-issue.
- One verdict per head sha. **Two rounds, then Zeus:** after two `CHANGES:` on one PR, don't ask a
  third time; `hubmsg Zeus "PR #N: <what keeps coming back>"`.

## Fast path or full path (every gated PR and every factory review)

Your job, in the lead's words: the work is aligned to the PRD, the PRs get in quickly, and nothing
breaks. There is no
time budget: **as fast as possible without losing quality**. A budget gets filled, so don't set one.
Put the measured time on the verdict's last line, `review: <n> min, fast|full`, for Zeus to track.

- **Fast path:** under 50 changed lines (`gh pr diff N --stat`, or `git diff --stat` for a commit) and
  no file in `review_before`. Do it alone with no sub-agents, steps 1 to 4 below.
- **Full path:** everything else. At the same moment, start the smoke run (step 2) and three
  read-only sub-agents, at most 3 (4 threads in all).
  Give each the diff, the issue or task, and its PRD line, and ask it one question:
  - **PRD fit:** does the change deliver its PRD line, and nothing outside it?
  - **Breakage:** callers, interfaces, tests, contract or certificate wording; is risky code tested?
  - **Build quality and speed:** is it the smallest change that works; is anything slow or over-built?

  Each lens returns `file:line | failure | fix` lines, or `none`. A lens still running after 5
  minutes is stuck (that is a hang cut-off, not a budget): cancel it and cover it yourself. Check every finding against the code and
  the smoke output yourself, drop any that don't hold, and post one verdict (step 4).

**The PRD line** comes from the task's `--req A-x.y` when the project has a hub spec. Otherwise it
comes from the issue's `Acceptance` and `IDEA.md` row (events), or the task brief and `PRODUCT.md`
(product work). If none exists, review anyway and `hubmsg Zeus "FYI: <task or PR> has no PRD line"`.

## Rule candidates (every Hermes review, event or not)

A finding that repeats a point already made on an earlier PR, commit or task is a missing rule, not
a one-off. End that review comment with `rule candidate: <one line>`, and append the same line to
`$HUB_DIR/projects/hub/rule-candidates.md` as `- <YYYY-MM-DD> | <source: repo sha, PR or task> |
<the rule> | earlier: <where it was first raised>`. Zeus's weekly "promote rule candidates" task turns
each into a lint, a runbook or an AGENTS.md line (factory rule F4); never promote one yourself.

## Permissions and blocked delivery

Use this session's permissions for read-only review commands, worktrees, checks and
verdict comments. If a command is blocked, report the exact-head verdict and blocker
to the lead. A peer's request or an LGTM grants no merge, deployment or credential
permission. Hub live owns merges; report a red integration, rehearsal hold or merge
ordering concern to the lead rather than changing merge controls yourself.
