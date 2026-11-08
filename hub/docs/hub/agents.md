# Agents, accounts and seats

Part of the hub manual. Index: `$HUB_DIR/HUB.md` (default `~/hub/HUB.md`).

For current assignments, start with `hub brief` and `hub agents`. `factory.json` owns
the roster and phase policy; the board and inbox carry task ownership and temporary
acting-lead assignments. The account details below do not assign current work.

## The default roster

| Agent | CLI | Role |
|---|---|---|
| **Zeus** | Claude Code | Lead. Planning, decomposition, task authoring, review. Usually the one you talk to. |
| **Apollo** | Claude Code | Worker. |
| **Hermes** | Claude Code | Worker. The reviewer when no agent has the `reviewer` phase (`$HUB_REVIEWER`). |
| **Athena** | Claude Code | Worker. |
| **Prometheus** | Codex | Worker. Not a Claude session: see [Two vendors, one hub](#two-vendors-one-hub). The example `factory.json` makes it the reviewer: a second model family has different blind spots. |

These are the defaults. The roster comes from `factory.json` (`factory.example.json` is the
template), or without one from `HUB_CLAUDE_AGENTS`, `HUB_CODEX_AGENTS`, `HUB_LEAD` and
`HUB_REVIEWER`. Renaming agents, changing the roster and running a second hub:
`docs/customizing.md` in the harness repo.

Roles beyond the lead are deliberately not specialised: assign by task, not by title.

## Two vendors, one hub

Prometheus runs OpenAI's Codex CLI. That is useful: a second model family has different
blind spots, so it is worth pointing at review and at anything Claude has got stuck on.
But it means the hub cannot assume one vendor's tooling.

The split is clean, and it is worth knowing which side of it you are on:

| Layer | Mechanism | Works across vendors? |
|---|---|---|
| Task board, inbox, ledger | Plain files under `hub/` | **Yes.** `board.py` attributes work by `$HUB_AGENT`, and has no roster to add names to. |
| Waking a running agent | `hubmsg` → the agent's Stop hook, or a tmux keystroke when idle | **Yes.** Every agent lives in a tmux session named `hub-<agent>`; the Stop hook runs on both CLIs. |
| Waking a running agent | `SendMessage` / `ListAgents` | **No.** Claude-only socket protocol; Codex can neither send nor receive. |
| Skills, slash commands | Vendor-specific | **No.** Never write a task for a Codex agent that assumes them. |

So: the board needed no changes to accept a Codex agent, and messaging needed `hubmsg`.

## Accounts

Each agent runs on its own subscription, so their rate limits and context budgets are
independent: five agents working hard don't compete for one account's capacity. The four
Claude agents bill to four Claude accounts; Prometheus bills to your ChatGPT account.

Claude Code keeps credentials, settings and history per *config directory*, so each agent
gets its own:

| Agent | Config dir |
|---|---|
| Zeus | `~/.claude` (the default, already signed in) |
| Apollo | `~/.claude-apollo` |
| Hermes | `~/.claude-hermes` |
| Athena | `~/.claude-athena` |
| Prometheus | `~/.codex` (Codex's own home, unrelated to the above) |

Any other Claude agent gets `~/.claude-<name>`.

**First run per agent:** type its name, pick a theme, sign in to that agent's account, then
`Ctrl-b d` to detach. Once only. `hubaccounts` shows who still needs a login, including
Prometheus, which signs in with `/login` inside the session against your ChatGPT account.

None of the Claude config-dir machinery below applies to Prometheus: Codex keeps its own
credentials, history and settings in `$CODEX_HOME`, and reads `AGENTS.md` rather than
`CLAUDE.md`. `~/.codex/AGENTS.md` is symlinked to `hub/AGENTS-codex.md` so its protocol
stays versioned alongside everything else.

**The Claude session registry stays shared.** Claude session discovery reads `<config>/sessions/`,
so fully isolated Claude config dirs would be invisible to native Claude messaging. Each Claude
agent's config dir therefore symlinks `sessions/` back to `~/.claude/sessions`. Credentials,
settings and history stay separate; only the registry of who-is-running is shared. Don't remove
that symlink. This does not apply to Codex's `$CODEX_HOME/sessions/`, which holds that seat's own
conversation history.

`CLAUDE.md` and `skills/` are also symlinked, so every Claude agent reads the same protocol and
loads the same skills. `settings.json` is copied rather than linked, because accounts differ in
which models they can use: edit each agent's copy independently.

Everything in `hub/` (board, ledger, inboxes) is plain files on disk and works across
accounts without any of this mattering.

## Starting and entering agents

Type the agent's name in any shell: `zeus`, `apollo`, `hermes`, `athena`, `prometheus`.

That attaches to the agent's tmux session, creating it on first use. The session keeps
running when you detach or close the terminal.

- Detach without stopping: `Ctrl-b d`
- See who's up (and which accounts are signed in): `hubs`
- Accounts only: `hubaccounts`
- Stop one: `hubkill apollo`

The agent commands are installed as executables as well as shell functions, so they also work
from zsh, the macOS default login shell.

### Where an agent lands

You should not have to think about paths. Resolution order:

1. **An explicit project**: `apollo webapp`, `zeus hub`. Any git repo directly under
   `$HUB_CODE_DIR` (default `~/code`) works by name with no registration, as does the hub
   directory. `apollo .` forces the current directory.
2. **The repo you are standing in**: `cd $HUB_CODE_DIR/webapp && apollo` keeps working.
3. **`$HUB_HOME_PROJECT`**, if you set one. With `HUB_HOME_PROJECT=webapp`, a bare
   `apollo` from your home directory, `/tmp`, or anywhere else that is not a repo lands in
   `$HUB_CODE_DIR/webapp`.
4. **Otherwise, the current directory.**

So the everyday case is one word from a fresh shell (with `HUB_HOME_PROJECT=webapp`):

```bash
apollo            # → $HUB_CODE_DIR/webapp, scoped to project webapp
```

The launch line confirms it, and re-entering a running agent tells you where it already is:

```
started Apollo in ~/code/webapp  (account: ...)  project: webapp
attaching to running Apollo in ~/code/webapp
```

An unknown project name lists the ones it knows rather than guessing.

### What an agent knows on arrival

`_hub_enter` runs `hub brief` at launch and passes the result to Claude Code via
`--append-system-prompt`, so a session opens already knowing its inbox, the tasks
available to it, its phase policy and the configured reviewer, and **what every peer is
currently holding**, instead of spending its first turn working that out. Run `hub brief` any
time for a fresh view; the injected copy is a snapshot from launch and says so.

Prometheus gets no injection (Codex has no equivalent flag), so `AGENTS-codex.md` tells it
to run `hub brief` on arrival instead. If a briefing is missing for any agent, run `hub brief`
before choosing work.
