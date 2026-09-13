# Codex agent can read the board but not write to it — or cannot wake anyone

**Symptom.** Prometheus (or any Codex agent) runs `hub inbox` fine, but `hub claim`,
`hub done`, `hub note` or `hubmsg` dies with a bare Python traceback ending in:

```
OSError: [Errno 30] Read-only file system: '~/hub/inbox/Zeus.jsonl'
```

Or: `hubmsg` succeeds but always prints `asleep -> hub-zeus not running`, for an agent
that is demonstrably running.

**Why.** Codex sandboxes the agent. Two separate restrictions bite:

1. **`workspace-write` only permits writes under the launch directory.** The hub lives at
   `~/hub`, outside any repo you would launch from, so every board mutation fails. Reads
   still work, which is what makes this confusing — the agent looks half-connected.
2. **seccomp blocks `connect()` on AF_UNIX sockets.** The agent can `stat`
   `/tmp/tmux-1000/default` but not connect to it, so `tmux has-session` returns
   "Operation not permitted". `hubmsg` cannot tell that from "session absent" unless it
   inspects the error text.

**Confirm it.** From outside the sandbox:

```bash
codex sandbox tmux has-session -t hub-zeus
# error connecting to /tmp/tmux-1000/default (Operation not permitted)

codex sandbox -c 'sandbox_mode="danger-full-access"' tmux has-session -t hub-zeus
# succeeds -> it is seccomp, not file permissions
```

Adding the socket directory as a writable root does **not** help; the block is on the
syscall, not the path.

**The fix, both already in place.**

- `_hub_enter_codex` launches with `codex --add-dir "$HUB_DIR"`, granting exactly the hub
  and nothing else. If you start `codex` by hand and skip this flag, symptom 1 returns.
- `hubmsg` distinguishes "cannot reach tmux" from "not running" by matching the error
  text, and in the first case writes a request to `hub/wake/` instead. `hubwaked`
  (tmux session `hub-relay`, started automatically by `_hub_enter_codex`) runs outside
  the sandbox and performs the keystroke.

**If wakes stop arriving from a Codex agent,** check structured relay health first:

```bash
hubs
~/hub/hubwaked --status
tail ~/hub/wake/hubwaked.log
```

Status reports pid, queue depth, oldest request age and retained failures. Pending
requests survive restart. Restart with `_hub_start_relay` (or re-enter `prometheus`);
the launcher also replaces a pre-upgrade relay lacking the current pidfile contract.

Every payload stays in the durable inbox under a unique ID. The tmux wake contains only
an idempotent `hub receive <id>` instruction, so an ambiguous wake can safely retry: the
payload is revealed at most once. A request is atomically claimed into `wake/inflight/`,
preventing direct delivery and the daemon from racing; dead-handler requests are recovered
on restart. Health reports `stale` when the running daemon's recorded code fingerprint no
longer matches the executable on disk.

## Related failure: `prometheus` starts and instantly exits

**Symptom.** `prometheus` prints its normal banner, then dumps you straight back to the
shell with no error:

```
started Prometheus in ~/code/refinery  (codex, account: ~/.codex)
  writable: $PWD and ~/hub
[exited]
```

The tmux session is gone by the time you look, so there is nothing to inspect.

**Why.** Since codex 0.153 (the `v1` sandbox migration recorded in
`~/.codex/.sandbox_migration`) a directory that is not a trusted project defaults to
**read-only**, and `--add-dir` under read-only is a hard error rather than a warning:

```
Error adding directories: Ignoring --add-dir (~/hub) because the effective
permissions do not allow additional writable roots. Switch to workspace-write or
danger-full-access to allow them.
```

codex exits 1, tmux tears down the session, and the launcher's own banner scrolls past
before you can read the error. Only a Windows home directory was ever marked trusted in
`~/.codex/config.toml`, so launching from any repo — including `~/code/refinery` — hits it.

**See the real error.** Run codex in a tmux session that outlives it:

```bash
tmux new-session -d -s probe -c ~/code/refinery \
  'codex --add-dir ~/hub; echo "EXIT=$?"; sleep 600'
sleep 8 && tmux capture-pane -p -t probe
```

**Fix, already in place.** `_hub_enter_codex` names the mode explicitly:

```bash
codex --sandbox workspace-write --add-dir "$HUB_DIR"
```

Do not rely on the default — it is trust-dependent and has changed once already. Confirm
the grant still works after any codex upgrade:

```bash
codex sandbox -c 'sandbox_mode="read-only"' -- touch ~/hub/.probe
#   -> touch: cannot touch '~/hub/.probe': Read-only file system

codex sandbox -c 'sandbox_mode="workspace-write"' \
  -c 'sandbox_workspace_write.writable_roots=["~/hub"]' -- touch ~/hub/.probe
#   -> succeeds
```

**One-time prompt.** The first launch in a new directory asks whether you trust it. Answer
`1. Yes, continue`; that records the directory in `~/.codex/config.toml`. It is a prompt,
not a failure — the session stays up either way once the sandbox mode is correct.

## Related hazard: keystroke wakes collide with a human typing

`hubmsg` never injects into an attached pane. It reports `deferred`, keeps the durable
request queued, and the relay delivers after the person detaches. The person can run
`hub inbox` immediately if they want to handle queued work without detaching. Prefer
`SendMessage` for Claude peers, which needs no tmux keystrokes.
