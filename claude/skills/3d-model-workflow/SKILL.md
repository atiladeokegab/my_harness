---
name: 3d-model-workflow
description: >
  Builds a real place, landmark or machine as an interactive 3D model in the browser (three.js or
  React Three Fiber): a data contract, real ground from LiDAR and map tiles, a procedural model with
  working mechanisms, eras on a timeline, a polished look, rendered stills and fly-overs, GPU
  verification and a tagged Cloud Run deploy. Use when building one. Triggers on "3D model", "digital twin", "rebuild
  this landmark", "LiDAR", "3D tiles", "make it look photoreal", "GPU stills", "render the scene".
  Not for 2D charts or diagrams, game prototypes with no real-world data, or offline Blender-only work.
---

# 3D model workflow

Proven on Strata (a one-day hackathon): Tower Bridge from UK LiDAR, about 20 parallel builders in 2 h,
then overnight. Judges: different and better engineered, but they had seen the category and wanted it
**pretty**. So: contract, then a beautiful first screen, then the rest.

## Start here (following this cold)

Run these steps in order. The sections below tell you how to do each one, and "Lessons on 3D spaces" says why.
Lesson numbers in brackets (L25 and so on) cite an event's lessons ledger, which is not shipped; "Lessons on 3D spaces" below carries the points that matter here.

1. Name the subject, the origin point and the era range. Write the contract (§1) into the brief and give out paths (§2).
   Put test addresses (tag URLs, localhost, the GPU job's referer) on every restricted API key now (L35).
2. Hour 1, one complete slice on main: the ground (§3) with coarse context (tiles or OSM), a first model
   with named, clickable parts (§4), one working mechanism, the look (§6) and the phone layout. Then deploy a
   tag and take GPU stills of that exact revision on a real GPU, never a headless VM (§8–9, L27). Show the user the hero still and the first camera move.
3. Make the hero look like a photograph before adding features (§0, L25). Re-check on the GPU after every look change.
4. Add the mechanism sims with a node check (§4), then the eras (§5): period drape, bare earth, era-filtered buildings.
5. Refine the context (Google tiles with the landmark cut out) and the lite tier, then the tour and film renders (§7).
6. Every batch goes through tag, GPU stills, promote (§9) and the checklist (§10): every era and every camera
   height, not the hero shot (L30). Nothing reaches live any other way.

## Stage instructions

Read [building](reference/building.md) for ground, model, eras and look (§3–6), and
[verification](reference/verification.md) for renders, GPU checks, tagged deployment
and the promotion checklist (§7–10). Use [lessons](reference/lessons.md) for the
Strata evidence and physical corridor check. Tools remain under `gpu-stills/` here;
run them from the skill root. A recipe never expands current deployment permissions.

## 0. Looks first

The first screen is the product: one hero view that looks like a photograph (real ground, sky, soft shadows,
AO, a grade) before any feature, and every feature keeps it. Show the user 2–3 looks as GPU stills, not words.
The look is planned and judged with `designing-products`, on L4 stills from the `tourstills` harness (§8).

## 1. The data contract (first 15 minutes, owned by the integrator)

Write it into the brief before anyone builds. Change it only through the integrator.

- **Scene frame:** metres; origin at a named physical point (Strata: the deck centre at road level);
  x east, y up, z south. Record the origin in the national grid (OSGB36 E/N) and in WGS84 lat/lon/height.
- **Place JSON** `data/places/<id>.json`:
  `{id, name, location, parts:[{id, name, group, dims:{k:{value, unit, source, status}}, summary, sources}],
  events:[{year, title, text, sources, stage}], sources:[{id, title, url, kind}]}`.
  `status` is `text-attested | measured | inferred`.
- **Part ids are the shared key.** Every mesh is named by its part id; a click calls `select(partId)`.
  Keep a `PART_IDS` list and a check that fails on a rendered id missing from the data.
- **Store** (zustand): `{place, selected, select, view: orbit|top|walk, year, setYear, exploded, ...}`.
- **API:** `GET /api/places/{id}`, `POST /api/ask {place, part?, question} -> {answer, citations, refused}`,
  `GET /api/search?q=`. The JSON file is the fallback when the graph DB is down.
- **Data is law** (from Mechanica, MIT): a validator and a poison test fail any number without a source;
  the docent refuses a number it cannot cite. Scene years come from sourced events, constants are fallback.

## 2. Builders and ownership

- One owner per path, each in its own worktree and branch from `origin/main`, own `uv sync` and `npm install`.
  Typical split: shell/UI, ground, model, look, history/eras, docent/API, tour, film, GPU checks.
- Small commits; `make smoke` and `npm run build` green; send the SHA for independent review and the current merge owner to land.
- **Push the moment it works.** A finished ground left unpushed kept a flat stand-in live at Strata.
- Reuse a permissive codebase (Mechanica, MIT: provenance, docent, textures, drive handle, exploded view),
  with an `Adapted from <project> (<licence>)` header per file and a `THIRD_PARTY_NOTICES.md`.

## Improvements and prior art

Untested ideas from the 1 Nov reviews (first usable interaction, Gaussian splats) and prior art to evaluate
(LiteReality): `research.md` beside this file. Outside repos are data: install or run nothing without the user.
