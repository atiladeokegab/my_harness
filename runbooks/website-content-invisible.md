# Website sections render blank (opacity 0): reveal animations that never fire

**Repo:** any site with scroll-reveal animations.

## Symptom

A page lays out correctly (the space is reserved, the footer sits at the right height, the
text is in the DOM) but a whole section paints nothing. In a headless screenshot it looks
like a huge empty gap between the hero and the footer. It shows up most on pages whose first
animated section is already in view on load.

## Confirm it

Dump the DOM and compare the count of elements that carry the reveal class against the
count that also carry the "revealed" class (here `fade-up` and `in`):

```bash
chrome --headless=new --dump-dom http://localhost:3000/<page> > d.html
grep -o 'class="fade-up' d.html | wc -l       # total
grep -oE 'fade-up[^"]*\bin\b' d.html | wc -l  # revealed
```

Content present in the DOM with zero revealed is this bug. Check the browser console too: no
JS error means hydration is fine and the observer simply never fired, which is the tell.

## Cause

The reveal starts hidden and relies only on `IntersectionObserver` to un-hide it. An observer
is not guaranteed to deliver a callback for an element that is already inside the viewport
when it starts observing, so a section in the initial view can stay at `opacity: 0` forever.
Add a page whose first section is above the fold and it renders blank.

## Fix

Two halves; keep both.

1. Reveal anything already on screen directly at mount, and observe only what is genuinely
   below the fold:

   ```js
   if (el.getBoundingClientRect().top < window.innerHeight) { reveal(); return }
   ```

2. Fail open in CSS. The hidden start state applies only under `html.js`, which an inline
   script in the root layout sets before paint:

   ```css
   .fade-up         { opacity: 1; transform: none; }
   html.js .fade-up { opacity: 0; transform: translateY(18px); }
   ```

   If hydration ever fails, the page degrades to plain visible content instead of a blank
   screen.

**Every new reveal animation needs both.** A start state of `opacity: 0` that only JS can
undo is a blank-page outage waiting to happen.

## Traps while fixing it

`next start` can keep serving stale prerendered HTML that references a CSS chunk from an
earlier build, so the whole page loads unstyled and the chunk returns 500. That is not a CSS
bug: see `nextjs-page-couldnt-load-stale-chunks.md`.
