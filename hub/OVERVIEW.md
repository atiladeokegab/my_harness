# The Hub

A small system for running several AI coding agents on one machine as a team: they share a
task board, message each other, and hand work back and forth without a human relaying it.

Five named sessions. Four run Claude Code, one runs OpenAI's Codex. **Zeus** plans and
decomposes; **Apollo**, **Hermes**, **Athena** and **Prometheus** execute.

Everything is plain files and Unix primitives — no server, no database, no network. About
2,300 lines total including tests and docs.

---

## The problem it solves

One agent session means one context window, one rate limit, and one thing happening at a
time. Long work serialises behind whatever the agent is currently doing, and any parallelism
means a human copy-pasting context between terminals.

The hub gives you agents that hold separate contexts, run on separate accounts (so they
don't compete for capacity), and pick up work written by whoever planned it. The design
constraint that drives everything: **a task must be executable by an agent that never saw
the conversation which produced it.** That is why planning happens up front and why every
task carries its own context, files, approach and acceptance criteria.

---

## Architecture

### The board

`board.json` is a snapshot; `events.jsonl` is an append-only ledger. Mutations take an
`flock` with a bounded wait, so a crashed holder is released by the kernel and a hung one
fails loudly with an actionable message rather than blocking everyone forever.

Writes are journal-first: events are appended and `fsync`ed *before* the snapshot is
replaced, and the snapshot's temp file and its parent directory are both `fsync`ed around
the rename. The ledger can therefore be legitimately **ahead** of the snapshot after a
crash; it can never be behind. That ordering is what makes "trust the ledger" true rather
than aspirational.

Agents identify themselves from `$HUB_AGENT`. There is no roster to register with — which
is the reason adding a non-Claude agent needed no board changes at all.

### Messaging

Two mechanisms, because two vendors:

| Path | Mechanism | Works across vendors |
|---|---|---|
| Claude → Claude | `SendMessage`, a Claude-private Unix socket | No |
| Anyone → anyone | `hubmsg`, a keystroke into the target's tmux pane | Yes |

Every agent lives in a tmux session named `hub-<agent>`, so typing into that pane is a wake
mechanism that works regardless of which vendor's CLI is on the other end.

The rule throughout is **queue *and* ping**: a durable inbox message (survives restarts,
passive) plus a live wake (gets attention now, ephemeral). `hubmsg` does both in one call.

---

## The interesting part: two vendors, one hub

Codex was added last. The split turned out cleaner than expected, and the failures were
instructive.

**What worked for free.** The board needed zero changes. Identity is an environment
variable and there is no roster, so a Codex agent claims, notes and finishes tasks
identically to a Claude one.

**What did not.** `SendMessage` is Claude-only in both directions, and `ListAgents` will
never list a Codex session. Waking had to be rebuilt on something vendor-neutral.

**Two sandbox discoveries**, both found by running the thing rather than reading docs:

1. Codex's `workspace-write` sandbox confines writes to the launch directory. The hub lives
   outside it, so the agent could *read* the board but every `claim`/`done`/`note` died with
   a bare `Read-only file system` error. Fixed by granting exactly the hub via `--add-dir`.
2. Codex's seccomp filter blocks `connect()` on AF_UNIX sockets. It can `stat` the tmux
   socket but never connect, so it could not wake anyone — and worse, the failure was
   indistinguishable from "that agent is asleep". No configuration short of disabling the
   sandbox lifts this.

Rather than disable the sandbox, wakes from a sandboxed agent are written as request files
into the hub directory, and a small relay daemon outside the sandbox performs the keystroke.

---

## Decisions worth arguing about

Listed because they are the places a reviewer should push.

**Keystrokes as a transport.** Waking an agent means typing into its terminal. It is
vendor-neutral and needs no cooperation from either CLI, but it is unmistakably a hack: if a
human is attached to that pane and mid-sentence, the injected text lands inside their
half-typed message and corrupts both. tmux cannot see a TUI's input buffer, so there is no
clean fix while the transport is keystrokes.

**Confirming delivery by reading the screen.** The relay confirms a submission by checking
the message id reached the active cursor line, then that Enter moved it. This is screen
scraping. An earlier version counted id occurrences anywhere in the pane and was fooled by a
duplicated paste into reporting success for a message that was never submitted.

**Failing closed.** When a wake is ambiguous, the relay records the id as delivered and does
*not* retry. Duplicating an agent's turn is considered worse than a missed ping, and the
durable inbox is the backstop. Reasonable people could pick the other trade.

**Notes are not ownership-gated.** Any agent may annotate any task, though only the owner
may finish or block one. Cross-agent commentary is the mechanism by which review findings
get recorded, so gating it would have broken the most valuable traffic on the board.

**No automatic crash recovery.** The ledger may end up ahead of the snapshot; reconciling is
a manual human job. Deliberate, but it is an unfinished edge.

---

## Testing

Two suites, dependency-free, run against throwaway boards and scratch tmux sessions:

```bash
python3 tests/test_board.py       # 11 checks
python3 tests/test_messaging.py   # 21 checks
```

The rule that mattered most: **each suite was written by the agent that did not write the
code under test.** Prometheus wrote the board tests, Zeus wrote the transport tests. That is
not ceremony — it caught real bugs in both directions that neither author found in their own
code.

Two lessons are worth repeating to anyone extending this:

- **A green test proves nothing until it has failed.** The first concurrency test passed
  against the *pre-fix* code too — process-spawn overhead dwarfed the race window, so it was
  measuring nothing. The board suite is now checked against a pre-cycle commit and produces
  8 failures and 2 errors there, which is what makes its green meaningful.
- **Test the configuration you actually run.** The transport suite was 19/19 green over a
  live bug because it never ran `hubmsg` while the relay daemon was up — the only
  configuration that exists in production.

---

## Known limitations

Stated plainly, because a reviewer's time is wasted rediscovering them.

1. **Wakes are still keystrokes.** The transport is fundamentally "type into someone's
   terminal". It is guarded now — deferred when a human is attached and when the pane shows
   a confirmation dialog — but the guards recognise known dialog shapes, so an unfamiliar
   modal from a future CLI version could slip through. This is the residual risk worth
   watching.
2. **Confirmation still observes the terminal**, though only via cursor coordinates
   (`cursor_x`/`cursor_y`) rather than matching rendered text. That is vendor-agnostic and
   far more stable than scraping output, but it is still an inference from the screen
   rather than an end-to-end acknowledgement.
3. **Wakes fail closed** — an ambiguous wake is dedup-guarded and never redelivered, so the
   durable inbox is the backstop rather than automatic retry.

Fixed since the first draft of this document, listed because an earlier reviewer flagged
them: crash recovery now replays a write-ahead log automatically rather than by hand; a
relay running stale code is detected by comparing a SHA-256 fingerprint of the script
against the one recorded in its pidfile, and refuses to report healthy; resolved errors no
longer appear in health output; the wake queue and inboxes are `chmod 700`; and a wake can
no longer confirm a dialog it happens to land on.

---

## Layout

| File | Lines | Role |
|---|---|---|
| `board.py` | 677 | Task board: state machine, locking, ledger, inboxes |
| `hubwaked` | 276 | Wake relay daemon for sandboxed agents |
| `hubmsg` | 115 | Queue-and-ping, the only cross-vendor message path |
| `shell.sh` | 190 | Session launchers, account status, relay supervision |
| `tests/` | 487 | The two suites |
| `HUB.md` | 259 | Operating manual |
| `README.md` | 248 | What it is and what is verified versus assumed |
| `AGENTS-codex.md` | 88 | Protocol for the Codex agent (it reads `AGENTS.md`, never `CLAUDE.md`) |
| `runbooks/` | — | Problems that already cost real time once, with symptom and fix |

---

## Trying it

```bash
hubs                                   # who is up, relay health, which accounts are signed in
zeus                                   # attach to an agent; Ctrl-b d detaches
hub new "title" --detail "..." --owner Prometheus
hubmsg Prometheus "..." --task T-020   # queues and wakes in one call
hub events --tail 20                   # the audit trail
```

Start an agent from inside the repository you want it working on — each session inherits the
directory it was launched from.
