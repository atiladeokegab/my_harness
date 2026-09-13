# A component class silently beating a Tailwind utility

**Symptom.** A utility on an element does nothing. `hidden sm:inline-flex` leaves the
element visible; a `text-*` class does not change the colour. The markup looks right and
the rule is present in the built CSS.

**Cause.** Unlayered CSS beats **every** `@layer`, regardless of specificity. Tailwind v4
puts its utilities in a layer. So a custom class written outside any layer wins over
`hidden` purely by being unlayered, and at equal specificity source order decides the rest.

**Confirm it** by byte offset in the built stylesheet:

```bash
CSS=$(find .next/static -name "*.css" | head -1)
grep -bo '\.hidden{display:none' "$CSS"
grep -bo '\.btn-primary{' "$CSS"
```

Later wins at equal specificity — but a layered rule loses to an unlayered one whatever the
order.

**Fix.** Put every rule in the right layer: `base < components < utilities`.

- element defaults (`html`, `body`, `a`) → `@layer base`
- component classes (`.btn-*`, `.card`, heading utilities) → `@layer components`
- Tailwind's own utilities are already in `utilities` and will then win, which is what you
  want: a utility on an element should override the component class.

**Both halves of this bit Refinery in one session.** First an unlayered `.btn-primary`
overrode `hidden`, so the nav CTA rendered on phones next to the hamburger. Then moving it
into `@layer components` dropped it below an unlayered `a { color: inherit }` in the same
file, and every green button on the site rendered ink text on green: **1.79:1**, failing
WCAG for body text, large text and graphical objects alike, live for about an hour.

**Note.** Neither was visible by reading the CSS — both rules looked correct in isolation,
and the two rules involved were in different parts of the file. What found it was asking
the browser for `getComputedStyle` on every element with a green background.
