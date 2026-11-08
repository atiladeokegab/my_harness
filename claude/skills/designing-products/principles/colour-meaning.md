# The palette comes from the product, not from fashion

Source: written from first principles for this skill, on public standards: WCAG 2.2 (W3C, 2023) SC 1.4.1
Use of Color; ISO 3864-1 safety colours (red stop or danger, yellow caution, green safe); the CSS Color 4
`oklch()` space. No book is paraphrased. Every threshold is ours.

**Principle.** The seed colour is chosen from the product's subject, its audience and the one feeling,
and it carries one meaning everywhere; states keep the meanings people already know.

## Why it holds

- A colour is read before a word. If the seed has no reason in the product, the screen says "template".
  The indigo-to-violet default (OKLCH hue about 260 to 300) is the most common AI-made accent for
  exactly that reason: it is what is left when nobody decided.
- The subject's world already has colours with meaning: a river, a ledger's green tick, a warning
  stripe. Taking one keeps the product's look honest about what it is (`steal-the-thinking`).
- Red, amber and green mean stop, caution and go by convention (ISO 3864, traffic lights). A brand that
  reuses one of those hues for decoration teaches the user to ignore the warning.
- Meaning by colour alone fails people with a colour vision deficiency; WCAG 1.4.1 asks for a second cue.

## What to check

- The planning file's §Brand names the seed hex with one line saying where it came from: a thing from
  the subject's world (one of the seven things in step 3) or the one feeling.
- Each colour has one meaning on every screen; the accent never also marks an error.
- `palette.mjs` printed no note, or the note's state carries an icon and a word on every screen.

## Pass or fail test

Apply to the planning file's §Brand and DESIGN.md's `colors`, then to each capture (1280x633, 390x757).

- **PASS:** the seed's reason names the subject or the feeling; on each capture every state colour
  sits beside an icon or a word; no state hue is used as decoration.
- **FAIL:** the reason is "modern", "clean", "bold", "trust" or a competitor's colour; the seed is in the
  violet band with no subject reason; a state is shown by colour alone; red or green decorates.

Observable: the seed's reason line, and each state colour on the capture with its icon or word.

## Used at

**Intent** (the one feeling picks the seed's family) and **look** (step 3: each direction card names
its seed and the reason). `palette.mjs` turns the seed into the palette.
