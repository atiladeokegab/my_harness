# Agent hub shell entry points. Sourced from ~/.bashrc (bash only).
#
# Everything is configurable by exporting a variable BEFORE this file is sourced:
#
#   HUB_DIR            where the board, inboxes and runbooks live   (default ~/hub)
#   HUB_CODE_DIR       where your git checkouts live                 (default ~/code)
#   HUB_HOME_PROJECT   repo a bare agent name lands in from outside any repo (default: none,
#                      so the agent starts in the current directory)
#   HUB_LEAD           the planning agent; runs on the default ~/.claude account (default Zeus)
#   HUB_CLAUDE_AGENTS  Claude Code agents, space-separated     (default "Zeus Apollo Hermes Athena")
#   HUB_CODEX_AGENTS   Codex agents, space-separated           (default "Prometheus")
#   HUB_RELAY_SESSION  tmux session name of the wake relay     (default hub-relay)
#
# Each agent name becomes a shell command: `zeus`, `apollo`, `prometheus`, ...

export HUB_DIR="${HUB_DIR:-$HOME/hub}"
export HUB_CODE_DIR="${HUB_CODE_DIR:-$HOME/code}"
export HUB_HOME_PROJECT="${HUB_HOME_PROJECT:-}"
HUB_LEAD="${HUB_LEAD:-Zeus}"
HUB_CLAUDE_AGENTS="${HUB_CLAUDE_AGENTS:-Zeus Apollo Hermes Athena}"
HUB_CODEX_AGENTS="${HUB_CODEX_AGENTS:-Prometheus}"
HUB_RELAY_SESSION="${HUB_RELAY_SESSION:-hub-relay}"

# Resolve a project name to its checkout. Any git repo directly under $HUB_CODE_DIR works
# with no registration, and the hub itself resolves by its directory name.
_hub_project_dir() {
    local n="$1" d
    for d in "$HUB_CODE_DIR/$n" "$HOME/$n"; do
        [ -d "$d/.git" ] && { echo "$d"; return 0; }
    done
    return 1
}

# Where should this agent start? Explicit argument wins; then the repo you are standing
# in (so `cd somewhere && apollo` keeps working); then the home project, if one is set;
# then wherever you are.
_hub_launch_dir() {
    local want="$1" dir
    if [ -n "$want" ]; then
        if [ "$want" = "." ]; then echo "$PWD"; return 0; fi
        if dir="$(_hub_project_dir "$want")"; then echo "$dir"; return 0; fi
        echo "no such project: $want" >&2
        echo "known:" >&2
        ls -d "$HUB_CODE_DIR"/*/.git "$HUB_DIR"/.git 2>/dev/null \
            | sed 's:/\.git$::; s:.*/::; s/^/  /' >&2
        return 1
    fi
    if git -C "$PWD" rev-parse --show-toplevel >/dev/null 2>&1; then
        git -C "$PWD" rev-parse --show-toplevel
        return 0
    fi
    if [ -n "$HUB_HOME_PROJECT" ] && dir="$(_hub_project_dir "$HUB_HOME_PROJECT")"; then
        echo "$dir"
        return 0
    fi
    echo "$PWD"
}

# Each agent runs on its own Claude account, so each needs its own config directory —
# credentials, settings and history are per-directory and would otherwise overwrite each
# other. The lead stays on the default ~/.claude (usually already authenticated).
_hub_config_dir() {
    if [ "$1" = "$HUB_LEAD" ]; then
        echo "$HOME/.claude"
    else
        echo "$HOME/.claude-$(echo "$1" | tr '[:upper:]' '[:lower:]')"
    fi
}

# Session discovery reads <config>/sessions/, so isolated config dirs cannot see each
# other unless that one directory is shared. Everything else stays separate.
_hub_bootstrap_config() {
    local name="$1" dir="$2"
    [ "$dir" = "$HOME/.claude" ] && return 0

    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "created config dir for $name: $dir"
        echo "  you will need to sign in to this agent's account once."
    fi
    mkdir -p "$HOME/.claude/sessions"
    [ -e "$dir/sessions" ]  || ln -s "$HOME/.claude/sessions" "$dir/sessions"
    [ -e "$dir/CLAUDE.md" ] || ln -s "$HOME/.claude/CLAUDE.md" "$dir/CLAUDE.md"
    [ -e "$dir/skills" ] || [ ! -d "$HOME/.claude/skills" ] || ln -s "$HOME/.claude/skills" "$dir/skills"
    # Copied, not linked: accounts differ in which models they can use.
    [ -f "$dir/settings.json" ] || cp "$HOME/.claude/settings.json" "$dir/settings.json" 2>/dev/null
}

# Claude Code names its sockets by PID and normally removes them on clean exit; an
# uncleanly killed session leaves one behind. A socket whose PID is gone is definitively
# orphaned. Never delete by name — the PID is the only safe signal.
_hub_prune_sockets() {
    local dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/cc-socks"
    [ -d "$dir" ] || return 0
    local sock pid
    for sock in "$dir"/*.sock; do
        [ -e "$sock" ] || continue
        pid="$(basename "$sock" .sock)"
        case "$pid" in (*[!0-9]*) continue ;; esac
        kill -0 "$pid" 2>/dev/null || rm -f "$sock"
    done
}

# The board is machine-wide, so an agent launched in a repo should not be offered another
# repo's work. Agents already inherit their working directory from wherever you launch
# them; this extends that so they inherit a task scope too. Deliberately empty inside the
# hub itself — the lead plans across every project and needs the whole board.
_hub_project_for() {
    local dir="$1" top
    top="$(cd "$dir" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)" || return 0
    [ -n "$top" ] || return 0
    [ "$top" -ef "$HUB_DIR" ] && return 0
    basename "$top" | tr '[:upper:]' '[:lower:]'
}

_hub_session() { echo "hub-$(echo "$1" | tr '[:upper:]' '[:lower:]')"; }

_hub_attach() {
    if [ -n "$TMUX" ]; then
        tmux switch-client -t "$1"
    else
        tmux attach -t "$1"
    fi
}

_hub_enter() {
    local name="$1" want="$2"
    local sess; sess="$(_hub_session "$name")"
    local cfg; cfg="$(_hub_config_dir "$name")"
    local dir; dir="$(_hub_launch_dir "$want")" || return 1
    local proj; proj="$(_hub_project_for "$dir")"

    _hub_prune_sockets
    _hub_bootstrap_config "$name" "$cfg"

    if ! tmux has-session -t "$sess" 2>/dev/null; then
        # Env is passed to the tmux session only — never exported into this shell, or it
        # would leak into every later command in this terminal.
        # The board state goes into the system prompt rather than being left for the
        # agent to discover: a session should open already knowing what is waiting for
        # it and what its peers are holding, instead of spending its first turn asking.
        local brief; brief="$(HUB_AGENT="$name" HUB_PROJECT="$proj" \
            "$HUB_DIR/board.py" brief 2>/dev/null)"

        tmux new-session -d -s "$sess" -c "$dir" \
            -e CLAUDE_CONFIG_DIR="$cfg" \
            -e CLAUDE_CODE_SESSION_NAME="$name" \
            -e HUB_AGENT="$name" \
            -e HUB_DIR="$HUB_DIR" \
            -e HUB_PROJECT="$proj" \
            claude ${brief:+--append-system-prompt "$brief"}
        echo "started $name in $dir  (account: $cfg)${proj:+  project: $proj}"
    else
        local at; at="$(tmux display-message -p -t "$sess" '#{pane_current_path}' 2>/dev/null)"
        echo "attaching to running $name${at:+ in $at}"
    fi

    _hub_attach "$sess"
}

# --- Codex agents --------------------------------------------------------------
# A Codex agent runs OpenAI's Codex CLI, not Claude Code, so none of the Claude config-dir
# machinery above applies: it authenticates against a ChatGPT account via `codex login`
# and keeps its state in $CODEX_HOME (~/.codex). What makes it a hub agent is the two
# things that are vendor-neutral -- HUB_AGENT, which is all board.py needs to attribute
# work, and a tmux session named hub-<agent>, which is how hubmsg wakes it.
# Codex is sandboxed and cannot connect to the tmux socket, so it cannot wake anyone
# itself -- hubmsg queues the keystroke and this relay, running outside the sandbox,
# performs it. Only needed while a sandboxed agent is up, so it starts with one.
_hub_start_relay() {
    # A relay started before a hubwaked upgrade has no current pidfile/status contract.
    # Replace that stale-code session instead of reporting a live daemon as down.
    if tmux has-session -t "$HUB_RELAY_SESSION" 2>/dev/null \
        && ! HUB_DIR="$HUB_DIR" "$HUB_DIR/hubwaked" --status >/dev/null 2>&1; then
        tmux kill-session -t "$HUB_RELAY_SESSION"
        echo "restarting wake relay after code upgrade"
    fi
    if ! tmux has-session -t "$HUB_RELAY_SESSION" 2>/dev/null; then
        tmux new-session -d -s "$HUB_RELAY_SESSION" -c "$HUB_DIR" \
            -e HUB_DIR="$HUB_DIR" \
            "$HUB_DIR/hubwaked"
        echo "started wake relay ($HUB_RELAY_SESSION)"
    fi
}

_hub_enter_codex() {
    local name="$1" want="$2"
    local sess; sess="$(_hub_session "$name")"
    local dir; dir="$(_hub_launch_dir "$want")" || return 1

    if ! command -v codex >/dev/null 2>&1; then
        echo "codex CLI not installed:  npm install -g @openai/codex" >&2
        return 1
    fi

    _hub_start_relay

    if ! tmux has-session -t "$sess" 2>/dev/null; then
        # Codex sandboxes writes to the workspace root (wherever you launched it). The hub
        # lives outside that, so without --add-dir the agent can read the board but not
        # claim, note, block or finish anything -- it fails with a bare
        # "Read-only file system: .../hub/inbox/<Agent>.jsonl". Grant exactly the hub, and
        # nothing else: the sandbox still protects everything outside the workspace.
        # --sandbox workspace-write is required, not optional. Since codex 0.153 (the
        # "v1" sandbox migration in ~/.codex/.sandbox_migration) an untrusted directory
        # defaults to read-only, and --add-dir under read-only is a hard error:
        #   "Ignoring --add-dir (...) because the effective permissions do not allow
        #    additional writable roots."
        # codex then exits 1, tmux tears the session down, and you land back in your
        # shell with no visible reason. Naming the mode explicitly keeps the grant valid
        # regardless of whether the launch directory happens to be a trusted project.
        # Codex has no --append-system-prompt; it reads ~/.codex/AGENTS.md (symlinked to
        # hub/AGENTS-codex.md) instead, which tells it to run `hub brief` on arrival.
        tmux new-session -d -s "$sess" -c "$dir" \
            -e HUB_AGENT="$name" \
            -e HUB_DIR="$HUB_DIR" \
            -e HUB_PROJECT="$(_hub_project_for "$dir")" \
            codex --sandbox workspace-write --add-dir "$HUB_DIR"
        echo "started $name in $dir  (codex, account: ${CODEX_HOME:-$HOME/.codex})"
        echo "  writable: \$PWD and $HUB_DIR"
        [ -e "${CODEX_HOME:-$HOME/.codex}/auth.json" ] || \
            echo "  not signed in yet -- run /login inside the session, once."
    fi

    _hub_attach "$sess"
}

# One shell command per agent, named after it in lower case.
for _hub_a in $HUB_CLAUDE_AGENTS; do
    eval "$(echo "$_hub_a" | tr '[:upper:]' '[:lower:]')() { _hub_enter $_hub_a \"\$1\"; }"
done
for _hub_a in $HUB_CODEX_AGENTS; do
    eval "$(echo "$_hub_a" | tr '[:upper:]' '[:lower:]')() { _hub_enter_codex $_hub_a \"\$1\"; }"
done
unset _hub_a

# Which account each agent uses, and whether it has been signed in yet.
hubaccounts() {
    local a cfg
    for a in $HUB_CLAUDE_AGENTS; do
        cfg="$(_hub_config_dir "$a")"
        if [ ! -d "$cfg" ]; then
            printf "  %-11s %-28s not created yet\n" "$a" "$cfg"
        elif [ -e "$cfg/.credentials.json" ]; then
            printf "  %-11s %-28s signed in\n" "$a" "$cfg"
        else
            printf "  %-11s %-28s NEEDS LOGIN\n" "$a" "$cfg"
        fi
    done
    # Codex keeps credentials in its own home, written by `codex login`.
    cfg="${CODEX_HOME:-$HOME/.codex}"
    for a in $HUB_CODEX_AGENTS; do
        if ! command -v codex >/dev/null 2>&1; then
            printf "  %-11s %-28s codex CLI not installed\n" "$a" "$cfg"
        elif [ -e "$cfg/auth.json" ]; then
            printf "  %-11s %-28s signed in (codex)\n" "$a" "$cfg"
        else
            printf "  %-11s %-28s NEEDS LOGIN (codex)\n" "$a" "$cfg"
        fi
    done
}

# Who's running, and what Claude Code itself can see.
hubs() {
    _hub_prune_sockets
    echo "tmux sessions:"
    timeout 5 tmux list-sessions -F "  #{session_name}  (#{?session_attached,attached,detached})" 2>/dev/null \
        | grep "hub-" || echo "  none"
    echo
    echo "claude sessions:"
    timeout 15 claude agents --json 2>/dev/null \
        | python3 -c "import json,sys; [print(f\"  {a['name']}  {a['kind']}  {a['status']}\") for a in json.load(sys.stdin)]" \
        2>/dev/null || echo "  none (or claude agents timed out)"
    echo
    echo "wake relay:"
    HUB_DIR="$HUB_DIR" "$HUB_DIR/hubwaked" --status 2>/dev/null || true
    echo
    echo "accounts:"
    hubaccounts
}

hubkill() {
    if [ -z "$1" ]; then echo "usage: hubkill <agent|all>"; return 1; fi
    if [ "$1" = "all" ]; then
        timeout 5 tmux list-sessions -F "#{session_name}" 2>/dev/null | grep "^hub-" \
            | while read -r s; do tmux kill-session -t "$s" && echo "stopped $s"; done
    else
        local sess; sess="$(_hub_session "$1")"
        tmux kill-session -t "$sess" && echo "stopped $sess"
    fi
    _hub_prune_sockets
}
