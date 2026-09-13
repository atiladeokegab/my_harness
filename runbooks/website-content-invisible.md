# Website sections render blank (opacity 0) — reveal animations that never fire

**Symptom.** A page on `website/` lays out correctly — the space is reserved, the
footer sits at the right height, the text is in the DOM — but a whole section
paints nothing. Most visible on `/pricing` and `/use-cases`. In a headless
screenshot it looks like a huge empty gap between the hero and the footer.

**Why it happens.** The reveal animations start hidden and depend on JS to
un-hide them:

- `.fade-up` (`components/FadeUp.tsx`)
- `.industry-card` (`app/use-cases/page.tsx`)
- `.repo-line` (`app/about/page.tsx`)

`FadeUp` and the use-cases cards originally relied *solely* on
`IntersectionObserver`. An observer is not guaranteed to deliver a callback for
an element that is already inside the viewport when it starts observing, so any
section sitting in the initial view could stay at `opacity: 0` forever. Add a
new page whose first section is above the fold and it renders blank.

**How to confirm.** Dump the DOM and compare the count of elements that carry the
reveal class against the count that also carry `in`:

    chrome --headless=new --dump-dom http://localhost:3100/pricing > d.html
    grep -o 'class="fade-up' d.html | wc -l     # total
    grep -oE 'fade-up[^"]*\bin\b' d.html | wc -l # revealed

Content present in the DOM with zero `in` is this bug. Check the browser console
too: no JS error means hydration is fine and the observer simply never fired,
which is the tell.

**The fix (already applied, commit `b54db61`).** Two halves, keep both:

1. Reveal directly at mount anything already on screen, and only observe what is
   genuinely below the fold:

       if (el.getBoundingClientRect().top < window.innerHeight) { reveal(); return }

2. Fail open in CSS. The hidden start state applies only under `html.js`, which
   an inline script in `app/layout.tsx` sets before paint:

       .fade-up         { opacity: 1; transform: none; }
       html.js .fade-up { opacity: 0; transform: translateY(18px); }

   So if hydration ever fails, the page degrades to plain visible content
   instead of a blank screen.

**If you add a new reveal animation, do both.** A start state of `opacity: 0`
that only JS can undo is a blank-page outage waiting to happen.

**Unrelated trap hit while debugging this.** `next start` keeps serving a stale
prerendered HTML that references a CSS chunk from an earlier build, so the whole
page loads unstyled and `/_next/static/chunks/*.css` returns 500. That is not a
CSS bug — kill the server, `rm -rf .next`, rebuild, restart.
