// node --test: the layout rules the kit keeps by construction, and the story rule the harness checks first.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { band, cardPlace, frameShift } from './guide.js'
import { storyProblems } from './shots.mjs'

const R = (left, top, right, bottom) => ({ left, top, right, bottom, width: right - left, height: bottom - top })
const hit = (a, b) => Math.min(a.right, b.right) > Math.max(a.left, b.left) && Math.min(a.bottom, b.bottom) > Math.max(a.top, b.top)
const placed = (p, H) => R(p.left, p.top ?? H - p.bottom - p.maxHeight, p.left + p.width, (p.top ?? H - p.bottom - p.maxHeight) + p.maxHeight)

// a phone: controls across the top, a dock along the bottom, an open sheet above the dock
const phone = { W: 390, H: 757, controls: R(0, 0, 390, 56), dock: R(0, 657, 390, 757), sheet: R(0, 363, 390, 657) }

test('band cuts each obstacle from the side that keeps most of the stage', () => {
  assert.deepEqual(band(390, 757, [phone.controls, phone.dock]), { l: 0, t: 56, r: 390, b: 657 })
  assert.deepEqual(band(1280, 633, [R(0, 0, 360, 633), R(360, 528, 1280, 633)]), { l: 360, t: 0, r: 1280, b: 528 })
})

test('phone card docks away from the spot, never over it or the chrome, at most 35% tall', () => {
  const chrome = [phone.controls, phone.dock, phone.sheet]
  for (const spot of [phone.sheet, R(20, 670, 370, 700), R(150, 70, 240, 110)]) {
    const p = cardPlace(phone.W, phone.H, chrome, spot, true), c = placed(p, phone.H)
    assert.ok(p.maxHeight <= 0.35 * phone.H)
    assert.ok(!hit(c, spot), `card ${JSON.stringify(c)} over spot`)
    for (const x of chrome) assert.ok(!hit(c, x), `card over chrome ${JSON.stringify(x)}`)
  }
})

test('desktop card is clear of the dock and the panel', () => {
  const chrome = [R(0, 0, 360, 633), R(360, 528, 1280, 633)], dockSpot = R(400, 540, 1240, 600)
  const p = cardPlace(1280, 633, chrome, dockSpot, false), c = placed(p, 633)
  assert.ok(p.width <= 440 && p.top !== undefined)
  for (const x of [...chrome, dockSpot]) assert.ok(!hit(c, x))
})

test('frameShift centres the subject in what the card leaves, and pulls back on a short band', () => {
  const [dx, dy, zoom] = frameShift(390, 757, [phone.controls, phone.dock, phone.sheet, R(8, 64, 382, 300)])
  assert.equal(dx, 0)
  assert.equal(dy, Math.round((300 + 363) / 2 - 757 / 2))
  assert.equal(zoom, 1.8)
})

test('the story rule and the step contract', () => {
  const step = (id, beat, extra = {}) => ({ id, title: 'A title', beat, caption: 'Short.', subject: '.x', shows: { claim: 'c', criterion: 'c' }, ...extra })
  const wow = step('b', 'wow', { caption: '140 years in one slider.', shows: { claim: 'c', criterion: 'c', number: '140 years' } })
  const story = (problem, b = wow) => storyProblems({ steps: [problem, b, step('c', 'ask', { last: true })] })
  assert.deepEqual(story(step('a', 'problem')), [])
  const bad = storyProblems({ steps: [step('a', 'feature', { hold: 25 }), step('b', 'feature'), step('c', 'wow', { subject: undefined, caption: 'w '.repeat(23) })] })
  assert.deepEqual(bad, ['step 1 is not the problem', 'the wow is not step 2: nothing but the problem comes before it',
    'the last step, and only it, must be last: true with beat ask', 'c: no subject', 'c: caption is 23 words'])
  // the wow on screen by 10 s: a 9 s problem passes, an 11 s one fails
  assert.deepEqual(story(step('a', 'problem', { hold: 9 })), [])
  assert.deepEqual(story(step('a', 'problem', { hold: 11 })), ['the wow is on screen at 11 s, after 10 s'])
  // problem + wow + the number by 20 s; a multi-stop wow counts its stops
  const long = { ...wow, stops: [{ label: 'a', action: { do: 'x' }, hold: 8 }, { label: 'b', action: { do: 'x' }, hold: 5 }] }
  assert.deepEqual(story(step('a', 'problem', { hold: 8 }), long), ['the problem and the wow land at 21 s, after 20 s'])
  assert.deepEqual(story(step('a', 'problem'), step('b', 'wow')), ['the one number (shows.number) is not in the problem\'s or the wow\'s caption or title'])
})

test('the Strata example passes the story rule', () => {
  assert.deepEqual(storyProblems(JSON.parse(readFileSync(new URL('./strata.tour.json', import.meta.url)))), [])
})
