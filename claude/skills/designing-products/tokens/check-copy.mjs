// The copy gate: banned phrases (copy-banned.txt, each with a reason) and unsourced stats in page text.
// node check-copy.mjs [--banned list.txt] path... (.html .jsx .tsx .mdx). Exit 0 clean, 2 findings, 1 no input.
import fs from 'node:fs'; import path from 'node:path';
const here = path.dirname(new URL(import.meta.url).pathname), args = process.argv.slice(2), at = args.indexOf('--banned');
const list = at >= 0 ? args.splice(at, 2)[1]
  : [path.join(here, 'copy-banned.txt'), path.join(here, '..', 'reference', 'copy-banned.txt')].find((p) => fs.existsSync(p));
const fail = (msg) => { console.error(`check-copy: ${msg}`); process.exit(1); };
if (!list || !fs.existsSync(list)) fail('no copy-banned.txt beside the script or given with --banned');
const rules = fs.readFileSync(list, 'utf8').split('\n').filter((l) => l.trim() && !l.startsWith('#')).map((l) => {
  const [phrase, reason] = l.split('|').map((s) => s.trim());
  if (!phrase || !reason) fail(`${list}: every entry needs "phrase | reason": ${l}`);
  const body = phrase.replace(/\*$/, '').split(/[\s-]+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('[\\s-]+');
  return { reason, re: new RegExp(`\\b${body}${phrase.endsWith('*') ? '\\w*' : '\\b'}`, 'i') };
});
const walk = (p) => (fs.statSync(p).isDirectory()
  ? fs.readdirSync(p).filter((n) => n !== 'node_modules' && !n.startsWith('.')).flatMap((n) => walk(path.join(p, n)))
  : /\.(html?|jsx|tsx|mdx)$/.test(p) ? [p] : []);
const files = args.flatMap((p) => (fs.existsSync(p) ? walk(p) : fail(`${p} does not exist`)));
if (!files.length) fail('no .html, .jsx, .tsx or .mdx file to scan');
// Copy: text nodes, attributes readers see, strings with a space, lines with no code. Not markup, CSS or calls.
const SEEN = new Set(['alt', 'title', 'aria-label', 'placeholder', 'content', 'value', 'label']);
const copyOf = (line) => {
  const l = line.replace(/\b([\w:-]+)=("[^"]*"|'[^']*'|\{\{[^}]*\}\})/g, (m, name) => (SEEN.has(name) ? m : ' '));
  const parts = [...l.matchAll(/(?<![=-])>([^<>{}]+)(?=<|$)/g), ...l.matchAll(/(["'`])((?:(?!\1).)*\s(?:(?!\1).)*)\1/g)]
    .map((m) => m[m.length - 1]).filter((t) => !/\w\(|\d(?:px|r?em|v[hw]|ms|deg)\b/.test(t));
  const bare = l.replace(/<[^>]*>/g, ' ');
  if (!/[;=(){}]|^\s*(import|export|const|let|return)\b/.test(bare)) parts.push(bare);
  return parts.join(' | ').replace(/[‘’]|&(apos|#39|rsquo);/g, "'").replace(/&nbsp;/g, ' ');
};
// shortcut: a source marker within a line counts as the stat's source; tie it to the element if gamed.
const STAT = /\d+(?:\.\d+)?\s?%|\b\d+(?:\.\d+)?\s?[x×](?!\w)|\b\d+(?:\.\d+)?\s+times\s+(?:faster|more|less|fewer|cheaper|better|quicker)\b/i;
const SOURCE = /source|<cite|according to|illustrative|<sup|data-source/i, blank = (m) => m.replace(/[^\n]/g, ' ');
// Numbers in a table, a <data>, <meter> or <output>, or an element with data-value are data, not claims.
const DATA = /<(table|td|th|data|meter|output)\b[^>]*>[\s\S]*?<\/\1>|<(\w+)\b[^>]*\bdata-value\b[^>]*>[\s\S]*?<\/\2>/gi;
let found = 0;
for (const f of files) {
  const raw = fs.readFileSync(f, 'utf8').split('\n'), code = raw.join('\n').replace(/<(script|style)\b[\s\S]*?<\/\1>|\/\*[\s\S]*?\*\/|<!--[\s\S]*?-->|(?<![:\w'"])\/\/[^\n]*/gi, blank);
  const lines = code.split('\n'), facts = code.replace(DATA, blank).split('\n');
  lines.forEach((line, i) => {
    if (/copy-ok:\s*\S/.test(raw[i]) || /copy-ok:\s*\S/.test(raw[i - 1] ?? '')) return; // the escape, with a reason
    const text = copyOf(line);
    const say = (hit, why) => { found++; console.error(`${f}:${i + 1} "${hit}": ${why}`); };
    for (const r of rules) { const m = text.match(r.re); if (m) say(m[0], r.reason); }
    const s = copyOf(facts[i]).match(STAT);
    if (s && !raw.slice(Math.max(0, i - 1), i + 2).some((x) => SOURCE.test(x))) say(s[0], 'a stat with no source; cite it or mark it illustrative');
  });
}
console.error(`${found} copy finding(s) in ${files.length} file(s)`);
process.exit(found ? 2 : 0);
