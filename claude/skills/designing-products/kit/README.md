# Kit

The default components for a product's UI: accessible, unstyled primitives from one library, styled only
from the product's `tokens.css` (generated from its `DESIGN.md`). Not shadcn's look, not hand-made widgets.
The files are copied into the product, like shadcn's model; nothing here is a package the product depends on.

## The library: React Aria Components, `react-aria-components@1.22.1` (pinned, exact)

Compared 2026-11-02 against Radix Primitives (`radix-ui@1.8.1`), npm metadata, GitHub API and an esbuild
measurement of the same piece set (dialog, select, tabs, tooltip, toast, plus each library's field and
button parts), minified and gzipped, over React and ReactDOM 19.3.1:

| | React Aria Components | Radix Primitives |
|---|---|---|
| Accessibility | Adobe's ARIA patterns, tested with screen readers on desktop and mobile; press, hover and focus-visible normalised across mouse, touch, pen and keyboard; i18n and RTL built in | Good ARIA patterns for overlays and menus; no button, link or text-field primitive, so those stay hand-made |
| Pieces we need | All ten have a primitive (card needs none). Toast still ships as `UNSTABLE_` | No Button, Link or TextField; Toast is stable |
| State hooks for styling | `data-hovered`, `data-pressed`, `data-focus-visible`, `data-disabled`, `data-pending` on every piece | `data-state`, `data-disabled`; hover, press and focus-visible left to CSS pseudo-classes |
| Bundle cost, this set | +69.7 KB gzip | +42.1 KB gzip |
| Licence | Apache 2.0 | MIT |
| Maintenance | 12 stable releases in 12 months; repo pushed 2026-10-29; Adobe staff | 12 stable releases in 12 months; repo pushed 2026-10-14 |

**Chosen: React Aria Components.** It is the stronger accessibility floor, it covers every piece so nothing
is hand-made, and its `data-*` states map one to one onto the states each piece must show (hover,
focus-visible, active, disabled, loading as `isPending`). The cost is about 28 KB gzip more than Radix and a
toast still marked unstable: `ui/toast.jsx` is the only file that names it, so a rename touches one file.

## Copy it in

1. In the product: `npm i -E react-aria-components@1.22.1` (React 18 or 19 is already there).
2. `cp -r ~/.claude/skills/designing-products/kit/ui web/src/ui` (or only the pieces you use, plus
   `kit.css`, which every piece imports).
3. Import `tokens.css` first (`tokens/check-design.md`), then use the pieces:
   `import { Button } from './ui/button.jsx'`. Mount `<ToastRegion />` once in the app shell.
4. Self-host every face `DESIGN.md` names: `npm i -E @fontsource/<family>` and import its weights
   (`import '@fontsource/literata/400.css'`). No font CDN and no system face standing in.
5. The copied files are the product's now: change them in the product, never upstream by hand-merging.

The pieces read these tokens. `fixture/build.mjs` fails, naming each one missing, when a `DESIGN.md` lacks one:
`palette.mjs`'s roles (`bg`, `surface`, `border`, `ink`, `muted`, `accent`, `on-accent`, `accent-text`,
`success`, `danger`, `info`) and its `neutral-950` step; `type-scale.mjs`'s `caption`, `body`, `label`, `h3`
(and `h1`, `lead` for the fixture page); `rounded` `control`, `panel`, `pill`; `spacing` `1` to `4`, `6`, `8`;
and `components: control: height:` (the density; 44px or more, the tap-target floor).

Elevation and motion have no slot in `DESIGN.md`'s frontmatter (Impeccable's `document`: they belong in the
sidecar), so `ui/kit.css` sets them once, built from those tokens: the overlay shadow and scrim from
`neutral-950`, the hover tint from `surface` and `ink`, durations and the easing curve. It is the only file
that writes a value. Reduced motion comes from `tokens.css`'s `prefers-reduced-motion` block, which stills
every transition and animation, the spinner included.

## The pieces

| File | Piece | States beyond the four interactive ones (hover, focus-visible, active, disabled) |
|---|---|---|
| `button.jsx` | `Button` `variant` primary, secondary, quiet | loading: `isPending`, spinner, focus kept |
| `link.jsx` | `Link` | none: navigation is the browser's |
| `input.jsx` | `Input` (label, description, error) | invalid; loading: `isPending`, spinner, `aria-busy` |
| `select.jsx` | `Select` (`items: [{ id, name }]`) | loading: `isPending` disables it and shows a spinner |
| `dialog.jsx` | `DialogTrigger`, `Dialog` | traps focus, Escape and outside click close, focus returns |
| `sheet.jsx` | `SheetTrigger`, `Sheet` | the dialog's rules, docked to the inline end |
| `tabs.jsx` | `Tabs`, `TabList`, `Tab`, `TabPanel` | loading: `TabPanel isPending` |
| `tooltip.jsx` | `Tooltip` around one focusable piece | shows on keyboard focus at once; Escape hides |
| `toast.jsx` | `toasts.add({ title, description, tone })`, `ToastRegion` | tone success, danger, info, pending (spinner), each with a word |
| `card.jsx` | `Card` (with `href`, one link) | loading: `isPending` placeholder lines |

Toasts sit under an open dialog or sheet's scrim. The overlays' and tooltip's own states are those of the buttons inside them. One focus ring for all:
`kit-focus`, in `accent-text`, which `palette.mjs` holds at 4.5:1 or better.

## A new piece

Build it the same way and add it here: the React Aria primitive, a `kit-*` class, a sibling `.css` that
reads only `var(--…)` and styles from its `data-*` states, `kit-focus` on whatever takes focus, an
`isPending` where loading makes sense. Then add it to `fixture/page.jsx` in both brands and to the
`PIECES` list in `fixture/keys.mjs`, and run the checks below.

## Checks

```bash
cd kit && npm ci                       # the fixture's deps only, into kit/node_modules (gitignored)
npm run fixture                        # out/<brand>/: tokens.css, the page, DESIGN.md beside it
PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright node fixture/shots.mjs OUT_DIR   # 8 captures; fails if a face falls back
PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright node fixture/keys.mjs            # keyboard and focus
DO_NOT_TRACK=1 ~/.local/share/impeccable/0.1.18/impeccable detect --json . < /dev/null > /tmp/kit.json
node ../tokens/check-detect.mjs /tmp/kit.json                                      # the G2 gate
for b in ledger signal; do for v in 1280x800 390x844; do                           # the rendered pages
  DO_NOT_TRACK=1 ~/.local/share/impeccable/0.1.18/impeccable detect --json --viewport $v \
    file://$PWD/out/$b/index.html < /dev/null > /tmp/kit-$b.json; node ../tokens/check-detect.mjs /tmp/kit-$b.json
done; done
```

Run `detect` after `npm run fixture`: the built pages carry each brand's `DESIGN.md` beside them, which
is what lets the `design-system-*` rules catch a literal colour. On the source alone a raw hex passes.
The rendered scan is stricter still: any colour on the page at rest that is not in `DESIGN.md` fails,
`color-mix()` results included, so at-rest colours are roles and only shadows and the scrim are mixed.

`fixture/ledger/` (light, bottle green, Literata headings over Source Sans 3, 3px controls in 10px panels, 52px controls) and `fixture/signal/`
(dark only, amber, Jost headings over IBM Plex Sans, 8px controls in 16px panels, 44px controls) are the two brands; each has its
`DESIGN.md` from `palette.mjs` and `type-scale.mjs` and a `copy.json` for its words. `build.mjs` self-hosts
each face it names as latin woff2 from the pinned `@fontsource` packages in `package.json`, so the fixture
needs no network, and exits 1 when a face or weight has no package.
