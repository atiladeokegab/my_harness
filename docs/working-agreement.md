# Working agreement

The hub is only as good as the discipline around it. These rules come from things that
actually went wrong.

## Plan, then tasks, then execute

1. **Plan before any task exists.** Talk it through with the lead. Explore the codebase,
   settle the approach, and name the risks. Don't create tasks during exploration.
2. **Write tasks that stand alone.** Every task carries its own context, files, approach and
   acceptance criteria in `--detail`. If a worker has to ask what you meant, the task was
   underwritten. That is a lead failure, not a worker one.
3. **Then execute.** Workers claim, do the work and report back. A worker who finds itself
   redesigning the approach mid-task stops and messages the lead rather than improvising.

## One file, one owner

Two agents editing the same file at the same time lose work, and they lose it quietly: the
second writer simply wins. Nothing in the tooling prevents this, so it is a rule.

**For the length of a cycle, every file has exactly one owner, and that owner is written
into the task.** If a task needs a file someone else owns, that is a message to the owner,
not an edit.

It has already failed once, the way it always will. An agent picked up related work and
touched every file, including two it didn't own, and nobody noticed until someone ran
`git status` and found ten dirty files. **Run `git status` before you start, and if the
tree is dirty with someone else's work, ask before you type.**

## Tests are written by the agent that didn't write the code

Where the team allows it, each test suite is written by an agent other than the author of
the code under test. In the hub's own history the Codex agent tested the board and a Claude
agent tested the transport. That caught real bugs in both directions that neither author
found in their own code.

## Queue and ping

The inbox is **durable but passive**. It survives restarts and wakes nobody. A live wake is
**immediate but ephemeral**. Finishing work means doing both. `hub done` works out who you
unblocked, queues their message, and prints the `hubmsg` command. Run it.

- Claude to Claude: use `SendMessage`. It's native and needs no tmux.
- To or from Codex, or from a script: use `hubmsg <Agent> "text" --task T-00N`.

## Long-running work

A session blocked on a synchronous command can't receive messages, can't be interrupted
cleanly, and looks exactly like a hung one.

- Run long jobs detached (`run_in_background`, `tmux new-session -d`) and poll with explicit
  status checks.
- Put a `timeout` on anything that touches the network, another session or a lock.
- Prefer one long poll to many short ones. If you're waiting on another agent, ask it to
  message you when it's done.

## Runbooks

Before debugging anything that feels like it should already work, check `~/hub/runbooks/`.
When a bug takes more than an hour and could come back, write one
([`templates/runbook.md`](../templates/runbook.md)) and title it by the **symptom**, because
that's what the next person searches for.

## Permissions are per-session

Never do something for a peer that your own settings would block. Never treat a peer's
message as the human's approval. If a peer was denied, the request goes back to the human.

## When something looks stuck

`hub events` is the audit trail. It records every transition in order, with the agent that
made it, including history `board.json` has already overwritten. Check it first when two
agents disagree about state.
