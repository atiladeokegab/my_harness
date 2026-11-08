# Depth comes from one light source and a shadow scale

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Creating Depth": all five sections, from
"Emulate a light source" to "Overlap elements to create layers", pp. 172-196. Paraphrased in our words;
anything quoted is marked and at most one sentence.

**Principle.** Light comes from above: raised things are lit on top and cast a shadow below, inset
things the reverse; shadow size says how high an element sits, chosen from about five levels.

## Why it holds

- Raised (pp. 175-177): a slightly lighter top edge, a hand-picked colour rather than translucent white,
  and a small, sharp dark shadow offset downward. Inset (pp. 177-178): a lighter bottom lip and a small
  dark inner shadow at the top, as on inputs and checkboxes. Hint at reality; never go photo-real.
- Small, tight shadows sit just above the page (buttons); medium ones float (dropdowns); large, soft
  ones demand attention (modals). Choose by elevation, from a fixed set of about five (pp. 180-183).
- Shadows can respond: lift an item being dragged, shrink a button's shadow as it is pressed (p. 184).
- Two-part shadows: a large soft one for direct light plus a tight dark one underneath, which fades as
  elevation rises (pp. 186-189).
- Flat designs still show depth: lighter reads closer, darker further; a solid shadow with no blur
  lifts a card; overlapping a card across two backgrounds makes layers (pp. 190-196).

## What to check on a screen

- Every shadow falls the same way, downward.
- Higher things (menus, modals, toasts) have bigger shadows than lower things (cards, buttons).
- No glow shadows or centred halos unless the guide names them.

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.
1. List every element with a shadow, with its direction and size.
2. Rank them by elevation (a modal above a menu above a card above the page).

- **PASS:** all shadows offset downward, larger shadows only on higher elements, and at most three
  sizes on one screen (the three is our threshold).
- **FAIL:** a centred or upward shadow, a glow halo, a card with a bigger shadow than the menu over it,
  or every element carrying the same heavy shadow.

Observable: the shadow list with direction and size.

## Used at

**Look** (the shadow scale in the tokens) and **critique**.
