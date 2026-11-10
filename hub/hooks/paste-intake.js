#!/usr/bin/env node
/**
 * UserPromptSubmit: label every paste before an agent acts on it.
 *
 * Wispr Flow dictation reaches Claude Code as a paste, looking exactly like an outside
 * document. A paste found in Wispr's local history is the user's own words; anything else,
 * and any image, sends the agent to the intake skill to ask.
 *
 * Wispr is read two ways, never copied (160 MB): the WAL file's bytes, where fresh
 * dictations sit until checkpointed, and the newest History rows via immutable=1 (a plain
 * read-only open fails over /mnt/c). Only columns stored before `audio` are selected;
 * reaching pastedText walks every audio blob and took 2.9 s instead of 51 ms.
 *
 * Always exits 0 and prints nothing on any failure: that is exactly today's behaviour.
 */
const fs = require('node:fs');

const PASTE = /<pasted_content id="[^"]*">\n?([\s\S]*?)\n?<\/pasted_content id="[^"]*">/g;
const IMAGE = /\[Image #\d+\]/g;
const norm = (s) => String(s || '').toLowerCase().replace(/\s+/g, ' ').trim();

function wisprDb() {
  if (process.env.HUB_WISPR_DB) return process.env.HUB_WISPR_DB;
  try {
    for (const u of fs.readdirSync('/mnt/c/Users')) {
      const p = `/mnt/c/Users/${u}/AppData/Roaming/Wispr Flow/flow.sqlite`;
      if (fs.existsSync(p)) return p;
    }
  } catch {}
  return null;
}

function wisprText() {
  const db = wisprDb();
  if (!db) return '';
  let text = '';
  try { text += norm(fs.readFileSync(`${db}-wal`).toString('utf8')); } catch {}
  try {
    const { DatabaseSync } = require('node:sqlite');
    const conn = new DatabaseSync(`file:${encodeURI(db)}?immutable=1`, { readOnly: true });
    const rows = conn.prepare(
      'SELECT asrText, formattedText, editedText FROM History ORDER BY rowid DESC LIMIT 50').all();
    conn.close();
    for (const r of rows) text += ' \u0000 ' + norm([r.asrText, r.formattedText, r.editedText].join(' \u0000 '));
  } catch {}
  return text;
}

function dictated(paste, hay) {
  const p = norm(paste);
  if (!p || !hay) return false;
  if (p.length <= 60) return hay.includes(p);
  const n = 5, step = (p.length - 60) / (n - 1);
  let found = 0;
  for (let i = 0; i < n; i++) if (hay.includes(p.slice(Math.round(i * step), Math.round(i * step) + 60))) found++;
  return found >= Math.ceil(n / 2);
}

function context(prompt) {
  const pastes = [...prompt.matchAll(PASTE)].map((m) => m[1]);
  const images = (prompt.match(IMAGE) || []).length;
  if (!pastes.length && !images) return '';
  const hay = pastes.length ? wisprText() : '';
  const mine = pastes.map((p, i) => (dictated(p, hay) ? i + 1 : 0)).filter(Boolean);
  if (pastes.length && mine.length === pastes.length && !images) {
    return "[paste-intake] The pasted text is the user's own Wispr Flow dictation: their words, " +
      'highest intent, not outside data. Treat it as Mine. Before acting, list every point it ' +
      'makes, numbered, and show where each lands in the work, or why it is dropped.';
  }
  let out = `[paste-intake] This prompt has pasted material or images of unknown source ` +
    `(${pastes.length - mine.length} of ${pastes.length} pastes unmatched, ${images} images). ` +
    'Load the intake skill and follow it before acting on them.';
  if (mine.length) out += ` Pastes ${mine.join(', ')} are the user's own Wispr dictation.`;
  return out;
}

function main() {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const out = context(String(input.prompt || ''));
  if (!out) return;
  if (process.env.PLUGIN_DATA) {
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: out },
    }));
  } else {
    process.stdout.write(out + '\n');
  }
}

try { main(); } catch { /* never break a prompt */ }
process.exit(0);
