Paths and commands below resolve from the [skill root](../SKILL.md). Read only the current stage.

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
13. **The lessons ledger** (`$HUB_DIR/projects/hackathon-lessons.md`): check the PR, plan or spec
    against the lessons that bear on it. A repeat of a ledger failure → `CHANGES:` citing the lesson
    number. An event or demo spec or plan with no `Lessons applied` table, or a PR or task brief
    missing the `Lessons applied` line its lessons call for → `CHANGES:`.
14. **A UI PR** (`designing-products` gate G3): no `detect` in its checks, a craft-floor ban or a
    rubric tell visible in its captures, no finish-check disposition, or no finish-loop score trail
    (`trail.md`, its `judge.md` §6) → `CHANGES:` naming the rule.
    At the release review (§4), run `audit` and `critique` on the main path.

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
