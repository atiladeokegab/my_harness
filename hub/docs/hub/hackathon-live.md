# Hackathon live crew

Part of the hub manual. Index: `~/hub/HUB.md`.

## Hackathon live crew

During a hackathon's build, responsibilities follow `factory.json` and the board (`hub agents`,
`hub brief`), rather than fixed agent names (full rules: the `hackathon` skill):

| Who | Does |
|---|---|
| `hub live` (script) | Every 5 min (a finished gate or deploy, or a `hub done`, runs a merge-and-deploy pass within 10 s): sync, sends PRs and sub-issue changes to the configured reviewer, merges approved PRs one at a time at the reviewed sha (at the reviewer's pace: `--merge-now`, `--hold-merges`), smoke → promote `main` or revert and reopen, the freeze, reminders, nudges. Stops after submit. Lead alerts currently route to Zeus in `live.py`. Log: `projects/<p>/live.log` |
| Configured reviewer | Reviews PRs against their issues, areas and IDEA.md; `LGTM <sha>` on PRs; `FLAG:` on drifting sub-issues; escalates scope, contract, design and secrets to the current lead |
| Assigned builders | Build the tasks they claim, in their own workspaces; never approve their own PRs |
| Lead or announced acting lead | You; DRAFTs, change-requests, questions, escalations and task assignment |

Start it at the end of planning: `systemctl --user enable --now hub-live@<p>`, then enter the assigned reviewer seat.
The unit restarts it on a crash and appends its output to `projects/<p>/live.out`; install, checks and
the switch from an old tmux `hub-live-<p>` are in `runbooks/install-factory-timers.md` section 6. Leave any agent's window with `Ctrl-b d`: `Ctrl-c` or `/quit` in Codex ends the
session, and its wakes then wait for nothing.

