# A background sub-agent never hears its job finish

**Repo:** any. **First cost:** a sub-agent sat idle for 2.5 hours on a job that had finished.

## Symptom

A sub-agent started with the Agent tool launches a job with Bash `run_in_background`, says it
is waiting for the completion notice, and goes quiet. The job finished long ago; the
sub-agent waits until its parent asks.

## Confirm it

The job's log or exit file shows it ended, and the sub-agent's last message says it is
waiting for a notice.

## Cause

The completion notice is a harness event, delivered into the turn of the session that started
the job. A sub-agent that ends its turn to wait has finished: there is no idle loop left to
take the notice. The hub cannot fix this either. Every hub wake path (`hubmsg`, the relay, the
Stop hook) targets a tmux pane `hub-<agent>` or a `$HUB_AGENT` inbox. A sub-agent has neither:
it runs inside its parent's process and inherits the parent's `$HUB_AGENT`, so a `hubmsg` to
"it" lands in the parent's inbox.

## Fix

Never end a sub-agent's turn to wait for a job.

- Job under about 9 minutes: run it in the foreground with a timeout, so the result comes
  back in the same tool call: `timeout 540 hub sh -- make check` with the Bash tool's
  `timeout: 600000`.
- Longer job: start it detached with an exit marker, then wait in the foreground in bounded
  slices, one tool call each, until the marker appears:

  ```bash
  setsid nohup bash -c 'cmd > job.log 2>&1; echo $? > job.exit' >/dev/null 2>&1 &
  # then, repeated as separate Bash calls (timeout 600000) until it prints the exit code:
  timeout 540 bash -c 'until [ -e job.exit ]; do sleep 20; done'; cat job.exit 2>/dev/null || tail -3 job.log
  ```

  For a cloud job, the loop polls the job's status command instead of a file, and matches
  every terminal state (`succeeded|failed|cancelled`), not just success.
- `run_in_background` is still fine in a session that keeps working (a main session, or a
  sub-agent with other tool calls to make meanwhile): the notice arrives on its next turn.
  Only ending the turn to wait for it is the trap.

## Traps while fixing it

Any brief that starts a long job in a sub-agent should say: "wait for it in the foreground in
9-minute slices; never end your turn to wait for a background notice."
