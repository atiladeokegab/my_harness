# Moving the hub to the cloud VM and back

**When.** The whole hub (Zeus, Hermes, Prometheus, `hub live`, the board) runs on `hub-host`
(e2-standard-4, europe-west2-a, project `my-hub-project`, no public IP; created and verified
2026-10-12), and the laptop is only a console. **The VM is always on:** nothing stops it but
`hub host down`. The idle stop is opt-in (instance metadata `hub-idle-stop=on`, off by default).
Always on: about $136 a month (e2-standard-4 $0.1727/h, plus disk and NAT); budget alert £110 at 50/90/100%.
**The hub lives in exactly one place at a time.**

**The laptop's commands.** `hub host up` · `hub host tunnel` (leave it running all day: it forwards
the dashboard, http://127.0.0.1:8765/, with every PDF and page under Files, and reviews,
http://127.0.0.1:8766/, and reconnects by itself) · `hub host ssh` (a shell, with the same forwards) ·
`hub host status` · `hub host down`.

## Laptop → VM

1. **Quiesce the laptop.** In each agent: let it finish or `hub release` what it holds. Push every
   builder branch (`git -C <worktree> push`). Then `hubkill all` and check: `tmux ls` shows no `hub-*`.
2. **Up.** `hub host status` → `RUNNING` (it is always on). If it says anything else: `hub host up` →
   `up. In: hub host ssh`.
3. **Copy the hub** (about 670 MB; minutes through IAP):
   ```bash
   tar -C ~ -czf - --exclude=hub/.uv-cache --exclude=hub/.venv --exclude='hub/__pycache__' hub \
     | gcloud compute ssh hub-host --zone=europe-west2-a --project=my-hub-project --tunnel-through-iap \
         --command='rm -rf ~/hub.prev; [ -d ~/hub ] && mv ~/hub ~/hub.prev; tar -C ~ -xzf -'
   ```
4. **Copy the config, no credentials:**
   ```bash
   cd ~ && tar -czf - .claude/settings.json .claude/CLAUDE.md .claude/agents .claude/skills \
       .claude-hermes/settings.json .codex/config.toml .gitconfig $(ls -d .claude/projects/-home-*/memory) \
     | gcloud compute ssh hub-host --zone=europe-west2-a --project=my-hub-project --tunnel-through-iap \
         --command='tar -C ~ -xzf -'
   ```
5. **Bootstrap** (first time ~10 minutes; later runs only fill gaps): `hub host ssh`, then
   `HUB_GIT_NAME=<name> HUB_GIT_EMAIL=<email> bash ~/hub/cloud/bootstrap.sh` (the Git identity your
   laptop commits with), then `exec bash -l` so `zeus`, `hermes` and `prometheus` exist.
6. **Logins**, first time and whenever one expires: start each agent once and sign it in (`zeus`,
   `hermes`, each with its own account; `codex login` for `prometheus`), then `gh auth login` and
   `gcloud auth login`. `hubaccounts` shows all three signed in.
7. **Event repos.** For each live event `<p>` (repo `<owner>/<p>`):
   ```bash
   gh repo clone <owner>/<p> ~/code/<p> && hub init-repo ~/code/<p>
   git -C ~/code/<p> config user.email "$HUB_GIT_EMAIL"
   ```
   Its `.env`, from the laptop (never git): `gcloud compute scp --tunnel-through-iap
   --zone=europe-west2-a --project=my-hub-project ~/code/<p>/.env hub-host:~/code/<p>/.env`
8. **Start.** On the VM: `hermes <p>`, `Ctrl-b d`; `prometheus <p>`, `Ctrl-b d`;
   `tmux new -d -s hub-live-<p> "hub live --project <p>"`; `zeus <p>` and stay attached.
9. **Verify.** `codex sandbox echo sandbox-ok` → `sandbox-ok` (if it fails with a user-namespace
   error, Ubuntu 24.04's AppArmor is blocking it: `echo kernel.apparmor_restrict_unprivileged_userns=0
   | sudo tee /etc/sysctl.d/60-codex.conf && sudo sysctl --system`). Then the round trip, from Zeus:
   `hubmsg Prometheus "ping from the VM: reply with hubmsg Zeus pong"` → `woke`, and within a minute
   Zeus gets `[hub wake]` → `hub receive <id>` shows `pong`. `hubs` lists `hub-zeus`, `hub-hermes`,
   `hub-prometheus`, `hub-relay`, `hub-dashboard`, `hub-live-<p>`. `tail -2 ~/hub/projects/<p>/live.log`
   shows a tick in the last 5 minutes. On the laptop, http://127.0.0.1:8765/ shows the board.
10. **Leave the laptop's agents off.** Its `~/hub` stays (the laptop's `hub host` runs from it, and it
    is the fallback copy), so nothing stops you typing `zeus` there by habit. Don't, while
    `hub host status` says `RUNNING`: a second Zeus on a stale board forks the hub.

**Approval windows on the VM.** `hub review` prints, after its URL, `no display here. On your laptop
run:` and a `gcloud compute ssh ... -- -N -L <port>:localhost:<port>` line. Zeus relays those lines;
the lead runs the line in a second laptop terminal and opens the URL. The click still lands on the VM.
Headless, the port is fixed (`HUB_REVIEW_PORT`, default 8766), so one tunnel serves every review;
leave it open. Only when 8766 is busy (a second review at once) does it print `port 8766 is busy` and
a different `-L` line. A random port each time is what lost two of three clicks on 2026-10-12.

## VM → laptop (when the hub moves back)

1. On the VM: `hub live` has stopped after submit; `hubkill all`.
2. On the laptop: `mv ~/hub ~/hub.before-vm`, then
   ```bash
   gcloud compute ssh hub-host --zone=europe-west2-a --project=my-hub-project --tunnel-through-iap \
     --command='tar -C ~ -czf - --exclude=hub/.uv-cache --exclude=hub/.venv hub' | tar -C ~ -xzf -
   ```
   Check `hub list` shows the event's tasks as the VM had them, then `rm -rf ~/hub.before-vm`.
3. Optional: with the hub back on the laptop, the VM has nothing to do, so `hub host down` →
   `hub host status` → `TERMINATED`. Only the disk is billed while it is stopped. Leave it up if the
   hub moves back to it soon.

## The VM stopped or vanished mid-event

- **It stopped** (a mistaken `hub host down`, host maintenance it didn't live-migrate through, or the
  idle stop if someone set `hub-idle-stop=on`): `hub host up`, `hub host ssh`, then step 8 above.
  Disk state survives (board, inboxes, `projects/`, clones); tmux sessions and any model turn in
  flight do not. Re-enter each agent and tell it to run `hub brief`.
- **You can't reach it** (venue wifi blocks IAP): the hub keeps running without you; agents need no
  console. Try a phone hotspot. `gcloud compute ssh hub-host --zone=europe-west2-a
  --project=my-hub-project --tunnel-through-iap --troubleshoot` names the blocked hop. GitHub's web UI
  still shows every issue and PR.
- **It is gone or broken and the event can't wait: the laptop fallback.** The laptop's `~/hub` is the
  copy from before the cutover. `hub gh-sync --project <p> --pull-only` brings it up to date with
  GitHub (closed issues, assignees, change-requests). `git -C ~/code/<p> pull`. Then `zeus <p>` and
  the hackathon skill's §7: `hub live` is down, so Zeus does the mechanical duties by hand with the
  `/loop` there, and starts `hub live` again as soon as the laptop clone is current. What is lost:
  board notes and inbox messages written on the VM since the cutover, and `~/hub` commits not yet
  mirrored. Copy `~/hub/projects/<p>/` back from the VM when it is reachable again, into
  `~/hub/projects/<p>/vm-<date>/`, never over the laptop's.

## Moving to another host

Same hub, same steps, different box. On a fresh Ubuntu LTS box at Hetzner, OVH or Linode:

1. Create it with the provider's console or CLI: Ubuntu LTS, at least 4 vCPU and 16 GB, your laptop's
   SSH public key. Close every inbound port but 22 (provider firewall), and prefer key-only SSH.
2. As root: `scp ~/hub/cloud/bootstrap.sh root@<ip>: && ssh root@<ip> bash bootstrap.sh` →
   `bootstrap: user hub ready.`
3. "Laptop → VM" steps 1 and 3 to 9 above, with `ssh hub@<ip>` wherever they say
   `gcloud compute ssh hub-host ... --tunnel-through-iap` (step 3:
   `... | ssh hub@<ip> 'rm -rf ~/hub.prev; [ -d ~/hub ] && mv ~/hub ~/hub.prev; tar -C ~ -xzf -'`),
   and `scp` for `gcloud compute scp`. The logins are CL3 unchanged.
4. Swap the commands. `hub host` wraps `gcloud compute`, so on another provider: up and down are that
   provider's start and stop (or never, for an always-on box); `hub host ssh` becomes
   `ssh -L 8765:localhost:8765 hub@<ip>`; and `hub review`'s printed line becomes
   `ssh -N -L <port>:localhost:<port> hub@<ip>` (same port). Making `hub host` provider-aware is a
   later task, once a provider is chosen; until then these are typed by hand.
5. Not carried over: the opt-in idle stop (`cloud/startup.sh` reads GCP instance metadata, and it is
   off by default anyway) and IAP (the provider's firewall plus SSH keys stand in for it).
6. When it works, `hub host down` the GCP VM, and delete it with `gcloud projects delete my-hub-project`
   once nothing on it is needed.

## Logins expire

Claude warns 3 days ahead (`Your login expires in 3 days · run /login to renew`) and `/status` has a
`Login` row; check both agents before an event and `/login` (CL3 flow) if it is close. Codex:
`codex login status`. Never put a `claude setup-token` token in the hub's env by default: it is a
year-long secret in a file. Keep it as the fallback if a login dies mid-event and the browser flow
is impossible (it can only make model requests).
