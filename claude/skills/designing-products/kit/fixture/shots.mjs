#!/usr/bin/env node
// Capture each built brand at the two judge sizes: the page (full height, tooltip held open) and one
// overlay each (dialog at 1280, sheet at 390). Exit 1 on a console error, a page that did not render, or a
// heading or body face that is not the one DESIGN.md names (a silent system fallback).
//   node fixture/shots.mjs OUT_DIR [brand ...]      (default brands: every folder in kit/out)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { parseFrontmatter } from '../../tokens/tokens-from-design.mjs';

const kit = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const [dest = '.', ...picked] = process.argv.slice(2);
const brands = picked.length ? picked : fs.readdirSync(path.join(kit, 'out'));
const SIZES = { desktop: [1280, 633, 'Close the year|Resolve all', 'dialog'], mobile: [390, 757, 'Filters|Timeline', 'sheet'] };
fs.mkdirSync(dest, { recursive: true });
const browser = await chromium.launch();
let bad = 0;
for (const brand of brands) {
  const url = pathToFileURL(path.join(kit, 'out', brand, 'index.html')).href;
  for (const [size, [width, height, opener, overlay]] of Object.entries(SIZES)) {
    const page = await browser.newPage({ viewport: { width, height }, reducedMotion: 'reduce' });
    page.on('console', (m) => { if (m.type() === 'error') { bad++; console.error(`${brand} ${size}: ${m.text()}`); } });
    page.on('pageerror', (e) => { bad++; console.error(`${brand} ${size}: ${e.message}`); });
    await page.goto(`${url}?still=1`);
    await page.getByRole('tooltip').waitFor();
    // The faces DESIGN.md names must be the ones Chromium renders, not a system fallback.
    const fm = parseFrontmatter(fs.readFileSync(path.join(kit, 'out', brand, 'DESIGN.md'), 'utf8'));
    const cdp = await page.context().newCDPSession(page);
    const { root } = await cdp.send('DOM.getDocument', { depth: -1 });
    await cdp.send('CSS.enable');
    for (const [role, sel] of [['h1', 'h1'], ['body', '.fx-lead']]) {
      const want = fm.typography[role].fontFamily.split(',')[0].replace(/["']/g, '').trim();
      const { nodeId } = await cdp.send('DOM.querySelector', { nodeId: root.nodeId, selector: sel });
      const { fonts } = await cdp.send('CSS.getPlatformFontsForNode', { nodeId });
      const got = fonts.map((f) => f.familyName);
      if (!got.some((g) => g.startsWith(want))) { bad++; console.error(`${brand} ${size}: ${role} wants "${want}", renders ${got.join(', ')}`); }
    }
    // Grow the viewport to the page so fixed pieces (toasts) sit at the bottom, as a visitor scrolled there sees them.
    await page.setViewportSize({ width, height: await page.evaluate(() => document.documentElement.scrollHeight) });
    await page.screenshot({ path: path.join(dest, `${brand}-${size}.png`) });
    await page.setViewportSize({ width, height });
    await page.goto(url);
    await page.getByRole('button', { name: new RegExp(`^(${opener})$`) }).click();
    await page.getByRole('dialog').waitFor();
    await page.screenshot({ path: path.join(dest, `${brand}-${size}-${overlay}.png`) });
    await page.close();
  }
}
await browser.close();
console.log(`${bad ? 'RED' : 'GREEN'}: ${brands.length * 4} captures in ${dest}`);
process.exit(bad ? 1 : 0);
