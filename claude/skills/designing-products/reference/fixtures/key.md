# Fixture key: the answer sheet (never give it to the judge)

What each fixture plants and what a correct judge returns. `judge.md` §5 says how to run the calibration.
All pages are synthetic HTML written for this set, or our own screens; no other company's product.

## The bad set (mode 1): each must come back `fix` or `rebuild`

| Fixture | Plants | Must name at least |
|---|---|---|
| `bad/t1-t4` | Purple-blue-cyan gradient hero, gradient text on "next-gen AI", centred hero, three equal emoji cards with one shadow, a sparkle in the logo, filler copy (supercharge, unlock, seamless, harness the power, revolutionize) | T1 and T4 (T3, T7 also present) |
| `bad/t5-t8` | Cream #F4F1EA with a serif and terracotta #D97757, an eyebrow above every heading, one italic accented word, mono meta strings joined with middle dots, "CAPTURE — every interview" labels, an arrow on every link | T5 and T8 |
| `bad/t9-t11` | Staggered fade-and-slide entrance frozen mid-motion (later sections blurred and faint), a marquee, a pulsing dot, hover lift held on every card, bounce easing; "John Doe", lorem, "No data", "Recent activity" with nothing under it | T9 or T11 (both present) |
| `bad/t14-t15` | At 390: a tool row and a table running off the right edge, 12px body text, 11px buttons about 20px tall, two stage labels overlapping; three cards nested, a 4px orange side stripe, a kicker above the heading and the card, grey text on a blue banner | T14 and T15 |

## The trio (mode 2): Fable's stated pick must rank last

- **Fable's stated pick: `c`.** It is deliberately the weakest: near-black with violet and cyan glows, a
  glowing pill eyebrow, gradient text, a hero metric, glass cards with emoji, filler copy. It looks
  "premium" at a glance and is the template. A correct judge ranks it below the standard card.
- `a`: the bascule elevation as the one memorable thing, one signal-red accent on the time and the raised
  leaves, a serif display time, real vessel names. Expected first.
- `b`: a clean timetable with one blue accent; competent, little only this subject has. Expected second.
- `standard`: browser defaults, a heading and a table. Expected third.

The calibration run shuffles names so the order gives nothing away: `specimen-1` = c, `specimen-2` = a,
`specimen-3` = b, `standard` = standard (the weak pick first, to catch an order bias).

## The first rule (mode 1 on `refs/refinery-*` with Refinery's `refinery-design` skill)

The dark ground and the single green accent are named in Refinery's guide, so neither may appear as a tell
(T8 tinted near-black, T13 dark mode, Anthropic trait 2). Other findings on Refinery's live home are
allowed and are real (the accented headline phrase and the appended arrows are not in the guide).

## Refs

`refs/strata-*` are Strata's home captured 2026-11-01 at 1280x800 and 390x844, cropped from the top to
1280x633 and 390x757 (not re-rendered at those viewports, so the layout is the taller one's);
`refs/refinery-*` are refinery.guru captured live by `capture.sh` on 2026-11-02.

## Library refs in the packet (`library.md`)

Since T-1011 each calibration packet also carries the field's library refs, picked by `library.md`; the
judge gets them under their product names with their one-line why. The stand-in refs stay in as the intent
step's references. Every packet also carries the lead's taste set (`lead_taste`: Linear and Stripe;
Apple is not captured, its terms forbid it).

| Fixture | Field | Library refs |
|---|---|---|
| `bad/t1-t4` (an AI product's home) | `developer-tools` | linear, vercel, raycast, resend |
| `bad/t5-t8` (an interview-notes tool) | `consumer-apps` | bear, things, notion |
| `bad/t9-t11`, `bad/t14-t15` (dashboards, Operate) | `data-dashboards` | plausible, retool, posthog, mixpanel (the field has no Operate ref yet; all four are Persuade) |
| `trio` (Strata Lifts) | `maps-geo-3d` | citymapper, felt, cesium, openstreetmap |
| `refs/refinery-*` (the R1 test: no stand-ins) | `developer-tools` | linear, vercel, supabase, resend; must return R1 naming the ref it is measured against |

## Notes

- The VM has no colour-emoji font, so `bad/t1-t4` and trio `c` render their emoji as missing-glyph boxes;
  the judge still reads them as T3. Re-render on a machine with an emoji font if that ever matters.
- `impeccable detect` 4.8.0 (build-d3, T-1003): exits 2 on trio `a` and `c`, 0 on `b` and `standard`. So `a`
  still has a floor finding; the judge scored it 17/24 (mostly B8 at 390): the direction ranks first, the
  screen is not shippable as is.

## The tournament dry run

`tournament/` holds the T-1013 dry run of `../tournament.md` on this trio's brief: the 30 lines, the eight
specimens, the winner and runner-up at both sizes, and `log.md` with every score and timing. It is a
record, not a calibration fixture: nothing in it must fail.

## Calibration log

| Date | Rubric and judge at | Bad set | Trio | First rule |
|---|---|---|---|---|
| 2026-11-02 | first commit (T-1002); judges on Opus 5.5, fresh, shuffled names, no detector | pass: t9-t11 `rebuild` (T9, T11), t1-t4 `rebuild` (T1, T4), t14-t15 `fix` (T14, T15), t5-t8 `rebuild` (T5, T8) | pass: a 1st (R1+R2 3, bar 17), b 2nd (bar 14), standard 3rd (bar 9), c last (bar 5, ten tells incl. a T15 ban) | pass: dark ground and green listed as chosen, not tells; `fix` on the BACKED BY chip (T15), appended arrows (T8), 42px phone buttons (T14) |
| 2026-11-02 | T-1011: library refs in every packet (judge.md R1 names its ref); judges on Opus 5.5, fresh, new bad shuffle (screen-1 t5-t8, 2 t14-t15, 3 t1-t4, 4 t9-t11), no detector | pass: t5-t8 `rebuild` (T5, T8; R1 0 vs Bear), t14-t15 `rebuild` (T14, T15; R1 0 vs Plausible), t1-t4 `rebuild` (T1, T4, also T3, T7; R1 0 vs Linear), t9-t11 `rebuild` (T9, T11; R1 0 vs Plausible) | pass: a 1st (R1+R2 3, bar 18), b 2nd (bar 13), standard 3rd (bar 8), c last (bar 4, ten tells incl. a T15 ban); R1 named Felt, Citymapper and OpenStreetMap | pass: dark ground and green listed as chosen, not tells; `fix`; R1 1 against Linear ("Linear's product frame enters in the page's own dark material; Refinery's enters as a #FFFFFF slab"), R2 2 (the flagged COBOL change record); T15 BACKED BY chip, T8 appended arrow, T14 42px phone buttons |
| 2026-11-02 | T-1011: the lead's taste set (Linear, Stripe) added to every packet; fresh Opus 5.5 judges, same shuffle, no detector | pass: t5-t8 `rebuild` (T5, T8; R1 0 vs Bear), t14-t15 `rebuild` (T14, T15; R1 0 vs Plausible), t1-t4 `rebuild` (T1, T4; R1 0 vs Linear), t9-t11 `rebuild` (T9, T11; R1 0 vs Plausible) | pass: a 1st (R1+R2 3, bar 18), b 2nd (bar 16), standard 3rd (bar 10), c last (bar 6, nine tells; R1 0 "beside Linear and Stripe") | pass: dark ground and green listed as chosen; `fix`; R1 1 against Linear (four emphasis devices where Linear has one), R2 1; T15, T8, T14 |
| 2026-11-02 | T-1013: judge.md mode 2 split into the tournament's three cuts (the final brief unchanged but for "opening every ref" and a verdict file); rubric.md §8 tie rule to tournament.md; judge on Opus 5.5, fresh, no detector, no craft-floor.md on the VM (rubric §6 in its place) | not re-run: mode 1 and its brief unchanged | pass: a 1st (R1+R2 3, bar 18), b 2nd (bar 15), standard 3rd (bar 6), c last (bar 5, eleven tells); R1 named Felt and OpenStreetMap | not re-run: mode 1 |
| 2026-11-02 | T-1013 follow-up: `evidence.mjs` in every packet, B9 and B12 scored on its PASS lines, B11 on four screens; fresh Opus 5.5 judges, shuffle screen-1 t9-t11, 2 t1-t4, 3 t14-t15, 4 t5-t8, each with its evidence file and focus captures | pass: t9-t11 `rebuild` (T9, T11; bar 5, B9 0 on FAIL focus, reduced-motion and contrast), t1-t4 `rebuild` (T1, T4, also T3, T5, T6; bar 6), t14-t15 `rebuild` (T14, T15; bar 6), t5-t8 `rebuild` (T5, T8; bar 7) | not re-run alone: `a` was the control in the follow-up's final packet, 16/24 (`tournament/log.md`) | not re-run: mode 1 brief unchanged but for the evidence step |
| 2026-11-02 | T-1013 follow-up 2: rubric.md `fix` below a 22 bar and five changes; judge.md §6 the finish loop; fresh Opus 5.5 judges on the same shuffle and evidence files, no detector | pass: t9-t11 `rebuild` (T9, T11; bar 5), t1-t4 `rebuild` (T1, T4, also T3, T5 to T8; bar 7), t14-t15 `rebuild` (T14, T15; bar 5), t5-t8 `rebuild` (T5, T8; bar 7); through `finish-loop.py` each prints `next: fix`, and a `ship` verdict on the same captures is refused | not re-run: mode 2 unchanged | not re-run: mode 1's brief changed only in its return format |
