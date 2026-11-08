#!/usr/bin/env node
// The judge tour harness. For each step of tour.json at 1280x633 and 390x757: open the app on ?tour=1&step=<first>,
// move to the step, wait for window.__<app>.settled (the app's signal, not a timer), screenshot, and assert the layout
// rules of reference/judge-tour.md. Writes <out>/tour-sheet.png (steps x sizes) and <out>/shots.json (a valid
// film shot list: one step is one beat, its caption the beat's caption, its hold the beat's seconds). Exit 1 on any
// failure.
//
//   node shots.mjs <url> <tour.json> [out-dir]      e.g. node shots.mjs http://127.0.0.1:5173/ web/src/tour/tour.json shots
//
// Playwright comes from the product's devDependencies; PLAYWRIGHT_CHROMIUM points it at a cached browser.
// SIZES=390x757 or STEPS=time,part narrow a run; SETTLE_MS (default 60000) bounds each wait. On an L4, one step x size per
// Cloud Run task: 3d-model-workflow/gpu-stills/tour.sh (CHROMIUM_ARGS, REFERER).
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const main = import.meta.url === `file://${process.argv[1]}` // imported by guide.test.js for storyProblems
const [url, tourPath, out = 'shots'] = main ? process.argv.slice(2) : []
if (main && (!url || !tourPath)) { console.error('usage: node shots.mjs <url> <tour.json> [out-dir]'); process.exit(2) }
const tour = main ? JSON.parse(readFileSync(tourPath, 'utf8')) : null
const SIZES = (process.env.SIZES ?? '1280x633,390x757').split(',')
const ONLY = process.env.STEPS?.split(',')
const SETTLE = Number(process.env.SETTLE_MS ?? 60000)
const words = (s) => (s ?? '').trim().split(/\s+/).filter(Boolean).length
const secs = (x) => (x.stops ? x.stops.reduce((n, s) => n + (s.hold ?? 3), 0) : x.hold ?? 6) // a step's seconds on screen

// The story rule and the step contract, before any browser. Judges decide in the first 20 s: the problem is step 1 and
// the wow step 2 (no title card, setup or login between), the wow is on screen by 10 s, and the problem, the wow and the
// one number (`shows.number`, in the problem's or the wow's caption or title) all land by 20 s. Then one last step that
// is the ask, every step with a subject, captions at most 22 words, titles at most 4.
export function storyProblems(t) {
  const p = [], s = t.steps ?? []
  const wow = s.findIndex((x) => x.beat === 'wow')
  if (s[0]?.beat !== 'problem') p.push('step 1 is not the problem')
  if (wow !== 1) p.push('the wow is not step 2: nothing but the problem comes before it')
  else {
    if (secs(s[0]) > 10) p.push(`the wow is on screen at ${secs(s[0])} s, after 10 s`)
    if (secs(s[0]) + secs(s[1]) > 20) p.push(`the problem and the wow land at ${secs(s[0]) + secs(s[1])} s, after 20 s`)
    const shown = (x) => x.shows?.number && `${x.caption ?? ''} ${x.title ?? ''}`.includes(x.shows.number)
    if (!shown(s[0]) && !shown(s[1])) p.push('the one number (shows.number) is not in the problem\'s or the wow\'s caption or title')
  }
  if (!s.at(-1)?.last || s.at(-1)?.beat !== 'ask' || s.filter((x) => x.last).length !== 1) p.push('the last step, and only it, must be last: true with beat ask')
  for (const x of s) {
    if (!x.subject) p.push(`${x.id}: no subject`)
    if (words(x.caption) > 22) p.push(`${x.id}: caption is ${words(x.caption)} words`)
    if (words(x.title) > 4 || !x.title) p.push(`${x.id}: title must be 1 to 4 words`)
    if (!x.caption && !x.captionFrom) p.push(`${x.id}: no caption`)
  }
  return p
}

// Runs in the page: every rule on what is on screen now.
function check({ step, chrome, app }) {
  const W = innerWidth, H = innerHeight, f = []
  const vis = (e) => e && e.checkVisibility({ opacityProperty: true, visibilityProperty: true })
  const box = (r) => r && { l: Math.round(r.left), t: Math.round(r.top), r: Math.round(r.right), b: Math.round(r.bottom) }
  const hit = (a, b) => a && b && Math.min(a.r, b.r) - Math.max(a.l, b.l) > 1 && Math.min(a.b, b.b) - Math.max(a.t, b.t) > 1
  const rect = (e) => (vis(e) ? box(e.getBoundingClientRect()) : null)
  const say = (rule, msg) => f.push({ rule, msg })
  const card = document.querySelector('.guide-card'), C = rect(card)
  const chromeEls = chrome.flatMap((q) => [...document.querySelectorAll(q)]).filter((e) => rect(e) && !card?.contains(e) && !e.contains(card))

  // ring: inside the viewport with a 4 px margin; its target on screen
  let spot = null
  if (step.spot) {
    const target = document.querySelector(step.spot), T = rect(target), ring = rect(document.querySelector('.guide-spot'))
    if (!T) say('ring', `spot ${step.spot} not found or hidden`)
    else if (T.b < 0 || T.t > H || T.r < 0 || T.l > W) say('ring', `spot ${step.spot} is off screen ${JSON.stringify(T)}`)
    if (!ring) say('ring', 'no ring shown')
    else if (ring.l < 3.5 || ring.t < 3.5 || ring.r > W - 3.5 || ring.b > H - 3.5) say('ring', `ring ${JSON.stringify(ring)} not 4 px inside ${W}x${H}`)
    spot = ring ?? T
  }
  // card: present, on screen, not clipped, phone height at most 35%, clear of the spot, the subject and the chrome
  if (!C) say('card', 'no card')
  else {
    if (C.l < 0 || C.t < 0 || C.r > W || C.b > H) say('card', `card ${JSON.stringify(C)} leaves the ${W}x${H} viewport`)
    if (card.scrollHeight > card.clientHeight + 1 || card.scrollWidth > card.clientWidth + 1) say('card', `card clips its text (${card.scrollHeight} > ${card.clientHeight} px)`)
    if (W <= (window.__tourPhone ?? 900) && C.b - C.t > 0.35 * H + 1) say('card', `card is ${C.b - C.t} px, over 35% of ${H}`)
    if (hit(C, spot)) say('card', `card ${JSON.stringify(C)} covers the spot ${JSON.stringify(spot)}`)
    for (const e of chromeEls) if (hit(C, rect(e))) say('card', `card covers chrome ${e.className || e.tagName}`)
  }
  // subject: on screen, not under the card or the chrome
  const sub = typeof step.subject === 'string' ? document.querySelector(step.subject) : null
  const S = typeof step.subject === 'string' ? rect(sub) : box(window[`__${app}`]?.subject?.())
  if (!S) say('subject', 'subject not found, hidden or behind the camera')
  else {
    if (S.r <= 0 || S.l >= W || S.b <= 0 || S.t >= H) say('subject', `subject ${JSON.stringify(S)} is off screen`)
    if (hit(C, S)) say('subject', `card ${JSON.stringify(C)} covers the subject ${JSON.stringify(S)}`)
    for (const e of chromeEls) if (!(sub && (e.contains(sub) || sub.contains(e))) && hit(rect(e), S)) say('subject', `chrome ${e.className || e.tagName} covers the subject ${JSON.stringify(S)}`)
  }
  // text: no two visible text boxes overlap (a label under the card, labels colliding); clipped by scrolling ancestors
  const texts = []
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.data.trim() ? 1 : 2) })
  for (let n; (n = walk.nextNode());) {
    const el = n.parentElement
    if (!vis(el) || el.closest('script,style,noscript')) continue
    const range = document.createRange(); range.selectNodeContents(n)
    let r = box(range.getBoundingClientRect())
    for (let a = el; a && r; a = a.parentElement) {
      const o = getComputedStyle(a)
      if (o.overflow !== 'visible' || o.overflowX !== 'visible' || o.overflowY !== 'visible') {
        const c = box(a.getBoundingClientRect())
        r = { l: Math.max(r.l, c.l), t: Math.max(r.t, c.t), r: Math.min(r.r, c.r), b: Math.min(r.b, c.b) }
        if (r.r - r.l < 2 || r.b - r.t < 2) r = null
      }
    }
    if (r && r.r > 0 && r.b > 0 && r.l < W && r.t < H) texts.push({ el, r, s: n.data.trim().slice(0, 30) })
  }
  const clash = []
  for (let a = 0; a < texts.length; a++) for (let b = a + 1; b < texts.length; b++) {
    const x = texts[a], y = texts[b]
    if (x.el !== y.el && !x.el.contains(y.el) && !y.el.contains(x.el) && hit(x.r, y.r)) clash.push(`"${x.s}" / "${y.s}"`)
  }
  if (clash.length) say('text', `${clash.length} overlapping text boxes: ${clash.slice(0, 4).join('; ')}`)
  // headings: none empty, none without content beside it
  for (const h of document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]')) {
    if (!vis(h)) continue
    const own = h.innerText.trim(), parent = h.parentElement
    const rest = parent ? parent.innerText.replace(h.innerText, '').trim() : ''
    if (!own) say('heading', `empty <${h.tagName.toLowerCase()}> in ${parent?.className || parent?.tagName}`)
    else if (!rest && !parent?.querySelector('img,canvas,svg,video,input,button,select,textarea')) say('heading', `"${own}" has no content`)
  }
  // caption: the words on the card at most 22, per line
  const caption = card?.querySelector('.guide-caption')?.innerText ?? '', readout = card?.querySelector('.guide-readout')?.innerText ?? ''
  for (const [k, s] of [['caption', caption], ['readout', readout]]) {
    const n = s.trim().split(/\s+/).filter(Boolean).length
    if (n > 22) say('caption', `${k} is ${n} words`)
  }
  return { failures: f, caption: caption.trim(), readout: readout.trim() }
}

async function run() {
  const { chromium } = await import('playwright')
  const problems = storyProblems(tour)
  for (const p of problems) console.log(`FAIL story ${p}`)
  const steps = tour.steps.filter((x) => !ONLY || ONLY.includes(x.id))
  // CHROMIUM_ARGS (the GPU job's flags, space-separated) replaces software WebGL; the renderer is logged as proof
  const gpu = process.env.CHROMIUM_ARGS?.split(' ').filter(Boolean)
  const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM || undefined, headless: !gpu, args: gpu ?? ['--enable-unsafe-swiftshader'] /* software WebGL where there is no GPU */ })
  if (gpu) { const p = await browser.newPage(); console.log(`renderer ${await p.evaluate(() => { const g = document.createElement('canvas').getContext('webgl2'), e = g?.getExtension('WEBGL_debug_renderer_info'); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'none' })}`); await p.close() }
  const results = Object.fromEntries(steps.map((x) => [x.id, { shots: {}, checks: {} }]))
  try {
    for (const size of SIZES) {
      const [w, h] = size.split('x').map(Number)
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: 'reduce', hasTouch: w <= (tour.phone ?? 900) })
      const page = await ctx.newPage()
      // a referrer-locked Maps key only answers the live origin; a tagged revision sends REFERER instead
      if (process.env.REFERER) await page.route((u) => u.hostname.endsWith('googleapis.com'), (r) => r.continue({ headers: { ...r.request().headers(), referer: process.env.REFERER } }))
      page.setDefaultTimeout(SETTLE) // software WebGL on a busy VM: a screenshot can wait on a slow frame
      let errors = []
      page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 200)))
      page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))
      const u = new URL(url); u.searchParams.set('tour', '1'); u.searchParams.set('step', steps[0].id)
      await page.goto(u.toString(), { waitUntil: 'domcontentloaded', timeout: SETTLE })
      await page.evaluate((p) => { window.__tourPhone = p }, tour.phone ?? 900)
      mkdirSync(join(out, size), { recursive: true })
      for (const [k, step] of steps.entries()) {
        const r = results[step.id]
        const settled = await page.waitForFunction(({ app, id }) => {
          const hook = window[`__${app}`]
          if (hook?.guide && hook.guide.step() !== id) hook.guide.go(id)
          return hook?.settled === true && hook.guide.step() === id
        }, { app: tour.app, id: step.id }, { timeout: SETTLE, polling: 200 }).then(() => true, () => false)
        if (!settled) {
          const shown = await page.evaluate((app) => window[`__${app}`]?.guide?.steps?.() ?? null, tour.app)
          const skipped = step.when && shown?.length && !shown.includes(step.id)
          const why = skipped ? `not shown: its when (${step.when}) is false` : `never settled in ${SETTLE} ms${shown?.length ? '' : ' (the tour never started: is ready() true?)'}`
          r.checks[size] = { failures: [{ rule: 'settle', msg: why }], errors }
          console.log(`${skipped ? 'SKIP' : 'FAIL'} ${size} ${step.id} settle: ${why}`)
          errors = []
          continue
        }
        await page.evaluate(() => new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(res))))
        const file = join(out, size, `${String(k + 1).padStart(2, '0')}-${step.id}.png`)
        await page.screenshot({ path: file })
        const c = await page.evaluate(check, { step, chrome: [...tour.chrome, ...(tour.credits ?? [])], app: tour.app })
        if (errors.length) c.failures.push({ rule: 'console', msg: `${errors.length} console errors: ${errors.slice(0, 2).join(' | ')}` })
        r.shots[size] = file
        r.checks[size] = c
        r.caption ??= [c.caption, c.readout].filter(Boolean).join(' ')
        console.log(c.failures.length ? c.failures.map((x) => `FAIL ${size} ${step.id} ${x.rule}: ${x.msg}`).join('\n') : `ok   ${size} ${step.id}`)
        errors = []
      }
      await ctx.close()
    }
    writeShots(steps, results)
    await sheet(browser, steps, results)
  } finally {
    await browser.close()
  }
  const failed = problems.length + steps.reduce((n, x) => n + Object.values(results[x.id].checks).filter((c) => c.failures.some((y) => !(x.when && /not shown/.test(y.msg)))).length, 0)
  console.log(`${failed ? 'RED' : 'GREEN'}: ${failed} failing (story + step x size); ${join(out, 'tour-sheet.png')}, ${join(out, 'shots.json')}`)
  process.exit(failed ? 1 : 0)
}

function writeShots(steps, results) {
  const shots = {
    title: `${tour.app} judge tour`,
    shots: steps.map((x) => ({
      shot_id: x.id.replace(/-/g, '_'), title: x.title, on_screen: x.shows.claim, criteria: [x.shows.criterion], beat: x.beat,
      lines: [{ sentence_id: x.id.replace(/-/g, '_'), text: results[x.id].caption || x.caption || x.title }],
      hold: secs(x),
      stops: x.stops?.map((s) => ({ label: s.label, hold: s.hold ?? 3 })),
      images: results[x.id].shots, failures: Object.fromEntries(Object.entries(results[x.id].checks).map(([s, c]) => [s, c.failures])),
    })),
  }
  writeFileSync(join(out, 'shots.json'), JSON.stringify(shots, null, 2))
}

// steps x sizes on one sheet, each shot labelled with its step and its failing rules
async function sheet(browser, steps, results) {
  const rows = steps.map((x, k) => `<tr><th>${k + 1}. ${x.id}<br><small>${x.beat}</small></th>${SIZES.map((s) => {
    const c = results[x.id].checks[s], bad = c?.failures.map((y) => y.rule) ?? []
    return `<td class="${bad.length ? 'bad' : 'ok'}">${results[x.id].shots[s] ? `<img src="${relative(out, results[x.id].shots[s])}">` : '<div class="none">no shot</div>'}<p>${s} ${bad.length ? `red: ${[...new Set(bad)].join(', ')}` : 'green'}</p></td>`
  }).join('')}</tr>`).join('')
  writeFileSync(join(out, 'tour-sheet.html'), `<style>body{margin:16px;font:13px system-ui;background:#111;color:#eee}table{border-collapse:collapse}th{text-align:left;padding:8px;vertical-align:top;width:120px}
td{padding:6px;vertical-align:top}img{height:320px;display:block;border:3px solid #2a2}td.bad img{border-color:#d33}.none{height:320px;width:160px;display:grid;place-items:center;border:3px dashed #555}p{margin:4px 0}td.bad p{color:#f66}</style>
<h1>${tour.app} judge tour</h1><table>${rows}</table>`)
  const page = await browser.newPage({ viewport: { width: 1100, height: 800 } })
  await page.goto(pathToFileURL(resolve(out, 'tour-sheet.html')).href, { waitUntil: 'load' })
  // a viewport the sheet's size, not fullPage: a tall fullPage capture fails under software rendering
  await page.setViewportSize(await page.evaluate(() => ({ width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight })))
  // shortcut: one retry, as software GL under load fails a capture now and then; drop it on a GPU runner
  await page.screenshot({ path: join(out, 'tour-sheet.png') }).catch(() => page.screenshot({ path: join(out, 'tour-sheet.png') }))
  await page.close()
}

if (main) await run()
