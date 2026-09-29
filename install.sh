#!/usr/bin/env bash
# my_harness installer. Idempotent: re-run it after `git pull` to upgrade.
#
# It never touches hub runtime state (board.json, events.jsonl, inbox/, wake/), and it
# backs up any file it would replace to <file>.bak.<timestamp> first.
set -euo pipefail

REPO="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HUB_DIR_FROM_ENV="${HUB_DIR:+yes}"
HUB_DIR="${HUB_DIR:-$HOME/hub}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
CLAUDE_DIR="$HOME/.claude"
CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"
STAMP="$(date +%Y%m%d-%H%M%S)"

DRY=0 DO_CLAUDE=1 DO_CODEX=1 DO_SHELL=1 DO_BIN=1

usage() {
    cat <<EOF
usage: ./install.sh [options]

  --dry-run        show what would change, change nothing
  --hub-dir DIR    install the hub somewhere other than ~/hub (default: \$HUB_DIR or ~/hub)
  --no-claude      skip ~/.claude (CLAUDE.md, skills, settings.json)
  --no-codex       skip the ~/.codex/AGENTS.md link
  --no-shell       don't add the source line to ~/.bashrc
  --no-bin         don't (re)point hub/hubmsg/hubwaked in ~/.local/bin — use this when
                   installing a second, separate hub
  -h, --help       this text

HUB_DIR is honoured if it is already exported (e.g. by a previous install's shell.sh).
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY=1 ;;
        --hub-dir) HUB_DIR="${2:?--hub-dir needs a path}"; HUB_DIR_FROM_ENV=""; shift ;;
        --no-claude) DO_CLAUDE=0 ;;
        --no-codex) DO_CODEX=0 ;;
        --no-shell) DO_SHELL=0 ;;
        --no-bin) DO_BIN=0 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
run()  { if [ "$DRY" = 1 ]; then printf '  would: %s\n' "$*"; else "$@"; fi; }
have() { command -v "$1" >/dev/null 2>&1; }

backup() {
    local f="$1"
    if [ -e "$f" ] || [ -L "$f" ]; then
        run cp -RP "$f" "$f.bak.$STAMP"
        say "  backed up $f -> $f.bak.$STAMP"
    fi
}

# Copy src to dst only when the content differs. Backs up a differing dst unless told the
# file is pure code that the harness owns (hub scripts are upgraded in place).
put() {
    local src="$1" dst="$2" mode="$3" owned="${4:-}"
    if [ -f "$dst" ] && cmp -s "$src" "$dst"; then return 0; fi
    [ -z "$owned" ] && [ -e "$dst" ] && backup "$dst"
    run install -m "$mode" "$src" "$dst"
    say "  $dst"
}

# Same, for text that mentions ~/hub: rewrite the path when installing elsewhere.
put_text() {
    local src="$1" dst="$2" tmp
    tmp="$(mktemp)"
    if [ "$HUB_DIR" = "$HOME/hub" ]; then cp "$src" "$tmp"
    else sed "s#~/hub#$HUB_DIR#g" "$src" > "$tmp"; fi
    put "$tmp" "$dst" 644 "${3:-}"
    rm -f "$tmp"
}

# ---------------------------------------------------------------------------------------
step "prerequisites"
missing=0
for c in python3 tmux git; do
    if have "$c"; then say "  ok       $c"; else say "  MISSING  $c (required)"; missing=1; fi
done
for c in claude uv codex gh node; do
    if have "$c"; then say "  ok       $c"; else say "  absent   $c (optional)"; fi
done
if [ "$(uname -s)" = Darwin ]; then
    # hubwaked needs GNU coreutils (stat -c, touch -d, readlink -f, sha256sum), and the
    # scripts expect a modern bash rather than macOS's bash 3.2.
    if [ -d /opt/homebrew/opt/coreutils/libexec/gnubin ] || [ -d /usr/local/opt/coreutils/libexec/gnubin ]; then
        say "  ok       GNU coreutils (Homebrew)"
    else
        say "  MISSING  GNU coreutils (required on macOS)"; missing=1
    fi
    bash_major="$(bash -c 'echo ${BASH_VERSINFO[0]}')"
    if [ "${bash_major:-3}" -ge 4 ]; then say "  ok       bash $bash_major"
    else say "  MISSING  bash 4+ (macOS ships 3.2)"; missing=1; fi
    [ "$missing" = 1 ] && say "  on macOS:  brew install bash coreutils tmux python git"
fi
[ "$missing" = 1 ] && { say "install the required tools first."; exit 1; }
[ "$DRY" = 1 ] && say "  (dry run: nothing will be written)"

# ---------------------------------------------------------------------------------------
step "hub -> $HUB_DIR"
[ -n "$HUB_DIR_FROM_ENV" ] && say "  (HUB_DIR taken from your environment; unset it or pass --hub-dir to choose another)"
run mkdir -p "$HUB_DIR/tests" "$HUB_DIR/runbooks"
for f in board.py hubmsg hubwaked hubctl; do put "$REPO/hub/$f" "$HUB_DIR/$f" 755 owned; done
put "$REPO/hub/gh_sync.py" "$HUB_DIR/gh_sync.py" 644 owned   # imported by board.py: missing = hub crashes
for f in gh_board.py live.py live_merge.py review.py; do put "$REPO/hub/$f" "$HUB_DIR/$f" 644 owned; done   # imported by board.py / gh_sync.py
put "$REPO/hub/shell.sh" "$HUB_DIR/shell.sh" 644 owned
put "$REPO/hub/.gitignore" "$HUB_DIR/.gitignore" 644 owned
# Docs and the Codex protocol are yours to edit (docs/customizing.md tells you to rename
# agents in AGENTS-codex.md), so a differing copy is backed up before it is refreshed.
for f in HUB.md OVERVIEW.md ARCHITECTURE.md AGENTS-codex.md; do
    put_text "$REPO/hub/$f" "$HUB_DIR/$f"
done
for f in "$REPO"/hub/tests/*.py; do put "$f" "$HUB_DIR/tests/$(basename "$f")" 644 owned; done
# Runbooks you wrote yourself are left alone; shipped ones are refreshed, with a backup
# if you edited them.
for f in "$REPO"/runbooks/*.md; do put_text "$f" "$HUB_DIR/runbooks/$(basename "$f")"; done

if [ ! -f "$HUB_DIR/board.json" ]; then
    if [ "$DRY" = 1 ]; then say "  would: seed $HUB_DIR/board.json"
    else printf '{"next_id": 1, "tasks": [], "schema_version": 1}\n' > "$HUB_DIR/board.json"
         say "  seeded $HUB_DIR/board.json"; fi
else
    say "  kept existing board.json"
fi

# ---------------------------------------------------------------------------------------
if [ "$DO_BIN" = 1 ]; then
    step "commands -> $BIN_DIR"
    run mkdir -p "$BIN_DIR"
    # Symlinks to the installed copy: board.py resolves its data directory from its own real
    # path, so a link into the git checkout would put your board inside the repo.
    # Agent launchers and hubs/hubaccounts/hubkill are also linked to hubctl, so they work
    # from any shell (macOS logs in to zsh; shell.sh is bash). Re-run the installer after
    # changing the roster to link new names.
    pairs="hub:board.py hubmsg:hubmsg hubwaked:hubwaked hubctl:hubctl"
    for name in ${HUB_CLAUDE_AGENTS-Zeus Apollo Hermes Athena} ${HUB_CODEX_AGENTS-Prometheus} hubs hubaccounts hubkill; do
        pairs="$pairs $(echo "$name" | tr '[:upper:]' '[:lower:]'):hubctl"
    done
    for pair in $pairs; do
        name="${pair%%:*}" target="$HUB_DIR/${pair#*:}"
        if [ "$(readlink "$BIN_DIR/$name" 2>/dev/null)" != "$target" ]; then
            [ -e "$BIN_DIR/$name" ] && [ ! -L "$BIN_DIR/$name" ] && backup "$BIN_DIR/$name"
            run ln -sfn "$target" "$BIN_DIR/$name"
            say "  $BIN_DIR/$name -> $target"
        fi
    done
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *) say "  NOTE: $BIN_DIR is not on PATH. Add: export PATH=\"$BIN_DIR:\$PATH\"" ;;
    esac
fi

# ---------------------------------------------------------------------------------------
if [ "$DO_CLAUDE" = 1 ]; then
    step "claude -> $CLAUDE_DIR"
    run mkdir -p "$CLAUDE_DIR/skills"
    put_text "$REPO/claude/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"

    for skill in "$REPO"/claude/skills/*/; do
        name="$(basename "$skill")" dst="$CLAUDE_DIR/skills/$name"
        if [ -d "$dst" ] && diff -rq "$skill" "$dst" >/dev/null 2>&1; then continue; fi
        if [ -d "$dst" ]; then
            run mv "$dst" "$dst.bak.$STAMP"
            say "  backed up $dst -> $dst.bak.$STAMP"
        fi
        run cp -R "$skill" "$dst"
        say "  skill: $name"
    done

    # Agent definitions: the hackathon lead starts its builder sub-agents from agents/builder.md.
    run mkdir -p "$CLAUDE_DIR/agents"
    for agent in "$REPO"/claude/agents/*.md; do
        put_text "$agent" "$CLAUDE_DIR/agents/$(basename "$agent")"
    done

    if [ ! -f "$CLAUDE_DIR/settings.json" ]; then
        put "$REPO/claude/settings.json" "$CLAUDE_DIR/settings.json" 644
    else
        # Never overwrite someone's settings. Only add the one key the hub relies on.
        if [ "$DRY" = 1 ]; then
            say "  would: ensure env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS in settings.json"
        else
            python3 - "$CLAUDE_DIR/settings.json" "$STAMP" <<'PY'
import json, shutil, sys
path, stamp = sys.argv[1], sys.argv[2]
with open(path) as f:
    data = json.load(f)
env = data.setdefault("env", {})
if env.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS") != "1":
    shutil.copy2(path, f"{path}.bak.{stamp}")
    env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"  settings.json: added env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS (backup {path}.bak.{stamp})")
else:
    print("  settings.json: already configured, left alone")
PY
        fi
        say "  a fuller template is in $REPO/claude/settings.json (autoMode, permissions)"
    fi
fi

# ---------------------------------------------------------------------------------------
if [ "$DO_CODEX" = 1 ] && { have codex || [ -d "$CODEX_DIR" ]; }; then
    step "codex -> $CODEX_DIR"
    run mkdir -p "$CODEX_DIR"
    link="$CODEX_DIR/AGENTS.md" target="$HUB_DIR/AGENTS-codex.md"
    if [ "$(readlink "$link" 2>/dev/null)" != "$target" ]; then
        [ -e "$link" ] && [ ! -L "$link" ] && backup "$link"
        run ln -sfn "$target" "$link"
        say "  $link -> $target"
    else
        say "  AGENTS.md already linked"
    fi
fi

# ---------------------------------------------------------------------------------------
if [ "$DO_SHELL" = 1 ]; then
    step "shell"
    rc="$HOME/.bashrc"
    if grep -qsF "$HUB_DIR/shell.sh" "$rc"; then
        say "  $rc already sources the hub"
    elif [ "$DRY" = 1 ]; then
        say "  would: append hub source line to $rc"
    else
        {
            printf '\n# agent hub (my_harness)\n'
            [ "$HUB_DIR" != "$HOME/hub" ] && printf 'export HUB_DIR="%s"\n' "$HUB_DIR"
            printf '[ -f "%s/shell.sh" ] && . "%s/shell.sh"\n' "$HUB_DIR" "$HUB_DIR"
        } >> "$rc"
        say "  appended hub source line to $rc"
    fi
    case "${SHELL##*/}" in
        bash) ;;
        *) say "  NOTE: your login shell is ${SHELL##*/}. The agent commands (zeus, hubs, ...) are"
           say "        installed as executables in $BIN_DIR, so they work there too; make sure"
           say "        $BIN_DIR is on PATH in that shell's rc file (e.g. ~/.zshrc)." ;;
    esac
fi

# ---------------------------------------------------------------------------------------
step "verify"
if [ "$DRY" = 1 ]; then
    say "  skipped (dry run)"
else
    HUB_DIR="$HUB_DIR" HUB_AGENT=installer "$HUB_DIR/board.py" list >/dev/null \
        && say "  hub CLI works" || say "  hub CLI FAILED — run: $HUB_DIR/board.py list"
    bash -n "$HUB_DIR/shell.sh" && say "  shell.sh parses"
fi

cat <<EOF

Done. Next:
  1. Open a new shell (or: source ~/.bashrc).
  2. Type \`zeus\` to start the lead agent. \`Ctrl-b d\` detaches; it keeps running.
  3. Type \`apollo\`, \`hermes\`, \`athena\` and sign each into its own account once.
     \`prometheus\` starts the Codex worker. \`hubs\` shows who is up.
  4. Read $REPO/docs/getting-started.md.
EOF
