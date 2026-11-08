# The library: the best real first screens, by field

R1 asks whether a screen would sit beside the best products in its field without reading as the cheaper
one. The intent step's two or three references answer that for one product; the library answers it for the
field, so the judge always has the bar in front of it, even before the intent step has run. It holds about
50 shipped products' first screens, each captured at our two sizes.

## Where it lives

`$HUB_DIR/projects/hub/refs/design-library/<field>/<product>/<product>-desktop.png` (1280x633) and
`-mobile.png` (390x757), with `manifest.json` beside the fields. Never copy a capture into this skill, a
product repo or a page anyone else sees: they are other people's work and the plugin is public. Packets
carry paths only.

Fields: `finance`, `maps-geo-3d`, `developer-tools`, `data-dashboards`, `consumer-apps`,
`editorial-marketing`. Each manifest entry carries `url`, `why` (one line), `mode` (Persuade, Operate,
Read, Experience), `audience` (developer, business, consumer, public), `captured` (UTC date), `capture`
(`virtual-time`, or `load-event` when a live page hung the clock), `first_visit` (what a first-time
visitor sees: `clean` or the banner) and the robots and terms checks. `skipped` lists every product
considered and left out, with the reason.

## Picking 3 to 5 refs for a product

The parent picks; the judge never browses the library.

1. **Field.** The subject's world, not the stack: a bridge-lift page is `maps-geo-3d`, a compliance tool
   for developers is `developer-tools`. Take 2 or 3 from the field.
2. **Mode.** Match the surface's mode from the surface brief: a Persuade first screen against Persuade
   refs, an Operate app against Operate refs. When the field has no ref in that mode, take one from the
   nearest field that has and say so in the packet.
3. **Audience.** Prefer refs that sell to the same reader (a developer, a buyer, a consumer), and an
   entry whose `first_visit` is `clean` or a small banner: a consent modal over the hero hides the bar.
4. **One stretch ref** may come from another field, for the trait the direction steals (`steal-from-many`):
   name the trait in the packet.
5. **Not the one it copies.** A ref the direction is derived from stays in, so R2 can catch a copy; but
   never make it the only ref.

Write the picks into the packet as one line each: `<field>/<product>: <why it is the bar here>`.

## The lead's taste set

`lead_taste` in the manifest is a pinned list of the products the lead has named as ones they love, so far
Linear, Stripe and Apple (2026-11-02). It is the first real evidence of the lead's eye, and it grows only
from the lead's own words: each entry carries `picked_by: "lead's pick"`, separate from the field picks.
Every packet carries its captures, whatever the field, on top of the 3 to 5 field refs. A pick whose site
forbids automated capture is listed with `not_captured` and its reason; it goes in no packet.

## How the judge uses them

The library refs and the taste set go in the packet next to the intent step's references (`judge.md` §2), and are read
before any text, after the candidate's own captures. R1 then names the ref it is measured against and the
one difference that decides it ("R1 1: beside Linear the type is fine, but the hero shows no product").
An R1 with no named ref is incomplete and the parent sends it back. R2 must name a thing none of the
library refs or the intent references has.

## Adding a product

1. **Bar.** Shipped and public: an award gallery (Awwwards, Godly, SiteInspire, CSS Design Awards),
   an Apple Design Award or Webby, or the leader its category copies. No Dribbble or Behance concepts.
   Choose by field, not by fame.
2. **Permission.** Skip it when `robots.txt` disallows `/` for `*` or `Claude-User`, when the website
   terms forbid automated access to the site itself (a ban on scraping data for reuse or training does not
   cover one screenshot), or when a bot wall answers automated requests. Record the skip in `skipped`.
3. **Capture.** `fixtures/capture.sh <url> <library>/<field>/<product>/<product>` captures the first
   screen only: no login, no paywall, no clicking a banner away, no crawling.
4. **Look.** A fresh sub-agent looks at both captures and confirms they show the product, not a
   challenge page, a blank or a broken layout, and names any cookie banner. A failed capture is not added.
5. **Record.** Add the manifest entry with today's date. Recapture an entry older than six months, or
   when the product has redesigned, over the same paths.

Fixtures (`fixtures/`) never use library captures; they stay synthetic and our own (`judge.md` §5).
