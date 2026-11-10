// node --test evidence.test.mjs: the fixture passes every check, and each deliberate break turns exactly its
// own check red (a probe that cannot go red proves nothing).
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { test } from 'node:test'
import { evidence, CHECKS } from './evidence.mjs'

const good = readFileSync(new URL('./fixtures/evidence/good.html', import.meta.url), 'utf8')
const BREAKS = {
  focus: [':focus-visible{outline:3px solid var(--ink);outline-offset:2px}', ':focus{outline:none}'],
  'reduced-motion': ['@media (prefers-reduced-motion:reduce){.mark{animation:none}}', ''],
  contrast: ['color:var(--ink);font:16px', 'color:#999;font:16px'],
  targets: ['min-height:48px', 'min-height:0'],
  console: ['</body>', '<script>console.error("boom")</script></body>'],
  selection: ['::selection{', '.no-selection{'],
  caret: [';caret-color:var(--accent)', ''],
  scrollbar: ['html{scrollbar-color:var(--ink) var(--ground)}', ''],
  tabular: [';font-variant-numeric:tabular-nums', ''],
  measure: ['p{max-width:65ch}', 'p{max-width:110ch}'],
  tracking: ['letter-spacing:-0.02em', 'letter-spacing:-0.06em'],
  'text-size': ['td{padding:4px 8px;', 'td{font-size:9px;padding:4px 8px;'],
  overlap: ['</table>', '</table><svg width="200" height="40" aria-label="lift"><text x="10" y="24" font-size="16">North bascule</text><text x="40" y="28" font-size="16">Pivot</text></svg>'],
  copy: ['>All lifts today<', '>Notify me of all lifts today<'],
}

test('evidence: green on the fixture, each break red on its own check', { timeout: 180000 }, async () => {
  assert.deepEqual(Object.keys(BREAKS).sort(), [...CHECKS].sort(), 'every check has a break')
  const dir = mkdtempSync(join(tmpdir(), 'evidence-'))
  const page = (name, html) => { const f = join(dir, `${name}.html`); writeFileSync(f, html); return pathToFileURL(f).href }
  const red = async (url, prefix) => (await evidence([url], prefix)).filter((r) => !r.ok).map((r) => r.check)

  assert.deepEqual(await red(page('good', good), join(dir, 'good')), [], 'the fixture passes every check')
  assert.ok(existsSync(join(dir, 'good-focus-desktop.png')) && existsSync(join(dir, 'good-focus-mobile.png')), 'focus captured at both sizes')
  for (const [check, [from, to]] of Object.entries(BREAKS)) {
    assert.ok(good.includes(from), `${check}: the break's text is in the fixture`)
    assert.deepEqual(await red(page(check, good.replace(from, to))), [check], `${check}: only its own check goes red`)
  }
})

// T-1015: the battery brief's copy that two fresh judges marked T7 on the final screens must go red here.
test('evidence: copy goes red on the battery eval screens\' old copy', { timeout: 60000 }, async () => {
  const url = new URL('./fixtures/eval/battery/old-copy.html', import.meta.url).href
  const line = (await evidence([url])).find((r) => r.check === 'copy')
  assert.equal(line.ok, false)
  for (const want of ['link worded as the action', 'more than one idea', 'no source or illustrative mark']) assert.ok(line.line.includes(want), `${want}: ${line.line}`)
})

// T-483: a fine pointer is held to WCAG 2.5.8 AA (24px, or spaced), a coarse one to 44; a list is one idea and
// an sr-only text alternative is exempt from the sentence rule.
test('evidence: targets by pointer, lists and sr-only copy', { timeout: 120000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), 'evidence-aa-'))
  const page = (name, body) => { const f = join(dir, `${name}.html`); writeFileSync(f, `<!doctype html><meta name="viewport" content="width=device-width"><body style="margin:40px">${body}</body>`); return pathToFileURL(f).href }
  const line = async (url, check) => (await evidence([url])).find((r) => r.check === check).line
  const btn = (x) => `<button style="position:absolute;left:${x}px;top:40px;width:20px;height:20px;padding:0;border:0">${x}</button>`

  const touching = await line(page('touching', btn(40) + btn(60)), 'targets')
  assert.match(touching, /^FAIL targets: 1280x633 under 24x24 and not spaced: button "40" 20x20, button "60" 20x20; 390x757 under 44x44: /, touching)
  const spaced = await line(page('spaced', btn(40) + btn(100)), 'targets')
  assert.match(spaced, /1280x633 2 target\(s\), all 24x24 or more or spaced \(WCAG 2\.5\.8\); 390x757 under 44x44: /, spaced)
  // Atlas (bdd5bc4): an inline prose link is exempt from its own size, not from another target's circle.
  const prose = (x) => `<p style="position:absolute;left:${x}px;top:41px;margin:0;font:14px/17px sans-serif"><a href="#">help</a> for more</p>`
  assert.match(await line(page('alone', btn(40)), 'targets'), /1280x633 1 target\(s\), all 24x24 or more or spaced/)
  const near = await line(page('inline-near', btn(40) + prose(60)), 'targets')
  assert.match(near, /^FAIL targets: 1280x633 under 24x24 and not spaced: button "40" 20x20; 390x757 /, near)
  assert.match(await line(page('inline-far', btn(40) + prose(100)), 'targets'), /1280x633 1 target\(s\), all 24x24 or more or spaced/)

  const list = 'Eleven named checks cover arithmetic drift, data declarations, control flow, exception paths, I/O order, dataflow and formal equivalence.'
  const long = 'Product preview, in eight steps: an AI tool edits a program; Refinery maps the programs, copybooks, datasets and batch jobs linked to it; it checks the changed program, finds the moved threshold, and asks a person to accept or return the change.'
  const sr = 'position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)'
  assert.match(await line(page('copy-ok', `<p>${list}</p><p style="${sr}">${long}</p>`), 'copy'), /^PASS copy/)
  assert.match(await line(page('copy-red', `<p>${long}</p>`), 'copy'), /^FAIL copy: .*more than one idea/)
})
