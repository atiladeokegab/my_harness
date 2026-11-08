// The judge tour's engine, lifted from Strata's guided tour. It reads tour.json (tour.schema.json), drives the app
// through a small adapter, and publishes window.__<app>.settled for the harness (shots.mjs). <Guide /> (Guide.jsx)
// draws the card and the ring. The rules it keeps by construction are in reference/judge-tour.md.
//
// setupGuide(tour, app) once at start-up, then mount <Guide /> once. The adapter:
//   ready()             the app has settled after load (data in, scene drawn): the settle signal, never a timer
//   show(want, step)    put the app in state `want` (tour.default with step.view over it) before layout is measured
//   frame(shift, want)  after layout: aim the camera or scroll at the clear spot [dx, dy, zoom] (frameShift)
//   reset()             Skip and the last step hand back a clean app
//   actions             { name: (arg) => void }, what a step's action runs live
//   readouts, subscribe { name: () => string } and the store's subscribe: captionFrom lines follow the store
//   idle(), project()   optional: camera at rest; [x, y, z] to screen [x, y] (or null) for a box subject

let tour = null
let app = null
let state = { active: false, i: 0, steps: [] }
const subs = new Set()
const set = (patch) => { state = { ...state, ...patch }; subs.forEach((f) => f()) }
export const guide = { get: () => state, subscribe: (f) => { subs.add(f); return () => subs.delete(f) } }
export const getApp = () => app

export const isPhone = () => innerWidth <= (tour?.phone ?? 900)
export const rectOf = (q) => {
  const r = q && document.querySelector(q)?.getBoundingClientRect()
  return r && r.width > 0 && r.height > 0 ? r : null
}
export const chromeRects = () => [...(tour?.chrome ?? []), ...(tour?.credits ?? [])].flatMap((q) => [...document.querySelectorAll(q)])
  .filter((e) => e.checkVisibility?.({ visibilityProperty: true }) ?? true)
  .map((e) => e.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0)

// On the phone the chrome a step is not about hides while its card is up (visibility only, so nothing reflows):
// a phone's bars, dock and sheet leave too little stage for a card and a subject. Credits never hide. Skip brings it all back.
function hideChrome(step) {
  for (const e of document.querySelectorAll('[data-guide-hidden]')) delete e.dataset.guideHidden
  if (!state.active || !isPhone()) return
  const keep = [step.spot, typeof step.subject === 'string' && step.subject].filter(Boolean).map((q) => document.querySelector(q)).filter(Boolean)
  for (const q of tour.chrome) for (const e of document.querySelectorAll(q))
    if (!keep.some((k) => e.contains(k) || k.contains(e))) e.dataset.guideHidden = ''
}

const area = (c) => Math.max(0, c.r - c.l) * Math.max(0, c.b - c.t)
// The stage left clear: the viewport minus each obstacle, cut from whichever side keeps the most area.
export function band(W, H, rects) {
  let b = { l: 0, t: 0, r: W, b: H }
  for (const o of rects) {
    if (!o || o.right <= b.l || o.left >= b.r || o.bottom <= b.t || o.top >= b.b) continue
    const cuts = [{ ...b, l: o.right }, { ...b, r: o.left }, { ...b, t: o.bottom }, { ...b, b: o.top }]
    b = cuts.reduce((best, c) => (area(c) > area(best) ? c : best))
  }
  return b
}

// The card's place: inside the band the chrome leaves, at the edge farthest from the spot, so it never covers the
// spot or the chrome. Phone: the band's width, at most 35% of the height. Desktop: at most 440 px wide, centred.
export function cardPlace(W, H, chrome, spot, phone) {
  const b = band(W, H, chrome), m = 8
  const high = !!spot && (spot.top + spot.bottom) / 2 > (b.t + b.b) / 2
  const width = Math.max(0, phone ? b.r - b.l - 2 * m : Math.min(440, b.r - b.l - 32))
  // a spot inside the band also caps the height, so even a full card stops short of it (too little room shows as a clip)
  const inBand = spot && spot.bottom > b.t && spot.top < b.b
  const room = inBand ? (high ? spot.top - b.t : b.b - spot.bottom) - 2 * m : Infinity
  const maxHeight = Math.max(0, Math.min(phone ? 0.35 * H : Infinity, b.b - b.t - 2 * m, room))
  return { left: (b.l + b.r - width) / 2, width, maxHeight, ...(high ? { top: b.t + m } : { bottom: H - b.b + m }) }
}

// The subject's clear spot (Strata's frameShift): the stage minus the chrome and the card, as [dx, dy, zoom] from the
// viewport centre. zoom > 1 asks the camera to pull back so the subject fits a short band.
export function frameShift(W = innerWidth, H = innerHeight, rects = [...chromeRects(), rectOf('.guide-card')]) {
  const b = band(W, H, rects)
  const h = Math.max(b.b - b.t, H * 0.2)
  return [Math.round((b.l + b.r - W) / 2), Math.round((b.t + b.b - H) / 2), Math.round(100 * Math.min(1.8, Math.max(1, (0.55 * H) / h))) / 100]
}

// Fill an input the way typing would, so the app's own handler runs.
let typed = null // the input this step typed into: cleared when the step is left
export function type(selector, text, submit = false) {
  const el = document.querySelector(selector)
  if (!el) return false
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, text)
  el.dispatchEvent(new Event('input', { bubbles: true }))
  if (submit) setTimeout(() => el.form?.requestSubmit(), 60) // after the app has the new value
  return true
}
export function runAction(a) {
  if (!a) return
  if (a.type !== undefined) { if (type(a.type, a.text, a.submit)) typed = a.type; return }
  const f = app.actions?.[a.do]
  if (!f) throw new Error(`tour: the app has no action "${a.do}"`)
  f(a.arg)
}
const leave = () => { if (typed) type(typed, ''); typed = null }

let applied = false
// Make the app show `step`: its view over the defaults, laid out, then framed, then its live action.
export function applyStep(step) {
  applied = false
  const want = { ...tour.default, ...step.view }
  const root = document.documentElement
  root.dataset.guide = step.id
  if (step.keepLabels) root.dataset.guideLabels = ''
  else delete root.dataset.guideLabels
  app.show(want, step)
  if (step.stops) runAction(step.stops[0].action)
  // a frame for the sheet and the card to lay out and the phone's spare chrome to hide, another before measuring
  const current = () => state.active && state.steps[state.i] === step // not skipped or moved on
  requestAnimationFrame(() => current() && (hideChrome(step), requestAnimationFrame(() => {
    if (!current()) return
    app.frame?.(frameShift(), want, step)
    runAction(step.action)
    applied = true
  })))
}

// The subject's screen box: its selector's rect, or its scene box projected by the app.
function subjectRect(step = state.steps[state.i]) {
  const s = step?.subject
  if (!s) return null
  if (typeof s === 'string') return rectOf(s)
  const [a, b] = s.box
  const pts = [0, 1, 2, 3, 4, 5, 6, 7].map((k) => app.project?.([(k & 1 ? b : a)[0], (k & 2 ? b : a)[1], (k & 4 ? b : a)[2]])).filter(Boolean)
  if (pts.length < 8) return null // behind the camera, or no projection
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1])
  const r = { left: Math.min(...xs), top: Math.min(...ys), right: Math.max(...xs), bottom: Math.max(...ys) }
  return { ...r, width: r.right - r.left, height: r.bottom - r.top }
}

const seenKey = () => `${tour.app}.guide.seen`
export const guideSeen = () => { try { return localStorage.getItem(seenKey()) === '1' } catch { return false } }
const NEVER = /[?&](embed|capture|film)=1\b/ // film takes, embeds and capture scripts never get the tour

export function setupGuide(tourJson, adapter) {
  tour = tourJson
  app = adapter
  if (tour.labels?.length) { // overlay labels hide while a card is up, unless the step keeps them
    const css = document.createElement('style')
    css.textContent = `html[data-guide]:not([data-guide-labels]) :is(${tour.labels.join(',')}) { visibility: hidden !important; }`
    document.head.append(css)
  }
  const hook = (window[`__${tour.app}`] ||= {})
  Object.defineProperties(hook, {
    settled: { configurable: true, get: () => state.active && applied && (app.idle?.() ?? true) },
    subject: { configurable: true, writable: true, value: subjectRect },
    guide: { configurable: true, writable: true, value: { go: (id) => goTo(state.steps.findIndex((x) => x.id === id)), steps: () => state.steps.map((x) => x.id), step: () => state.steps[state.i]?.id } },
  })
}

let pending = false // one start at a time (the button and the first-visit start can both ask)
// auto: the first visit. ?tour=1 forces it, ?tour=1&step=<id> opens any step. Waits on the app's settle signal, then
// up to 1 s more for lazy features so their optional steps (`when`) are counted.
export function startGuide({ auto = false, step } = {}) {
  if (!tour || NEVER.test(location.search) || pending || state.active || (auto && guideSeen())) return
  pending = true
  let lit = 0
  const wait = () => {
    const ready = app.ready()
    if (ready) lit ||= performance.now()
    const lazy = tour.steps.some((x) => x.when && !document.querySelector(x.when))
    if (ready && (!lazy || performance.now() - lit > 1000)) go()
    else setTimeout(wait, 150)
  }
  const go = () => {
    pending = false
    const steps = tour.steps.filter((x) => !x.when || document.querySelector(x.when))
    const i = Math.max(0, steps.findIndex((x) => x.id === step))
    set({ active: true, i, steps })
    applyStep(steps[i])
  }
  wait()
}
export function autoStart() {
  const q = new URLSearchParams(location.search)
  if (q.get('tour') === '1') startGuide({ step: q.get('step') })
  else startGuide({ auto: true })
}

export function goTo(i) {
  const { steps, i: from } = state
  if (i < 0 || i >= steps.length || i === from) return
  leave()
  set({ i })
  applyStep(steps[i])
}

export function stopGuide() {
  if (!state.active) return
  leave()
  set({ active: false })
  hideChrome()
  delete document.documentElement.dataset.guide
  delete document.documentElement.dataset.guideLabels
  try { localStorage.setItem(seenKey(), '1') } catch { /* private mode: it just shows again */ }
  app.reset()
}
