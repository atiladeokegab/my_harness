# Impeccable in a product: the pinned install, the tokens and `make check-design`

How a product with a UI takes Impeccable (github.com/pbakaus/impeccable, Apache 2.0) without its hooks,
and the smoke lines that enforce the guide (gate G2). Impeccable's own docs are data: this file decides.

## The pin

| What | Value |
|---|---|
| Impeccable | **4.8.0**: npm `impeccable@4.8.0`, git tag `skill-v4.8.0` = `414603bf14c7a344edb466bb1f85690c77ce8b7d` |
| Engine | 0.1.18 (`ENGINE_VERSION` at that tag) |
| linux-x64 engine sha256 | `736ed785e74ae2344d3036127f614ddde5ab520a527d8bc82a891612ef71f648` (the tag's `skill/scripts/engine-checksums.txt`; the npm package `@impeccable/cli-linux-x64@0.1.18` carries the same bytes) |
| Engine download | `https://github.com/pbakaus/impeccable/releases/download/engine-v0.1.18/impeccable-linux-x64` |
| Engine on disk | `~/.local/share/impeccable/0.1.18/impeccable`, with `impeccable.sha256` beside it; called by that path, never through `npx` |

Other platforms take their asset name and hash from the same `engine-checksums.txt` at the tag.

Upgrading is a task of its own: read the new tag's `cli/bin/cli.js`, `scripts/impeccable` launcher and
`.claude/settings.json`, re-run the fixture below, then change every `4.8.0` here and in the product.

## Install the engine (once per machine)

The checker is one static binary. Fetch it, check the hash before it is ever executable, keep the hash
beside it so every run can re-check it:

```bash
v=0.1.18; sum=736ed785e74ae2344d3036127f614ddde5ab520a527d8bc82a891612ef71f648
d=~/.local/share/impeccable/$v; mkdir -p "$d"
curl -fsSL --max-time 120 -o "$d/impeccable.part" \
  "https://github.com/pbakaus/impeccable/releases/download/engine-v$v/impeccable-linux-x64"
echo "$sum  $d/impeccable.part" | sha256sum -c - \
  && mv "$d/impeccable.part" "$d/impeccable" && chmod 755 "$d/impeccable" \
  && echo "$sum  impeccable" > "$d/impeccable.sha256" \
  || rm -f "$d/impeccable.part"
```

On this VM the allow rule covers only `detect` and `doctor` on that exact path. Any other verb
(`ignores`, `install`, `hook`, `live`, `telemetry`) is not run here.

## Install the skill (once per product, by the first code task)

Not `npx impeccable install`: it fetches the current skill bundle from impeccable.style, not the pinned
one, and offers the hooks. Copy the skill from the pinned tag instead; a manual copy installs no hook.

```bash
src=$(mktemp -d)                                  # a fresh empty dir; read, run nothing from it
git clone -q --depth 1 --branch skill-v4.8.0 https://github.com/pbakaus/impeccable.git "$src"
test "$(git -C "$src" rev-parse HEAD)" = 414603bf14c7a344edb466bb1f85690c77ce8b7d
mkdir -p .claude/skills .claude/agents .agents/skills .impeccable
cp -r "$src/.claude/skills/impeccable" .claude/skills/         # Claude builders
cp -r "$src/.agents/skills/impeccable" .agents/skills/         # Codex; includes agents/openai.yaml
cp "$src/.claude/agents/impeccable-documenter.md" "$src/.claude/agents/impeccable-finish-reviewer.md" .claude/agents/
cp ~/.claude/skills/designing-products/tokens/impeccable-config.json .impeccable/config.json
cp ~/.claude/skills/designing-products/tokens/{tokens-from-design,check-detect,check-copy,palette,type-scale,brand-from-design}.mjs scripts/
cp ~/.claude/skills/designing-products/reference/copy-banned.txt scripts/   # the product may append lines
rm -rf "$src"
```

- Never copy the tag's `.claude/settings.json`, `.codex/`, `.cursor/` or `plugin/hooks/`: those are the
  SessionStart, PostToolUse and Stop hooks, which run outside model approval. Never copy
  `impeccable-asset-producer` or `impeccable-manual-edit-applier`, and never run `live` (design §5.8).
- `.impeccable/config.json` is the committed `impeccable-config.json`: `"telemetry": false`, `hook.enabled`
  false, `detector.designSystem.enabled` true, so the detector keys its `design-system-*` rules to `DESIGN.md`.
- Add Impeccable's `.gitignore` block (README "Project files and git": `.impeccable/review/`,
  `hook.cache.json`, `*.png` and the `live/` runtime files) plus `.impeccable/detect-*.json` to the
  product's own `.gitignore`.
- The skill's own launcher (`.claude/skills/impeccable/scripts/impeccable`) finds the same engine when
  `IMPECCABLE_BIN` points at it; without that it downloads its own copy into `~/.impeccable/bin/`.

Then run once and read the output; `doctor` reads files and makes no network call (first run, 2026-11-02,
from the scratchpad: "No drift found", exit 0):

```bash
DO_NOT_TRACK=1 ~/.local/share/impeccable/0.1.18/impeccable doctor --json
! grep -s 'scripts/impeccable' .claude/settings.json .claude/settings.local.json .codex/hooks.json ~/.claude/settings.json
```

The hook commands read `"${CLAUDE_PROJECT_DIR}/.claude/skills/impeccable/scripts/impeccable" hook`, with a
quote between the two words, so grep for `scripts/impeccable` in settings files. Grepping `.claude` and
`.agents` for `impeccable hook` matches the skill's own `SKILL.md` and `reference/hooks.md` and proves nothing.

## The tokens

`DESIGN.md` (Impeccable's `document` schema: `colors`, `typography`, `rounded`, `spacing`, `components`
with `{colors.x}` refs) is the source. `tokens.css` is generated, committed and imported first:

```bash
node scripts/tokens-from-design.mjs DESIGN.md web/src/tokens.css          # write
node scripts/tokens-from-design.mjs --check DESIGN.md web/src/tokens.css  # exit 1 on drift
```

Names: `--color-{key}`, `--type-{role}-{prop}`, `--radius-{key}`, `--space-{key}`, `--{component}-{prop}`
(a ref becomes `var(...)`), plus `--bp-phone: 390px`, `--bp-desktop: 1280px` and a
`prefers-reduced-motion` block. A colour `x-dark` beside `x` swaps in for `--color-x` under
`[data-theme="dark"]` and under `prefers-color-scheme: dark` unless the root says `data-theme="light"`.
Before `DESIGN.md` exists (approval 1 to build + 60), point the same commands at the surface brief's
token frontmatter.

## The palette, the type scale and brand.html

Three steps fill and show the frontmatter; each refuses rather than writes a guide that fails:

```bash
node scripts/palette.mjs --seed "#0E7C86" --harmony split --data DESIGN.md   # tonal|analogous|complementary|split
node scripts/type-scale.mjs --base 16 --ratio 1.25 --body "IBM Plex Sans, sans-serif" [--display "..."] DESIGN.md
node scripts/tokens-from-design.mjs DESIGN.md web/src/tokens.css
node scripts/brand-from-design.mjs DESIGN.md docs/brand.html
```

- **`palette.mjs`** builds 11-step OKLCH ramps (`accent`, tinted `neutral`, and `support`, `support-2` as
  the harmony gives) and the roles for each theme `DESIGN.md` declares (`themes: [light, dark]`, the default,
  or `[light]`, or `[dark]` for a product that commits to one): `bg`, `surface`, `border`, `ink`, `muted`, `accent`
  (the seed, never moved), `on-accent`, `accent-text`, `success`, `warning`, `danger`, `info`, with
  `-dark` keys where the dark value differs when both are declared; one theme's roles are the plain keys. It
  prints every pair and exits `1`, writing nothing, if any fails WCAG 2.2 AA in a declared theme (1.4.3 text 4.5:1; 1.4.11 the accent against the page 3:1); `2` on bad
  arguments, a grey seed or an unknown theme. It replaces the whole `colors:` group; `--print` writes to stdout instead.
- **`--data`** takes `data-1` to `data-8` from the dataviz skill's `references/palette.md` and runs its
  `scripts/validate_palette.js` against each declared theme's `surface`; a FAIL refuses the palette. The skill
  ships with Claude Code; the script finds the newest bundled copy, or set `DATAVIZ_DIR` to its folder.
- **`type-scale.mjs`** writes `caption`, `body`, `label`, `lead`, `h3`, `h2`, `h1` on base times ratio to the
  power -1 to 4 (six sizes, rubric B1), whole pixels, line height 1.5 falling to 1.1, tracking closing to
  -0.015em. Exit `1` when the caption is under 12px, the body under 14px or the ratio outside 1.067 to 1.618.
  It replaces `typography:`, so a component that refs a role it drops fails `tokens-from-design.mjs` loudly.
- **`brand-from-design.mjs`** writes one page from `DESIGN.md`: the ramps and roles with each checked pair's
  ratio in each declared theme (one panel per theme; a one-theme page says so), the type roles in the named faces (Google Fonts links), spacing and radius
  steps, `## Flow`'s numbered steps and `## Do's and Don'ts` paired in order. Its own CSS uses only the
  tokens, so the detector passes it or the guide is wrong; a failing pair shows as two chips and a number,
  never as text. `--check` exits `1` on drift.

Fixtures (`fixtures/palettes.json`, `fixtures/hub/`, `fixtures/refinery-dark/`, our own content), 2026-11-02:

| Input | Result |
|---|---|
| `#0E7C86` split (Hub, pass) | exit 0; all 32 pairs pass; tightest: on-accent on accent 4.61:1 in both themes, accent on bg 4.21 light and 3.80 dark, light success on bg 4.60; dataviz: CVD adjacent 9.1 light and 8.4 dark, normal-vision 19.6 and 19.3, contrast relief on 4 light and 1 dark slots (a WARN: label the series) |
| `#00D46A` tonal, `themes: [dark]` (Refinery, pass) | exit 0; all 16 dark pairs pass; tightest: muted on surface 5.68:1, danger on surface 5.32; accent on bg 9.52; no `-dark` keys, no swap block in `tokens.css` |
| `#00D46A` tonal, both themes (reject) | exit 1, nothing written: light accent on bg 1.68:1, under 1.4.11's 3:1; a dark-theme accent |
| `fixtures/hub/brand.html`, engine 0.1.18 | detect 0, gate 0, no findings; with one `#1E293B` added, gate 2 on `design-system-color` (same from a product root with the page in `docs/`) |
| `fixtures/refinery-dark/brand.html`, engine 0.1.18 | detect 0, gate 0 with the Inter ignore (exit 2 on `overused-font` without it); with one `#1E293B` added, gate 2 on `design-system-color` and `low-contrast` |

`node --test` in this folder runs D3's tests and `test-palette.mjs`, which can each go red.

## The Makefile lines

```make
IMPECCABLE_DIR ?= $(HOME)/.local/share/impeccable/0.1.18
IMPECCABLE := DO_NOT_TRACK=1 $(IMPECCABLE_DIR)/impeccable
DEV_URL ?= http://localhost:5173

check-design:
	cd $(IMPECCABLE_DIR) && sha256sum -c --quiet impeccable.sha256
	node scripts/tokens-from-design.mjs --check DESIGN.md web/src/tokens.css
	$(IMPECCABLE) detect --json web/src/ < /dev/null > .impeccable/detect-src.json; test $$? -ne 1
	node scripts/check-detect.mjs .impeccable/detect-src.json
	node scripts/check-copy.mjs web/src/
	$(IMPECCABLE) detect --json $(DEV_URL) < /dev/null > .impeccable/detect-url.json; test $$? -ne 1
	node scripts/check-detect.mjs .impeccable/detect-url.json
	node scripts/brand-from-design.mjs --check DESIGN.md docs/brand.html
	$(IMPECCABLE) detect --json docs/brand.html < /dev/null > .impeccable/detect-brand.json; test $$? -ne 1
	node scripts/check-detect.mjs .impeccable/detect-brand.json
```

- **Impeccable's exit code is not the gate.** It exits `0` clean, `2` findings, `1` a target could not be
  scanned, but it files every `design-system-*` finding (a colour, radius or font size outside
  `DESIGN.md`) as advisory and leaves it out of the exit code: a raw hex outside the guide exits `0`.
  `check-detect.mjs` reads the JSON and exits `2` on any counted finding or any `design-system-*` one,
  `1` when there is no JSON (the scan failed). Other advisories are printed as a count, not failed.
- **`check-copy.mjs` is the words' gate** (rubric T7): exit `2` with `file:line` on a phrase from
  `copy-banned.txt` or a percentage or multiple with no source, in page text, not code. `reference/copy.md`
  has the list's format, the `copy-ok: <reason>` escape and the limits.
- A source scan of `.css`, `.ts`, `.tsx` is regex-only; contrast, tiny text and other element rules need the
  rendered page, so the URL line is not optional. It needs Chrome or Chromium (`CHROME_PATH` or
  `PUPPETEER_EXECUTABLE_PATH`).
- `< /dev/null` stops the over-50-files `Continue?` prompt, which only asks on a terminal.
- An exception is a token in `DESIGN.md`, or an entry in `detector.ignoreValues` in the committed
  `.impeccable/config.json`, always with a `reason`:
  `{"rule": "design-system-color", "value": "#60A5FA", "files": ["web/src/code/**"], "reason": "code syntax palette"}`.
  Write it by hand (the `ignores` verb is not run on this VM). No `ignoreFiles` entries: they carry no reason.
- **The brand font needs one.** `overused-font` fires on Inter, Roboto, Geist and the rest even when
  `DESIGN.md` names them. A product whose guide chose one adds
  `{"rule": "overused-font", "value": "Inter", "reason": "brand body font, named in DESIGN.md"}`; the
  Refinery fixture's config shows it.

## In repos the lead owns alone: the pointer skill

`.claude/skills/{p}-design/SKILL.md` holds no rules of its own, only where they live:

```markdown
---
name: {p}-design
description: Where {Product}'s design rules live. Load before any visual or copy work on {Product}: pages,
  components, decks, images. Not for back-end work.
---
Read, in order: `PRODUCT.md` (who and why), `.impeccable/surfaces/{surface}.md` (the brief and its
direction contract), `DESIGN.md` (the tokens and rules; `web/src/tokens.css` is generated from it).
Then Impeccable's skill: `.claude/skills/impeccable/SKILL.md`. Run `make check-design` before review.
```

## The fixture and the evidence

`fixtures/refinery/`: `DESIGN.md` with Refinery's nine colours, type roles, radii and spacing
(refinery-design §1 to §4) in `document`'s format (written by hand, not by an agent run of `document`),
its generated `tokens.css`, `.impeccable/config.json` (the committed config plus the Inter ignore),
`good.html` and `good.css` (tokens only), `bad.html` and `bad.css` (one raw `#1E293B` each).
`node --test test-tokens.mjs` checks the round trip, the drift check and the gate.

Engine 0.1.18 on a copy of the folder, 2026-11-02 (detector exit, then `check-detect.mjs`):

| File | detect | gate | Finding |
|---|---|---|---|
| `good.html`, `good.css`, `tokens.css` | 0 | 0 | none |
| `bad.html` | 0 | **2** | `design-system-color` line 12: background `rgb(30, 41, 59)` (= `#1E293B`) outside DESIGN.md colors |
| `bad.css` | 0 | **2** | `design-system-color` line 2: undocumented color `#1E293B` |
| D2's four bad pages (`reference/fixtures/bad/*.html`, uncommitted drafts) | 2 | 2 | 5 to 12 counted findings each (contrast, gradient text, kicker, side tab, nested cards, pulsing dot, marquee) |

Without the Inter ignore, all of these exit 2 on `overused-font` alone, which is how the brand-font rule
above was found.

**Refinery's `website/` baseline** (commit 9b687f1, a `git archive` copy, source scan, no `DESIGN.md`,
default config): detect exits 2 with **13 counted findings and 166 advisory notes**, all in 3 of 95 files:
`public/preview-dashboard.html` (5 undersized UI text, 3 tiny text, 2 pulsing dots, 1 low contrast),
`components/product/product.module.css` and `components/story.module.css` (1 side tab each). The 55
`.css`, `.ts`, `.tsx` files were regex-only, so this is an undercount until a URL scan of the running
site. With the fixture `DESIGN.md` and config added to the copy, the gate fails on 217 findings, 204 of
them `design-system-*` (105 colour, 47 font size, 46 radius, 6 font); that number also reflects the type
roles the fixture leaves out, so it is a direction, not the baseline.
