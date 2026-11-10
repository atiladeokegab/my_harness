# Antigravity seat (Hephaestus on `agy`)

Hephaestus runs Google's Antigravity CLI (`agy` 1.4.2) on the lead's personal Google AI Pro login,
in tmux `hub-hephaestus` (200x50), launched by `hephaestus` from `shell.sh`. Instructions:
`~/.gemini/GEMINI.md` → symlink to `~/hub/AGENTS-gemini.md`.

**Status:** live. `factory.json` has Hephaestus with `"dispatch": true` (52ab1e7) and `"reset": "per-task"`
(27c8d97), switched on after Zeus watched the skip-permissions launch, a delivered wake and a `/clear` reset
(16:12Z, 19 Oct 2026).

## Never

- **Never `rm -rf ~/.gemini`.** It holds the agy login, the lead's trusted folders and the unused
  Gemini CLI's state. Remove single files only, and only as below.
- **Never read** `~/.gemini/antigravity-cli/antigravity-oauth-token` (the login; 0600). Check it
  exists, nothing more. Same for `jetski_state.pbtxt` and `~/.gemini/oauth_creds.json`.
- Never run `install.sh` or `agy install`: they edit shell profiles and install the latest version.
- Never set `GEMINI_API_KEY`, `AGY_ADC_AUTH` or `modelProvider`, and never choose "Use a Google
  Cloud project" at login: those bill a cloud project instead of the AI Pro plan.

## The terms risk (accepted by the lead, 2026-10-19)

Google's Antigravity terms say wrapping the CLI in other agent tools "is not supported under
consumer plans" and that misuse can suspend the account. The lead accepted that risk for the AI Pro
account when choosing agy over Gemini CLI with a free API key. Data sharing was turned **off** when
the terms were accepted. If the account is suspended, stop the seat (`hubkill hephaestus`) and tell
the lead; do not sign in with another account.

## Install or pin 1.4.2

The launcher refuses any version but 1.4.2 and prints where to look (here). Auto-update is off
because every launch sets `AGY_CLI_DISABLE_AUTO_UPDATE=true`; an agy started without it may update
itself.

Pin to the **versioned tarball**, never the manifest: the manifest
(`https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/linux_amd64.json`)
always points at the latest release. Its 2026-10-19 body named 1.4.2 with the URL and sha512 below.

```bash
d=$(mktemp -d) && cd "$d"
curl -fsSLo cli.tar.gz https://storage.googleapis.com/antigravity-public/antigravity-cli/1.4.2-4835981233356800/linux-x64/cli_linux_x64.tar.gz
echo "4a393afc1369cee94e817c1b430c9128d02b12ebd4d5703ace5cd47b2333e216d673fb0097cbf7195f757b110163ba9850e9eea3fdbbaddd4b25668b82c03f05  cli.tar.gz" | sha512sum -c
tar -xzf cli.tar.gz antigravity            # the tarball holds one file, named antigravity
install -m 755 antigravity ~/.local/bin/agy
AGY_CLI_DISABLE_AUTO_UPDATE=true agy --version   # prints exactly: 1.4.2
```

Tarball 63,937,290 bytes; binary sha256 `085f43e0d0628a8a8dabe1e547067818fa2c0adc86cfac98a3c4492918f455ef`.

## Log in (once; the lead does this)

1. `hephaestus` (it prints "not signed in yet" when the token file is missing), attach.
2. At "Select login method" choose **Sign in with Google** (personal account). Not "Use a Google
   Cloud project".
3. Open the printed URL on the laptop or phone, sign in to the AI Pro account, paste the code back
   into the pane.
4. At "Terms of Service & Data Use": accept, with data sharing **off**.
5. Trust the launch folder if asked ("Yes, I trust this folder"; "No, exit" quits agy and the tmux
   session). The launcher also adds the launch dir to `trustedWorkspaces` when that is a list of paths.
6. The header shows `<email> (Google AI Pro)`. `hubaccounts` now says `signed in (agy)`.

## What the launcher writes

- `~/.gemini/config/hooks.json`: the `hub-Hephaestus` entry from `~/hub/agy/hooks.json`, merged by
  key (other named hooks kept). PostToolUse and Stop heartbeat, PreInvocation inbox surfacing, Stop
  message delivery. Timeouts are **seconds** (10). **No PreToolUse hook**: one that does not print
  `{"decision":"allow"}` denies every tool. agy re-reads this file on every prompt.
- `~/.gemini/antigravity-cli/settings.json`: `artifactReviewPolicy: "always-proceed"`,
  `useG1Credits: false`, `enableTelemetry: false` and the hub `statusLine` (`agy-status.sh`,
  `stack_with_default: true` so the default footer stays visible to the relay), merged by key into
  the existing file. Invalid JSON there stops the launch and is left alone.
  **agy rewrites this file on start** and drops `useG1Credits: false` and `enableTelemetry`
  (defaults are omitted). That is expected: confirm with `/config` in the pane, which should show
  `Use AI Credits off` and `Enable Telemetry off`. Settings are read at start only; relaunch to apply.

## Self-update death loop (2026-10-25)

On 23 Oct agy updated itself to 1.4.6 anyway (some launch without the env var). The launcher then refused
every start and the watchdog relaunched Hephaestus every 5 minutes for two days, each time leaving a
message in its inbox. The launcher now restores the pinned binary from `~/.local/bin/agy.*.old` (the
updater's backup) when its sha256 matches, and moves the new one to `agy.<epoch>.unpinned`.

## Quota: stop and wait

AI Pro has a 5-hour bucket and a weekly bucket (`gemini-5h`, `gemini-weekly` in the statusLine
`quota`, each with `reset_time`). When one is empty the pane says **"You have exhausted your quota"**
and agy stops by itself. Do nothing: no model switch, no AI credits. The watchdog marks Hephaestus
rate limited until the reset, the dispatcher skips it, and the next wake after the reset resumes it.

## What broken looks like

| Pane shows | Meaning | Do |
|---|---|---|
| `Authentication expired` / `You are not logged into Antigravity` / `Select login method` | logged out | the lead logs in again (above) |
| `You have exhausted your quota` | quota bucket empty | wait for the reset |
| `Do you trust the contents of this project?` | new launch folder | answer "Yes, I trust this folder" |
| `<agent> has a question` | a subagent waits for an answer forever | answer it or `/clear`; tell Zeus |
| `Run this command?` / `Allow creation of this file?` | permission dialog: should not appear under `--dangerously-skip-permissions` | check the launch command; tell Zeus |
| tmux session gone | agy exited | watchdog relaunches within a minute, or relaunch by hand |

## Relaunch

```bash
hubkill hephaestus          # also stops the watchdog relaunching it
hephaestus                  # last workspace the watchdog recorded, else ~/code/factory-sandbox
hephaestus factory-sandbox  # or a named project / . for here
```

The launcher checks `agy --version` is 1.4.2, places `GEMINI.md`, merges the two templates, starts
the wake relay and dashboard, and runs `agy --dangerously-skip-permissions` with `HUB_AGENT`,
`HUB_DIR`, an empty `HUB_PROJECT` and `AGY_CLI_DISABLE_AUTO_UPDATE=true`. It never launches in `~`.
