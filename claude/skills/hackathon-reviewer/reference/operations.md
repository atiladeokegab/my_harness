Paths and commands below resolve from the [skill root](../SKILL.md). Read only the current stage.

## What merges how

hub live merges a PR **without you** only when every changed file is outside `review_before`, every
changed file is inside its issue's `Files:`, its `DONE:` has a `Verified:` line, and the smoke is
green. Everything else waits for your `LGTM`; you see the rest after merge, in the digest (§2).

Prometheus reviews first and Atlas second (the lead's decisions since 2026-10-23, updated 2026-10-30):

- **One `LGTM` merges by default; two (Prometheus and Atlas) for a gate, privacy, delivery or security
  change.**
- Either reviewer may push a small fix (about 20 lines or fewer) on a PR it reviews; the other reviewer
  then checks those lines before the merge.

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

Why: at real-world-agents every real catch sat in one of these (runner #51 #56, input trust #36
#115, safety #69, case loader #42); the 31 PRs under 50 lines caught nothing.


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
4. Post one exact-head verdict: `gh pr comment N -R <repo> --body "LGTM <headRefOid>"`,
   then `hub approve <owner/repo>#<N> <headRefOid>` to record the board receipt, and notify
   the current lead. For changes, use `--body-file <file>` with `CHANGES:` first.
   A later push needs a new review. If recording or delivery is blocked, report the exact
   SHA and blocker; never infer merge permission or trigger a broad merge loop.
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
