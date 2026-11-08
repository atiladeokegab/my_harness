#!/usr/bin/env node
// brand.html from DESIGN.md: the palette with contrast numbers, the type scale in the chosen faces, the spacing
// and radius steps, the flow's steps and the do/don't pairs, on one page a builder keeps open. No dependencies.
//   node brand-from-design.mjs [DESIGN.md] [docs/brand.html]           write
//   node brand-from-design.mjs --check [DESIGN.md] [docs/brand.html]   exit 1 if brand.html has drifted
// The page uses only DESIGN.md's tokens (inlined from tokens-from-design.mjs), so the detector passes it
// or the guide itself is wrong. A pair that fails AA is shown as two chips and a number, never as text.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseFrontmatter, toCss, varName } from './tokens-from-design.mjs';
import { contrast, STEPS, themesOf } from './palette.mjs';

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>');
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const px = (v) => parseFloat(v) * (/rem$/.test(v) ? 16 : 1);
const GENERIC = /^(sans-serif|serif|monospace|system-ui|ui-[a-z-]+|-apple-system|BlinkMacSystemFont|Segoe UI|Arial|Helvetica|Georgia|Times New Roman|Menlo|Consolas)$/i;
// The pairs palette.mjs checks: [fg, bg, minimum, WCAG rule].
const PAIRS = [...['ink', 'muted', 'accent-text', 'success', 'warning', 'danger', 'info']
  .flatMap((fg) => [[fg, 'bg', 4.5, '1.4.3'], [fg, 'surface', 4.5, '1.4.3']]),
['on-accent', 'accent', 4.5, '1.4.3'], ['accent', 'bg', 3, '1.4.11']];

function sections(body) {
  const out = {};
  for (const part of body.split(/^## /m).slice(1)) out[part.split('\n')[0].trim().toLowerCase()] = part;
  return out;
}
const items = (text, re) => [...(text ?? '').matchAll(re)].map((m) => m[1].trim());

export function brandHtml(md, source = 'DESIGN.md') {
  const fm = parseFrontmatter(md);
  if (!fm) throw new Error(`${source}: no YAML frontmatter between --- lines`);
  const body = md.split(/^---\s*$/m).slice(2).join('---');
  const colors = fm.colors ?? {}, typo = fm.typography ?? {}, space = fm.spacing ?? {}, rounded = fm.rounded ?? {};
  const cv = (k) => `var(${varName('colors', k)})`;
  const near = (group, want) => {
    const e = Object.entries(fm[group] ?? {}).filter(([, v]) => typeof v !== 'object');
    if (!e.length) return `${want}px`;
    const [k] = e.reduce((a, b) => (Math.abs(px(b[1]) - want) < Math.abs(px(a[1]) - want) ? b : a));
    return `var(${varName(group, k)})`;
  };
  // Chrome colours: the role names palette.mjs writes, then common synonyms, then lightest and darkest.
  const byLum = Object.keys(colors).filter((k) => /^#[0-9a-f]{6}$/i.test(colors[k]) && !k.endsWith('-dark'))
    .sort((a, b) => contrast(colors[b], '#000000') - contrast(colors[a], '#000000'));
  const role = (names, fallback) => names.find((n) => colors[n]) ?? fallback;
  const c = { bg: role(['bg', 'background', 'ground'], byLum[0]), ink: role(['ink', 'text', 'foreground'], byLum.at(-1)) };
  Object.assign(c, { surface: role(['surface'], c.bg), muted: role(['muted', 'text-muted'], c.ink), border: role(['border'], c.ink) });
  // Type roles for the page itself: body nearest 16px, small the least that is 12px or more, headings nearest 32 and 22.
  const roles = Object.entries(typo).filter(([, v]) => v && typeof v === 'object' && v.fontSize);
  const nearType = (want, min = 0) => roles.filter(([, v]) => px(v.fontSize) >= min)
    .reduce((a, b) => (!a || Math.abs(px(b[1].fontSize) - want) < Math.abs(px(a[1].fontSize) - want) ? b : a), null)?.[0];
  const font = (r) => (r ? ['font-family', 'font-size', 'font-weight', 'line-height', 'letter-spacing']
    .filter((p) => typo[r][p.replace(/-([a-z])/g, (_, x) => x.toUpperCase())] !== undefined)
    .map((p) => `${p}: var(${varName('typography', r, p)});`).join(' ') : '');
  const small = roles.filter(([, v]) => px(v.fontSize) >= 12).sort((a, b) => px(a[1].fontSize) - px(b[1].fontSize))[0]?.[0];
  const t = { body: typo.body ? 'body' : nearType(16, 14), small, h2: nearType(32, 20), h3: nearType(20, 16), title: nearType(48, 24) };

  // The declared themes; a hand-written DESIGN.md without `themes:` gets a dark panel only if it has `x-dark` keys.
  const themes = fm.themes !== undefined ? themesOf(fm) : Object.keys(colors).some((k) => k.endsWith('-dark')) ? ['light', 'dark'] : ['light'];
  const val = (k, theme) => (theme === 'dark' && colors[`${k}-dark`]) || colors[k];
  const sec = sections(body);
  const flow = items(sec.flow, /^\d+\.\s+(.+)$/gm);
  const dosText = sec["do's and don'ts"] ?? '';
  const dos = items(dosText.split(/^### Don't/m)[0], /^[-*]\s+(.+)$/gm);
  const donts = items(dosText.split(/^### Don't/m)[1], /^[-*]\s+(.+)$/gm);

  // The palette: ramps by name, data colours, then the rest (the roles).
  const rampOf = {}, data = [], rest = [];
  for (const k of Object.keys(colors)) {
    const m = k.match(/^(.+)-(\d+)$/);
    if (m && STEPS.includes(+m[2])) (rampOf[m[1]] ??= []).push(k);
    else if (/^data-\d+(-dark)?$/.test(k)) data.push(k);
    else rest.push(k);
  }
  const swatch = (k) => `<li><span class="swatch" style="background: ${cv(k)}"></span><span class="name">${esc(k)}</span><span class="hex">${esc(colors[k])}</span></li>`;
  const strip = (title, keys) => keys.length ? `<h3>${esc(title)}</h3><ul class="ramp">${keys.map(swatch).join('')}</ul>` : '';

  const pairRows = (theme) => PAIRS.filter(([fg, bg]) => colors[fg] && colors[bg]).map(([fg, bg, min, rule]) => {
    const ratio = contrast(val(fg, theme), val(bg, theme)), pass = ratio >= min;
    const sample = rule === '1.4.11'
      ? `<span class="sample" style="background: ${cv(bg)}"><span class="chip" style="background: ${cv(fg)}"></span></span>`
      : pass ? `<span class="sample" style="background: ${cv(bg)}; color: ${cv(fg)}">Aa</span>`
        : `<span class="sample split"><span class="chip" style="background: ${cv(fg)}"></span><span class="chip" style="background: ${cv(bg)}"></span></span>`;
    return `<li>${sample}<span class="what">${esc(fg)} on ${esc(bg)}</span><span class="num">${ratio.toFixed(2)}:1</span><span class="verdict">${pass ? 'passes' : 'fails'} ${min}:1, WCAG ${rule}</span></li>`;
  }).join('');
  const themePanels = themes.map((th) => `<div class="theme" data-theme="${th}"><h3>${th === 'dark' ? 'Dark' : 'Light'} theme</h3><ul class="pairs">${pairRows(th)}</ul></div>`).join('');

  // Do and don't: the guide's own lines, paired in order, then one pair computed from the palette.
  const doPairs = dos.map((d, i) => [d, donts[i]]).concat(donts.slice(dos.length).map((d) => [null, d]));
  if (colors.muted && colors.surface && colors.accent) {
    const good = contrast(colors.muted, colors.surface), bad = contrast(colors.muted, colors.accent);
    if (bad < 4.5) doPairs.push([`Set secondary text in **muted** on **surface**: ${good.toFixed(2)}:1.`, `Put **muted** text on the **accent**: ${bad.toFixed(2)}:1, under AA.`]);
  }
  const mark = (ok) => { const k = ok ? 'success' : 'danger'; return `<span class="mark" style="color: ${cv(colors[k] ? k : c.ink)}">${ok ? 'Do' : 'Don’t'}</span>`; };

  const fonts = [...new Set(roles.map(([, v]) => String(v.fontFamily ?? '').split(',')[0].trim().replace(/^["']|["']$/g, '')))]
    .filter((f) => f && !GENERIC.test(f));
  const weights = (f) => [...new Set(roles.filter(([, v]) => String(v.fontFamily).startsWith(f)).map(([, v]) => v.fontWeight ?? 400))].sort();
  const links = fonts.map((f) => `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=${f.replace(/ /g, '+')}:wght@${weights(f).join(';')}&amp;display=swap">`).join('\n');

  const css = toCss(fm, source).replace(/@media \(prefers-reduced-motion[\s\S]*$/, '').trim();
  return `<!doctype html>
<!-- Generated from ${esc(source)} by brand-from-design.mjs. Do not edit: change ${esc(source)} and rerun. -->
<html lang="en" data-theme="${themes[0]}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(fm.name ?? 'Product')} brand</title>
${links}
<style>
${css}
  * { box-sizing: border-box; }
  body { margin: 0; background: ${cv(c.bg)}; color: ${cv(c.ink)}; ${font(t.body)} }
  main { max-width: 1120px; margin: 0 auto; padding: ${near('spacing', 48)} ${near('spacing', 24)}; }
  h1 { ${font(t.title)} margin: 0 0 ${near('spacing', 8)}; }
  h2 { ${font(t.h2)} margin: 0 0 ${near('spacing', 16)}; }
  h3 { ${font(t.h3)} margin: ${near('spacing', 24)} 0 ${near('spacing', 12)}; }
  p, li, figcaption { overflow-wrap: anywhere; }
  section { margin-top: ${near('spacing', 64)}; }
  ul, ol { list-style: none; margin: 0; padding: 0; }
  .lede, .name, .hex, .what, .verdict, .spec, .note { color: ${cv(c.muted)}; }
  .name, .hex, .verdict, .spec, .note { ${font(t.small)} }
  .ramp { display: grid; grid-template-columns: repeat(auto-fill, minmax(84px, 1fr)); gap: ${near('spacing', 12)}; }
  .ramp li { display: grid; gap: ${near('spacing', 4)}; }
  .swatch { display: block; height: ${near('spacing', 48)}; border-radius: ${near('rounded', 6)}; border: 1px solid ${cv(c.border)}; }
  .themes { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: ${near('spacing', 24)}; }
  .theme { background: ${cv(c.bg)}; color: ${cv(c.ink)}; padding: ${near('spacing', 24)}; border: 1px solid ${cv(c.border)}; border-radius: ${near('rounded', 12)}; }
  .theme h3 { margin-top: 0; }
  .pairs li { display: grid; grid-template-columns: auto 1fr auto; column-gap: ${near('spacing', 12)}; align-items: center; padding: ${near('spacing', 8)} 0; border-top: 1px solid ${cv(c.border)}; }
  .pairs .verdict { grid-column: 2 / 4; }
  .sample { display: inline-flex; align-items: center; justify-content: center; gap: ${near('spacing', 4)}; width: ${near('spacing', 56)}; height: ${near('spacing', 40)}; ${font(t.body)} font-weight: 600; }
  .chip { display: block; width: ${near('spacing', 16)}; height: ${near('spacing', 16)}; border-radius: ${near('rounded', 4)}; }
  .split { justify-content: flex-start; }
  .num { font-variant-numeric: tabular-nums; }
  .type li { padding: ${near('spacing', 16)} 0; border-top: 1px solid ${cv(c.border)}; }
  .type .say { margin: 0 0 ${near('spacing', 4)}; }
  .steps { display: grid; gap: ${near('spacing', 8)}; }
  .steps li { display: grid; grid-template-columns: minmax(120px, max-content) 1fr; align-items: center; gap: ${near('spacing', 16)}; }
  .bar { display: block; height: ${near('spacing', 12)}; background: ${cv(colors.accent ? 'accent' : c.ink)}; }
  .corner { display: block; width: ${near('spacing', 64)}; height: ${near('spacing', 40)}; border: 2px solid ${cv(colors.accent ? 'accent' : c.ink)}; }
  .flow { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: ${near('spacing', 16)}; counter-reset: step; }
  .flow li { padding-top: ${near('spacing', 12)}; border-top: 2px solid ${cv(colors.accent ? 'accent' : c.ink)}; }
  .flow li::before { counter-increment: step; content: counter(step); display: block; ${font(t.h3)} }
  .dos li { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: ${near('spacing', 24)}; padding: ${near('spacing', 16)} 0; border-top: 1px solid ${cv(c.border)}; }
  .dos p { margin: 0; }
  .mark { display: block; font-weight: 600; }
  code { font-family: ui-monospace, monospace; }
</style>
</head>
<body>
<main>
<header>
<h1>${esc(fm.name ?? 'Product')}</h1>
<p class="lede">${esc(fm.description ?? '')}</p>
<p class="note">Generated from ${esc(source)}. Every value on this page is a token; change ${esc(source)} and regenerate, never this file.${fm.themes !== undefined && themes.length === 1 ? ` The product ships the ${themes[0]} theme only (themes: [${themes[0]}]).` : ''}</p>
</header>

<section id="palette">
<h2>Palette</h2>
${Object.entries(rampOf).map(([name, keys]) => strip(name, keys)).join('\n')}
${strip('Roles', rest.filter((k) => !k.endsWith('-dark')))}
${strip('Roles, dark theme', rest.filter((k) => k.endsWith('-dark')))}
${strip('Data (the dataviz skill’s palette, validated on these surfaces)', data)}
${colors.bg && colors.ink ? `<h3>Contrast, as checked</h3><div class="themes">${themePanels}</div>` : ''}
</section>

<section id="type">
<h2>Type</h2>
<ul class="type">${roles.map(([r, v]) => `<li><p class="say" style="${font(r)}">${esc(fm.description ?? fm.name ?? r)}</p><span class="spec">${esc(r)} · ${esc(v.fontSize)} / ${esc(v.lineHeight ?? 'normal')} · ${esc(v.letterSpacing ?? '0em')} · ${esc(String(v.fontFamily).split(',')[0])} ${esc(v.fontWeight ?? 400)}</span></li>`).join('')}</ul>
</section>

<section id="space">
<h2>Spacing and radius</h2>
<ul class="steps">${Object.entries(space).map(([k, v]) => `<li><span class="spec">${esc(k)} · ${esc(v)}</span><span class="bar" style="width: var(${varName('spacing', k)})"></span></li>`).join('')}</ul>
<h3>Radius</h3>
<ul class="steps">${Object.entries(rounded).map(([k, v]) => `<li><span class="spec">${esc(k)} · ${esc(v)}</span><span class="corner" style="border-radius: var(${varName('rounded', k)})"></span></li>`).join('')}</ul>
</section>
${flow.length ? `
<section id="flow">
<h2>Flow</h2>
<ol class="flow">${flow.map((s) => `<li><p>${inline(s)}</p></li>`).join('')}</ol>
</section>` : ''}
${doPairs.length ? `
<section id="dos">
<h2>Do and don’t</h2>
<ul class="dos">${doPairs.map(([d, n]) => `<li><p>${d ? `${mark(true)}${inline(cap(d.replace(/^\*\*Do\*\*\s*/, '')))}` : ''}</p><p>${n ? `${mark(false)}${inline(cap(n.replace(/^\*\*Don't\*\*\s*/, '')))}` : ''}</p></li>`).join('')}</ul>
</section>` : ''}
</main>
</body>
</html>
`;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const check = args[0] === '--check';
  if (check) args.shift();
  const [designPath = 'DESIGN.md', htmlPath = 'docs/brand.html'] = args;
  let html;
  try { html = brandHtml(fs.readFileSync(designPath, 'utf8'), path.basename(designPath)); } catch (e) { console.error(e.message); process.exit(1); }
  if (check) {
    if ((fs.existsSync(htmlPath) ? fs.readFileSync(htmlPath, 'utf8') : '') !== html) {
      console.error(`${htmlPath} has drifted from ${designPath}: run node brand-from-design.mjs ${designPath} ${htmlPath}`);
      process.exit(1);
    }
  } else {
    fs.mkdirSync(path.dirname(htmlPath), { recursive: true });
    fs.writeFileSync(htmlPath, html);
    console.log(`wrote ${htmlPath}`);
  }
}
