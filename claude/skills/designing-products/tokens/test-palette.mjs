// node --test plugin/skills/designing-products/tokens/
// The palette, type-scale and brand steps (T-1009): the two palette fixtures, the scale, the theme swap,
// brand.html's drift check and token lock, and the dataviz validator going red on a bad data palette.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { buildPalette, dataColours, findDataviz, hexToOklch, STEPS, themesOf, UsageError, writeGroup } from './palette.mjs';
import { typeScale } from './type-scale.mjs';
import { parseFrontmatter, toCss } from './tokens-from-design.mjs';
import { brandHtml } from './brand-from-design.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const fx = JSON.parse(fs.readFileSync(path.join(here, 'fixtures', 'palettes.json'), 'utf8'));
const hub = path.join(here, 'fixtures', 'hub');
const run = (script, ...a) => { try { execFileSync('node', [path.join(here, script), ...a], { stdio: 'pipe' }); return 0; } catch (e) { return e.status; } };
const tmpCopy = (file) => { const d = fs.mkdtempSync(path.join(os.tmpdir(), 'palette-')); const p = path.join(d, path.basename(file)); fs.copyFileSync(file, p); return p; };

test('the pass fixture clears AA in both themes, keeps the seed as the accent, and ramps in lightness', () => {
  const p = buildPalette(fx.pass);
  assert.ok(p.ok);
  assert.equal(new Set(p.pairs.map((x) => x.theme)).size, 2);
  for (const x of p.pairs) assert.ok(x.ratio >= x.min, `${x.theme} ${x.fg} on ${x.bg} ${x.ratio}`);
  assert.equal(p.colors.accent, fx.pass.seed);
  for (const r of ['accent', 'neutral', 'support', 'support-2']) {
    const L = STEPS.map((s) => hexToOklch(p.colors[`${r}-${s}`]).L);
    assert.ok(L.every((l, i) => !i || l < L[i - 1]), `${r} lightness falls step by step`);
  }
  assert.ok(p.colors['bg-dark'] && p.colors['ink-dark'] && !('accent-dark' in p.colors));
});

test('the reject fixture is refused with the failing pair named, and DESIGN.md is left as it was', () => {
  const p = buildPalette(fx.reject);
  assert.equal(p.ok, false);
  assert.deepEqual(p.pairs.filter((x) => x.ratio < x.min).map((x) => [x.theme, x.fg, x.bg]), fx.reject.fails);
  const design = tmpCopy(path.join(hub, 'DESIGN.md'));
  const before = fs.readFileSync(design, 'utf8');
  assert.equal(run('palette.mjs', '--seed', fx.reject.seed, '--harmony', fx.reject.harmony, design), 1);
  assert.equal(fs.readFileSync(design, 'utf8'), before);
  assert.equal(run('palette.mjs', '--seed', fx.pass.seed, '--harmony', 'triadic', design), 2);
  assert.equal(run('palette.mjs', '--seed', '#808080', '--harmony', 'tonal', design), 2);
});

test('the committed fixture is what the palette and type steps write, and writeGroup leaves other groups alone', () => {
  const md = fs.readFileSync(path.join(hub, 'DESIGN.md'), 'utf8');
  const fm = parseFrontmatter(md);
  const p = buildPalette(fx.pass);
  for (const [k, v] of Object.entries(p.colors)) assert.equal(fm.colors[k], v, k);
  assert.deepEqual(fm.typography, typeScale({ base: 16, ratio: 1.25, body: 'IBM Plex Sans, sans-serif' }).typography);
  const again = parseFrontmatter(writeGroup(md, 'colors', { only: '#000000' }));
  assert.deepEqual(again.colors, { only: '#000000' });
  for (const g of ['typography', 'rounded', 'spacing', 'components']) assert.deepEqual(again[g], fm[g], g);
});

test('the type scale steps by the ratio in six sizes and refuses a caption under 12px', () => {
  const t = typeScale({ base: 16, ratio: 1.25, body: 'X, sans-serif' });
  assert.deepEqual(Object.values(t.typography).map((v) => v.fontSize), ['13px', '16px', '16px', '20px', '25px', '31px', '39px']);
  assert.ok(t.ok);
  const lh = Object.values(t.typography).map((v) => v.lineHeight);
  assert.ok(lh.at(-1) < lh[1] && lh.every((l) => l >= 1.05));
  assert.equal(typeScale({ base: 16, ratio: 1.5, body: 'X' }).ok, false);
  assert.equal(run('type-scale.mjs', '--base', '16', '--ratio', '1.5', '--body', 'X', '--print'), 1);
  assert.equal(run('type-scale.mjs', '--ratio', '1.2', '--print'), 2);
});

test('a -dark colour swaps in for its base in the dark theme, on data-theme and on the OS setting', () => {
  const css = toCss(parseFrontmatter(fs.readFileSync(path.join(hub, 'DESIGN.md'), 'utf8')));
  assert.match(css, /\[data-theme="dark"\] \{\n {2}--color-bg: var\(--color-bg-dark\);/);
  assert.match(css, /:root:not\(\[data-theme="light"\]\) \{\n {4}--color-bg: var\(--color-bg-dark\);/);
  assert.equal(run('tokens-from-design.mjs', '--check', path.join(hub, 'DESIGN.md'), path.join(hub, 'tokens.css')), 0);
});

test('brand.html is current, goes red on drift, and every colour in it is a DESIGN.md colour', () => {
  const design = path.join(hub, 'DESIGN.md'), html = path.join(hub, 'brand.html');
  assert.equal(run('brand-from-design.mjs', '--check', design, html), 0);
  const drifted = tmpCopy(html);
  fs.writeFileSync(drifted, fs.readFileSync(html, 'utf8').replace('Palette', 'Colours'));
  assert.equal(run('brand-from-design.mjs', '--check', design, drifted), 1);
  const page = fs.readFileSync(html, 'utf8');
  const allowed = new Set(Object.values(parseFrontmatter(fs.readFileSync(design, 'utf8')).colors).map((v) => v.toUpperCase()));
  for (const hex of page.match(/#[0-9a-fA-F]{6}\b/g)) assert.ok(allowed.has(hex.toUpperCase()), hex);
  for (const id of ['palette', 'type', 'space', 'flow', 'dos']) assert.ok(page.includes(`<section id="${id}">`), id);
  assert.ok(page.includes('11.95:1') && page.includes('<strong>Review</strong>'));
  assert.ok(!brandHtml(fs.readFileSync(path.join(here, 'fixtures', 'refinery', 'DESIGN.md'), 'utf8')).includes('undefined'));
});

test('data colours come from the dataviz skill and its validator goes red on a bad palette', { skip: !findDataviz() && 'dataviz skill not found; set DATAVIZ_DIR' }, async () => {
  const roles = buildPalette(fx.pass).roles;
  const good = await dataColours(roles);
  assert.ok(good.ok);
  assert.equal(Object.keys(good.colors).filter((k) => !k.endsWith('-dark')).length, 8);
  const fake = fs.mkdtempSync(path.join(os.tmpdir(), 'dataviz-'));
  fs.mkdirSync(path.join(fake, 'references')); fs.mkdirSync(path.join(fake, 'scripts'));
  fs.copyFileSync(path.join(good.source, 'scripts', 'validate_palette.js'), path.join(fake, 'scripts', 'validate_palette.js'));
  const row = (i, hex) => `| ${i} | x | \`${hex}\` | \`${hex}\` |`;
  fs.writeFileSync(path.join(fake, 'references', 'palette.md'), `## Categorical palette\n\n${['#2A78D6', '#2B79D7', '#2C7AD8'].map((h, i) => row(i + 1, h)).join('\n')}\n\n## Next\n`);
  assert.equal((await dataColours(roles, fake)).ok, false);
});

test('themes: a dark-only product passes on dark alone, writes one set of roles, and the CLI reads themes from DESIGN.md', () => {
  const p = buildPalette(fx.darkOnly);
  assert.ok(p.ok);
  assert.deepEqual([...new Set(p.pairs.map((x) => x.theme))], ['dark']);
  assert.equal(p.colors.accent, fx.darkOnly.seed);
  assert.ok(!Object.keys(p.colors).some((k) => k.endsWith('-dark')));
  assert.equal(p.colors.bg, p.roles.dark.bg);
  const dir = path.join(here, 'fixtures', 'refinery-dark');
  const md = fs.readFileSync(path.join(dir, 'DESIGN.md'), 'utf8');
  for (const [k, v] of Object.entries(p.colors)) assert.equal(parseFrontmatter(md).colors[k], v, k);
  assert.deepEqual(themesOf({}), ['light', 'dark']);
  assert.deepEqual(themesOf({ themes: '[dark, light]' }), ['light', 'dark']);
  assert.deepEqual(themesOf({ themes: '[light]' }), ['light']);
  assert.throws(() => themesOf({ themes: '[sepia]' }), UsageError);
  assert.throws(() => themesOf({ themes: '[]' }), UsageError);
  const copy = tmpCopy(path.join(dir, 'DESIGN.md'));
  assert.equal(run('palette.mjs', '--seed', fx.darkOnly.seed, '--harmony', fx.darkOnly.harmony, copy), 0);
  fs.writeFileSync(copy, md.replace('themes: [dark]', 'themes: [light, dark]'));
  assert.equal(run('palette.mjs', '--seed', fx.darkOnly.seed, '--harmony', fx.darkOnly.harmony, copy), 1);
  fs.writeFileSync(copy, md.replace('themes: [dark]', 'themes: [sepia]'));
  assert.equal(run('palette.mjs', '--seed', fx.darkOnly.seed, '--harmony', fx.darkOnly.harmony, copy), 2);
  // Tokens and brand.html carry the dark theme only: no swap block, no light panel.
  assert.equal(run('tokens-from-design.mjs', '--check', path.join(dir, 'DESIGN.md'), path.join(dir, 'tokens.css')), 0);
  assert.ok(!fs.readFileSync(path.join(dir, 'tokens.css'), 'utf8').includes('data-theme'));
  assert.equal(run('brand-from-design.mjs', '--check', path.join(dir, 'DESIGN.md'), path.join(dir, 'brand.html')), 0);
  const page = fs.readFileSync(path.join(dir, 'brand.html'), 'utf8');
  assert.ok(page.includes('<html lang="en" data-theme="dark">') && page.includes('Dark theme') && !page.includes('Light theme'));
});
