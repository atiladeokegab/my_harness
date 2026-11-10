#!/usr/bin/env bash
# Make a fresh Ubuntu LTS box able to run the hub: the GCP event VM today, any always-on host later.
# Nothing here knows the provider; starting and stopping the box is `hub host` (CL1), per provider.
#   As root, first (a box whose only login is root, e.g. Hetzner, OVH, Linode):
#     bash bootstrap.sh            creates hub with sudo and root's SSH keys, then stops
#   As hub, after ~/hub and the config files are copied over (runbooks/hub-on-a-vm.md, 3 and 4):
#     bash ~/hub/cloud/bootstrap.sh
# Every step checks first, so a rerun only fills gaps. It installs no credentials: every agent,
# gh and gcloud log in on the box by hand afterwards (runbook step 6).
set -euo pipefail

if [ "$(id -u)" = 0 ]; then
    id hub >/dev/null 2>&1 || useradd -m -s /bin/bash -G sudo hub
    echo 'hub ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/hub && chmod 0440 /etc/sudoers.d/hub
    if [ -f /root/.ssh/authorized_keys ] && [ ! -f ~/.ssh/authorized_keys ]; then
        install -d -m 0700 -o hub -g hub ~/.ssh
        install -m 0600 -o hub -g hub /root/.ssh/authorized_keys ~/.ssh/authorized_keys
    fi
    echo "bootstrap: user hub ready. Copy ~/hub over as hub, then run this again as hub."
    exit 0
fi
[ "$(id -un)" = hub ] || { echo "bootstrap: run as hub; the hub's paths are ~/..." >&2; exit 1; }
[ -f "$HOME/hub/board.py" ] || { echo "bootstrap: copy ~/hub here first (runbook step 3)" >&2; exit 1; }
export PATH="$HOME/.local/bin:$PATH"
have() { command -v "$1" >/dev/null 2>&1; }
apt_install() { sudo DEBIAN_FRONTEND=noninteractive apt-get install -yq "$@"; }

sudo apt-get update -q
apt_install tmux git make jq curl ca-certificates gnupg graphviz build-essential python3

if ! have gh; then
    sudo install -d -m 0755 /etc/apt/keyrings
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
    sudo apt-get update -q && apt_install gh
fi
if ! have gcloud; then   # the starter's make deploy targets Cloud Run, whatever the host
    curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        | sudo gpg --dearmor --yes -o /usr/share/keyrings/cloud.google.gpg
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
        | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list >/dev/null
    sudo apt-get update -q && apt_install google-cloud-cli
fi
if ! have node; then     # Codex is an npm package
    curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
    apt_install nodejs
fi
if ! have google-chrome; then   # agents' headless screenshots (runbooks/headless-browser-css-checks.md)
    curl -fsSLo /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    apt_install /tmp/chrome.deb && rm -f /tmp/chrome.deb
fi
have uv || curl -LsSf https://astral.sh/uv/install.sh | sh
have claude || curl -fsSL https://claude.ai/install.sh | bash
# Global npm packages into ~/.local, never sudo npm.
[ "$(npm config get prefix)" = "$HOME/.local" ] || npm config set prefix "$HOME/.local"
have codex || npm install -g @openai/codex
if ! have agy; then
    mkdir -p "$HOME/.local/bin"
    tmp=$(mktemp -d)
    curl -fsSL --connect-timeout 10 --max-time 300 -o "$tmp/cli.tar.gz" \
        https://storage.googleapis.com/antigravity-public/antigravity-cli/1.4.2-4835981233356800/linux-x64/cli_linux_x64.tar.gz
    echo "4a393afc1369cee94e817c1b430c9128d02b12ebd4d5703ace5cd47b2333e216d673fb0097cbf7195f757b110163ba9850e9eea3fdbbaddd4b25668b82c03f05  $tmp/cli.tar.gz" | sha512sum -c
    tar -xzf "$tmp/cli.tar.gz" -C "$tmp" antigravity
    install -m 755 "$tmp/antigravity" "$HOME/.local/bin/agy"
    rm -rf "$tmp"
fi
export AGY_CLI_DISABLE_AUTO_UPDATE=true

# The hub's commands, and agent names in every shell.
mkdir -p "$HOME/.local/bin"
for cmd in hub:board.py hubmsg:hubmsg hubwaked:hubwaked; do
    ln -sfn "$HOME/hub/${cmd#*:}" "$HOME/.local/bin/${cmd%%:*}"
done
grep -q '^# agent hub$' "$HOME/.bashrc" || cat >> "$HOME/.bashrc" <<'EOF'

# agent hub
export PATH="$HOME/.local/bin:$PATH"
[ -f "$HOME/hub/shell.sh" ] && . "$HOME/hub/shell.sh"
EOF

# Plugins: one hub plugin for both vendors (HUB.md, "One plugin, both vendors").
for cfg in "$HOME/.claude" "$HOME/.claude-hermes"; do
    mkdir -p "$cfg"
    for m in anthropics/claude-plugins-official "$HOME/hub/plugin" DietrichGebert/ponytail; do
        CLAUDE_CONFIG_DIR="$cfg" claude plugin marketplace add "$m" >/dev/null
    done
    for p in hub@hub ponytail@ponytail; do
        CLAUDE_CONFIG_DIR="$cfg" claude plugin install "$p" >/dev/null
    done
done
CLAUDE_CONFIG_DIR="$HOME/.claude" claude plugin install vercel@claude-plugins-official >/dev/null
mkdir -p "$HOME/.codex"
ln -sfn "$HOME/hub/AGENTS-codex.md" "$HOME/.codex/AGENTS.md"
mkdir -p "$HOME/.gemini"
if [ ! -e "$HOME/.gemini/GEMINI.md" ] || [ -L "$HOME/.gemini/GEMINI.md" ]; then
    ln -sfn "$HOME/hub/AGENTS-gemini.md" "$HOME/.gemini/GEMINI.md"
else
    echo "bootstrap: ~/.gemini/GEMINI.md is a real file; left alone" >&2
fi
if [ -f "$HOME/.codex/config.toml" ]; then   # copied from the laptop: it names the marketplaces
    codex plugin marketplace upgrade >/dev/null
    for p in hub@hub ponytail@ponytail; do codex plugin add "$p" >/dev/null; done
fi

# Commits from here must carry the same Git identity as your laptop, or a deploy that checks the
# author (Vercel does) is silently blocked. Set HUB_GIT_NAME and HUB_GIT_EMAIL before running this.
[ -n "${HUB_GIT_NAME:-}" ] && git config --global user.name "$HUB_GIT_NAME"
[ -n "${HUB_GIT_EMAIL:-}" ] && git config --global user.email "$HUB_GIT_EMAIL"

echo "bootstrap: done. Versions:"
for c in "tmux -V" "git --version" "gh --version" "gcloud --version" "node --version" "uv --version" \
         "claude --version" "codex --version" "agy --version" "dot -V" "google-chrome --version"; do
    printf '  %s\n' "$($c 2>&1 | head -1)"
done
echo "next: logins (runbook step 6), then hubaccounts"
