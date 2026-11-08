# Style the defaults, do not add decoration

Source: Adam Wathan and Steve Schoger, *Refactoring UI*, ch. "Finishing Touches": "Supercharge the
defaults", pp. 220-222. Paraphrased in our words; anything quoted is marked and at most one sentence.

**Principle.** Polish comes from upgrading the elements already on the screen (bullets, quotes, links,
checkboxes, radio buttons, form fields), not from adding new ornaments.

## Why it holds

- A bulleted list can use icons that say something (ticks for features, a padlock for security items).
- A testimonial's quotation marks can become a large, coloured shape that is part of the design.
- Links can carry a thick, colourful underline that sits partly behind the text.
- Restyled links and controls must still look clickable: Krug's `obvious-clickables` comes first.
- Browser-default checkboxes, radio buttons and selects look like nobody touched them; recolouring them
  in the brand colour is one of the cheapest upgrades in the book.
- This is the safe part of the chapter. Its other cheap tricks (accent borders, gradient and patterned
  backgrounds, pp. 224-232) now read as generated-UI defaults; the rubric and the guide decide them.

## What to check on a screen

- Native form controls: browser defaults or styled to the guide?
- Lists: plain dots where a meaningful icon would say more?
- Links: styled on purpose, or the default blue underline?

## Pass or fail test

Apply to each capture on its own: desktop 1280x633 and phone 390x757.

- **PASS:** every visible checkbox, radio, select, range and file input uses the guide's colour and
  radius; links follow the guide's style; no ornament appears that is not an upgraded default or named in
  the guide.
- **FAIL:** a browser-default control (system blue tick, grey native select), default blue links, or
  decoration added for its own sake (stripes, blobs, glows the guide does not name).

Observable: each control or link checked, default or styled.

## Used at

**Look** (control styles in the tokens) and **critique**.
