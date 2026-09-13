---
name: design-system
description: Build, reconcile and enforce a binding design system for a product — typefaces, palette and contrast, spacing scale, radii, effects, components and their states, icons, the brand mark, section rhythm, motion and content doctrine — then verify the built result in a real browser. Load before any visual or copy work - website pages and components, landing pages, pitch decks, one-pagers, OG images, favicons, diagrams. Triggers on "design system", "design", "styling", "brand", "typeface", "font", "colour", "color", "palette", "contrast", "spacing", "layout", "section", "deck", "slide", "logo", "wordmark", "landing page", "hero", "Figma", "tokens", "copy for the site".
---

# Design system

A design system is a set of **acceptance criteria**, not a mood board. Every rule written
into a project's design skill is something a build can pass or fail. The standard this
harness was built around: *"abide by it 120%, no room for errors."*

This skill does two jobs:

1. **Author** a project design skill (`<repo>/.claude/skills/<project>-design/SKILL.md`)
   from whatever the designer has supplied — Figma, screenshots, a type specimen, a live
   site, a conversation.
2. **Apply and verify** it: build to the rules, then prove in a real browser that the
   result obeys them.

A fully worked example lives in this harness at `examples/refinery-design/` — a real
product's skill, reconciled from Figma, screenshots and a type specimen. Read it once
before writing your first one; its structure is the template below.

---

## 1. Authoring a project design skill

### 1.0 Decide which source wins — before trusting any number

Design inputs disagree. Record, per source, what it is authoritative for and what it is
**not**, and put that table first in the skill:

| Source | Authoritative for | Not authoritative for |
|---|---|---|
| Type specimen | Font **families** | anything else |
| Figma inspection / design tokens | Spacing, radii, sizes, line-heights, hexes, effects, icons | families, if the file was only partly migrated |
| Vector (SVG) exports | **Exact colour** — fills are literal | layout intent |
| Screenshots | Layout, composition, structure | **exact colour** (see §3) |
| The live site | What is shipped today | what is *wanted* |

A partly-updated Figma file is normal: often only the hero has the new type. Keep the old
roles' size, line-height and colour, and swap the family.

### 1.1 Intake — ask, don't invent

Ask the owner for what is missing rather than filling gaps with taste. Minimum set:

- Typefaces for headings and body (and whether serif, italic or mono are allowed at all)
- The accent colour(s) and the grounds they sit on
- A spacing scale, or permission to derive one from the frames
- The mark: wordmark, icon, and any detachable element
- Reference products they consider the bar (e.g. Apple compare pages, Revolut, Wise)
- Voice: how scannable, how technical, who the reader is

If the user dictates prompts (voice transcription garbles words — "the dot above the eye"
for "the i"), reconstruct the intended meaning, say it back plainly, and ask only where two
readings lead to materially different work.

### 1.2 The sections every project skill has

Use these headings, in this order. Leave a section as *"undefined — ask"* rather than
guessing; §13 collects every such gap.

0. **Which source wins** — the table above.
1. **Typography** — one table for headings (role · size · line-height · tracking ·
   colour), one for body/UI (role · weight · size · line-height · tracking · colour).
   Say which values were *measured* and which were *derived*, and flag derived ones as
   unsigned-off. State where fonts load from and delete retired font variables rather than
   aliasing them, so a stray use fails loudly.
2. **Palette** — tokens with value and role; the single accent (or the structured palette:
   *primary* for brand and state, *utility* for info/warning/danger, *decorative* for
   non-semantic variety). Include a **contrast table** for every foreground/ground pair
   actually used, computed with `scripts/colour.py matrix`. If the accent fails on light
   grounds, define a second "accent-ink" value for light surfaces — it is not optional.
3. **Spacing** — frame width, gutter, content max-width, **the scale** ("use nothing
   else"), then a table of contexts (section padding, header→body gap, grid gaps, card
   padding by card type).
4. **Layout primitives** — fixed chrome (nav height as one fluid token that everything
   else derives from — never a repeated literal), section rhythm, breakpoints.
5. **Radii** — per element type.
6. **Effects** — list the few that exist; everything else is flat. Name what to retire.
7. **Components** — buttons (fill, text, border, radius, padding, height) **with every
   state**: default, hover, focus-visible, pressed, disabled. A component with only a
   default state is not done. Then cards, badges, inputs as needed.
8. **Icons** — library, stroke, sizes, colour rule.
9. **The mark** — lockups per ground (word colour, mark colour), any detachable element and
   its sanctioned uses, and **where the exported assets live**. Use exported assets; never
   redraw a mark by hand — that is how lockups drift apart.
10. **Motion** — one curve, one duration family, travel distances, and the failure rules
    in §4 below.
11. **Content doctrine** — how pages read (see §5).
12. **Page structure** — decided-but-not-built layouts, so builders don't reinvent them.
13. **Still undefined** — the explicit list of things nobody has decided. *Do not invent
    these.* Typical: button states, motion, light mode, imagery, deck content slides,
    voice and tone, responsive breakpoints.
14. **Before you write code** — framework version warnings (e.g. "this is not the Next.js
    you know — read `node_modules/next/dist/docs/`").

Close with a **References** table: each file in `references/`, and what it settles.

### 1.3 Where things go

```
<repo>/.claude/skills/<project>-design/
├── SKILL.md
└── references/
    ├── README.md          # naming rule: name files by subject, e.g. deck-title-slide.png
    ├── *.png              # screenshots — layout truth, never colour truth
    └── svg/               # vector exports — colour truth, and the mark assets
```

When a new batch of references lands, update `SKILL.md` in the same change so rules and
images agree.

---

## 2. Typography rules that generalise

- Contrast comes from **size and colour**, not weight. Headings stay at one regular
  weight; a heavier heading reads as a different brand. Small UI text (≤14px: buttons,
  nav, eyebrows) keeps a heavier weight because at that size weight is legibility.
- If monospace is retired, code and hashes get alignment from layout: a grid per column,
  `white-space: pre`, `font-variant-numeric: tabular-nums`. If that reads badly, raise mono
  with the owner rather than working around it.
- Derive line-height and tracking for smaller sizes from the one measured size, loosening
  as size drops, and mark the derivation as unsigned-off.

## 3. Colour rules that generalise

- **Never take a hex from a screenshot.** macOS captures are Display P3; saturated colours
  shift and neutrals don't, so the greys "confirm" a wrong accent. Check with
  `python3 scripts/colour.py from-p3 <sampled>` — if it lands on the stated token, nothing
  changed. Prefer SVG exports, where fills are literal, as the tiebreaker.
- Compute every pair you ship: `python3 scripts/colour.py matrix <fgs> <grounds>`.
  Body text needs 4.5:1, large text 3:1, UI and graphical objects 3:1. A tertiary grey
  that only clears 3–4.5:1 is for timestamps and legal lines, never body copy.
- **A saturated accent usually fails on light grounds** (a bright green on near-white was
  1.79:1 — failing text, large text *and* graphics). Give light surfaces their own darker
  accent token and never put the bright one there, decoration included.
- **Decorative colour must never look like a state.** If the accent means "verified", it
  cannot also mean "decorative".
- Replace a token everywhere in one commit, then grep for the old literal.

## 4. Build rules that generalise (Tailwind / Next.js)

- **CSS layers:** unlayered CSS beats every `@layer` regardless of specificity, and
  Tailwind v4 puts utilities in a layer. Put element defaults in `@layer base`, component
  classes in `@layer components`, and let utilities win. Both failure directions have
  shipped: an unlayered `.btn-primary` beating `hidden`, then `@layer components` losing to
  an unlayered `a { color: inherit }`. See `runbooks/tailwind-layer-order.md`.
- **Reveal animations must fail open.** A start state of `opacity: 0` that only JS can undo
  is a blank page waiting to happen. Two halves, keep both: (1) reveal at mount anything
  already on screen — an `IntersectionObserver` is not guaranteed to fire for elements
  already in view; (2) hide only under a class the inline head script sets (`html.js`), and
  add a timed failsafe that forces everything visible if hydration never arrives. Re-check
  reveals on `hashchange` and `load` — a same-page anchor fires `hashchange`, a fresh
  `#hash` URL does not. See `runbooks/website-content-invisible.md`.
- Full-viewport sections: `min-height: 100svh` (not `vh`), centred content, composed with
  the section padding — never ad-hoc per-section padding values.
- Fixed chrome height is **one token**; page top padding, sticky sub-bars, drawers and
  `scroll-margin-top` all derive from it.

## 5. Content doctrine that generalises

- Design for **scanning**, not reading. Each section carries one key thing; technical
  detail lives behind a link.
- **Context before the claim.** The explanatory section comes first; the big callout
  follows it.
- Show, minimally: a 1-2-3 progression (what was bad → what is good now) beats a
  paragraph arguing it.
- Sourcing stays visible. Competitive claims cite the other party's own documentation.

---

## 6. Verification — prove it in a browser, both directions

Reading CSS proves nothing: every rule can look right in isolation and still lose. Verify
the **built** page.

1. **Assert the stylesheet loaded** before measuring anything. An unstyled page (stale
   `.next` build) has no sidebar and no margins and measures as *perfectly responsive*.
2. **Prove each check can go red.** Inject the defect (a fixed-width element, a failing
   contrast pair) and require the check to catch it. Then remove it and require the check
   to go quiet. A probe that has never failed has measured nothing.
3. **When a check goes red, find the element it points at** before changing code. Carousels,
   deliberately clipped decoration and nested `<nav>`s all produce correct-code failures.
4. **Trust pixels over computed style.** Under headless virtual time, transitions and
   `requestAnimationFrame` don't advance, smooth scrolling never completes, and `100svh`
   resizes with the capture window. See `runbooks/headless-browser-css-checks.md` for the
   same-origin iframe probe that works around all of it.
5. **Strip every `<script>`** from the built page and screenshot it: the page must still be
   readable. That is the fail-open test for motion.
6. Check every element with the accent as background via `getComputedStyle` — text colour
   on the accent is the pair most often broken by a cascade change.

## 7. Checklist before calling design work done

- [ ] Every value used is in the skill's tables or scale — no one-off numbers
- [ ] Contrast matrix recomputed for every pair on the page
- [ ] Every interactive component has hover, focus-visible, pressed and disabled states
- [ ] Mark rendered from the exported asset, not redrawn
- [ ] Page readable with scripts stripped
- [ ] Measured at phone width with a real narrow viewport, not a cropped screenshot
- [ ] Anything decided in the conversation written back into the project skill
- [ ] Anything still undecided listed in §13, not silently invented
