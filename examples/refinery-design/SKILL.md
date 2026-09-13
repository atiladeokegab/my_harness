---
name: refinery-design
description: Refinery's binding design system — typefaces, palette, spacing, radii, the green dot mark, section rhythm and content doctrine. Load before any Refinery visual or copy work: website pages and components under website/, pitch decks, one-pagers, OG images, favicons, diagrams. Triggers on "design", "styling", "brand", "typeface", "font", "colour", "palette", "spacing", "layout", "section", "deck", "slide", "logo", "wordmark", "landing page", "hero", "copy for the site".
---

# Refinery design system

**v2, 2026-09-05.** Reconciled from three sources of differing authority. Read
§0 before trusting any single number.

The user's standard: *"we need to abide by that 120%, no room for errors."*
Every rule here is an acceptance criterion. **None of it is built yet** — the live
site still runs the old serif/cream system, so expect these rules to disagree with
the current code.

## 0. Which source wins

| Source | Authoritative for | Not authoritative for |
|---|---|---|
| **Type specimen** (`references/… 23.34.47.png`) | Font **families** — Work Sans headings, Inter body | anything else |
| **Figma inspection** (§ below, pasted 2026-09-05) | Spacing, radii, **sizes**, line-heights, colour hexes, effects, icons | font **families** |
| **Screenshots** (`references/*.png`) | Layout, composition, structure | **exact colour** — see §2 |

The Figma file was only partly updated: **the hero was converted to the new type,
the rest of the file still carries IBM Plex.** So every IBM Plex role in that
inspection is stale — keep its size, line-height and colour, swap the family per §1.
IBM Plex Serif, Sans and Mono are all retired.

## 1. Typography

Two families. **Work Sans** for headings, **Inter** for everything else. No serif,
no italic, no monospace. `font-serif` and `font-mono` must not survive in `website/`.

### Headings — Work Sans

Only the hero is measured; the rest keeps Figma's sizes with families swapped. The
line-heights and tracking below are **derived** from the hero's ratio (97% leading,
−4% tracking at 60px), loosening as size drops — flagged because they are the one
part of this table nobody has signed off.

| Role | Size | Line-height | Tracking | Colour |
|---|---|---|---|---|
| Hero | 60px | 97% | −4% | `#F4F4F5` (accent phrase `#00D46A`) |
| CTA heading | 56px | 105% | −3% | `#F4F4F5` |
| Section heading | 40px | 110% | −2.5% | `#F4F4F5` |
| Video / minor heading | 32px | 115% | −2% | `#F4F4F5` |
| Card title | 22px | 130% | −1% | `#F4F4F5` |
| Partner name | 20px | 130% | −1% | `#F4F4F5` |

All headings are **Work Sans Regular 400**. Contrast comes from size and colour, not
weight — never reach for a heavier heading. Weight 500–600 belongs to the wordmark.

### Body and UI — Inter

| Role | Weight | Size | Line-height | Tracking | Colour |
|---|---|---|---|---|---|
| Hero / CTA subhead | 400 | 20px | 150% | 0 | `#A1A1AA` |
| Section body | 400 | 16px | 150% | 0 | `#A1A1AA` |
| Card body | 400 | 14px | 160% | 0 | `#A1A1AA` |
| Nav link | 500 | 15px | auto | 0 | `#A1A1AA` |
| Button text | 600 | 14px | auto | 0 | ground or ink |
| Strength label / tab | 600 | 13px | auto | 0 | `#F4F4F5` |
| Strength value | 600 | 16px | auto | 0 | `#00D46A` |
| Eyebrow (section kicker) | 600 | 13px | auto | **+2%**, uppercase | `#00D46A` |
| Card eyebrow | 600 | 12px | auto | +1%, uppercase | `#00D46A` |
| Competitor value | 400 | 13px | auto | 0 | `#71717A` |
| Code / hashes | 400 | 13px | 20px | 0 | see §2 |
| Meta, tags, SHA, timestamps | 400 | 10–12px | auto | 0–1% | `#71717A` / `#A1A1AA` |
| Legal, copyright | 400 | 12px | 150% | 0 | `#71717A` |

**On the 500/600 weights above.** The Regular-only rule governs *headings*. Small UI
text — buttons, nav, eyebrows, labels at ≤14px — keeps the weight Figma specifies,
because at that size weight is legibility, not emphasis. A 400-weight 13px uppercase
eyebrow disappears. This is a judgement call, not something the user stated; raise it
if it looks wrong in build.

**Code without a mono face.** Mono is retired, so COBOL panels and SHA strings get
their alignment from layout — a CSS grid per column, `white-space: pre`, and
`font-variant-numeric: tabular-nums`. This is the weakest point in the system; if the
FlowDemo code panel reads badly, re-raise mono with the user rather than working
around it.

Both families load from `next/font/google` in `app/layout.tsx`. Delete `--font-serif`
and `--font-mono` from the `@theme` block rather than aliasing them, so a stray
`font-serif` fails loudly.

## 2. Palette

**The green never changed. Do not "correct" it to `#60D175`.**

Sampling the reference PNGs returns `#60D175` for the brand green. That is a
colour-profile artefact, not a design decision: the screenshots are macOS captures
tagged Display P3, and sRGB `#00D46A` converts to exactly `#60D175` in P3. Every
other token round-trips byte-identically (neutrals are unchanged by the conversion),
which is what proves it. **Trust the Figma hexes; treat PNG-sampled saturated colour
as untrustworthy.**

| Token | Value | Role |
|---|---|---|
| Ground | `#09090B` | page background, editor body, inner panels |
| Surface | `#18181B` | cards, panels, editor header |
| Surface 2 | `#1F1F23` | competitor cards, portal top bar |
| Border | `#27272A` | **every** border — 1px, inside |
| Ink | `#F4F4F5` | primary text, headings |
| Muted | `#A1A1AA` | body copy, secondary text |
| Tertiary | `#71717A` | timestamps, meta, legal |
| **Green** | **`#00D46A`** | the single accent |
| Error | `#EF4444` | defect alerts only |

Independently confirmed from the Figma SVG exports, where colour is literal and immune to
the P3 problem: `#00D46A` appears 55 times across the two landing frames, alongside
`#A1A1AA` (57), `#F4F4F5` (52), `#71717A` (36), `#09090B` (24), `#18181B` (22),
`#1F1F23` (19), `#27272A` (7) and `#EF4444` (3).

Derived greens: `#00D46A` at ~10% for badge tints, at 20% for badge borders.

### The code panel is the one exception to green-only

The COBOL editor mock carries a syntax palette, found in the vector exports and absent from
the Figma inspection summary. It is **code colour, not brand colour** — do not flatten it to
green when applying the single-accent rule:

| Hex | Observed role in the mock |
|---|---|
| `#E2E8F0` | default code text |
| `#00D46A` | division and section headers |
| `#60A5FA` | secondary keywords |
| `#FBBF24` | the AI-rewrite comment line |
| `#F87171` / `#FCA5A5` | the changed statements |

Role attribution is read off the mock, not from named tokens — treat the hexes as fixed and
the mapping as a starting point.

**Two real changes from the live site:** ink moves from warm cream `#F0EDE5` to
neutral `#F4F4F5`, and borders move from `rgba(255,255,255,0.08)` to solid `#27272A`.
Grep for `F0EDE5` and `--r-border` when converting.

**Green is the only accent — for now, and this rule is under revision.**

As shipped, green is the sole accent: the Figma's `#4589FF` and `#A78BFA` partner dots
were taken to green. But on 2026-09-05 the founder pushed back on exactly this, and they are
right: "the overuse of the primary colour makes it start looking boring at the end."

The direction he asked for, not yet built, is a structured palette:

| Role | What it does |
|---|---|
| **Primary** `#00D46A` | the brand, and every verdict. Load-bearing, stays |
| **Utility** | semantic: info, warning, danger. Already exists, quarantined in the code panel |
| **Decorative** | non-semantic, one hue per item in a set, to stop the primary going flat |

Every candidate already clears AA on both dark grounds: `#60A5FA` 7.83:1, `#FBBF24`
11.92:1, `#F87171` 7.19:1, `#4589FF` 5.95:1, `#A78BFA` 7.31:1 on `#09090B`.

The discipline to keep when this lands: **decorative colour must never look like a state.**
Green means verified, so it cannot also mean decorative. A violet dot on a partner card is
fine; a violet dot beside a check result is not. Waiting on the founder's reference brands
before building it.

### Green goes on dark. Always.

`#00D46A` is built for a dark ground and only works there:

| Pair | Ratio | Verdict |
|---|---|---|
| Green on ground `#09090B` | 10.07:1 | AAA |
| Green on surface `#18181B` | 8.96:1 | AAA |
| **Green on ink `#F4F4F5`** | **1.79:1** | **fails text, large text AND graphical objects** |

So there is a second value for light grounds, and it is not optional:

**`--color-green-ink: #00753A`** — 5.53:1 on `#FAF9F5`, 4.71:1 on `#E9E7E0`, 5.82:1 on
white. Use it anywhere green sits on a light surface: the FlowDemo Change Contract mock,
a light deck slide, any printed piece. Never put `#00D46A` on a light ground, including
for decoration, even though WCAG exempts decoration.

The one asset that still carries brand green on white is
`public/brand/refinery-wordmark-on-light.svg`, where the dot is the trademark and the
lockup is fixed. That is a partner-facing asset, not site UI.

Contrast clears WCAG AA throughout: ink 18.1:1, green 10.1:1, muted 7.8:1 on ground;
muted 6.9:1 on surface. Tertiary `#71717A` is 4.12:1 on ground and 3.67:1 on surface,
which passes for large and incidental text only — it is used for timestamps, meta and
legal lines, never body copy. Do not push muted darker than `#A1A1AA`.

## 3. Spacing

Frame 1440px · page gutter **80px** · content max-width **1280px**.

**Scale: 4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48 · 56 · 64 · 80 · 120.**
Use nothing else. (The file also holds one-off 134 and 140 section bottoms; ignore
them, they are not scale.)

| Context | Value |
|---|---|
| Section vertical padding | 120px (the default; hero is 180 top) |
| Section header → body gap | 12px between eyebrow, heading and body |
| Card grid gap | 24px |
| Competitor grid gap | 12px (both axes) |
| Nav links | 32px |
| Hero heading → subhead | 20px |
| Button gap | 16px |
| CTA bullet gap | 32px |
| Chip/tag gap | 8px |

| Card padding | Value |
|---|---|
| Feature and partner cards | 32px |
| Strength cards | 20px |
| Portal columns | 20px |
| Competitor cards, mock-UI panels | 16px |
| Portal items | 12px |

## 3b. The nav

Height is `--nav-h`, a single fluid token: `clamp(64px, 57.33px + 1.852vw, 84px)` — 64px on
a phone, 84px at the 1440px frame.

**Everything that has to clear the nav derives from it**: page top padding, the sticky docs
sub-bar (`top: var(--nav-h)`), the mobile drawer, and `scroll-margin-top` on every anchor.
Before this it was a hard-coded `h-14` repeated in seven files, so the bar could not be
resized without silently breaking an anchor somewhere else. Never re-introduce a literal.

Nav links are 15px, not the 14px the rest of the small UI uses — the user asked for a
bigger bar and 14px read as undersized against it. The nav CTA is the standard
`.btn-primary`, not a smaller hand-rolled variant.

## 4. Radii

| Element | Radius |
|---|---|
| Feature and partner cards | 8px |
| Competitor cards | 10px |
| Large panels — editor, video, portal, strength cards | 12px |
| Buttons, mock-UI inner panels, portal items | 6px |
| Badges, tags, chips | 4px |
| Pill badge ("Backed by") | full (100px) |

## 5. Effects — the system is flat

Three effects exist in the entire file. Everything else is a flat fill.

| Effect | Where | Spec |
|---|---|---|
| Background blur | nav bar | 16px, over `#09090B` at 80% |
| Drop shadow | editor card | `#00D46A` 5.9%, blur 40, y+16 |
| Inner shadow | video card | `#000000` 66.7%, blur 12, y+4 |

Plus two decorative radial-glow ellipses (`#00D46A` ~17%→0% top, ~8%→0% bottom) —
gradient fills on shapes, not effects.

**Retire:** `.glass`, `.glow-border`, `.noise-overlay`, `--r-glass*`, `--r-blur`, and
most of `components/Backdrop.tsx`. **Keep:** the nav's `backdrop-filter`, and the two
glow ellipses. No noise, no grain, no layered glows, no gradient card fills.

## 6. Buttons

| | Primary | Secondary |
|---|---|---|
| Fill | `#00D46A` | transparent |
| Text | `#09090B`, Inter 600 14px | `#F4F4F5`, Inter 600 14px |
| Border | none | `#27272A` 1px inside |
| Radius | 6px | 6px |
| Padding | 12px / 20px | 12px / 20px |
| Height | 42px | 42px |

**No hover, focus, pressed or disabled states are defined anywhere.** Design them,
then get them signed off — do not ship a button with only a default state, and do not
ship one without a visible `:focus-visible` ring.

## 7. Icons

**Lucide**, stroke-only, stroke width 2, no fills. Frames at 24 / 16 / 14px.
Colour follows the text it sits with — `#00D46A` for brand, `#A1A1AA` for muted,
`#EF4444` for errors.

## 8. The wordmark and the green dot

**"Refinery" in Work Sans with the tittle over the "i" replaced by a green dot**
(`#00D46A`). The serif italic wordmark and the four-stacked-bars mark in
`components/RefineryLogo.tsx` are retired.

Three lockups, all 129×42 at source:

| Ground | Word | Dot |
|---|---|---|
| Dark `#09090B` | `#F4F4F5` | `#00D46A` |
| Light `#FFFFFF` | `#000000` | `#00D46A` |
| Green plate `#00D46A` | `#000000` | `#FFFFFF` |

On a green plate the dot inverts to white so it never disappears into its own ground.

**The dot detaches and is the trademark element in its own right:**

- **A full stop** closing a heading — `software.` in the hero, in green.
- **An image anchor or placeholder** — a circular green dot standing in for an image,
  or a circular frame content is arranged around.
- **A bullet** in short inline trust lists (`● No setup fee ● No lock-in`). Short
  lists only, never a general `<ul>` marker.
- **The app icon** — "R" plus the dot on a near-black square, 41×41 at source.
- **The recurring motif** in every deck and page.

Never tint it, outline it, or animate it gratuitously.

### The assets exist — do not redraw them

Exported from Figma and stored in `references/svg/`. Use these; tracing the mark by hand is
how the lockups drift apart.

| File | Size | Word | Dot | Use |
|---|---|---|---|---|
| `refinery-wordmark-on-dark.svg` | 130×42 | `#F4F4F5` | `#00D46A` | the site, dark decks |
| `refinery-wordmark-on-light.svg` | 130×42 | `#000000` | `#00D46A` | light decks, print |
| `refinery-wordmark-on-green.svg` | 130×42 | `#000000` | `#FFFFFF` | green plates |
| `refinery-wordmark-mono.svg` | 97×24 | `#F4F4F5` | ink | single-colour contexts |
| `refinery-app-icon.svg` | 41×41 | `#F4F4F5` R on `#09090B` | `#00D46A` | favicon, app icon |
| `refinery-dot.svg` | 16×16 | — | `#00D46A` | the standalone mark |

Text is outlined in all of them, so they carry no font dependency.

**One caveat:** the green-plate lockup was **derived**, not exported — built by recolouring
the light lockup's dot to white, then rendered and checked against
`references/… 23.30.16.png`. It matches, but if Figma ever exports the real one, prefer it.

Adopting the wordmark moves `RefineryLogo.tsx`, `Nav.tsx`, `Footer.tsx`,
`public/favicon.svg`, `public/og.svg` / `og.png`, and the four JPGs in `public/brand/`.
All of them move together or the brand splits.

## 9. Section rhythm

```css
.section-full {
  min-height: 100svh;          /* fills the screen; grows only if content demands it */
  display: flex;
  flex-direction: column;
  justify-content: center;
}
```

A short window never crushes a section below its content plus spacing; a section never
floats taller than the viewport without cause. `svh`, not `vh`. This composes with the
120px section padding in §3 — it does not replace it.

## 10. Content doctrine — build for scanning

- A visitor scans first and reads only after they are interested. Every section carries
  **one key thing**; technical detail lives behind a link to `/docs`.
- **Context before the claim.** The explanatory section comes first and must make
  Refinery legible to anyone; the big callout follows it.
- Prefer a minimal **1-2-3 animated progression** — what was bad, what is good now —
  over a paragraph arguing the same point.
- Sourcing stays visible. Competitive claims come from the other vendor's own published
  documentation, and the page says so.
- Reference bar named by the user: Apple's compare pages, Revolut, Wise.

## 11. Page structure (decided, not yet built)

**Homepage** — the comparison leaves. In its slot: **Four Key Advantages**, plus a
clean pain-point → fix animation. No background animation behind it.

**`/pricing`** — receives the comparison, rebuilt to
`references/… 23.31.46.png`: a `WHY REFINERY IS DIFFERENT` row of five strength chips
(Change Behavior Equivalence · Verification Strategy · Regulator Deliverables ·
Compliance Binding · Who authors changes), then `HOW OTHERS COMPARE` as a
three-column card grid (AI Migrations · AI Code Gates · Manual Review) with a legend.
The grid is what makes it work on a phone — today's table is `min-w-[860px]`.
Keep the "drawn from the vendor's own published documentation" note.

## 12. Still undefined

Do not invent these:

1. **Button states** — hover, focus, pressed, disabled (§6).
2. **Motion** — no durations or easing anywhere. Only "no background animation" and
   "prefer a 1-2-3 progression" are recorded.
3. **Light mode** — the Figma has isolated light and green-plate hero explorations, not
   a light theme. Unknown whether the site ever gets one.
4. **Imagery** — the dot-as-placeholder rule exists, but nothing shows how a real image
   or render is treated.
5. **Deck layouts past the title slide** — no content-slide, chart or diagram style.
6. **Voice and tone** — scannability is captured; sentence case, punctuation habits and
   how to write for a risk/audit reader are not.
7. **Heading line-height and tracking below 60px** — derived in §1, unsigned-off.
8. **Responsive** — every number here is the 1440px frame. No breakpoints defined.

## 13. Before you write code

`website/AGENTS.md` warns that this Next.js (16.2.6, React 19, Tailwind v4) differs from
training data — read `node_modules/next/dist/docs/` for anything non-obvious.

## References

`references/` holds the user's screenshots; §0 governs what each is good for.
`references/svg/` holds the Figma vector exports — the named mark assets above, plus
`refinery-landing-top.svg` / `refinery-landing-bottom.svg` (the full landing page as vectors,
the best source for exact geometry) and the outlined type-specimen pieces. All text is
outlined, so the SVGs carry no font names — but their colour is literal, which makes them the
tiebreaker whenever a PNG sample and a stated hex disagree.

| File | What it settles |
|---|---|
| `… 23.34.47.png` | The type specimen: Heading = Work Sans, Body = Inter |
| `… 23.29.55.png` | Wordmark, dark-on-light lockup |
| `… 23.30.16/23.30.30.png` | Wordmark on green plate — dot inverts to white |
| `… 23.28.55.png` | Deck title slide, dark. Green full stop closing the heading |
| `… 23.29.16.png` | The same slide, light ground |
| `… 23.31.19.png` | Homepage top: nav, hero, FlowDemo, video, How it works |
| `… 23.31.46.png` | Five strengths + How others compare card grid (→ `/pricing`) |
| `… 23.32.16.png` | Portal teaser, ecosystem cards, CTA with dot bullets |
| `unnamed.png` | App icon: "R" + dot |

> **Public copy.** This harness ships the screenshots and the six mark assets only. The
> full-page Figma frames (`refinery-landing-*.svg`, `hero-section*.svg`) and the outlined
> type-specimen exports stay in the private repo.
