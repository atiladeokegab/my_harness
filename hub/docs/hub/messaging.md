# Notifications, wakes and messaging

Part of the hub manual. Index: `$HUB_DIR/HUB.md` (default `~/hub/HUB.md`).

## Notifications

When a task completes, `hub done` works out which tasks it just unblocked and queues a
message to each new owner's inbox. Read yours with `hub inbox`: a count plus the latest 20
messages, `--all` for every one.

**A queued message does not wake anybody up.** The inbox is durable but passive, so
finishing a task means queue *and* ping: the inbox survives restarts, the ping gets
attention now. `hub done` prints the exact call to make, and the agent finishing the work
is expected to make it.

Two ways to ping, because two vendors:

- `SendMessage`: Claude to Claude. Native, no tmux dependency. Only a Claude session can
  call it; a shell script cannot speak that socket protocol.
- `hubmsg <Agent> "text"`: anyone to anyone, including to and from a Codex agent. A plain
  shell command, so scripts can use it too. It queues *and* wakes in one call.

A status line that only matters while current (a health-watch alert) is sent with `--key K` on
`hub notify` or `hubmsg`: it replaces the recipient's earlier message with that key, so the lead's
inbox holds one current alert per agent rather than a pile of stale ones.

Each message has a unique ID and its payload stays in the locked durable inbox. A wake carries
no payload, only `[hub wake] Run exactly: hub receive --pending`, and that command reveals every
unreceived message once and writes a receipt for each. A repeated wake therefore prints `nothing
pending` and cannot repeat the work.

### Wake semantics

| Rule | What happens |
|---|---|
| **One wake per agent** | `hubmsg` writes one request, `wake/<Agent>.wake`. A message that arrives while it is pending only adds its id, so three messages in a minute make one turn. The relay drops the request once every listed id has a receipt. |
| **Stop-hook delivery first** | The `stop-deliver` hook (`hooks/stop-deliver.js`) runs when an agent's turn ends. With messages pending it runs `hub receive --pending` and hands them over as a Stop block, so the agent continues straight into them with no keystroke. The receipts stop it looping. Both CLIs honour the block. |
| **Busy: nothing typed** | A pane showing `esc to interrupt`, or a heartbeat whose last event is a fresh `UserPromptSubmit`/`PostToolUse`, is mid-turn. The relay requeues for 15 s; the Stop hook usually delivers first. `hubmsg` prints `busy`. |
| **Attached: deferred** | A person attached to the pane gets no keystrokes, and the Stop hook stays silent too, so you talking to an agent are not pushed into peer mail. A notice goes to the tmux status line. `hubmsg` prints `deferred`. |
| **Dialog: deferred** | A permission prompt, Codex's "Hooks need review" or any `esc skip` screen gets no Enter: it would confirm the highlighted option, and a wrongly granted permission cannot be taken back. |
| **Idle: one line** | Only an idle, unattached pane with no dialog gets the receive line typed, after clearing any half-typed input. |
| **The lead exempt** | `$HUB_LEAD` (Zeus by default) gets no Stop-hook delivery and no reset, because it holds your conversation. The `inbox-surface` hook still shows it new messages on every prompt and tool call. |
| **Old messages** | A wake older than `HUB_WAKE_MAX_AGE` (6 h) is dropped; the message stays in the inbox for `hub inbox`. |

The hooks are optional and need `node`; without them every wake is a keystroke into an idle pane.
Install them with `runbooks/install-factory-timers.md` section 4. Codex hooks run in a shared daemon
whose environment belongs to whichever process started it, so each Codex seat's `$CODEX_HOME/hooks.json`
passes its identity and `HUB_DIR` explicitly (`--agent Prometheus` in `~/.codex/hooks.json`); the hooks
ignore a Codex payload without them.

When you see a `[hub wake]` prompt, run its exact `hub receive` command before acting on the
messages. An old-style `[hub wake:<id>]` line works the same way.

## Messaging

**Between Claude agents**, over a local Unix socket: no server, no MCP, no network.

- `ListAgents` shows reachable sessions; the name **is** the address.
- `SendMessage` with `to: "Apollo"` delivers directly.
- Messages queue if the agent is busy and drain on its next turn.
- Plain text output is *not* visible across sessions. To communicate, an agent must
  actually call `SendMessage`.

**To or from a Codex agent**, `SendMessage` is not available in either direction, so use
`hubmsg`, a shell command, therefore usable by any agent:

```bash
hubmsg Prometheus "T-007 is yours — detail is on the board" --task T-007
```

It does both halves of the queue-and-ping rule in one call: `hub notify` for the durable
inbox, then one coalesced wake for that agent (see [Wake semantics](#wake-semantics)). It
prints `woke` only after confirmation, `relayed` when the sandbox relay owns delivery,
`busy` when the target is mid-turn (its Stop hook or the relay delivers at turn end),
`deferred` when a person is attached or a dialog is up, and `asleep` when the target is not
running; the message remains in the durable inbox either way. Tmux carries only the receive
command, never the payload. Run `hubs` or `hubwaked --status` for relay pid, pending queue
depth/age, retained failures and the last error. The relay is single-instance, adopts queued
requests on startup and bounds its log. Its pidfile records a code fingerprint, so `hubs`
reports `relay=stale` after an on-disk upgrade and the launcher replaces the old process.
`last_error` is shown only while a retained failure is active, not merely because an old log
entry exists.

A wake is `deferred` while a person is attached, so it cannot be the only path to the
lead. The `inbox-surface` hook runs on every prompt and tool call of an agent with
`$HUB_AGENT` set and adds `hub inbox --unseen` to its context, headed `[hub inbox] new since
last check:`. That prints only messages it has not shown before, at most 8, and skips hub
live's routine invite and deploy lines. It shares receipts with `hub receive`, so a message it
shows is not delivered again by the Stop hook or the relay. It never deletes: plain `hub inbox`
(latest 20, `--all` for everything) and `--clear` still see every message.

`hubmsg` works for *any* agent, Claude ones included. Prefer `SendMessage` between Claude
agents (it is native and does not depend on tmux) and reach for `hubmsg` when the target
is a Codex agent, or when a shell script needs to do the waking.

State fix requests explicitly: investigate, test and push the fix for independent review;
do not imply that a new commit may merge before review. If a native permission classifier
rejects a message, keep the exact tool input and denial for diagnosis. Approval is per
session: ask the human in the blocked session, rather than relaying the rejected action
through another agent or disabling the classifier.

Permissions are per-session. Never ask a peer to do something your own session was denied:
route it back to the human instead.
