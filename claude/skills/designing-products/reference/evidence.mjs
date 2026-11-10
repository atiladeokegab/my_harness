#!/usr/bin/env node
// The judge packet's measured evidence (judge.md §2): what a still cannot show, measured in Chromium at 1280x633
// and 390x757 over every screen of one candidate. One line per check, PASS or FAIL with the measured value:
// focus (a ring on every Tab stop, captured), reduced-motion, contrast, targets, console, selection, caret,
// scrollbar, tabular, measure, tracking, text-size, overlap, copy. rubric.md §6 scores B8, B9 and B12 at 2 only on these lines;
// copy is the mechanical part of T7.
//   node evidence.mjs <out-prefix> <url> [url ...]    writes <prefix>-evidence.md and <prefix>-focus-{desktop,mobile}.png
//                                                     (the first screen's first Tab stop); exit 1 on any FAIL
// The file names no URL or path, so it can sit in a blind packet under the specimen's neutral name.
import { writeFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

// Playwright from the product's devDependencies, else the copy kit/ pins for its fixture checks.
const { chromium } = await import('playwright').catch(() => import(new URL('../kit/node_modules/playwright/index.mjs', import.meta.url)))
const SIZES = [['1280x633', 1280, 633, 'desktop'], ['390x757', 390, 757, 'mobile']]
export const CHECKS = ['focus', 'reduced-motion', 'contrast', 'targets', 'console', 'selection', 'caret', 'scrollbar', 'tabular', 'measure', 'tracking', 'text-size', 'overlap', 'copy']

// Runs in the page after load: every check that reads the DOM at rest. Returns { check: [ok, value] }.
function atRest() {
  const vis = (e) => e.checkVisibility?.({ opacityProperty: true, visibilityProperty: true }) ?? true
  const ctx = Object.assign(document.createElement('canvas'), { width: 1, height: 1 }).getContext('2d', { willReadFrequently: true })
  const rgba = (c) => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = '#000'; ctx.fillStyle = c; ctx.fillRect(0, 0, 1, 1); const d = ctx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255] }
  const over = (top, bot) => top.slice(0, 3).map((v, i) => v * top[3] + bot[i] * (1 - top[3])).concat(1)
  const lum = (c) => { const [r, g, b] = c.slice(0, 3).map((v) => (v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4); return 0.2126 * r + 0.7152 * g + 0.0722 * b }
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }
  // shortcut: ancestor opacity and filters are ignored; a background image or gradient leaves the text unmeasured.
  const ground = (el) => {
    const layers = []
    for (let e = el; e; e = e.parentElement) {
      const s = getComputedStyle(e)
      if (s.backgroundImage !== 'none') return null
      const c = rgba(s.backgroundColor)
      if (c[3] > 0) layers.push(c)
      if (c[3] === 1) break
    }
    return layers.reverse().reduce((bot, top) => over(top, bot), [255, 255, 255, 1])
  }
  const own = (el) => [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim()
  const texts = [...document.querySelectorAll('body *')].filter((el) => own(el) && vis(el) && !el.closest('[aria-hidden="true"], :disabled, script, style'))
  const px = (el) => parseFloat(getComputedStyle(el).fontSize) * (el.getScreenCTM?.()?.a ?? 1) // SVG text scales with its viewBox
  const q = (el) => `"${own(el).slice(0, 28)}"`
  const out = {}

  let worst = null, unmeasured = 0
  for (const el of texts) {
    const s = getComputedStyle(el), bg = ground(el)
    const fg = rgba(el instanceof SVGElement ? s.fill : s.color)
    if (!bg || (el instanceof SVGElement && !/^(rgb|#|oklch|lab|lch|hsl|color)/.test(s.fill))) { unmeasured++; continue }
    const size = px(el), large = size >= 24 || (size >= 18.66 && +s.fontWeight >= 700)
    const r = ratio(over(fg, bg), bg), need = large ? 3 : 4.5
    if (!worst || r / need < worst.r / worst.need) worst = { r, need, el }
  }
  out.contrast = worst ? [worst.r >= worst.need, `lowest ${worst.r.toFixed(2)}:1 against ${worst.need}:1 at ${q(worst.el)}${unmeasured ? `; ${unmeasured} on an image unmeasured` : ''}`] : [false, 'no text found']

  const HIT = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], [role=tab], [role=checkbox], [role=switch], [tabindex]:not([tabindex="-1"])'
  // A coarse pointer (the 390 run emulates touch) is held to 44 by 44. A fine pointer is held to WCAG 2.5.8 AA:
  // 24 by 24, or a 24px circle on the target's centre that meets no other target and no other such circle.
  // A link inside running text is exempt from its own size check at both, but it is still a target another
  // target's 24px circle must not reach.
  const coarse = matchMedia('(pointer: coarse)').matches, need = coarse ? 44 : 24
  const all = [...document.querySelectorAll(HIT)].filter((el) => vis(el) && !(el instanceof SVGElement))
    .map((el) => ({ el, b: el.getBoundingClientRect() })).filter(({ b }) => b.width && b.height)
  const hits = all.filter(({ el }) => !(el.matches('a') && getComputedStyle(el).display === 'inline' && own(el.parentElement)))
  const centre = ({ b }) => [b.left + b.width / 2, b.top + b.height / 2]
  const gap = ([x, y], b) => Math.hypot(Math.max(b.left - x, 0, x - b.right), Math.max(b.top - y, 0, y - b.bottom))
  const under = hits.filter(({ b }) => b.width < need || b.height < need)
  const spaced = (t) => !coarse && all.every((o) => o === t || o.el.contains(t.el) || t.el.contains(o.el)
    || (gap(centre(t), o.b) >= 12 && (!under.includes(o) || Math.hypot(...centre(t).map((v, i) => v - centre(o)[i])) >= 24)))
  const small = under.filter((t) => !spaced(t))
    .map(({ el, b }) => `${el.tagName.toLowerCase()} "${(el.getAttribute('aria-label') ?? el.textContent).trim().slice(0, 24)}" ${Math.round(b.width)}x${Math.round(b.height)}`)
  out.targets = [!small.length, small.length ? `under ${need}x${need}${coarse ? '' : ' and not spaced'}: ${small.join(', ')}`
    : `${hits.length} target(s), all ${need}x${need} or more${coarse ? ' (coarse pointer)' : ' or spaced (WCAG 2.5.8)'}`]

  const rules = []
  const walk = (list) => { for (const r of list) { if (r.cssRules) walk(r.cssRules); if (r.selectorText || r.style) rules.push(r) } }
  for (const sh of document.styleSheets) { try { walk(sh.cssRules) } catch { /* a cross-origin sheet cannot be read */ } }
  const sel = rules.some((r) => /::selection/.test(r.selectorText ?? ''))
  const caret = rules.some((r) => r.style?.getPropertyValue('caret-color') && r.style.getPropertyValue('caret-color') !== 'auto')
  const bar = rules.some((r) => /::-webkit-scrollbar/.test(r.selectorText ?? '') || r.style?.getPropertyValue('scrollbar-color'))
  out.selection = [sel, sel ? '::selection is styled' : 'no ::selection rule: browser default highlight']
  out.caret = [caret, caret ? 'caret-color is set' : 'no caret-color: browser default caret']
  out.scrollbar = [bar, bar ? 'scrollbar-color or ::-webkit-scrollbar is set' : 'no scrollbar styling: browser default']

  const data = texts.filter((el) => /\d/.test(own(el)) && (el.matches('td, th, time, data, output') || /^[\d\s:.,%°+\-–−/]+$/.test(own(el))))
  const prop = data.filter((el) => { const s = getComputedStyle(el); return !/tabular-nums/.test(s.fontVariantNumeric) && !/"tnum"/.test(s.fontFeatureSettings) })
  out.tabular = [!prop.length, prop.length ? `proportional numerals at ${prop.slice(0, 3).map(q).join(', ')}` : data.length ? `${data.length} numeral(s) in data, all tabular` : 'no numerals in data']

  let widest = null
  for (const el of document.querySelectorAll('p, li, dd, blockquote, figcaption')) {
    const s = getComputedStyle(el), size = parseFloat(s.fontSize)
    if (!vis(el) || size < 14 || size > 22) continue
    const lines = new Map(), range = document.createRange()
    const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
    for (let n; (n = tw.nextNode());) {
      range.selectNodeContents(n) // text only: a button's box inside a paragraph is not a line
      for (const r of range.getClientRects()) {
        if (!r.width) continue
        const k = Math.round(r.top), l = lines.get(k) ?? [r.left, r.right]
        lines.set(k, [Math.min(l[0], r.left), Math.max(l[1], r.right)])
      }
    }
    if (lines.size < 2) continue // a one-line text does not show the column's measure
    ctx.font = `${s.fontStyle} ${s.fontWeight} ${s.fontSize} ${s.fontFamily}`
    const ch = Math.max(...[...lines.values()].map(([a, b]) => b - a)) / ctx.measureText('0').width
    if (!widest || ch > widest.ch) widest = { ch, el }
  }
  // craft-floor: body measure 65 to 75ch. Over 75 fails; a narrower column is a layout choice and is reported.
  out.measure = widest ? [widest.ch <= 75, `widest wrapped body line ${Math.round(widest.ch)}ch at "${widest.el.textContent.trim().slice(0, 28)}"`] : [true, 'no wrapped body text']

  let tight = null
  for (const el of texts) {
    const s = getComputedStyle(el), em = (parseFloat(s.letterSpacing) || 0) / parseFloat(s.fontSize)
    if (!tight || em < tight.em) tight = { em, el }
  }
  out.tracking = tight ? [tight.em >= -0.04 - 1e-6, `tightest ${tight.em.toFixed(3)}em at ${q(tight.el)}`] : [true, 'no text']

  // A figure shrunk to fit 390 shrinks its labels with it (T-1013: a 9px clearance label); none goes under 12px.
  let tiny = null
  for (const el of texts) { const size = px(el); if (!tiny || size < tiny.size) tiny = { size, el } }
  out['text-size'] = tiny ? [tiny.size >= 12 - 0.05, `smallest ${tiny.size.toFixed(1)}px at ${q(tiny.el)}`] : [true, 'no text']

  // A figure's SVG label over another label (T-1015: "peaked at 13:20" on "2.3 times" at 390). HTML text is laid out
  // by the browser, so only pairs with an SVG label are compared.
  // shortcut: label against label only; a label on a shape's stroke (a pier, a bar) is left to the judge's eye.
  let clash = null
  const boxes = texts.filter((el) => el instanceof SVGElement || el.closest('svg') === null).flatMap((el) => [...el.getClientRects()].map((r) => ({ el, r })))
  for (const [i, a] of boxes.entries()) for (const b of boxes.slice(i + 1)) {
    if (clash || a.el === b.el || !(a.el instanceof SVGElement || b.el instanceof SVGElement) || a.el.contains(b.el) || b.el.contains(a.el)) continue
    const w = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left), h = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top)
    if (w > 2 && h > 2) clash = `${q(a.el)} over ${q(b.el)}`
  }
  out.overlap = [!clash, clash ?? 'no SVG label over another label']

  // T7, the mechanical part of the copy- principles; the judge's eye covers the rest.
  // shortcut: a back link is matched against this screen's controls only, not every screen's; widen if one slips by.
  const bad = []
  const first = (t) => t.trim().split(/\s+/)[0].toLowerCase()
  const acts = [...document.querySelectorAll('button, [role=button], input[type=submit]')].filter(vis).map((b) => (b.textContent || b.value).trim()).filter(Boolean)
  for (const a of document.querySelectorAll('a[href]')) {
    const t = a.textContent.trim()
    if (vis(a) && t && acts.some((b) => b !== t && first(b) === first(t))) bad.push(`link worded as the action "${t.slice(0, 32)}"`)
  }
  // A text alternative read only by a screen reader (the sr-only pattern) is exempt from the sentence rule.
  const srOnly = (el) => { for (let e = el; e; e = e.parentElement) { const s = getComputedStyle(e), r = e.getBoundingClientRect(); if (s.position === 'absolute' && s.overflow === 'hidden' && r.width <= 1 && r.height <= 1) return true } return false }
  // A list ("x, y, z and w": every item after the lead-in 4 words or fewer) is one idea, so its commas are not joins.
  const list = (line) => { const parts = line.split(', '); return parts.length >= 3 && parts.slice(1).every((p) => p.split(/\s+/).length <= 4) && /\b(and|or)\b/.test(parts.at(-1)) }
  for (const el of texts) for (const line of srOnly(el) ? [] : own(el).split(/(?<=[.!?])\s+/)) {
    // 4 joins, not 3: "Fed at 08:10: 50 g flour, 50 g water, 50 g starter" is one idea, a list (T-1015 Rise)
    // 4 joins, not 3: "Fed at 08:10: 50 g flour, 50 g water, 50 g starter" is one idea, a list (T-1015 Rise)
    const words = line.split(/\s+/).length, joins = (line.match(list(line) ? /[;:—] /g : /[,;:—] /g) || []).length
    if (words > 25 || joins >= 4) bad.push(`more than one idea (${words} words, ${joins} joins) "${line.slice(0, 32)}"`)
  }
  const inView = (el) => { const r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight && r.width > 0 }
  const seen = texts.filter(inView).map(own).join(' ')
  const claim = seen.match(/[£$€]\s?\d[\d,.]*|\d[\d,.]*\s?(%|°|[kMG]Wh?\b|m\b|km\b|kg\b|×|times\b)/)
  if (claim && !/illustrative|example|source|published by|according to|estimate/i.test(seen)) bad.push(`"${claim[0]}" with no source or illustrative mark in the first viewport`)
  out.copy = [!bad.length, bad.length ? bad.slice(0, 3).join('; ') : 'no back link worded as an action, one idea per line, every figure sourced']
  return out
}

// Runs in the page: running animations, and transitions that move something (they would run on hover or change).
// shortcut: motion driven by requestAnimationFrame is invisible here; the judge's stills are the check for it.
const motion = () => {
  const anims = document.getAnimations().filter((a) => a.playState === 'running' && (a.effect?.getComputedTiming().duration ?? 0) > 10).length
  const moves = [...document.querySelectorAll('*')].filter((el) => {
    const s = getComputedStyle(el)
    return s.transitionDuration.split(',').some((d) => parseFloat(d) > 0.01) && /\b(all|transform|translate|scale|rotate|top|left|right|bottom|inset|margin)\b/.test(s.transitionProperty)
  }).length
  return { anims, moves }
}

// A ring: a visible outline, or a box-shadow that was not there at rest.
const ringNow = () => {
  const el = document.activeElement
  if (!el || el === document.body) return null
  const again = el.dataset.evStop === '1'
  el.dataset.evStop = '1'
  const s = getComputedStyle(el)
  const outline = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0 && !/rgba\(.*, 0\)|transparent/.test(s.outlineColor)
  return { again, name: `${el.tagName.toLowerCase()} "${(el.getAttribute('aria-label') ?? el.textContent).trim().slice(0, 24)}"`, ring: outline || s.boxShadow !== (el.dataset.evRestShadow ?? 'none') }
}

export async function evidence(urls, prefix) {
  const browser = await chromium.launch()
  const res = Object.fromEntries(CHECKS.map((c) => [c, {}])) // check -> size -> [[ok, value, screen], ...]
  const put = (check, size, screen, ok, value) => (res[check][size] ??= []).push([ok, value, screen])
  try {
    for (const [size, width, height, name] of SIZES) {
      for (const [i, url] of urls.entries()) {
        const screen = urls.length > 1 ? `screen ${i + 1}: ` : ''
        const errors = []
        const touch = name === 'mobile' // a phone has a coarse pointer, so its pointer-coarse styles apply
        const page = await browser.newPage({ viewport: { width, height }, reducedMotion: 'no-preference', hasTouch: touch, isMobile: touch })
        page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 80)))
        page.on('pageerror', (e) => errors.push(e.message.slice(0, 80)))
        page.on('requestfailed', (r) => errors.push(`failed to load ${r.url().split('/').pop()}`))
        await page.goto(url)
        await page.evaluate(() => document.fonts.ready)
        await page.waitForTimeout(300)
        const free = await page.evaluate(motion)
        await page.emulateMedia({ reducedMotion: 'reduce' })
        await page.waitForTimeout(100)
        const reduced = await page.evaluate(motion)
        put('reduced-motion', size, screen, !reduced.anims && !reduced.moves,
          `motion allowed: ${free.anims} running animation(s), ${free.moves} moving transition(s); under reduce: ${reduced.anims}, ${reduced.moves}`)
        for (const [check, [ok, value]] of Object.entries(await page.evaluate(atRest))) put(check, size, screen, ok, value)

        await page.evaluate(() => { for (const el of document.querySelectorAll('*')) el.dataset.evRestShadow = getComputedStyle(el).boxShadow })
        const stops = []
        for (let n = 0; n < 60; n++) {
          await page.keyboard.press('Tab')
          const f = await page.evaluate(ringNow)
          if (!f || f.again) break
          stops.push(f)
          if (stops.length === 1 && i === 0 && prefix) await page.screenshot({ path: `${prefix}-focus-${name}.png` })
        }
        const bare = stops.filter((f) => !f.ring)
        put('focus', size, screen, stops.length > 0 && !bare.length,
          !stops.length ? 'Tab reaches nothing' : bare.length ? `no ring on ${bare.map((f) => f.name).join(', ')}` : `${stops.length} Tab stop(s), each with a visible ring`)
        put('console', size, screen, !errors.length, errors.length ? errors.slice(0, 3).join('; ') : 'no errors')
        await page.close()
      }
    }
  } finally { await browser.close() }
  // One line per check: FAIL when any screen at any size fails; the value is the first failure, else the first screen's.
  return CHECKS.map((check) => {
    const sizes = Object.entries(res[check])
    const ok = sizes.every(([, rows]) => rows.every((r) => r[0]))
    const say = sizes.map(([size, rows]) => { const bad = rows.find((x) => !x[0]); return [size, bad ? `${bad[2]}${bad[1]}` : `${rows.length > 1 ? `all ${rows.length} screens; screen 1: ` : ''}${rows[0][1]}`] })
    const text = say[0][1] === say[1]?.[1] ? `both sizes, ${say[0][1]}` : say.map(([size, v]) => `${size} ${v}`).join('; ')
    return { check, ok, line: `${ok ? 'PASS' : 'FAIL'} ${check}: ${text}` }
  })
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [prefix, ...urls] = process.argv.slice(2)
  if (!prefix || !urls.length) { console.error('usage: node evidence.mjs <out-prefix> <url> [url ...]'); process.exit(2) }
  const rows = await evidence(urls.map((u) => (/^[a-z]+:/.test(u) ? u : pathToFileURL(u).href)), prefix)
  const text = `# Measured evidence\n\nChromium at 1280x633 and 390x757, ${urls.length} screen(s); the focus capture is the first screen's first Tab stop (\`-focus-desktop.png\`, \`-focus-mobile.png\` beside this file).\n\n${rows.map((r) => `- ${r.line}`).join('\n')}\n`
  writeFileSync(`${prefix}-evidence.md`, text)
  console.log(text)
  process.exit(rows.every((r) => r.ok) ? 0 : 1)
}
