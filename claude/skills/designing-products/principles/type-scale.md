# One type scale: ratio, sizes, line height, measure, tracking

Source: written from first principles for this skill, on public material: the modular scale idea (Tim
Brown, "More Meaningful Typography", A List Apart, 2011); WCAG 2.2 (W3C, 2023) SC 1.4.8 Visual
Presentation (lines under 80 characters, line spacing 1.5 in paragraphs) and 1.4.12 Text Spacing.
Every threshold is ours.

**Principle.** Every size on a screen is a step of one scale (base times ratio to a power); line height
tightens and tracking closes as size grows; running text holds a readable measure.

## Why it holds

- A ratio makes sizes related, so hierarchy reads at a glance; sizes picked one by one drift into
  near-duplicates (15, 16, 17px) that look like mistakes. `type-scale.mjs` writes the steps as tokens.
- The ratio sets the mood: 1.125 to 1.2 is quiet and dense (tools, dashboards); 1.25 to 1.333 is
  balanced; 1.5 and over is editorial and leaves the small end too small. At most six sizes (rubric B1).
- Body text wants line height about 1.5 (WCAG 1.4.8); large headings need less, about 1.1 to 1.2, or
  their lines drift apart. Under 1.3 on body-size text the detector flags `tight-leading`.
- Large text looks loose because letter spacing is drawn for reading sizes: close it slightly (about
  -0.01 to -0.02em) at heading sizes; open it slightly on small captions.
- A line of 45 to 75 characters is comfortable; over 80 the eye loses the next line (WCAG 1.4.8).

## What to check

- Every text size on the capture is one of DESIGN.md's typography sizes (the detector's
  `design-system-font-size` does this mechanically on the rendered page).
- Paragraphs of running text: count the characters in one full line.
- Headings at 390 wide wrap to three lines or fewer.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.

- **PASS:** six sizes or fewer, all on the scale; body 16px or more (14px floor for dense tools);
  running text 45 to 75 characters a line at 1280; paragraph line height about 1.5; the main
  heading fits in three lines at 390.
- **FAIL:** a size off the scale, two sizes within 2px of each other, running text over 80 characters a
  line, cramped multi-line body text, or a heading that breaks into four lines or more at 390.

Observable: the sizes seen, characters in one full line, the heading's line count at 390.

## Used at

**Look** (step 4: `type-scale.mjs --base --ratio`), **build** and **critique**.
