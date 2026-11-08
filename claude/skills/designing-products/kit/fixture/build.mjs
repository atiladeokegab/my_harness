#!/usr/bin/env node
// Build the fixture page for one brand from its DESIGN.md: tokens.css through the skill's own generator,
// the kit bundled with esbuild, copy.json beside DESIGN.md. Output: kit/out/<brand>/index.html (file:// safe).
//   node fixture/build.mjs fixture/ledger/DESIGN.md
// Writes DESIGN.md beside the page so `impeccable detect kit/` checks every colour against that brand.
// Exit 1 when tokens.css lacks a custom property the kit reads: the kit's token contract, checked, not listed.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { parseFrontmatter, toCss } from '../../tokens/tokens-from-design.mjs';

const kit = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const design = path.resolve(process.argv[2] ?? '');
const brand = path.basename(path.dirname(design));
const fm = parseFrontmatter(fs.readFileSync(design, 'utf8'));
if (!fm) { console.error(`${design}: no token frontmatter`); process.exit(1); }
const tokens = toCss(fm, 'DESIGN.md');

const defined = new Set([...tokens.matchAll(/^\s*(--[\w-]+):/gm)].map((m) => m[1]));
const used = new Set();
for (const dir of ['ui', 'fixture']) {
  for (const f of fs.readdirSync(path.join(kit, dir)).filter((f) => f.endsWith('.css'))) {
    const css = fs.readFileSync(path.join(kit, dir, f), 'utf8');
    for (const m of css.matchAll(/var\((--[\w-]+)/g)) used.add(m[1]);
  }
}
// --kit-* is kit.css's own layer; --trigger-width is set by React Aria on popovers.
const missing = [...used].filter((v) => !v.startsWith('--kit-') && v !== '--trigger-width' && !defined.has(v));
if (missing.length) {
  console.error(`${design}: tokens.css lacks ${missing.join(', ')}; add them to DESIGN.md (kit/README.md, the token contract)`);
  process.exit(1);
}

const out = path.join(kit, 'out', brand);
fs.mkdirSync(out, { recursive: true });
fs.writeFileSync(path.join(out, 'tokens.css'), tokens);
// The guide beside the page, as at a product root: the detector keys its design-system-* rules to it.
fs.copyFileSync(design, path.join(out, 'DESIGN.md'));
// Every face DESIGN.md names is self-hosted (latin woff2 from a pinned @fontsource package), never a system
// face or a CDN: exit 1 naming the package when a family or weight is missing.
const faces = new Map();
for (const role of Object.values(fm.typography ?? {})) {
  const family = String(role.fontFamily).split(',')[0].replace(/["']/g, '').trim();
  if (!faces.has(family)) faces.set(family, new Set());
  faces.get(family).add(String(role.fontWeight ?? 400));
}
fs.mkdirSync(path.join(out, 'fonts'), { recursive: true });
let fontCss = '';
for (const [family, weights] of faces) for (const w of weights) {
  const id = family.toLowerCase().replace(/\s+/g, '-');
  const file = `${id}-latin-${w}-normal.woff2`;
  const src = path.join(kit, 'node_modules', '@fontsource', id, 'files', file);
  if (!fs.existsSync(src)) { console.error(`${design}: no self-hosted "${family}" ${w}; npm i -E @fontsource/${id} in kit/`); process.exit(1); }
  fs.copyFileSync(src, path.join(out, 'fonts', file));
  fontCss += `@font-face { font-family: "${family}"; font-weight: ${w}; font-style: normal; font-display: block; src: url("fonts/${file}") format("woff2"); }\n`;
}
fs.writeFileSync(path.join(out, 'fonts.css'), fontCss);
await build({
  entryPoints: [path.join(kit, 'fixture', 'page.jsx')], bundle: true, minify: true, format: 'iife',
  jsx: 'automatic', outdir: out, define: { 'process.env.NODE_ENV': '"production"' }, logLevel: 'error',
});
const copy = { ...JSON.parse(fs.readFileSync(path.join(path.dirname(design), 'copy.json'), 'utf8')), name: fm.name };
const dark = String(fm.themes ?? '').replace(/[[\]\s]/g, '') === 'dark';
fs.writeFileSync(path.join(out, 'index.html'), `<!doctype html>
<html lang="${copy.lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="${dark ? 'dark' : 'light'}"><title>${fm.name}: kit fixture</title>
<link rel="stylesheet" href="fonts.css"><link rel="stylesheet" href="tokens.css"><link rel="stylesheet" href="page.css">
<script>window.COPY = ${JSON.stringify(copy).replace(/</g, '\\u003c')}</script>
<script defer src="page.js"></script></head><body><div id="root"></div></body></html>
`);
console.log(`built ${path.relative(process.cwd(), out)}/index.html`);
