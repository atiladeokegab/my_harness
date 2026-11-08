#!/usr/bin/env node
/**
 * SessionStart: warn when harness files would reach someone else's tree.
 *
 * The guard everyone agreed to and nobody runs at 17:50. `hub ship-check --quiet` prints
 * nothing unless there is something to say, so a clean repo costs a silent ~150ms and
 * adds nothing to context.
 *
 * Two hosts, two output shapes. Codex (PLUGIN_DATA set) wants SessionStart JSON; native
 * Claude reads raw stdout. Emitting raw text to Codex is how the warning silently went
 * nowhere -- Prometheus caught that from inside a Codex session.
 *
 * Always exits 0. A hook that breaks session startup is a hook somebody deletes, and the
 * warning was the whole product.
 */

const { execFileSync } = require('node:child_process');

function sh(cmd, args) {
  try {
    return execFileSync(cmd, args, { encoding: 'utf8', timeout: 8000, stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  } catch (e) {
    // ship-check exits 1 when it has something to report; that is a result, not a failure.
    return e && typeof e.stdout === 'string' ? e.stdout.trim() : '';
  }
}

function main() {
  if (!sh('git', ['rev-parse', '--show-toplevel'])) return;   // not a repo

  const hub = process.env.HUB_DIR || `${process.env.HOME}/hub`;
  let out = sh('hub', ['ship-check', '--quiet']);
  if (!out) out = sh(`${hub}/board.py`, ['ship-check', '--quiet']);
  if (!out) return;                                            // clean, or no upstream

  if (process.env.PLUGIN_DATA) {
    process.stdout.write(JSON.stringify({
      systemMessage: 'CLEAN-REPO',
      hookSpecificOutput: { hookEventName: 'SessionStart', additionalContext: out },
    }));
  } else {
    process.stdout.write(out + '\n');
  }
}

try { main(); } catch { /* never break startup */ }
process.exit(0);
