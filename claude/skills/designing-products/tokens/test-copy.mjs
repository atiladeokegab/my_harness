// node --test plugin/skills/designing-products/tokens/test-copy.mjs
// The copy gate passes the good page, fails the bad one with file:line, and each pass can be made to go red.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

const here = path.dirname(new URL(import.meta.url).pathname);
const fixtures = path.join(here, 'fixtures', 'copy');
const gate = (...a) => spawnSync('node', [path.join(here, 'check-copy.mjs'), ...a], { encoding: 'utf8' });
const tmp = (name, body) => { const f = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'copy-')), name); fs.writeFileSync(f, body); return f; };

test('the good page exits 0 and the bad page exits 2 naming each line', () => {
  assert.equal(gate(path.join(fixtures, 'good.html')).status, 0);
  const bad = gate(path.join(fixtures, 'bad.html'));
  assert.equal(bad.status, 2);
  for (const want of [':5 "reimagined"', ':8 "Unlock"', ':9 "In today\'s fast-paced"', ':9 "solution"', ':10 "10x"', ':11 "can help"'])
    assert.ok(bad.stderr.includes(want), want);
});

test('the good page goes red without its copy-ok note or its source', () => {
  const good = fs.readFileSync(path.join(fixtures, 'good.html'), 'utf8');
  assert.equal(gate(tmp('a.html', good.replace(/<!-- copy-ok:.*-->/, ''))).status, 2);
  assert.equal(gate(tmp('b.html', good.replace(/<cite>.*<\/cite>/, ''))).status, 2);
});

test('JSX code is not copy; JSX text and copy strings are', () => {
  const code = 'export const Hero = () => <button onClick={() => unlock(seamless)} style={{ width: "100%" }}>Open the report</button>;\n';
  assert.equal(gate(tmp('ok.jsx', code)).status, 0);
  const css = "const bg = { background: 'radial-gradient(115% 60% at 50% -6%, transparent 62%)', m: '0px 0px -35% 0px' };\n";
  assert.equal(gate(tmp('css.tsx', `${css}    // waiting for 35% left a blank box\n`)).status, 0); // Refinery's false positives
  assert.equal(gate(tmp('text.jsx', '<p className="lead">\n  Unlock the power of audits\n</p>\n')).status, 2);
  assert.equal(gate(tmp('str.tsx', 'const hero = { title: "A powerful way to ship" };\n')).status, 2);
  assert.equal(gate(tmp('cell.html', '<table><tr><td>99%</td><th>2x</th></tr></table>\n<td>\n  8.3%\n</td>\n<meter value="0.4">40%</meter> <span data-value="5.1">5.1%</span>\n')).status, 0);
  assert.equal(gate(tmp('hero.html', '<table><tr><td>99%</td></tr></table>\n<h1>Cut audit time by 73%</h1>\n')).status, 2);
  assert.match(gate(tmp('line.tsx', '<p>ok</p>\n<p>Run 3 times faster</p>\n')).stderr, /line\.tsx:2 "3 times faster"/);
});

test('the list and the inputs are checked', () => {
  assert.equal(gate('/nonexistent').status, 1);
  assert.equal(gate(path.join(here, 'check-copy.mjs')).status, 1);
  assert.equal(gate('--banned', tmp('l.txt', 'seamless\n'), path.join(fixtures, 'bad.html')).status, 1);
  const rows = fs.readFileSync(path.join(here, '..', 'reference', 'copy-banned.txt'), 'utf8').split('\n').filter((l) => l.trim() && !l.startsWith('#'));
  for (const r of rows) assert.match(r, /^[^|]+\S \| \S/, `no reason: ${r}`);
});
