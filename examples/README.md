# Examples

## `refinery-design/` — a real, filled-in design skill

The design system for [Refinery](https://refinery.guru), an AI change-attestation platform,
exactly as it lives in that repo at `.claude/skills/refinery-design/`. It is the worked
example behind the generic `design-system` skill: it shows what the finished artefact looks
like after reconciling three sources that disagreed — a Figma file that was only partly
migrated, macOS screenshots whose colours were shifted by Display P3, and a type specimen.

Things worth copying from it:

- **§0, "Which source wins"** — decided before a single number is trusted.
- The contrast table, including the bright accent that *fails* on light grounds and the
  second `green-ink` token it forced.
- Measured values kept separate from derived ones, with the derived ones flagged as
  unsigned-off.
- **§12, "Still undefined"** — an explicit list of what nobody has decided, so no agent
  invents it.
- Exported mark assets in `references/svg/`, with a rule never to redraw them.

It is **not installed** by `install.sh` — it describes one brand. To start your own, copy
the structure, not the values:

```bash
mkdir -p <your-repo>/.claude/skills/<project>-design/references
# then ask Claude: "load the design-system skill and help me write <project>-design"
```

The screenshots and mark SVGs are Refinery's brand assets, included for reference. Please
don't reuse the Refinery wordmark or brand in your own product.
