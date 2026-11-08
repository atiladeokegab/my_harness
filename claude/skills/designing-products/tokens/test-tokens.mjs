// node --test plugin/skills/designing-products/tokens/test-tokens.mjs
// Round trip of Refinery's tokens (refinery-design sections 1 to 4), the drift check and the detect gate can each go red.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { parseFrontmatter, toCss } from './tokens-from-design.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = path.join(here, 'fixtures', 'refinery');
const css = toCss(parseFrontmatter(fs.readFileSync(path.join(fixture, 'DESIGN.md'), 'utf8')));

test('the nine palette tokens, the hero and body roles, radii and spacing come through exactly', () => {
  const want = {
    '--color-ground': '#09090B', '--color-surface': '#18181B', '--color-surface-2': '#1F1F23',
    '--color-border': '#27272A', '--color-ink': '#F4F4F5', '--color-muted': '#A1A1AA',
    '--color-tertiary': '#71717A', '--color-green': '#00D46A', '--color-error': '#EF4444',
    '--type-hero-font-family': '"Work Sans", sans-serif', '--type-hero-font-size': '60px',
    '--type-hero-font-weight': '400', '--type-hero-line-height': '0.97', '--type-hero-letter-spacing': '-0.04em',
    '--type-body-font-family': 'Inter, sans-serif', '--type-body-font-size': '16px', '--type-button-font-weight': '600',
    '--radius-button': '6px', '--radius-panel': '12px', '--space-30': '120px',
    '--button-primary-background-color': 'var(--color-green)',
    '--button-primary-typography-font-size': 'var(--type-button-font-size)',
    '--bp-phone': '390px', '--bp-desktop': '1280px',
  };
  for (const [name, value] of Object.entries(want)) assert.ok(css.includes(`  ${name}: ${value};\n`), `${name}: ${value}`);
  assert.equal((css.match(/^  --color-/gm) || []).length, 9);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
});

test('the committed fixture tokens.css is current, and --check goes red on drift', () => {
  const script = path.join(here, 'tokens-from-design.mjs');
  const run = (...a) => { try { execFileSync('node', [script, ...a], { stdio: 'pipe' }); return 0; } catch (e) { return e.status; } };
  assert.equal(run('--check', path.join(fixture, 'DESIGN.md'), path.join(fixture, 'tokens.css')), 0);
  const tmp = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'tokens-')), 'tokens.css');
  fs.writeFileSync(tmp, css.replace('#00D46A', '#60D175'));
  assert.equal(run('--check', path.join(fixture, 'DESIGN.md'), tmp), 1);
});

test('a family name with a space or a digit is quoted, so "Source Sans 3" stays valid CSS', () => {
  const out = toCss(parseFrontmatter('---\ntypography:\n  body:\n    fontFamily: "Source Sans 3, sans-serif"\n  h1:\n    fontFamily: "' + "'Literata'" + ', serif"\n---\n'));
  assert.ok(out.includes('  --type-body-font-family: "Source Sans 3", sans-serif;\n'), out);
  assert.ok(out.includes("  --type-h1-font-family: 'Literata', serif;\n"), out);
});

test('an unresolved token ref fails loudly', () => {
  assert.throws(() => toCss(parseFrontmatter('---\ncomponents:\n  x:\n    textColor: "{colors.nope}"\n---\n')), /unresolved/);
});

test('check-detect fails on design-system advisories and counted findings, not on other advisories', () => {
  const gate = (input) => {
    try { execFileSync('node', [path.join(here, 'check-detect.mjs')], { input, stdio: 'pipe' }); return 0; } catch (e) { return e.status; }
  };
  // The shape engine 0.1.18 printed for fixtures/refinery/bad.css, which it exited 0 on.
  const rawHex = { antipattern: 'design-system-color', severity: 'advisory', advisory: true, file: 'bad.css', line: 2,
    snippet: 'Undocumented color #1E293B is outside DESIGN.md colors', ignoreValue: '#1E293B' };
  assert.equal(gate('[]'), 0);
  assert.equal(gate(JSON.stringify([rawHex])), 2);
  assert.equal(gate(JSON.stringify([{ antipattern: 'side-tab', severity: 'warning', file: 'x', line: 1, snippet: '' }])), 2);
  assert.equal(gate(JSON.stringify([{ ...rawHex, antipattern: 'undersized-ui-text' }])), 0);
  assert.equal(gate(''), 1);
  assert.equal(gate('{}'), 1);
});
