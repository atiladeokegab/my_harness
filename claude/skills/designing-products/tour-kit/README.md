# Tour kit

The judge tour, lifted from Strata's guided tour and made generic: a step list in `tour.json`, a card and a
ring that keep the layout rules by construction, and a harness that proves it at both sizes. The contract
is `../reference/judge-tour.md`; read it first.

| File | What it is |
|---|---|
| `tour.schema.json` | The step contract: titles at most 4 words, captions at most 22, a `subject` on every step, stateful lines only through `captionFrom` |
| `guide.js` | The engine: `setupGuide`, `startGuide`, `goTo`, `stopGuide`, `applyStep`, `frameShift`, `cardPlace`; publishes `window.__<app>.settled` |
| `Guide.jsx` | The card, the clamped ring, the docking, the stops, the readout (React 18+, no other dependency) |
| `guide.css` | The card and ring; map the `--guide-*` variables to the product's tokens |
| `shots.mjs` | The harness: every step at 1280x633 and 390x757, `tour-sheet.png`, `shots.json` |
| `strata.tour.json` | Strata's fourteen steps converted: a complete example |
| `guide.test.js` | `node --test guide.test.js`: the band, the docking, `frameShift` and the story rule |

## Wire it in

```js
// web/src/main.jsx
import tour from './tour/tour.json'
import { setupGuide } from './tour/guide.js'
import { useStore } from './store.js'
setupGuide(tour, {
  ready: () => useStore.getState().settled,          // the app's own settle signal, never a timer
  show: (want) => useStore.getState().apply(want),   // state that changes layout (sheet, route, toggles)
  frame: (shift, want) => useStore.setState({ frameShift: shift, cam: want.cam }), // after layout: aim the camera
  reset: () => useStore.getState().reset(),
  actions: { lift: () => useStore.getState().lift() },
  readouts: { year: () => `${useStore.getState().year}` },
  subscribe: useStore.subscribe,
  // 3D only: idle() true when the camera is at rest; project([x, y, z]) -> [x, y] screen pixels or null
})
// in the app shell, once: <Guide />  and a "Take the tour" button calling startGuide()
```

## Run the harness

```bash
npm i -D playwright                                   # once; PLAYWRIGHT_CHROMIUM=<path> uses a cached browser
node scripts/tour-shots.mjs http://127.0.0.1:5173/ src/tour/tour.json shots
SIZES=390x757 STEPS=time,part node scripts/tour-shots.mjs ...   # narrow a run while fixing
```

It loads the app once per size on `?tour=1&step=<first>`, then moves step to step in the app (as Next
would), so each step also proves Back and Next leave a clean state. Output: `FAIL <size> <step> <rule>: ...`
lines, a `RED`/`GREEN` summary, `shots/tour-sheet.png`, `shots/shots.json`; exit 1 when red. On a VM without
a GPU the scene renders in software WebGL; judge the look on the L4 stills, the layout here.
Software WebGL takes about 40 minutes a size there. On a 3D app, run it on the L4 job instead, one Cloud Run task
per step x size: `3d-model-workflow/gpu-stills/tour.sh <tag> <url> [tour.json]` (its README has the env). Locally,
`CHROMIUM_ARGS` replaces the software-GL flags and `REFERER` re-sends Maps requests with the live origin.
