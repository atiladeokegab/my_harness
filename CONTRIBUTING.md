# Contributing

Thanks for looking. Issues, fixes, runbooks and skills are all welcome.

## How this repo is maintained

This is the public copy of a harness that runs real work every day. The maintainer's working
copy is private; changes flow from it into this repo through a sync that strips machine paths,
accounts and private projects, then a sweep that refuses anything that looks like a secret or
personal data. A pull request here is reviewed and merged here, then ported back, so the next
sync keeps it. If a sync later conflicts with your change, the maintainer resolves it by hand.

## Before you open a pull request

1. **Keep the hub dependency-free.** `hub/` is Python standard library, bash, tmux and git. A new
   dependency needs a reason in the PR, and an optional one must degrade cleanly when absent.
2. **Run the checks.** `make check` unsets the roster and session variables (`HUB_DIR`, `HUB_AGENT`, `HUB_LEAD` and the
   rest of its `unexport` line), so the suites build their own hub in a temp dir:
   ```bash
   cd hub && make check
   ```
   `tests/test_messaging.py` drives real scratch tmux sessions and needs the `hub` command on
   `PATH` (run `./install.sh` first). Every suite uses throwaway boards and never types into a
   real agent's pane.
3. **Test from the behaviour.** A bug fix comes with a test that fails without the fix. Say in
   the PR that you saw it fail.
4. **Write a runbook** in `runbooks/` for a bug that took you more than an hour: the symptom,
   how to confirm it, and the fix.
5. **Keep docs in step.** A change to a command, flag or file layout updates `hub/HUB.md`, the
   page under `hub/docs/hub/` that covers it, and the README if it is user-facing.

## Skills

A skill is a folder in `claude/skills/` with a `SKILL.md` (frontmatter `name` and
`description`) and, for anything long, a `reference/` folder. Add a row to the
[skills index](claude/skills/README.md). Write it for any machine: use `$HUB_DIR`,
`$HUB_CODE_DIR` and the roster variables, never your own paths, accounts or private repos.

## Never commit

- Credentials of any kind: API keys, tokens, service-account JSON, `.env` files, cookies.
- Personal data: real email addresses (use `example.com` or `.invalid`), phone numbers,
  messaging IDs, home paths with a real user name.
- Board data: `board.json`, `events.jsonl`, `inbox/`, `wake/`, `state/`, or a real
  `factory.json` (copy `hub/factory.example.json` instead).

If you find any of these in the repo or its history, please report it privately through
GitHub's security advisory form rather than in a public issue.

## Licence

By contributing you agree that your contribution is licensed under the MIT licence in
[LICENSE](LICENSE).
