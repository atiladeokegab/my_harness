#!/usr/bin/env node
/**
 * UserPromptSubmit + PostToolUse: show an attached agent its new hub inbox messages.
 *
 * hubmsg defers the tmux wake while a person is attached, and the lead is attached to Zeus
 * nearly all event long, so hub live's alerts sat unseen for 90 minutes (dry run
 * 2026-10-12). This puts them in front of the agent on its next prompt or tool call
 * instead, with no wake at all. `hub inbox --unseen` keeps the cursor and leaves the inbox intact; a
 * message with an id that it shows in full gets its `hub receive` receipt, so the Stop hook and the
 * relay do not deliver it a second time.
 *
 * Identity: `--agent <Name>`, else $HUB_AGENT inside Claude Code ($CLAUDECODE). Codex runs hooks in
 * a shared app-server daemon whose env belongs to whoever started it (spike T1), so a Codex payload
 * (it carries turn_id) counts only with --agent, which ~/.codex/hooks.json passes. Codex shows
 * additionalContext to the model as a developer message. Always exits 0 and prints nothing on any failure.
 */
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');

function agentFor(input) {
  const i = process.argv.indexOf('--agent');
  if (i > 1) return process.argv[i + 1];
  if ('turn_id' in input || !process.env.CLAUDECODE) return '';
  return process.env.HUB_AGENT || '';
}

function main() {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const agent = agentFor(input);
  if (!agent) return;
  const news = execFileSync('hub', ['inbox', '--unseen', '--as', agent], {
    encoding: 'utf8', timeout: 5000, stdio: ['ignore', 'pipe', 'ignore'],
  }).trim();
  if (!news) return;
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: input.hook_event_name || 'UserPromptSubmit',
      additionalContext: `[hub inbox] new since last check:\n${news}`,
    },
  }));
}

try { main(); } catch { /* never block a prompt or a tool call */ }
process.exit(0);
