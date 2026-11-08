// The judge tour's card: the step's title and caption, a ring on the control it is about, progress dots, Back / Next
// and Skip. Lifted from Strata's guided tour. Steps and their live actions come from tour.json through guide.js;
// call setupGuide(tour, app) first, then mount <Guide /> once. Captions live in this DOM overlay, pinned to the
// screen, never in a scene-anchored layer.
import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import { guide, getApp, goTo, stopGuide, autoStart, runAction, cardPlace, chromeRects, rectOf, isPhone } from './guide.js'
import './guide.css'

// The ring, clamped 4 px inside the viewport so all four edges show; it follows its target through layout shifts and
// scrolls an off-screen target into view once.
function Spotlight({ selector }) {
  const ref = useRef(null)
  useLayoutEffect(() => {
    let raf, scrolled = false
    const tick = () => {
      const el = ref.current
      const target = selector && document.querySelector(selector)
      let r = target?.getBoundingClientRect()
      if (r && !scrolled && (r.top < 0 || r.left < 0 || r.bottom > innerHeight || r.right > innerWidth)) {
        scrolled = true
        target.scrollIntoView({ block: 'nearest', inline: 'nearest' })
        r = target.getBoundingClientRect()
      }
      if (el) {
        const show = r && r.width > 0 && r.height > 0
        el.style.opacity = show ? 1 : 0
        if (show) {
          const L = Math.max(4, r.left - 6), T = Math.max(4, r.top - 6), R = Math.min(innerWidth - 4, r.right + 6), B = Math.min(innerHeight - 4, r.bottom + 6)
          Object.assign(el.style, { left: `${L}px`, top: `${T}px`, width: `${R - L}px`, height: `${B - T}px` })
        }
      }
      raf = requestAnimationFrame(tick)
    }
    tick()
    return () => cancelAnimationFrame(raf)
  }, [selector])
  return <div ref={ref} className="guide-spot" aria-hidden="true" />
}

// Dock the card every frame: in the band the chrome leaves clear, at the edge farthest from the spot (guide.js cardPlace).
function useDock(ref, spot, active) {
  useLayoutEffect(() => {
    if (!active) return
    let raf
    const tick = () => {
      const el = ref.current
      if (el) {
        const p = cardPlace(innerWidth, innerHeight, chromeRects(), rectOf(spot), isPhone())
        Object.assign(el.style, { left: `${p.left}px`, width: `${p.width}px`, maxHeight: `${p.maxHeight}px`,
          top: p.top === undefined ? 'auto' : `${p.top}px`, bottom: p.bottom === undefined ? 'auto' : `${p.bottom}px` })
      }
      raf = requestAnimationFrame(tick)
    }
    tick()
    return () => cancelAnimationFrame(raf)
  }, [ref, spot, active])
}

// A captionFrom line: read from the app's store on every change, so it never goes out of step with the UI.
const none = () => () => {}
function Readout({ name }) {
  const app = getApp()
  const text = useSyncExternalStore(app.subscribe ?? none, () => app.readouts?.[name]?.() ?? '')
  return text ? <p className="guide-readout">{text}</p> : null
}

export default function Guide() {
  const { active, i, steps } = useSyncExternalStore(guide.subscribe, guide.get)
  const step = steps[i]
  const card = useRef(null)
  const [stop, setStop] = useState(0)
  const [auto, setAuto] = useState(true)
  useDock(card, step?.spot, active)

  useEffect(autoStart, []) // first visit, or ?tour=1
  useEffect(() => { setStop(0); setAuto(true) }, [step])
  useEffect(() => { // a multi-stop step plays its stops on its own, each for its hold, until the visitor taps one
    if (!active || !step?.stops || !auto || stop >= step.stops.length - 1) return
    const id = setTimeout(() => { runAction(step.stops[stop + 1].action); setStop(stop + 1) }, 1000 * (step.stops[stop].hold ?? 3))
    return () => clearTimeout(id)
  }, [active, step, stop, auto])
  useEffect(() => {
    if (!active) return
    const key = (e) => e.key === 'Escape' && stopGuide()
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  }, [active])

  if (!active || !step) return null
  const last = i === steps.length - 1
  const pick = (k) => { setAuto(false); setStop(k); runAction(step.stops[k].action) }
  return (
    <>
      {step.spot && <Spotlight selector={step.spot} />}
      <section ref={card} className={`guide-card guide-${step.id}`} role="dialog" aria-label="Guided tour" aria-live="polite">
        <div className="guide-head">
          <p className="guide-count">{i + 1} of {steps.length}</p>
          <button type="button" className="guide-skip" onClick={stopGuide}>Skip tour</button>
        </div>
        <div className="guide-body" key={step.id}>
          <h2>{step.title}</h2>
          {step.caption && <p className="guide-caption">{step.caption}</p>}
          {step.stops && (
            <div className="guide-stops" role="group" aria-label={step.title}>
              {step.stops.map((x, k) => (
                <button key={x.label} type="button" className={k === stop ? 'on' : ''} aria-pressed={k === stop} onClick={() => pick(k)}>{x.label}</button>
              ))}
            </div>
          )}
          {step.captionFrom && <Readout name={step.captionFrom} />}
        </div>
        <div className="guide-foot">
          <div className="guide-dots">
            {steps.map((x, k) => (
              <button key={x.id} type="button" className={k === i ? 'on' : k < i ? 'done' : ''} onClick={() => goTo(k)}
                aria-label={`Step ${k + 1}: ${x.title}`} aria-current={k === i ? 'step' : undefined} />
            ))}
          </div>
          <div className="guide-nav">
            {i > 0 && <button type="button" className="guide-back" onClick={() => goTo(i - 1)}>Back</button>}
            <button type="button" className="guide-next" onClick={() => (last ? stopGuide() : goTo(i + 1))}>{last ? 'Start exploring' : 'Next'}</button>
          </div>
        </div>
      </section>
    </>
  )
}
