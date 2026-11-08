#!/usr/bin/env node
// Keyboard and focus over every kit piece on each built brand, at 1280 and 390 wide:
// Tab reaches every piece and each shows a visible focus ring; the tooltip opens on focus and Escape hides it;
// arrows move tabs and skip a disabled one; select, dialog and sheet trap focus, close on Escape and give
// focus back to their trigger; a toast's dismiss button is reachable and works; every target is 44px or
// more (inline links exempt); the open tooltip stays in the viewport and covers no text; toasts sit under
// an overlay's scrim; no text is under 14px; every target's box is 44 by 44 or more, on the page and in each
// open overlay; an identifier (.kit-id) never wraps; every face DESIGN.md names is a loaded @font-face.
//   node fixture/keys.mjs [brand ...]       exit 1 on any failure (FAIL lines, then RED or GREEN)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { parseFrontmatter } from '../../tokens/tokens-from-design.mjs';

const kit = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const brands = process.argv.slice(2).length ? process.argv.slice(2) : fs.readdirSync(path.join(kit, 'out'));
const PIECES = ['kit-button', 'kit-link', 'kit-input', 'kit-select__trigger', 'kit-tab', 'kit-card', 'kit-toast__close'];
const fails = [];
const browser = await chromium.launch();

// The focused element's kit class, whether a ring shows, and whether it sits inside an open overlay.
const probe = (page) => page.evaluate(() => {
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  const s = getComputedStyle(el);
  return {
    cls: [...el.classList].find((c) => c.startsWith('kit-') && c !== 'kit-focus') ?? el.tagName,
    name: el.getAttribute('aria-label') ?? el.textContent.trim().slice(0, 30),
    ring: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0,
    inDialog: !!el.closest('[role="dialog"]'),
    // Inline text links are exempt from the target size (WCAG 2.5.8); everything else is held to 44px.
    small: !(el.matches('a.kit-link') && getComputedStyle(el).display === 'inline')
      && Math.min(el.getBoundingClientRect().width, el.getBoundingClientRect().height) < 44,
  };
});

// Boxes, as a judge sees them: every visible control under 44 by 44, and every .kit-id broken across lines.
const BOXES = '.kit-icon-button, .kit-tab, .fx-nav a, .kit-button, .kit-select__trigger';
const boxes = (page, within) => page.evaluate(([sel, scope]) => {
  const out = [];
  for (const el of (scope ? document.querySelector(scope) : document).querySelectorAll(sel)) {
    if (!el.checkVisibility()) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 44 || r.height < 44) out.push(`${el.className.split(' ').find((c) => c.startsWith('kit-') && c !== 'kit-focus') ?? el.tagName} "${el.getAttribute('aria-label') ?? el.textContent.trim().slice(0, 20)}" is ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  for (const el of document.querySelectorAll('.kit-id')) if (el.getClientRects().length > 1) out.push(`.kit-id "${el.textContent}" wraps`);
  return out;
}, [BOXES, within]);

for (const brand of brands) {
  const copy = JSON.parse(fs.readFileSync(path.join(kit, 'fixture', brand, 'copy.json'), 'utf8'));
  const design = parseFrontmatter(fs.readFileSync(path.join(kit, 'out', brand, 'DESIGN.md'), 'utf8'));
  for (const [width, height] of [[1280, 633], [390, 757]]) {
    const at = `${brand} ${width}`;
    const fail = (rule, msg) => fails.push(`FAIL ${at} ${rule}: ${msg}`);
    const page = await browser.newPage({ viewport: { width, height }, reducedMotion: 'reduce' });
    await page.goto(pathToFileURL(path.join(kit, 'out', brand, 'index.html')).href);
    await page.getByRole('heading', { level: 1 }).waitFor();
    await page.locator('.kit-toast').first().waitFor();
    for (const b of await boxes(page)) fail('box', b);

    // 1. Tab through the page; F6 enters the toast region, as React Aria's landmark navigation intends.
    const seen = new Set();
    let first = null;
    for (let i = 0; i < 80; i++) {
      await page.keyboard.press('Tab');
      const f = await probe(page);
      if (!f) continue;
      const key = `${f.cls}|${f.name}`;
      if (key === first) break;
      first ??= key;
      seen.add(f.cls);
      if (!f.ring) fail('focus-visible', `${f.cls} "${f.name}" has focus and no visible ring`);
      if (f.small) fail('target', `${f.cls} "${f.name}" is under 44px`);
    }
    await page.keyboard.press('F6');
    for (let i = 0; i < 3 && !(await probe(page))?.cls.startsWith('kit-toast__close'); i++) await page.keyboard.press('Tab');
    const t = await probe(page);
    if (t) { seen.add(t.cls); if (!t.ring) fail('focus-visible', `${t.cls} has focus and no visible ring`); }
    for (const p of PIECES) if (!seen.has(p)) fail('reach', `Tab and F6 never reached a ${p}`);
    if (t?.cls === 'kit-toast__close') {
      const before = await page.locator('.kit-toast').count();
      await page.keyboard.press('Enter');
      await page.waitForFunction((n) => document.querySelectorAll('.kit-toast').length < n, before, { timeout: 2000 })
        .catch(() => fail('toast', 'Enter on dismiss left the toast up'));
    }

    // 2. Tooltip: shows on keyboard focus at once, Escape hides it.
    await page.getByRole('button', { name: copy.tipLabel }).focus();
    await page.keyboard.press('Shift+Tab'); await page.keyboard.press('Tab'); // focus by keyboard, not script
    if (!(await page.getByRole('tooltip').isVisible().catch(() => false))) {
      await page.getByRole('tooltip').waitFor({ timeout: 1500 }).catch(() => fail('tooltip', 'no tooltip on keyboard focus'));
    }
    const tipProblem = await page.evaluate(() => {
      const tip = document.querySelector('[role="tooltip"]');
      if (!tip) return null;
      const t = tip.getBoundingClientRect();
      if (t.left < 0 || t.top < 0 || t.right > innerWidth || t.bottom > innerHeight) return 'leaves the viewport';
      const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n; (n = walk.nextNode());) {
        if (!n.textContent.trim() || tip.contains(n)) continue;
        const range = document.createRange(); range.selectNodeContents(n);
        for (const r of range.getClientRects()) {
          if (r.width && r.left < t.right && r.right > t.left && r.top < t.bottom && r.bottom > t.top) return `covers "${n.textContent.trim().slice(0, 30)}"`;
        }
      }
      return null;
    });
    if (tipProblem) fail('tooltip', tipProblem);
    await page.keyboard.press('Escape');
    await page.getByRole('tooltip').waitFor({ state: 'hidden', timeout: 1500 }).catch(() => fail('tooltip', 'Escape left the tooltip up'));

    // 3. Tabs: ArrowRight selects the next tab and skips the disabled one.
    await page.getByRole('tab', { name: copy.tabs[0] }).focus();
    await page.keyboard.press('ArrowRight');
    if ((await page.getByRole('tab', { name: copy.tabs[1] }).getAttribute('aria-selected')) !== 'true') fail('tabs', 'ArrowRight did not select the next tab');
    await page.keyboard.press('ArrowRight');
    if ((await page.getByRole('tab', { name: copy.tabs[2] }).getAttribute('aria-selected')) === 'true') fail('tabs', 'a disabled tab was selected');
    await page.getByRole('tab', { name: copy.tabs[0] }).click();

    // 4. Select, dialog, sheet: open from the keyboard, focus stays in, Escape closes, focus returns.
    const overlays = [
      ['select', page.locator('.kit-select__trigger').first(), 'listbox'],
      ['dialog', page.getByRole('button', { name: copy.dialog.open, exact: true }), 'dialog'],
      ['sheet', page.getByRole('button', { name: copy.sheet.open, exact: true }), 'dialog'],
    ];
    for (const [name, trigger, role] of overlays) {
      await trigger.focus();
      await page.keyboard.press('Enter');
      const layer = page.getByRole(role);
      if (!(await layer.waitFor({ timeout: 2000 }).then(() => true, () => false))) { fail(name, 'Enter did not open it'); continue; }
      if (name !== 'select') for (const b of await boxes(page, '[role="dialog"]')) fail(`${name} box`, b);
      for (const key of ['Tab', 'Tab', 'Tab', 'Tab', 'Tab', 'Shift+Tab', 'Shift+Tab']) {
        if (name === 'select') break; // a listbox holds focus with arrows; Tab closes it by design
        await page.keyboard.press(key);
        const f = await probe(page);
        if (!f?.inDialog) { fail(name, `${key} moved focus out of the open ${name} to ${f?.cls ?? 'body'}`); break; }
        if (!f.ring) fail(name, `${f.cls} inside the ${name} has no visible ring`);
        if (f.small) fail(name, `${f.cls} "${f.name}" inside the ${name} is under 44px`);
      }
      if (name === 'select' && !(await page.evaluate(() => !!document.activeElement.closest('[role="listbox"]')))) fail(name, 'focus did not move into the listbox');
      await page.keyboard.press('Escape');
      if (!(await layer.waitFor({ state: 'hidden', timeout: 2000 }).then(() => true, () => false))) { fail(name, 'Escape did not close it'); continue; }
      // React Aria restores focus a frame after the layer unmounts, so poll rather than read once.
      if (!(await trigger.evaluate((el) => new Promise((ok) => { const t0 = performance.now(); (function poll() { if (el === document.activeElement) ok(true); else if (performance.now() - t0 > 2000) ok(false); else requestAnimationFrame(poll); })(); })))) fail(name, 'focus did not return to the trigger');
    }
    // 5. Toasts sit under an open overlay's scrim: by z-index and by what is actually on top at a toast.
    await page.getByRole('button', { name: copy.dialog.open, exact: true }).click();
    await page.getByRole('dialog').waitFor();
    const layer = await page.evaluate(() => {
      const toast = document.querySelector('.kit-toast'), scrim = document.querySelector('.kit-scrim');
      if (!toast) return 'no toast left to check';
      const z = (el) => Number(getComputedStyle(el).zIndex) || 0;
      const r = toast.getBoundingClientRect();
      const top = document.elementFromPoint(r.left + 4, r.top + 4);
      return z(toast.closest('.kit-toasts')) < z(scrim) && !toast.contains(top) ? null : 'a toast sits above the scrim';
    });
    if (layer) fail('toast-layer', layer);
    await page.keyboard.press('Escape');

    // 6. Text: nothing under 14px, and every face DESIGN.md names is available to the page.
    const tiny = await page.evaluate(() => {
      const out = [];
      const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n; (n = walk.nextNode());) {
        const el = n.parentElement;
        if (!n.textContent.trim() || !el.checkVisibility() || el.closest('.kit-visually-hidden, [aria-hidden="true"]')) continue;
        const px = parseFloat(getComputedStyle(el).fontSize);
        if (px < 14) out.push(`${px}px "${n.textContent.trim().slice(0, 30)}"`);
      }
      return out;
    });
    for (const t of tiny) fail('text-size', t);
    // Each family: @font-face entries exist (a system face has none), every one has loaded (the page uses each
    // weight it declares; nothing here calls load()), and the glyph test passes on the loaded face.
    const fonts = await page.evaluate(async (roles) => {
      await document.fonts.ready;
      const out = [];
      for (const [family, weight] of roles) {
        const faces = [...document.fonts].filter((f) => f.family.replace(/["']/g, '') === family);
        if (!faces.length) out.push(`"${family}" has no @font-face: a system face stands in`);
        for (const f of faces) if (f.status !== 'loaded') out.push(`"${family}" ${f.weight} is ${f.status}`);
        if (faces.length && !document.fonts.check(`${weight} 16px "${family}"`, 'Ag£')) out.push(`"${family}" ${weight} fails the glyph test`);
      }
      return out;
    }, Object.values(design.typography).map((r) => [r.fontFamily.split(',')[0].replace(/["']/g, '').trim(), String(r.fontWeight ?? 400)]));
    for (const f of fonts) fail('font', f);
    await page.close();
  }
}
await browser.close();
for (const f of fails) console.error(f);
console.log(`${fails.length ? 'RED' : 'GREEN'}: ${brands.length} brands x 2 widths, ${fails.length} failure(s)`);
process.exit(fails.length ? 1 : 0);
