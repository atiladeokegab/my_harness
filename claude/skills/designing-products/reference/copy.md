# Copy and voice: the Voice section and the copy gate

Rubric tell T7 names filler copy; this file is how a product avoids it. The words are designed at step 4
with the tokens, enforced in the smoke beside the detector, and judged in the finish check with the
`copy-` principles.

## The Voice section of `DESIGN.md`

`DESIGN.md` carries `## Voice` after its do's and don'ts, written at step 4 by the step-4 sub-agent from
`PRODUCT.md` and the UX step's vocabulary, and kept by `document`. It holds:

- one line: who reads this product, and the product's few nouns for its own things (the vocabulary);
- three pairs, each a `- Do:` line and a `- Don't:` line saying the same thing, from the product's own
  subject: one about what the product does, one about a result or number, one about an error or empty state.

A Don't is a line a builder would really write (from a draft or `copy-banned.txt`); its Do uses the
product's nouns, a verb that says what happens, and a number only with its source. Pairs about any
product ("be clear, not vague") fail: a builder cannot copy from them. Refinery's, from its subject:

```markdown
## Voice
Read by mainframe engineers and their auditors. Nouns: program, change, check, certificate, sign-off.
- Do: Refinery compares the original program with the AI's change and runs 11 checks on the difference.
- Don't: Refinery unlocks seamless, AI-powered governance for your mainframe.
- Do: Check 6 failed: the changed PAYROLL program rounds line 212 differently. Re-run after the fix.
- Don't: Oops! Something went wrong with your audit. Please try again.
- Do: A named reviewer signs the certificate; the PDF records who and when.
- Don't: Empower your teams with robust, best-in-class oversight.
```

## The gate: `check-copy.mjs`

`node scripts/check-copy.mjs web/src/` scans `.html`, `.jsx`, `.tsx` and `.mdx` text (not code, CSS or
comments) for `copy-banned.txt` phrases and for a percentage or multiplier with no source marker (`source`,
`<cite>`, `<sup>`, `data-source`, `illustrative`) within a line. Exit `0` clean, `2` with `file:line`
and the reason, `1` when it has no list or no file. Copy `reference/copy-banned.txt` beside the script;
a product appends its own lines, each `phrase | reason`. A real use (a vault that unlocks) takes
`copy-ok: <reason>` in a comment on that line or the line above, as the detector's ignores carry a reason.

It does not judge runs of adjectives, one idea per line, labels or headings: the finish check does, with
the `copy-` principles. Copy kept in `.ts` data files is not scanned; only the first stat per line is.

A number inside a `<table>`, `<data>`, `<meter>` or `<output>`, or an element with `data-value`, is data,
not a claim, and is not counted; a dashboard built from plain `<div>`s should use one of those.

Fixtures (`tokens/fixtures/copy/`): `good.html` exits `0`; `bad.html` exits `2` on 12 findings. Refinery's
`website/` (commit 9b687f1, a `git archive` copy, 42 files): exit `2`, 7 findings: one "leverage" (about
page) and six unsourced stats ("99%" in a use case; five in `public/preview-dashboard.html`'s sample data,
plain `<div>`s, which want `data-value` or an "illustrative" label). No hype word from the list.
