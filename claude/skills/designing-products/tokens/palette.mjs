#!/usr/bin/env node
// The palette step: a seed colour and a harmony become OKLCH ramps plus role tokens for each theme DESIGN.md
// declares (`themes: [light, dark]` by default, or `[light]`, or `[dark]`), written into its `colors:`
// frontmatter. No dependencies.
//   node palette.mjs --seed "#1F5FD0" --harmony split [--data] [--print] [DESIGN.md]
// Harmonies: tonal, analogous, complementary, split. --print writes the block to stdout, not the file.
// The seed is the brand's decision, so it is the accent in both themes and is never moved; every other
// role is picked from the ramps to pass. Exit 1, writing nothing, when any pair fails WCAG 2.2 AA
// (1.4.3 text 4.5:1, 1.4.11 the accent as a control against the page 3:1) in a declared theme, or when
// --data colours fail the dataviz skill's validator. Exit 2 on bad arguments.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseFrontmatter } from './tokens-from-design.mjs';

export const STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];
const LIGHTNESS = [0.975, 0.945, 0.89, 0.81, 0.72, 0.635, 0.55, 0.465, 0.385, 0.29, 0.18]; // OKLCH L per step
const HARMONY = { tonal: [], analogous: [30], complementary: [180], split: [150, 210] }; // support hues, degrees from the seed
const STATE_HUE = { success: 150, warning: 70, danger: 27, info: 245 }; // OKLCH h; meaning by convention, not by brand
const NEUTRAL_CHROMA = 0.014; // tinted, never pure grey
const AA_TEXT = 4.5, AA_CONTROL = 3;
// Each theme's roles: [ramp, preferred step]. Searchable roles walk toward the ink end until they pass.
const THEMES = {
  light: { bg: ['neutral', 100], surface: ['neutral', 50], border: ['neutral', 200], ink: ['neutral', 900], muted: ['neutral', 600] },
  dark: { bg: ['neutral', 950], surface: ['neutral', 900], border: ['neutral', 800], ink: ['neutral', 100], muted: ['neutral', 400] },
};

// sRGB <-> OKLab (Ottosson 2020, public domain matrices).
const toLin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const toGamma = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
const rgbOf = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
export function hexToOklch(hex) {
  const [r, g, b] = rgbOf(hex).map(toLin);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return { L, C: Math.hypot(A, B), h: ((Math.atan2(B, A) * 180) / Math.PI + 360) % 360 };
}
function oklchToLinear(L, C, h) {
  const a = C * Math.cos((h * Math.PI) / 180), b = C * Math.sin((h * Math.PI) / 180);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s];
}
// Out-of-gamut colours keep their lightness and hue and lose chroma until they fit.
export function oklchToHex(L, C, h) {
  const fits = (c) => oklchToLinear(L, c, h).every((v) => v >= -1e-4 && v <= 1 + 1e-4);
  let lo = 0, hi = C;
  if (!fits(C)) { for (let i = 0; i < 30; i++) { const mid = (lo + hi) / 2; if (fits(mid)) lo = mid; else hi = mid; } C = lo; }
  return '#' + oklchToLinear(L, C, h).map((v) => Math.round(toGamma(Math.min(1, Math.max(0, v))) * 255)
    .toString(16).padStart(2, '0')).join('').toUpperCase();
}
const luminance = (hex) => { const [r, g, b] = rgbOf(hex).map(toLin); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
export const contrast = (a, b) => { const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

// Chroma tapers toward white and black; the seed replaces the step nearest its own lightness.
function ramp(name, h, C, seed) {
  const out = {};
  STEPS.forEach((step, i) => {
    const L = LIGHTNESS[i];
    out[`${name}-${step}`] = oklchToHex(L, C * (1 - 0.7 * ((L - 0.6) / 0.45) ** 2), h);
  });
  if (seed) {
    const { L } = hexToOklch(seed);
    const i = LIGHTNESS.reduce((best, l, j) => (Math.abs(l - L) < Math.abs(LIGHTNESS[best] - L) ? j : best), 0);
    out[`${name}-${STEPS[i]}`] = seed;
  }
  return out;
}

// Walk a ramp from the preferred step toward `towardInk` until fg passes `min` on every background.
function pick(colors, rampName, from, towardInk, backs, min) {
  const order = towardInk === 'up' ? STEPS.filter((s) => s >= from) : STEPS.filter((s) => s <= from).reverse();
  for (const s of order) {
    const hex = colors[`${rampName}-${s}`];
    if (backs.every((b) => contrast(hex, b) >= min)) return hex;
  }
  return colors[`${rampName}-${from}`]; // nothing passes: keep the preferred step and let the check refuse it
}
function stateColour(h, backs, dark) {
  for (let k = 0; k <= 40; k++) {
    const hex = oklchToHex(dark ? 0.72 + k * 0.006 : 0.52 - k * 0.006, 0.15, h);
    if (backs.every((b) => contrast(hex, b) >= AA_TEXT)) return hex;
  }
  return oklchToHex(dark ? 0.72 : 0.52, 0.15, h);
}

// DESIGN.md's `themes:` as a list in light, dark order. A product may commit to one theme; both is the default.
export function themesOf(fm) {
  const raw = fm?.themes;
  if (raw === undefined) return Object.keys(THEMES);
  const list = (Array.isArray(raw) ? raw : String(raw).replace(/^\[|\]$/g, '').split(','))
    .map((t) => String(t).trim().replace(/^["']|["']$/g, '')).filter(Boolean);
  if (!list.length || list.some((t) => !(t in THEMES))) throw new UsageError(`themes must be [light], [dark] or [light, dark], got ${raw}`);
  return Object.keys(THEMES).filter((t) => list.includes(t));
}

export function buildPalette({ seed, harmony, themes = Object.keys(THEMES) }) {
  themes = themesOf({ themes });
  if (!/^#[0-9A-Fa-f]{6}$/.test(seed ?? '')) throw new UsageError(`--seed must be #RRGGBB, got ${seed}`);
  if (!(harmony in HARMONY)) throw new UsageError(`--harmony must be one of ${Object.keys(HARMONY).join(', ')}`);
  seed = seed.toUpperCase();
  const s = hexToOklch(seed);
  if (s.C < 0.04) throw new UsageError(`${seed} is a grey (OKLCH C ${s.C.toFixed(3)}); a harmony needs a hue, so pick a colour`);
  const neutralHue = harmony === 'complementary' ? (s.h + 180) % 360 : s.h;
  const colors = { ...ramp('accent', s.h, s.C, seed), ...ramp('neutral', neutralHue, NEUTRAL_CHROMA) };
  HARMONY[harmony].forEach((d, i) => Object.assign(colors, ramp(i ? `support-${i + 1}` : 'support', (s.h + d) % 360, s.C)));

  const roles = {}, pairs = [];
  for (const theme of themes) {
    const spec = THEMES[theme], dark = theme === 'dark', ink = dark ? 'down' : 'up';
    const r = Object.fromEntries(Object.entries(spec).map(([k, [rp, st]]) => [k, colors[`${rp}-${st}`]]));
    r.muted = pick(colors, 'neutral', spec.muted[1], ink, [r.bg, r.surface], AA_TEXT);
    r.accent = seed;
    r['on-accent'] = [colors['neutral-50'], colors['neutral-950']].sort((a, b) => contrast(b, seed) - contrast(a, seed))[0];
    const seedStep = STEPS.find((st) => colors[`accent-${st}`] === seed);
    r['accent-text'] = pick(colors, 'accent', seedStep, ink, [r.bg, r.surface], AA_TEXT);
    for (const [name, h] of Object.entries(STATE_HUE)) r[name] = stateColour(h, [r.bg, r.surface], dark);
    const check = (fg, bg, min, rule) => pairs.push({ theme, fg, bg, ratio: contrast(r[fg], r[bg]), min, rule });
    for (const fg of ['ink', 'muted', 'accent-text', ...Object.keys(STATE_HUE)]) for (const bg of ['bg', 'surface']) check(fg, bg, AA_TEXT, '1.4.3');
    check('on-accent', 'accent', AA_TEXT, '1.4.3');
    check('accent', 'bg', AA_CONTROL, '1.4.11');
    roles[theme] = r;
  }
  // The first declared theme's roles are the plain keys; with both themes, dark values that differ are `x-dark`.
  const [first, second] = themes;
  for (const [k, v] of Object.entries(roles[first])) {
    colors[k] = v;
    if (second && roles[second][k] !== v) colors[`${k}-dark`] = roles[second][k];
  }
  const notes = [];
  const near = Object.entries(STATE_HUE).find(([, h]) => Math.min(Math.abs(h - s.h), 360 - Math.abs(h - s.h)) < 25);
  if (near) notes.push(`the accent's hue is within 25 degrees of ${near[0]}: ${near[0]} must always carry an icon and a label`);
  return { colors, roles, pairs, ok: pairs.every((p) => p.ratio >= p.min), notes };
}

// The dataviz skill (bundled with Claude Code) owns data colours: its documented categorical palette and
// its validator, re-run against our surfaces. Found through DATAVIZ_DIR, else the newest bundled copy.
export function findDataviz() {
  if (process.env.DATAVIZ_DIR) return process.env.DATAVIZ_DIR;
  const root = path.join(os.tmpdir(), `claude-${process.getuid?.() ?? ''}`, 'bundled-skills');
  const found = [];
  for (const ver of fs.existsSync(root) ? fs.readdirSync(root) : []) {
    for (const hash of fs.readdirSync(path.join(root, ver))) {
      const d = path.join(root, ver, hash, 'dataviz');
      if (fs.existsSync(path.join(d, 'scripts', 'validate_palette.js'))) found.push([fs.statSync(d).mtimeMs, d]);
    }
  }
  return found.sort((a, b) => b[0] - a[0])[0]?.[1];
}
export async function dataColours(roles, dir = findDataviz()) {
  if (!dir) throw new Error('--data needs the dataviz skill: set DATAVIZ_DIR to its folder (references/, scripts/)');
  const { validate } = await import(pathToFileURL(path.join(dir, 'scripts', 'validate_palette.js')));
  const md = fs.readFileSync(path.join(dir, 'references', 'palette.md'), 'utf8');
  const table = md.split('## Categorical palette')[1].split('\n## ')[0];
  const rows = [...table.matchAll(/^\|\s*\d+\s*\|[^|]*\|\s*`(#[0-9a-fA-F]{6})`\s*\|\s*`(#[0-9a-fA-F]{6})`\s*\|/gm)];
  if (rows.length < 3) throw new Error(`no categorical table found in ${dir}/references/palette.md`);
  const colors = {}, reports = {};
  for (const [ti, theme] of Object.keys(roles).entries()) {
    const list = rows.map((m) => m[theme === 'light' ? 1 : 2].toUpperCase());
    reports[theme] = validate(list, { mode: theme, surface: roles[theme].surface });
    list.forEach((hex, i) => {
      const k = `data-${i + 1}`;
      if (!ti) colors[k] = hex; else if (colors[k] !== hex) colors[`${k}-dark`] = hex;
    });
  }
  return { colors, reports, ok: Object.values(reports).every((r) => r.ok), source: dir };
}

// Replace one top-level group of the frontmatter, keeping every other line as it is.
export function writeGroup(md, group, entries, comment) {
  const lines = md.split('\n');
  if (lines[0].trim() !== '---') throw new Error('no YAML frontmatter between --- lines');
  const end = lines.findIndex((l, i) => i > 0 && l.trim() === '---');
  const block = [`${group}:`, ...(comment ? [`  # ${comment}`] : []), ...yaml(entries, 2)];
  const start = lines.findIndex((l, i) => i > 0 && i < end && l.startsWith(`${group}:`));
  if (start < 0) lines.splice(end, 0, ...block);
  else {
    let stop = start + 1;
    while (stop < end && (!lines[stop].trim() || /^\s/.test(lines[stop]))) stop++;
    lines.splice(start, stop - start, ...block);
  }
  return lines.join('\n');
}
const yaml = (obj, n) => Object.entries(obj).flatMap(([k, v]) => (v && typeof v === 'object'
  ? [`${' '.repeat(n)}${k}:`, ...yaml(v, n + 2)]
  : [`${' '.repeat(n)}${k}: ${typeof v === 'number' ? v : JSON.stringify(String(v))}`]));

export class UsageError extends Error {}
export function parseArgs(argv, valueFlags) {
  const opts = {}, rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (valueFlags.includes(a)) opts[a.slice(2)] = argv[++i];
    else if (a.startsWith('--')) opts[a.slice(2)] = true;
    else rest.push(a);
  }
  return [opts, rest];
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [opts, [designPath = 'DESIGN.md']] = parseArgs(process.argv.slice(2), ['--seed', '--harmony']);
  let p;
  try {
    const fm = fs.existsSync(designPath) ? parseFrontmatter(fs.readFileSync(designPath, 'utf8')) : null;
    p = buildPalette({ ...opts, themes: themesOf(fm) });
  } catch (e) { console.error(e.message); process.exit(e instanceof UsageError ? 2 : 1); }
  for (const x of p.pairs) {
    console.log(`${x.ratio >= x.min ? 'pass' : 'FAIL'}  ${x.theme.padEnd(5)}  ${`${x.fg} on ${x.bg}`.padEnd(24)} ${x.ratio.toFixed(2).padStart(5)}:1  (needs ${x.min}:1, WCAG ${x.rule})`);
  }
  p.notes.forEach((n) => console.log(`note: ${n}`));
  let ok = p.ok, colors = p.colors;
  if (opts.data) {
    const d = await dataColours(p.roles).catch((e) => { console.error(e.message); process.exit(1); });
    for (const [theme, r] of Object.entries(d.reports)) for (const [check, state, detail] of r.report) console.log(`data   ${theme.padEnd(5)}  ${String(state).padEnd(6)} ${check}: ${detail}`);
    ok &&= d.ok;
    colors = { ...colors, ...d.colors };
  }
  if (!ok) {
    console.error(`refused: ${opts.seed} with ${opts.harmony} fails the checks marked FAIL above; nothing written (a product that ships one theme declares themes: [dark] or [light] in DESIGN.md)`);
    process.exit(1);
  }
  const comment = `generated by palette.mjs --seed ${opts.seed.toUpperCase()} --harmony ${opts.harmony}${opts.data ? ' --data' : ''}; rerun it, do not hand-edit`;
  if (opts.print) console.log(writeGroup('---\n---', 'colors', colors, comment).split('\n').slice(1, -1).join('\n'));
  else {
    fs.writeFileSync(designPath, writeGroup(fs.readFileSync(designPath, 'utf8'), 'colors', colors, comment));
    console.log(`wrote ${Object.keys(colors).length} colours to ${designPath}`);
  }
}
