# Agent hub shell entry points. Sourced from ~/.bashrc (bash only).
#
# Everything is configurable by exporting a variable BEFORE this file is sourced:
#
#   HUB_DIR            where the board, inboxes and runbooks live   (default ~/hub)
#   HUB_CODE_DIR       where your git checkouts live                 (default ~/code)
#   HUB_HOME_PROJECT   repo a bare agent name lands in from outside any repo (default: none,
#                      so the agent starts in the current directory)
#   HUB_LEAD           the planning agent; runs on the default ~/.claude account (default Zeus)
#   HUB_REVIEWER       the hackathon reviewer agent `hub live` sends PRs to  (default Hermes)
#   HUB_CLAUDE_AGENTS  Claude Code agents, space-separated     (default "Zeus Apollo Hermes Athena")
#   HUB_CODEX_AGENTS   Codex agents, space-separated           (default "Prometheus")
#   HUB_AGY_AGENTS     Antigravity (agy) agents, space-separated (default none; runbooks/antigravity-seat.md)
#   HUB_RELAY_SESSION  tmux session name of the wake relay     (default hub-relay)
#   HUB_DASHBOARD      0 to not start the local dashboard (hub dashboard) with an agent
#
# Each agent name becomes a shell command: `zeus`, `apollo`, `prometheus`, ...

export HUB_DIR="${HUB_DIR:-$HOME/hub}"
export HUB_CODE_DIR="${HUB_CODE_DIR:-$HOME/code}"
export HUB_HOME_PROJECT="${HUB_HOME_PROJECT:-}"
HUB_LEAD="${HUB_LEAD:-Zeus}"
HUB_REVIEWER="${HUB_REVIEWER:-Hermes}"
# `-` not `:-`: an explicitly empty roster (e.g. HUB_CODEX_AGENTS="" for a Claude-only
# setup) is honoured; only an unset variable falls back to the default.
HUB_CLAUDE_AGENTS="${HUB_CLAUDE_AGENTS-Zeus Apollo Hermes Athena}"
HUB_CODEX_AGENTS="${HUB_CODEX_AGENTS-Prometheus}"
HUB_AGY_AGENTS="${HUB_AGY_AGENTS-}"
export HUB_LEAD HUB_REVIEWER HUB_CLAUDE_AGENTS HUB_CODEX_AGENTS HUB_AGY_AGENTS  # `hub gh-sync`, `hub live` and dispatch read these
HUB_RELAY_SESSION="${HUB_RELAY_SESSION:-hub-relay}"

# `timeout` is GNU coreutils. macOS has none by default; Homebrew's coreutils installs it
# as `gtimeout`. Without either, run the command unbounded rather than not at all.
_hub_timeout() {
    local secs="$1"; shift
    if command -v timeout >/dev/null 2>&1; then timeout "$secs" "$@"
    elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$secs" "$@"
    else "$@"; fi
}

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
    # board.py accepts [a-z0-9][a-z0-9._-]{0,47}. Map anything else (spaces, a leading
    # dot or underscore, very long names) onto that, or every hub command in the session
    # would exit with "invalid project name".
    basename "$top" | tr '[:upper:]' '[:lower:]' \
        | sed 's/[^a-z0-9._-]/-/g; s/^[^a-z0-9]*//' | cut -c1-48
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
    # hubmsg defers a wake to an attached pane and hands it to the relay. Without a relay,
    # a deferred or relayed wake is never delivered, so start it for every agent.
    _hub_start_relay
    _hub_start_dashboard

    if ! tmux has-session -t "$sess" 2>/dev/null; then
        # Env is passed to the tmux session only — never exported into this shell, or it
        # would leak into every later command in this terminal.
        # The board state goes into the system prompt rather than being left for the
        # agent to discover: a session should open already knowing what is waiting for
        # it and what its peers are holding, instead of spending its first turn asking.
        # hub claim puts each task's worktree under ~/work; --add-dir saves a prompt per edit there.
        mkdir -p "$HOME/work"
        local brief; brief="$(HUB_AGENT="$name" HUB_PROJECT="$proj" \
            "$HUB_DIR/board.py" brief 2>/dev/null)"

        # Token and cost metrics go to the dashboard's local OTLP sink, tagged by agent.
        local otel=()
        [ "${HUB_DASHBOARD:-1}" = 0 ] || otel=(-e CLAUDE_CODE_ENABLE_TELEMETRY=1
            -e OTEL_METRICS_EXPORTER=otlp
            -e OTEL_EXPORTER_OTLP_METRICS_PROTOCOL=http/json
            -e OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:8765/v1/metrics
            -e OTEL_RESOURCE_ATTRIBUTES="agent=$name")
        tmux new-session -d -s "$sess" -c "$dir" \
            -e CLAUDE_CONFIG_DIR="$cfg" \
            -e CLAUDE_CODE_SESSION_NAME="$name" \
            "${otel[@]}" \
            -e HUB_AGENT="$name" \
            -e HUB_DIR="$HUB_DIR" \
            -e HUB_PROJECT="$proj" \
            claude --add-dir "$HOME/work" ${brief:+--append-system-prompt "$brief"}
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
    # A current relay is enough wherever it runs: one whose tmux server lost its socket (the default
    # socket was recreated) is invisible to has-session, and the watchdog then started a doomed
    # second relay every minute.
    "$HUB_DIR/hubwaked" --status >/dev/null 2>&1 && return 0
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

# The dashboard is a page you glance at, so it should already be there: one background
# session, started with the first agent of the day, idempotent after that.
# HUB_DASHBOARD=0 turns it off.
_hub_start_dashboard() {
    [ "${HUB_DASHBOARD:-1}" = 0 ] && return 0
    tmux has-session -t hub-dashboard 2>/dev/null && return 0
    tmux new-session -d -s hub-dashboard -c "$HUB_DIR" -e HUB_DIR="$HUB_DIR" \
        "$HUB_DIR/board.py" dashboard
    echo "started dashboard (http://127.0.0.1:8765/, hub dashboard --open for a window)"
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
    _hub_start_dashboard

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
        # Trust the launch dir up front: an untrusted dir opens on "Trust this folder?",
        # and the next wake's keystrokes back out of it into the Agent Command Center.
        # A -c override doesn't skip that prompt, so record the trust the way clicking
        # "Trust" does, in config.toml.
        # The HUB_* vars go through shell_environment_policy.set because Codex's tool
        # commands run in its shared app-server daemon, whose env is whatever the first
        # launch had -- the tmux -e values never reach them.
        # ~/work holds each claim's worktree (hub claim), so it is writable too, and so is
        # $HUB_CODE_DIR: a worktree's commits land in its clone's .git ($HUB_CODE_DIR/<p>/.git).
        # No worktrees feature: hub claim makes the worktrees, and with it /new in a git repo opens a
        # "Where should the new conversation run?" picker that ate a reset's handover.
        local proj; proj="$(_hub_project_for "$dir")"
        mkdir -p "$HOME/work"
        local ccfg="${CODEX_HOME:-$HOME/.codex}/config.toml"
        grep -qF "[projects.\"$dir\"]" "$ccfg" 2>/dev/null || \
            printf '\n[projects."%s"]\ntrust_level = "trusted"\n' "$dir" >> "$ccfg"
        tmux new-session -d -s "$sess" -c "$dir" \
            -e HUB_AGENT="$name" \
            -e HUB_DIR="$HUB_DIR" \
            -e HUB_PROJECT="$proj" \
            -e CODEX_HOME="${CODEX_HOME:-$HOME/.codex}" \
            codex --sandbox workspace-write --add-dir "$HUB_DIR" --add-dir "$HOME/work" --add-dir "$HUB_CODE_DIR" \
                --disable worktrees \
                -c "shell_environment_policy.set.HUB_AGENT=\"$name\"" \
                -c "shell_environment_policy.set.HUB_DIR=\"$HUB_DIR\"" \
                -c "shell_environment_policy.set.HUB_PROJECT=\"$proj\""
        echo "started $name in $dir  (codex, account: ${CODEX_HOME:-$HOME/.codex})"
        echo "  writable: \$PWD, $HUB_DIR, $HOME/work and $HUB_CODE_DIR"
        [ -e "${CODEX_HOME:-$HOME/.codex}/auth.json" ] || \
            echo "  not signed in yet -- run /login inside the session, once."
    fi

    _hub_attach "$sess"
}

# --- Antigravity (agy) agents ---------------------------------------------------
# An agy agent runs Google's Antigravity CLI on a Google AI Pro login, which
# lives under ~/.gemini (shared with the unused Gemini CLI: never rm it). Its hooks and
# statusLine come from the templates in $HUB_DIR/agy/, merged key by key into agy's own files
# so your trusted folders and agy's own keys survive. runbooks/antigravity-seat.md.
_hub_agy_config() {
    python3 - "$HUB_DIR" "$1" "$2" <<'PY'
import json, os, sys, tempfile
hub, name, cwd = sys.argv[1:]
home = os.path.expanduser("~/.gemini")

def render(template):
    text = open(os.path.join(hub, "agy", template)).read()
    return json.loads(text.replace("<HUB>", json.dumps(hub)[1:-1]).replace("<Name>", name))

def merge(path, update, trust=None):
    try:
        cur = json.load(open(path))
    except FileNotFoundError:
        cur = {}
    except ValueError as e:
        sys.exit(f"{path} is not valid JSON ({e}); left alone, fix it by hand")
    if not isinstance(cur, dict):
        sys.exit(f"{path} is not a JSON object; left alone, fix it by hand")
    cur.update(update)
    # shortcut: assumes trustedWorkspaces is a list of paths (unseen); any other shape is left alone.
    tw = cur.get("trustedWorkspaces")
    if trust and isinstance(tw, list) and all(isinstance(p, str) for p in tw) and trust not in tw:
        tw.append(trust)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = os.stat(path).st_mode & 0o777 if os.path.exists(path) else 0o644
    with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(path), delete=False) as f:
        json.dump(cur, f, indent=2)
        f.write("\n")
    os.chmod(f.name, mode)
    os.replace(f.name, path)

merge(os.path.join(home, "config", "hooks.json"), render("hooks.json"))
merge(os.path.join(home, "antigravity-cli", "settings.json"), render("settings.json"), cwd)
PY
}

_hub_enter_agy() {
    local name="$1" want="$2"
    local sess; sess="$(_hub_session "$name")"
    local dir
    # Its last workspace (what the watchdog recorded), unless told otherwise; never ~.
    if [ -n "$want" ]; then dir="$(_hub_launch_dir "$want")" || return 1
    else dir="$(cat "$HOME/.local/state/hub-watchdog/$name" 2>/dev/null)"; fi
    # Else a scratch checkout the reader may write in (create it once: git init $HUB_CODE_DIR/factory-sandbox).
    if [ ! -d "$dir" ] || [ "$dir" -ef "$HOME" ]; then dir="$HUB_CODE_DIR/factory-sandbox"; fi
    [ -d "$dir" ] || { echo "no launch dir: $dir (create it, or name a project)" >&2; return 1; }

    local v; v="$(AGY_CLI_DISABLE_AUTO_UPDATE=true timeout 20 agy --version 2>&1)"
    # agy's self-update keeps the old binary as agy.<id>.old; put back the one matching the pinned hash.
    if ! grep -qE '(^|[^0-9.])1\.4\.2([^0-9.]|$)' <<<"$v"; then
        local old; for old in "$HOME"/.local/bin/agy.*.old; do
            [ "$(sha256sum "$old" 2>/dev/null | cut -d' ' -f1)" = 085f43e0d0628a8a8dabe1e547067818fa2c0adc86cfac98a3c4492918f455ef ] || continue
            mv "$HOME/.local/bin/agy" "$HOME/.local/bin/agy.$(date +%s).unpinned" 2>/dev/null
            cp -p "$old" "$HOME/.local/bin/agy" && echo "agy was ${v:-missing}; restored pinned 1.4.2 from $old" >&2
            v="$(AGY_CLI_DISABLE_AUTO_UPDATE=true timeout 20 agy --version 2>&1)"; break
        done
    fi
    if ! grep -qE '(^|[^0-9.])1\.4\.2([^0-9.]|$)' <<<"$v"; then
        echo "agy 1.4.2 needed, found: ${v:-not installed}" >&2
        echo "  pin it from the versioned tarball (never install.sh): $HUB_DIR/runbooks/antigravity-seat.md" >&2
        return 1
    fi

    _hub_start_relay
    _hub_start_dashboard

    if ! tmux has-session -t "$sess" 2>/dev/null; then
        mkdir -p "$HOME/work" "$HOME/.gemini"
        # agy reads ~/.gemini/GEMINI.md; a real file there is someone's own, so it is kept.
        local md="$HOME/.gemini/GEMINI.md"
        if [ ! -e "$md" ] || [ -L "$md" ]; then ln -sfn "$HUB_DIR/AGENTS-gemini.md" "$md"
        else echo "  $md is a real file, left alone: $name will not see AGENTS-gemini.md" >&2; fi
        _hub_agy_config "$name" "$dir" || return 1
        # Flash by default: the Pro model's weekly bucket runs dry first. HUB_AGY_MODEL picks another
        # Gemini model, probed once.
        local model=gemini-3.8-flash-medium m="${HUB_AGY_MODEL:-}"
        case "$m" in
            ""|"$model") ;;
            gemini-*)
                # HUB_NO_HOOKS: the global hooks fire in -p mode too and would beat, surface and deliver as the seat.
                if (cd /tmp && HUB_NO_HOOKS=1 AGY_CLI_DISABLE_AUTO_UPDATE=true timeout 90 env -u GEMINI_API_KEY -u AGY_ADC_AUTH \
                        agy -p "Reply with the single word OK" --model "$m" --output-format json 2>/dev/null) \
                        | grep -q '"status":"SUCCESS"'; then model=$m
                else echo "  $m did not answer a probe; starting on $model" >&2; fi ;;
            *) echo "  HUB_AGY_MODEL=$m refused: only Gemini models run in agy; starting on $model" >&2 ;;
        esac
        # HUB_PROJECT empty: the reader works across projects, like the lead. env -u keeps a stray
        # key in the tmux server's env from moving agy off the AI Pro login.
        tmux new-session -d -s "$sess" -x 200 -y 50 -c "$dir" \
            -e HUB_AGENT="$name" \
            -e HUB_DIR="$HUB_DIR" \
            -e HUB_PROJECT= \
            -e AGY_CLI_DISABLE_AUTO_UPDATE=true \
            env -u GEMINI_API_KEY -u AGY_ADC_AUTH agy --dangerously-skip-permissions --model "$model"
        echo "started $name in $dir  (agy $model, login: ~/.gemini/antigravity-cli)"
        [ -e "$HOME/.gemini/antigravity-cli/antigravity-oauth-token" ] || \
            echo "  not signed in yet -- sign in with Google inside the session, once (runbook)."
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
for _hub_a in $HUB_AGY_AGENTS; do
    eval "$(echo "$_hub_a" | tr '[:upper:]' '[:lower:]')() { _hub_enter_agy $_hub_a \"\$1\"; }"
done
unset _hub_a

# Which account each agent uses, and whether it has been signed in yet.
# Names of factory.json's agents of one kind (claude, codex, agy); nothing without a factory.json.
_hub_factory_agents() {
    python3 -c 'import json, sys
try: agents = json.load(open(sys.argv[1])).get("agents") or []
except (OSError, ValueError): agents = []
print(" ".join(a["name"] for a in agents if isinstance(a, dict) and a.get("kind") == sys.argv[2] and a.get("name")))' \
        "$HUB_DIR/factory.json" "$1" 2>/dev/null
}

hubaccounts() {
    local a cfg claudes agys
    claudes="$(_hub_factory_agents claude)"; claudes="${claudes:-$HUB_CLAUDE_AGENTS}"
    for a in $claudes; do
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
    # agy keeps its Google login in one token file (checked, never read).
    agys="$(_hub_factory_agents agy)"; agys="${agys:-$HUB_AGY_AGENTS}"
    cfg="$HOME/.gemini/antigravity-cli"
    for a in $agys; do
        if ! command -v agy >/dev/null 2>&1; then
            printf "  %-11s %-28s agy CLI not installed\n" "$a" "$cfg"
        elif [ -e "$cfg/antigravity-oauth-token" ]; then
            printf "  %-11s %-28s signed in (agy)\n" "$a" "$cfg"
        else
            printf "  %-11s %-28s NEEDS LOGIN (agy)\n" "$a" "$cfg"
        fi
    done
}

# Who's running, and what Claude Code itself can see.
hubs() {
    _hub_prune_sockets
    echo "tmux sessions:"
    _hub_timeout 5 tmux list-sessions -F "  #{session_name}  (#{?session_attached,attached,detached})" 2>/dev/null \
        | grep "hub-" || echo "  none"
    echo
    echo "claude sessions:"
    _hub_timeout 15 claude agents --json 2>/dev/null \
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
        _hub_timeout 5 tmux list-sessions -F "#{session_name}" 2>/dev/null | grep "^hub-" \
            | while read -r s; do tmux kill-session -t "$s" && echo "stopped $s"; done
    else
        local sess; sess="$(_hub_session "$1")"
        tmux kill-session -t "$sess" && echo "stopped $sess"
    fi
    # Forget it in the watchdog too, or it relaunches a deliberately stopped agent.
    if [ "$1" = "all" ]; then rm -f "$HOME"/.local/state/hub-watchdog/*
    else rm -f "$HOME/.local/state/hub-watchdog/$(echo "${1:0:1}" | tr '[:lower:]' '[:upper:]')${1:1}"*; fi
    _hub_prune_sockets
}
