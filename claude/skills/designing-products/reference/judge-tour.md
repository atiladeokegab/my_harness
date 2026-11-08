# The judge tour

The tour is the first screen's workflow: a judge who opens the link sees what the product is, reaches the
moment that proves it is worth their time, then sees one judging criterion per step, the proof and the
call to action. `tour-kit/` is the code (lifted from Strata's guided tour). This file is the contract the kit
and its harness enforce.

## Contents

- The sequence rule
- Each step (`tour.json`)
- Layout rules that hold at both sizes, by construction
- Behaviour
- The harness
- Add the kit to a product
- The film hand-off
- Strata's failures, and the rule that prevents each

## The sequence rule

Judges decide in the first 20 seconds whether a team can win, so those seconds carry the case. Problem (what
this is, one look, step 1) → the wow (step 2, on screen by 10 seconds from the first frame; no title card,
setup or login before it; the job is not to teach the product but to reach the moment that proves it is
worth the visitor's time). The problem, the wow and the one number (`shows.number`, in the problem's or the
wow's caption or title) all land by 20 seconds: the problem's hold plus the wow's (a multi-stop wow counts
its stops) is at most 20. Then each feature in the order that builds the case, one judging criterion per step → the proof (the
number, the chart, the comparison) → the call to action ("now you try"). A tour of features is not a story
(demo-bar rule 3): the step list is the criteria-to-evidence table made clickable, so each step names the
criterion it serves. Strata's fourteen steps follow it: orbit (establish, 6 s) → time (the wow at 6 s: the bridge
rebuilt by year, "140 years" in its caption, landed by 19 s) → exploded, bascules, part, docent, search, lidar, top, walk, identify, reimagine, voice → next (the
ask). Captions go through Impeccable's `clarify`, the layout through `adapt`.

## Each step (`tour.json`)

`tour-kit/tour.schema.json` checks it; `tour-kit/strata.tour.json` is a complete example. Top level: `app`
(the hook name), `phone` (width, default 900), `chrome` (selectors of the bars, dock, panel and sheet),
`credits` (attribution lines), `labels` (overlay labels and callouts), `default` (the state every step starts from) and `steps`.

| Field | Contract |
|---|---|
| `id`, `title` | title at most 4 words |
| `beat` | `problem`, `wow`, `feature`, `proof` or `ask`; the harness checks the sequence rule from it |
| `shows` | `claim` (the feature or claim), `criterion` (the judging criterion id it serves) and, on the problem or the wow, `number`: the one number the first 20 s land, which must appear in that step's caption or title |
| `caption` | at most 22 words, sentence case, no filler (T7), in the product's vocabulary |
| `captionFrom` | a stateful line: an app readout derived from the same store value the UI shows, never a hard-coded string (Strata's slider readout went out of step). A step with `stops` must have one; a stop cannot carry words |
| `view` | app state laid over `default`: a camera key, route or toggles. Anything not named returns to the default, so Back and Next are clean |
| `spot` | the selector of the control it is about; the ring follows it through layout shifts |
| `subject` | required: the selector, or the scene box `{"box": [[x,y,z],[x,y,z]]}`, that must stay uncovered |
| `action` | what the step performs live: `{"do": "<app action>", "arg": ...}` through the store, or `{"type": "<input>", "text": "...", "submit": false}` into a real input (cleared on leaving). A judge sees the feature work, not a picture of it |
| `stops` | a multi-stop step: chips `{label, action, hold}` that play on their own until tapped |
| `hold` | seconds on screen when auto-playing and in the film (default 6; a multi-stop step gives each stop its own) |
| `when` | a selector that must exist for the step to show: a panel with no content yet does not show (the empty heading) |
| `keepLabels` | keep overlay labels up on this step; they must then pass the overlap rule |
| `last` | the call to action; its button reads "Start exploring" |

## Layout rules that hold at both sizes, by construction

1. The stage keeps a clear band: the card, bars, dock and sheet are subtracted from the viewport (each cut
   from the side that keeps most of the stage) and the subject is framed into what is left (`frameShift`);
   on a short screen the camera pulls back so the subject fits the band.
2. The ring is clamped inside the viewport with a 4px margin; a target off screen is scrolled into view
   or the step fails in the harness.
3. The card docks inside the band the chrome leaves, at the edge farthest from the spot, so it never covers
   the spot or the chrome; a spot inside the band also caps the card's height. On the phone it is the band's
   width and at most 35% of the viewport height; on the desktop at most 440px wide, clear of the dock and the
   panel. On the phone the chrome the step is not about (neither holding its spot nor its subject) hides while
   the card is up, because a phone's bars, dock and sheet leave too little stage for a card and a subject;
   `credits` (attribution and licence lines) are avoided like chrome and never hide.
4. Overlay labels and callouts (`labels`) hide while a card is up, or the step keeps them and they pass a
   collision layout; no two text boxes overlap.
5. Captions are DOM in the card, pinned to the screen; never in a scene-anchored layer (drei `Html`).

## Behaviour

- One visible "Take the tour" button (`startGuide()`); it restarts from step 1.
- Auto-start on the first visit once the app's settle signal says it is ready (never a timer), with Skip
  visible; `?tour=1` forces it again, `?tour=1&step=<id>` opens any step. `?embed=1`, `?capture=1` and
  `?film=1` never get it.
- Skip is always visible, one tap (and Escape), restores the default state, marks the tour seen; Back works;
  the last step's "Start exploring" hands back a clean app.

## The harness

`tour-kit/shots.mjs`, in the product's smoke (and on a 3D product on the L4 job as `ORDER=tourstills`). It
first checks the sequence rule and the step contract from `tour.json`, then for each step at 1280x633 and
390x757: opens `?tour=1&step=<first>`, moves to the step, waits for `window.__<app>.settled` (not a timer),
screenshots, and asserts:

| Rule | Red when |
|---|---|
| ring | the spot target is missing or off screen, or the ring is not 4px inside the viewport |
| card | the card leaves the viewport, clips its text, is over 35% of a phone's height, or covers the spot or any chrome |
| subject | the subject is missing or off screen, or the card or the chrome covers it |
| text | two visible text boxes overlap (a label under the card, labels colliding) |
| heading | a visible heading is empty or has no content beside it |
| caption | the caption or the readout on the card is over 22 words |
| console | any console error or page error during the step |
| settle | the step never settled (a step whose `when` is false is reported as skipped) |

It writes `tour-sheet.png` (steps × 2 sizes, each shot framed green or red with its failing rules) for the
screenshot judge and the lead, and `shots.json`. Exit 1 on any failure.

## Add the kit to a product

1. Copy `guide.js`, `Guide.jsx` and `guide.css` to `web/src/tour/`, and `shots.mjs` to `web/scripts/tour-shots.mjs`.
2. Write `web/src/tour/tour.json` in story order; validate it against `tour.schema.json` in the smoke.
3. Write the adapter (`ready`, `show`, `frame`, `reset`, `actions`, `readouts`, `subscribe`; `idle` and `project` for a 3D subject); the header of `guide.js` defines each.
4. Expose a settle signal from the app (data in, scene drawn) and return it from `ready`.
5. Call `setupGuide(tour, app)` at start-up; mount `<Guide />` once over the app; wire "Take the tour" to `startGuide()`.
6. A 3D product passes `frameShift`'s `[dx, dy, zoom]` from `frame` to its camera rig (Strata's `framed()`).
7. Map the `--guide-*` variables in `guide.css` to the product's tokens.
8. `npm i -D playwright`; add `node scripts/tour-shots.mjs $URL src/tour/tour.json shots` to the smoke.
9. Fix every red on `tour-sheet.png` before any screen goes to the lead or the judge.
10. Re-run the harness after any change to the chrome, the card or a caption.

## The film hand-off

`shots.json` is a valid film shot list (`film/contracts/shotlist.schema.json`): one step is one beat
(`shot_id` the step id), its caption the beat's line, `on_screen` its claim, `criteria` its criterion and
`hold` the beat's seconds (a multi-stop step sums its stops). It is the demo section's shot list, so the
film and the tour cannot disagree. As of 2026-11-02 `film.story prepare` builds its shot list from
story.json only and does not read `shots.json`; until it does, the lead agent copies the step order, captions and holds
into the storyboard by hand.

## Strata's failures, and the rule that prevents each

| Failure | Prevented by | Caught by |
|---|---|---|
| Captions anchored to the world origin slid under the dock (fixed on Strata main in a111bee) | rule 5: captions are DOM in the card | card, text |
| The phone's bottom sheet covered the subject | rule 1: the sheet is chrome, the subject is framed above it | subject |
| The phone card sat over the controls | rule 3: the card docks inside the band the chrome leaves | card |
| The ring ran off a short screen; the desktop card covered the timeline's ring (9270085, e8756a6) | rules 2 and 3 | ring, card |
| A clipped caption | rule 3 caps the height; the copy is cut, never the box | card (clips its text), caption |
| An empty heading | `when` hides a step until its panel has content | heading |
| The year readout out of step with the slider | `captionFrom`: the line is read from the store | schema |
