---
name: hackathon-reviewer
description: >
  The reviewer's routine for an event run with hackathon: gated PRs before they merge, the
  after-merge digest of everything else, FLAG: on drifting sub-issues, and the release review at
  freeze minus 45. Use when you are Hermes reviewing an event repo, when hub live sends "PR #N ready
  for review", "merged without review:" or "release review:", or when Zeus starts a backup reviewer
  sub-agent; its "Rule candidates" section also applies to every factory review Hermes does. Not for planning or building (hackathon), not for merging or reverting (hub live
  and Zeus do that), and never for a PR you built.
---

# Reviewing a hackathon

You review; hub live merges; Zeus decides. You never merge, revert, edit code, briefs or `IDEA.md`,
and never answer a question for an owner. What you check against: `$HUB_DIR/projects/<p>/hackathon.json`,
the repo's `IDEA.md` (areas, `Ceilings`, `Deploy owner`), `docs/CONTRACT.md`, and the issue the PR
closes. Every `gh` command names the repo (`-R <repo>`). `P=~/code/<p>` below.

## What merges how

hub live merges a PR **without you** only when every changed file is outside `review_before`, every
changed file is inside its issue's `Files:`, its `DONE:` has a `Verified:` line, and the smoke is
green. Everything else waits for your `LGTM`; you see the rest after merge, in the digest (§2).

Default `review_before`, the only copy anywhere (Zeus copies it into hackathon.json at setup and adds
the event's own runner, safety and verify paths at approval 3; with the key missing, every PR waits
for you). The globs are `fnmatch`: `*` crosses
`/`, so `starter/agent/*` is the whole directory and `*verify*` matches at any depth:

```json
["scripts/run_cases.py", "starter/agent/*", "starter/core/*", "starter/runtime/*",
 "starter/eval/*", "tests/test_no_leak.py", "ANSWERS/*",
 "*prompt*", "*verify*", "*safety*", "*guard*", "rules/*", "*/rules/*",
 "docs/CONTRACT.md", "IDEA.md", "AGENTS.md",
 "*pyproject.toml", "*uv.lock", "*package.json", "*package-lock.json", "*requirements*.txt",
 ".github/*", "Makefile", "Dockerfile", ".dockerignore", "scripts/deploy.sh"]
```

Why: at one real event every real catch sat in one of these (runner #51 #56, input trust #36
#115, safety #69, case loader #42); the 31 PRs under 50 lines caught nothing.

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

## Must still catch, whatever the tier

1. **Secrets.** `gh pr diff N -R <repo> | grep -nEi 'sk-ant-|sk_live|AKIA|ghp_|github_pat_|AIza|xox[bp]-|BEGIN [A-Z ]*PRIVATE KEY|://[^/ ]+:[^@ ]+@|(password|secret|api[_-]?key|token) *[:=]'`,
   then read every hit. Never LGTM it; at once `hubmsg Zeus "SECRET in PR #N (<file>): revoke <which key>"`.
   The repo is public: the key must be revoked at its provider, deleting the commit is not enough.
2. **Edits outside the owner's area:** any changed file outside the issue's `Files:` (a pool issue:
   exactly its `Files:`) with no accepted change-request → `CHANGES:`, and tell Zeus.
3. **Untrusted input reaching the model or a tool without a trust boundary** (#36 forged event in
   voice input, #115 "ignore" as a flag word): case or user text must reach a prompt only as quoted
   data and a tool only through the gateway's validation; a rule must never key on a word the input
   can simply contain.
4. **Timeout and fallback order on the answer path** (#51, #56): every inner timeout (model call,
   tool call) is shorter than the per-case timeout, and a timeout or error still writes a fallback
   `ANSWER.md`. Check the constants, then run one case with the provider slowed or failing.
5. **Mocks or prompts reading a recorded outcome:** nothing outside `starter/eval/` reads a case's
   expected or recorded outcome; `tests/test_no_leak.py` is green and not weakened.
6. **Guard rails shifting the final-state mix:** on a PR touching verify, safety, prompts or rules,
   in its worktree (§1 step 2):
   ```bash
   uv run scripts/run_cases.py cases/sample --set practice --out ANSWERS-practice
   uv run scripts/run_cases.py cases/sample --set holdout --out ANSWERS-holdout
   uv run scripts/run_cases.py --compare ANSWERS-practice ANSWERS-holdout; echo "exit $?"
   ```
   Exit 2 with a ` <- shift` row (more than 20 points between holdout and practice) → `CHANGES:`
   with the table. Exit 2 for any other reason (an unlabelled dir, a case on the wrong side, an empty
   side) means the run is wrong, not the PR: fix the run and rerun. With only a few cases a side, one case
   is already more than 20 points, so read the `cases` row before acting. The PR body still states the
   mix before and after; missing → `CHANGES:` asking for it.
7. **Contract or shape changes** (`docs/CONTRACT.md`, or a shape it defines, changed in code) with
   no accepted change-request → `CHANGES:`, and tell Zeus.
8. **New dependencies** (`pyproject.toml`, `uv.lock`, `package.json`, …): need an accepted
   change-request; check the package name is the real, maintained one.
9. **Anything that writes to `ANSWERS/` or touches the freeze:** only the runner writes `ANSWERS/`;
   after code freeze only PRs labelled `fix`; freeze files (`.github/**`) change only through Zeus.
10. **README or demo claims the code doesn't back** (#91, #94): each changed claim points at code
    that does it, or → `CHANGES:`.
11. **Async UI that outlives its dialog or session** (Physical-Shazam `0fe618c`): a page that awaits
    an upload, a permission or a model call inside a dialog or session needs a test that holds the
    call open, closes and reopens, then resolves it, and shows the late result is dropped. Missing →
    `CHANGES:` (after merge: an issue on the owner's area).
12. **A changed model or encoder id** (Physical-Shazam PR #3 `9609d35`): it needs a pinned version
    or revision, `make eval` before and after on the same cases pasted in the PR, and a test for any
    stored data the new model re-reads (embeddings, cues, caches). Missing, or `trust_remote_code=True`
    anywhere → `CHANGES:`.

**Trace sweep**, after every run you do (§1, §2, §4), in the run's checkout. It is the starter's own
script, so you and the team count the same thing:

```bash
uv run scripts/trace_sweep.py ANSWERS; echo "exit $?"           # <cases> <calls>  <tool>: <error>, most cases first
grep -h '^Final state:' ANSWERS/*/ANSWER.md | sort | uniq -c    # the final-state mix
```

Exit 1 means the same (tool, error) is in 3 or more cases: a `CHANGES:` on the PR that caused it,
with those rows (L4: a tool error repeated 10 times in a rival team's traces went unnoticed all day).
Exit 2 means there is no `trace.jsonl` under that dir: the path or the run is wrong, so fix that
before judging anything. A run with `--out` writes to that dir, not `ANSWERS`.

## 1. A gated PR: `PR #N ready for review at <sha>`

1. Read it: `gh pr view N -R <repo> --json title,body,files,headRefOid,baseRefName`,
   `gh pr diff N -R <repo>`, the issue it closes, and that area's `IDEA.md` row and Ceilings.
2. **Run it.** Catches come from running the code, not reading the diff:
   ```bash
   git -C "$P" fetch -q origin && d=$(mktemp -d) && git -C "$P" worktree add -q --detach "$d" <headRefOid>
   git -C "$d" merge -q --no-edit origin/integration && cp "$P/.env" "$d"/ 2>/dev/null
   (cd "$d" && timeout 900 make smoke)    # offline and deterministic: every PR
   ```
   A gated PR touching the agent or the core (runner, agent loop, verify, prompts, gateway, store)
   also gets the real model: `(cd "$d" && timeout 1800 make eval)`, with `.env` copied in as above.
   Nothing else runs `make eval`: it costs model calls and its answers vary run to run.
   Then the trace sweep in `"$d"`. Remove the worktree after the verdict:
   `git -C "$P" worktree remove --force "$d"`.
3. Check the must-still-catch list, the issue's Acceptance, and its `Verified:` counts against yours.
4. Verdict, one comment: `gh pr comment N -R <repo> --body "LGTM <headRefOid>"` and then
   `hub live --project <p> --merge-now` (merges within about 10 s); or
   `gh pr comment N -R <repo> --body-file <file>` whose first line starts `CHANGES:`.
5. **Escalate to Zeus** (`hubmsg Zeus "…"`) instead of deciding when you're unsure, or the PR touches
   scope, `IDEA.md`, the contract or the design.
6. **The design PR is never LGTM'd by you:** post `FYI:` findings; the lead approves the design in
   its window and Zeus merges it.

## 2. The after-merge digest: `<p> merged without review: #31, #33 (…)`

Target: done within 15 minutes of the message. For each PR:
1. `gh pr diff N -R <repo>`; secrets first, then the rest of the must-still-catch list.
2. **Re-run one in five:** every PR whose number ends in 0 or 5, plus any whose `Verified:` you doubt.
   Worktree at the merge commit (`gh pr view N -R <repo> --json mergeCommit --jq .mergeCommit.oid`),
   run the `Verified:` commands, compare the counts.
3. Post exactly one comment on the merged PR: `FYI: after-merge review: ok`, or
   `FYI: after-merge review: <finding>` plus `hubmsg Zeus "after-merge #N: <finding>. Recommend: revert | follow-up issue"`.
   A count that doesn't reproduce: recommend revert. A secret: at once, as above.

These comments are the record: the release review lists merged PRs that have neither an `LGTM` nor an
after-merge comment.

## 3. Sub-issue changes: `NEW` / `CHANGED #n in #v …`

Read the sub-issue. If it drifts from `IDEA.md`, the contract or the design while staying inside its
vertical, comment once, starting `FLAG:`. Otherwise nothing.

## 4. The release review: `<p> release review: code freeze in 45 min, …`

The one review that happens whatever else is cut.
1. `git -C "$P" fetch -q origin && sha=$(git -C "$P" rev-parse origin/main)`.
2. The runner is at that sha: `git -C "$P" cat-file -e "$sha:$(jq -r .runner $HUB_DIR/projects/<p>/hackathon.json)"`.
3. Worktree at `$sha`, `.env` copied in; run the runner on 5 practice cases; the trace sweep and the
   final-state mix.
4. Unreviewed merges:
   ```bash
   gh pr list -R <repo> --state merged --limit 300 --json number,comments \
     --jq '.[] | select([.comments[].body] | any(startswith("LGTM ") or startswith("FYI: after-merge review")) | not) | .number'
   ```
   Review each now (§2), secrets first.
5. `hubmsg Zeus "release review at <sha12>: runner present|MISSING; 5 cases: <mix>; tool errors: <top 3>; unreviewed after-merge: #a #b"`.
   Anything red is Zeus's call before the freeze.

## Rule candidates (every Hermes review, event or not)

A finding that repeats a point already made on an earlier PR, commit or task is a missing rule, not
a one-off. End that review comment with `rule candidate: <one line>`, and append the same line to
`$HUB_DIR/projects/hub/rule-candidates.md` as `- <YYYY-MM-DD> | <source: repo sha, PR or task> |
<the rule> | earlier: <where it was first raised>`. Zeus's weekly "promote rule candidates" task turns
each into a lint, a runbook or an AGENTS.md line (factory rule F4); never promote one yourself.

## Pace and holds

After an `LGTM`, `hub live --project <p> --merge-now`. Hold merges with
`hub live --project <p> --hold-merges` while `integration` is red, during a demo run-through, or to
land related PRs in a set order; `--resume-merges` lifts it and merges at once. A hold longer than
15 minutes is reported to Zeus.

## Backup reviewer

When Hermes is out, or hub live tells Zeus a gated PR has waited more than 10 minutes, Zeus starts:

```
Agent(description: "Review PR #N", subagent_type: "general-purpose", name: "review-N",
      prompt: "You are the backup reviewer for <p> (<repo>). Load the hackathon-reviewer skill and
               follow it for PR #N at <sha>. Post exactly one verdict comment, then report it in one line.")
```

It follows this skill exactly, can't ask the lead anything (it reports to Zeus), and never reviews a
PR a sub-agent of the same name built. Its sender is Zeus, so `hubmsg Zeus` refuses: wherever this
skill says `hubmsg Zeus`, a backup reviewer puts that line in its final message instead.

## Permissions

Your `/permissions` must allow `gh pr comment`, `gh pr view`, `gh pr diff`, `gh pr list`,
`git worktree`, `make`, `uv run` and `hub live` (dry run #4: without them auto mode blocked every
LGTM). If they're blocked anyway, send the verdict to Zeus by message; the lead approves and Zeus
merges by hand.
