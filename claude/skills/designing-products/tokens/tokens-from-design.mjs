#!/usr/bin/env node
// tokens.css from DESIGN.md's token frontmatter (Impeccable's `document` schema). No dependencies.
//   node tokens-from-design.mjs [DESIGN.md] [tokens.css]           write tokens.css
//   node tokens-from-design.mjs --check [DESIGN.md] [tokens.css]   exit 1 if tokens.css has drifted
// Defaults: ./DESIGN.md and ./web/src/tokens.css.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Group in the frontmatter -> custom-property prefix. Components keep their own name.
const PREFIX = { colors: 'color', typography: 'type', rounded: 'radius', spacing: 'space', components: '' };
const BREAKPOINTS = { phone: '390px', desktop: '1280px' }; // the two judge sizes

// The same YAML subset the detector reads (design_system.rs parse_yaml_subset):
// nested maps by indentation and scalars; no lists, anchors or multi-line strings.
export function parseFrontmatter(md) {
  const lines = md.split(/\r?\n/);
  if (lines[0].trim() !== '---') return null;
  const end = lines.findIndex((l, i) => i > 0 && l.trim() === '---');
  if (end < 0) return null;
  const root = {};
  const stack = [[-1, root]];
  for (const raw of lines.slice(1, end)) {
    if (!raw.trim() || /^\s*#/.test(raw)) continue;
    const indent = raw.length - raw.trimStart().length;
    const content = raw.trimStart();
    const colon = topLevelColon(content);
    if (colon < 0) continue;
    while (stack.length > 1 && stack.at(-1)[0] >= indent) stack.pop();
    const key = unquote(content.slice(0, colon).trim());
    const rest = content.slice(colon + 1).trim().replace(/\s+#.*$/, '');
    const parent = stack.at(-1)[1];
    if (!rest) stack.push([indent, (parent[key] = {})]);
    else parent[key] = scalar(rest);
  }
  return root;
}

function topLevelColon(s) {
  let q = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (q) { if (c === q) q = null; continue; }
    if (c === '"' || c === "'") q = c;
    else if (c === ':' && (i + 1 === s.length || /\s/.test(s[i + 1]))) return i;
  }
  return -1;
}
const unquote = (s) => (/^(["']).*\1$/.test(s) ? s.slice(1, -1) : s);
const scalar = (s) => (/^(["']).*\1$/.test(s) ? s.slice(1, -1) : /^-?\d+(\.\d+)?$/.test(s) ? Number(s) : s);
export const kebab = (s) => String(s).replace(/([a-z0-9])([A-Z])/g, '$1-$2').replace(/[^A-Za-z0-9-]+/g, '-').toLowerCase();
export const varName = (group, ...keys) => '--' + [PREFIX[group] ?? kebab(group), ...keys.map(kebab)].filter(Boolean).join('-');

// {colors.primary} -> var(--color-primary); a ref to a map (a type role) expands per property.
function resolve(fm, value) {
  const m = typeof value === 'string' && value.match(/^\{([^.}]+)\.([^}]+)\}$/);
  if (!m) return value;
  const target = fm[m[1]]?.[m[2]];
  if (target === undefined) throw new Error(`unresolved token ref ${value}`);
  if (target && typeof target === 'object') {
    return Object.fromEntries(Object.keys(target).map((k) => [k, `var(${varName(m[1], m[2], k)})`]));
  }
  return `var(${varName(m[1], m[2])})`;
}

// A family name with a space or a digit is quoted: unquoted, "Source Sans 3" is invalid CSS and the whole
// font-family declaration is dropped. Generic names (sans-serif) and names already quoted pass through.
export const quoteFamilies = (v) => String(v).split(',').map((f) => f.trim())
  .map((f) => (/^["']/.test(f) || !/[\s\d]/.test(f) ? f : `"${f}"`)).join(', ');

export function toCss(fm, source = 'DESIGN.md') {
  const out = [];
  for (const [group, entries] of Object.entries(fm)) {
    if (!entries || typeof entries !== 'object') continue; // name, description
    out.push(`  /* ${group} */`);
    for (const [key, val] of Object.entries(entries)) {
      if (val && typeof val === 'object') {
        for (const [prop, v] of Object.entries(val)) {
          const r = resolve(fm, v);
          if (r && typeof r === 'object') {
            for (const [sub, sv] of Object.entries(r)) out.push(`  ${varName(group, key, prop, sub)}: ${sv};`);
          } else out.push(`  ${varName(group, key, prop)}: ${prop === 'fontFamily' ? quoteFamilies(r) : r};`);
        }
      } else out.push(`  ${varName(group, key)}: ${resolve(fm, val)};`);
    }
  }
  out.push('  /* breakpoints: the two judge sizes; media queries cannot read these, so write 390px and 1280px there */');
  for (const [k, v] of Object.entries(BREAKPOINTS)) out.push(`  --bp-${k}: ${v};`);
  // A colour `x-dark` beside `x` (palette.mjs writes them) swaps in for `x` in the dark theme:
  // data-theme="dark" on any element, or the OS setting unless the root says data-theme="light".
  const swaps = Object.keys(fm.colors ?? {}).filter((k) => k.endsWith('-dark') && k.slice(0, -5) in fm.colors)
    .map((k) => `${varName('colors', k.slice(0, -5))}: var(${varName('colors', k)});`);
  const dark = swaps.length ? `
[data-theme="dark"] {
${swaps.map((s) => `  ${s}`).join('\n')}
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
${swaps.map((s) => `    ${s}`).join('\n')}
  }
}
` : '';
  return `/* Generated from ${source} by tokens-from-design.mjs. Do not edit: change ${source} and rerun. */
:root {
${out.join('\n')}
}
${dark}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
`;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const check = args[0] === '--check';
  if (check) args.shift();
  const [designPath = 'DESIGN.md', cssPath = 'web/src/tokens.css'] = args;
  const fm = parseFrontmatter(fs.readFileSync(designPath, 'utf8'));
  if (!fm) {
    console.error(`${designPath}: no YAML frontmatter between --- lines`);
    process.exit(1);
  }
  const css = toCss(fm, path.basename(designPath));
  if (check) {
    const current = fs.existsSync(cssPath) ? fs.readFileSync(cssPath, 'utf8') : '';
    if (current !== css) {
      console.error(`${cssPath} has drifted from ${designPath}: run node tokens-from-design.mjs ${designPath} ${cssPath}`);
      process.exit(1);
    }
  } else {
    fs.mkdirSync(path.dirname(cssPath), { recursive: true });
    fs.writeFileSync(cssPath, css);
    console.log(`wrote ${cssPath}`);
  }
}
