# Agents stall at permission and approval dialogs

Measured 2026-10-25 to 2026-11-08 (14 days) for T-1055. All times UTC. This runbook proposes
rules only. Nobody has edited a settings file; the lead applies the rules.

## Symptom

- Zeus's inbox shows `[watchdog] Zeus: healthy -> permission prompt (❯ 1. Yes)`, or a WhatsApp
  forward says `(handed to Hermes: you were permission prompt)` or `(handed to Hephaestus: ...)`.
  The second form means **Zeus** sat at the dialog and the lead's message went to a peer.
- `wake/hubwaked.log` repeats `deferred id=<Agent> session=hub-<agent> (confirmation dialog on screen)`
  every 5 s. hubwaked will not type into a dialog, because the Enter would answer it.
- The watchdog reports `healthy -> stuck (no heartbeat for N min)` while hubwaked's log shows a
  dialog for the same agent. That case is a detection gap (see the fixes below).

## Confirm it

```bash
tmux capture-pane -p -t hub-zeus | tail -15          # numbered "1. Yes / 2. ... / No" options, or a question
grep 'confirmation dialog' ~/hub/wake/hubwaked.log | tail -3
grep -- '-> permission prompt' ~/hub/watchdog.log | tail -5
```

Why a Claude dialog was shown: the tool_result record in the session transcript carries
`permissionDecision`. `"source":"user_temporary"` means a person answered a dialog, and
`reasonCode` gives the reason: `bashMiss:no-rule-match`, `bashMiss:too-complex` or
`bashMiss:semantics`. A question tool has `unknown`. For example:

```bash
grep -o '"permissionDecision":{[^}]*user_temporary[^}]*}' ~/.claude/projects/-home-you-code-refinery/<session>.jsonl | sort | uniq -c
```

Codex never shows a person a dialog here. `approvals_reviewer = "auto_review"` sends every
sandbox escalation to a reviewer model. Those reviews are separate rollouts in
`$CODEX_HOME/sessions` with `"turn_trigger":"guardian_review"` and a final `{"outcome":"allow|deny"}`.

## What the 14 days show

Sources: `~/hub/watchdog.log` and the `hubwatchdog` journal, `wake/hubwaked.log` (it holds only
2026-11-05 to 2026-11-08, because `rotate_log` trims it by size), `hub events`, Claude transcripts
(`permissionDecision`), and Codex rollouts for Prometheus (`~/.codex`) and Atlas (`~/.codex-atlas`).

### Stalls by cause

| Cause | Agent | Dialogs | Time held | Should it prompt? |
|---|---|---|---|---|
| **Question to the lead** (AskUserQuestion, not a permission) | Zeus (Claude) | 96 (2 declined) | 16.5 h in total, median 43 s. Seven waits of 5 min or more took **15.3 h**: 542, 284, 49, 14, 12, 11 and 7 min | Partly. Most were small calls the lead delegates |
| **Production deploy or prod change**: `deploy.sh` with `. ./.env`, `gcloud run services update`, `update-traffic`, `delete`, `add-iam-policy-binding`, push to `main` | Zeus, 2026-11-07 Murmur hackathon | 56 | 106 min in total. Longest 44, 9, 7 and 6 min | **Yes**, by design |
| **Read-only check** with no allow rule: `gcloud run services describe ...; hubwa send ...`, `. ./.env; gcloud logging read` | Zeus, 2026-11-07 | 4 | 85 min, including **one 84-min stall** (18:59 to 20:23, during the prize-giving) | **No** |
| Workflow tool launch | Claude session, 2026-11-04 | 1 | 26 s | Yes |
| Dialog not identified: hubwaked saw a confirmation dialog, but the watchdog called it `stuck` | Hermes, 2026-11-05 04:41 to 04:51 | 1 | at least 10 min (no heartbeat for over 880 min) | Unknown. No decision appears in the transcript |
| Codex sandbox escalation, auto-reviewed | Prometheus | 3,276 allowed, 5 denied | median 2 s, longest 30 s, never a person | No person needed |
| Codex sandbox escalation, auto-reviewed | Atlas | 1,613 allowed, 7 denied | median 2 s, longest 33 s | No person needed |
| agy dialog | Hephaestus | 0 | none. agy runs with `--dangerously-skip-permissions` | n/a |

Reason codes behind the 60 Claude Bash dialogs: `too-complex` 33, `no-rule-match` 16,
`semantics` 11 (sourcing `./.env`). An allow rule can only fix `no-rule-match`. The other 44 are
compound commands (`cd X && export ... && . ./.env && ./deploy.sh && gcloud ... | tail`), which
no rule matches. Those need to be split into separate commands.

The watchdog recorded 30 `permission prompt` episodes (29 Zeus, 1 Hermes), about 307 sampled
minutes for Zeus in all. Nine were question dialogs whose options read "Yes, ... (Recommended)",
and 21 were the Bash dialogs from 2026-11-07. It misses a question whose first option does not
start with "Yes": the 542-min wait on 2026-10-31 never raised an alert.

`stuck` alerts (Prometheus 47, Zeus 33, Hermes 34, Atlas 10 episodes) are mostly idle agents that
hold claimed tasks, not dialogs. Only the Hermes episode on 2026-11-05 lines up with a dialog.

Zeus's `.claude/settings.json` in the refinery repo allows `Bash(*)`, yet `gcloud run services describe` still missed
(`no-rule-match`). In auto mode that broad rule does not cover these commands, so narrow rules
are needed.

## Proposed allow rules (lead applies; nothing here is applied)

Only routine read-only and hub commands. Every rule is a prefix rule. Unless noted, the patterns
below were not tested against the live sessions.

### Zeus and Hermes (Claude Code): `~/.claude/settings.json`, merge into `permissions.allow`

Both sessions start in `~/code/refinery` and do their work in `~/work/...`, so the user file is the
one that reaches both. Keep hub rules out of the product repo's `.claude/settings.json`. The
space before `*` makes the match stop at a word boundary, so `hub new *` does not match
`hub new-project`.

```json
"Bash(hub brief)", "Bash(hub inbox)", "Bash(hub next)", "Bash(hub agents)",
"Bash(hub brief *)", "Bash(hub inbox *)", "Bash(hub receive *)", "Bash(hub list *)",
"Bash(hub show *)", "Bash(hub next *)", "Bash(hub claim *)", "Bash(hub release *)",
"Bash(hub done *)", "Bash(hub note *)", "Bash(hub notify *)", "Bash(hub block *)",
"Bash(hub events *)", "Bash(hub trace *)", "Bash(hub map *)", "Bash(hub ship-check *)",
"Bash(hub tag *)", "Bash(hub new *)",
"Bash(hubmsg *)",
"Bash(hub sh -- uv run pytest *)", "Bash(hub sh -- npm test *)",
"Bash(hub sh -- npm run build *)", "Bash(hub sh -- npm run test *)",
"Bash(git status)", "Bash(git status *)", "Bash(git log *)", "Bash(git diff)", "Bash(git diff *)",
"Bash(git show *)", "Bash(git fetch *)", "Bash(git rev-parse *)",
"Bash(uv run pytest *)", "Bash(npm test)", "Bash(npm test *)", "Bash(npm run build *)", "Bash(npm run test *)",
"Bash(gh pr view *)", "Bash(gh pr list *)", "Bash(gh pr diff *)", "Bash(gh pr checks *)",
"Bash(gcloud run services describe *)", "Bash(gcloud run revisions list *)"
```

The last line alone would have prevented the 84-min stall on 2026-11-07. `hubwa send` is already
allowed. Optional: today the `autoMode.allow` lines for `hub`, `hubmsg` and `uv run` end in
`in $HUB_CODE_DIR/refinery`, and every 2026-11-07 dialog ran in `~/work/a11y-agents-nov26/`.
Repeating those three lines with `in ~/work` and `in $HUB_DIR` would extend
the same classifier guidance to the workspaces.

### Prometheus: `~/.codex/rules/hub.rules`. Atlas: `~/.codex-atlas/rules/hub.rules`

Codex has no allowlist key in `config.toml`. Its allow rules are execpolicy prefix rules in
`$CODEX_HOME/rules/*.rules`, a Starlark file and not TOML. Put the same file in both homes. This
exact file was checked with `codex execpolicy check --rules hub.rules <cmd>` on codex-cli 0.166.0:
`hub claim`, `hub sh -- uv run pytest`, `git fetch` and `gh pr view` return `allow`, while
`hub sh -- rm`, `hub live`, `hub approve`, `npm run deploy`, `git push` and `gh pr merge`
match nothing and keep the auto review.

```python
# Routine hub and read-only commands: no sandbox escalation review (T-1055).
prefix_rule(
    pattern = ["hub", ["brief", "inbox", "receive", "list", "show", "next", "claim", "release",
                       "done", "note", "notify", "block", "events", "agents", "trace", "map",
                       "ship-check", "tag", "new"]],
    decision = "allow",
    justification = "hub board CLI: writes only ~/hub",
)
prefix_rule(pattern = ["hubmsg"], decision = "allow", justification = "hub messaging between agents")
prefix_rule(pattern = ["hub", "sh", "--", "uv", "run", "pytest"], decision = "allow")
prefix_rule(pattern = ["hub", "sh", "--", "npm", "test"], decision = "allow")
prefix_rule(pattern = ["hub", "sh", "--", "npm", "run", ["build", "test", "lint"]], decision = "allow")
prefix_rule(pattern = ["git", ["status", "log", "diff", "show", "fetch", "rev-parse", "ls-remote"]], decision = "allow")
prefix_rule(pattern = ["gh", "pr", ["view", "list", "diff", "checks"]], decision = "allow")
prefix_rule(pattern = ["uv", "run", "pytest"], decision = "allow")
prefix_rule(pattern = ["npm", "test"], decision = "allow")
prefix_rule(pattern = ["npm", "run", ["build", "test", "lint"]], decision = "allow")
```

Of the 5,155 escalations, `gh pr view/list/diff/checks` (about 1,380) and `git fetch/diff/ls-remote/rev-parse` (about 480)
make up roughly 35%. These rules remove those reviews at about 2 s each, which saves time and
tokens but does not unblock a person, because Codex never waited on one. Tokens are fixed, so
`hub sh --name x -- uv run pytest` and `hub sh -- timeout 240 ...` do not match. Agents that want
the fast path should leave `--name` and `timeout` off routine test runs.

### Hephaestus (agy)

Nothing to add. It runs with `--dangerously-skip-permissions` and has no gate at all. That is the
opposite risk, and it is out of scope here.

## Keep these prompting (or auto-reviewed) on purpose

- Deploys and production changes: `gcloud run deploy`, `deploy.sh`, `make deploy`,
  `gcloud run services update | update-traffic | delete | add-iam-policy-binding`, any `--allow-unauthenticated`.
- Outward-facing writes: `git push` (above all to `main` and with `--force`), `gh pr merge` outside the
  merges the lead has authorised, `gh pr create | comment | edit`, `gh release create`,
  `gh repo create | fork`, `gh secret set`, `gh variable set`, `gh workflow run`, `hub approve`, `hub changes`, `hub gh-sync`.
- Spend and fleet control: `hub host`, `hub live`, `hub pause | resume`, `gcloud` writes, `gcloud storage cp` to shared or public buckets.
- Anything that reads secrets: sourcing `./.env`, `grep` for API keys, `cat` of credential files.
- Destruction: `git reset --hard`, `git worktree remove --force`, `rm -rf` outside the agent's own
  scratch or workspace, `kill`/`pkill` of processes the agent did not start, `hub scrub`.
- Arbitrary execution through a wrapper: `hub sh -- <anything>` beyond the test and build forms above, `npx <pkg>`, `npm install`, `git clone` of outside code.

## Non-settings fixes (bigger lever than the allowlist)

1. **The watchdog misses dialogs that hubwaked sees.** `dispatch.py classify()` needs a `1. Yes`
   line and a `No` line. hubwaked's `MODAL_MARKERS` (`Do you want to`, `Esc to cancel`,
   `Enter to confirm`, `esc skip`) caught the Hermes dialog on 2026-11-05 while the watchdog said
   `stuck`. Share one marker list between the two, and add a separate `question` cause for
   AskUserQuestion screens, whose options carry `(Recommended)` and do not start with "Yes".
2. **Say what is being asked.** The alert text is only `❯ 1. Yes`. Include the 3 or 4 pane lines
   above the options, which show the command, so the lead can answer from WhatsApp without
   opening tmux.
3. **Reach the lead for any agent, and repeat.** `report()` sends WhatsApp only when the agent is
   Zeus, and only on the change of state. After 3 min at a prompt, WhatsApp the lead for every
   agent, then remind every 15 min while it lasts. The 84-min stall got one alert.
4. **Zeus: split checks from deploys.** 44 of the 60 Bash dialogs were compound commands that no
   rule can match. A read-only `gcloud ... describe` chained with `hubwa send` prompted as one
   unit. Run checks, deploys and messages as separate tool calls, so only the deploy prompts.
5. **Zeus: do not block on a question when the lead is away.** Seven questions held Zeus for
   15.3 h. Under "lead delegates small calls", make the call, or send it with `hubwa send` and
   keep working. Keep AskUserQuestion for account, spend or outward-facing decisions.
6. **Keep the evidence.** `rotate_log` trims `hubwaked.log` to `KEEP_LOG_BYTES`, which held about
   3 days here. Keep 14 days, so the next measurement can count dialogs per agent directly.
