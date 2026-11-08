# mode1.py PACKET_DIR REFS_MD GUIDE_LINE PRODUCT OUT_VERDICT [PRODUCT_MD] : print the judge.md §3 brief, filled
import sys
from pathlib import Path
p, refs, guide, product, out = sys.argv[1:6]
pm = sys.argv[6] if len(sys.argv) > 6 else None
pline = f'PRODUCT.md: {pm} (the surface brief, holding product, audience, job and action)' if pm else 'PRODUCT.md: missing'
pers = 'Persistence: PRODUCT.md is the surface brief named above; the eval has no state.json or seed roll (the direction came from the blind tournament, recorded in the contract).' if pm else 'Persistence: PRODUCT.md is missing.'
I = str(Path.home() / '.local/share/impeccable/skill-v4.8.0')
D = str(Path.home() / '.claude/skills/designing-products')
four = Path(p, 'desktop-s2.png').exists()
det = Path(p, 'detector.txt').read_text().strip() if Path(p, 'detector.txt').exists() else 'detector: not run'
print(f"""You are the finish check for {product}, run fresh: you have not seen the build.
Read, in this order, and nothing else:
  1. The captures in {p}/: desktop.png (1280x633), mobile.png (390x757){', and screens 2 to 4 as desktop-s2.png to desktop-s4.png and mobile-s2.png to mobile-s4.png (a detail, a state, the action result)' if four else ''}. Look at them before any text, and inventory what the first screen shows in your own words. Then {p}/evidence.md and the focus captures {p}/focus-desktop.png and focus-mobile.png (where present): measured on this revision, not opinions; B8's text size, B9 and B12 are scored from them (rubric.md §6).
  2. The references, the library refs (best of the field) and the lead's taste set, listed one per line in {refs}; open every one at both sizes.
  3. Accepted findings: none (no ignore.md). {pline}. The guide: {guide}.
  4. {I}/.claude/agents/impeccable-finish-reviewer.md, {I}/skill/reference/craft-floor.md, the "Design Specificity Verdict" and "Design Health Score" parts of {I}/skill/reference/critique.md, and {D}/reference/rubric.md.
  5. The copy- principles listed under "Copy and voice" in {D}/principles/index.md: read every visible word against them; each failing line is a T7 tell, quoted.
{det[0].upper() + det[1:]}.
Act as impeccable-finish-reviewer: checks 0 to 6 in order, on these captures. This is a code-led build with no approved comp: judge fidelity, TYPE, MATERIAL and GROUND against the direction contract and the guide. {pers} Then critique's specificity verdict and design health score from the captures alone (no detector run of your own, no browser).
Apply rubric.md §1 first: list the traits the guide names; they are never tells.
Return exactly: the disposition line, written `disposition: <ship|fix|rebuild|recapture>` (rubric.md §7 decides the word); Impeccable's five sections; then the "## Rubric verdict" block from rubric.md §7, its bar as table rows written `| B1 | <0-2> | <reason> |` through B12 and the total /24. R1 names the ref it is measured against and the one difference that decides it. No praise, no summary prose.
Write the whole verdict to {out}, then reply `written`.""")
