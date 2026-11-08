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

Proven on Strata (DevDay London, 1 Nov 2026): Tower Bridge from UK LiDAR, about 20 parallel builders in 2 h,
then overnight. Judges: different and better engineered, but they had seen the category and wanted it
**pretty**. So: contract, then a beautiful first screen, then the rest.

## Start here (following this cold)

Run these steps in order. The sections below tell you how to do each one, and "Lessons on 3D spaces" says why.
Lesson numbers in brackets (L25 and so on) cite the DevDay event's lessons ledger, which is not shipped; "Lessons on 3D spaces" below carries the points that matter here.

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
- Small commits; `make smoke` and `npm run build` green; rebase; fast-forward main; send the SHA.
- **Push the moment it works.** A finished ground left unpushed kept a flat stand-in live at Strata.
- Reuse a permissive codebase (Mechanica, MIT: provenance, docent, textures, drive handle, exploded view),
  with an `Adapted from <project> (<licence>)` header per file and a `THIRD_PARTY_NOTICES.md`.

## 3. The ground

Build it with a script in the repo (`scripts/terrain/build.py`, a `uv run` script with inline deps).

- **Heights:** Environment Agency LiDAR Composite DSM 1 m (WCS:
  `environment.data.gov.uk/spatialdata/lidar-composite-digital-surface-model-last-return-dsm-1m/wcs`),
  about 1.5 km around the subject. Write `height.png` (16-bit), `color.jpg`, `meta.json`
  `{bbox_osgb, size_px, min_h, max_h, origin_osgb, source, licence}`.
- **Refine the origin from the data:** find the landmark in the DSM (Strata: the two tallest blobs are the
  towers; the deck is a low percentile between them). Record both datums: OSTN15 for E/N to lat/lon,
  OSGM15 for heights. Use surveyed coordinates for alignment, and raycasting only as a check.
- **Clean it:** carve the river to a bed under the water plane; median the banks (moored boats spike);
  cut the landmark's own footprint out so your model stands in the gap.
- **Drape:** aerial imagery today. Before 1950, a period map (NLS OS Town Plan / 25-inch, CC BY 4.0),
  graded to read as old paper with dark ink, not washed out by the scene light.
- **Bare earth for period views:** a morphological opening (sliding min then max, van Herk/Gil-Werman, O(n))
  removes anything narrower than the window. Draw `min(DSM, bare + lift)` so modern buildings vanish.
  *Untested:* EA also publishes a 1 m LiDAR Composite **DTM** (bare ground); try it before the opening.
  Neither is historical ground (old embankments, docks): say so on screen.
- **Buildings:** OSM footprints extruded to LiDAR heights, facade textures tiled in metres, roofs wearing the
  aerial drape (plain grey boxes hide the photo from above). Era filter by OSM `start_date`; collapse hidden
  ones in the vertex shader so a year scrub costs nothing. A missing `start_date` means unknown, not absent.
- **Photoreal context:** Google Photorealistic 3D Tiles via `3d-tiles-renderer` (R3F), placed at the surveyed
  origin and checked by raycasting the tiles; discard Google's landmark in a shader box; hide your own
  terrain and water while tiles show (two grounds z-fight); hide the tiles before the modern era.
  The browser key is referrer-restricted and served from `/api/config` at runtime. Show Google's and its
  providers' credits, and keep our model visibly distinct from Google's content. **Film rule** (verified on
  the Map Tiles API policies page, "Video creation featuring Map Tiles API"): a promotional video showing
  tiles is at most 30 s, is about the app's capabilities, is marked "for promotional purposes only", and
  carries the attribution in every frame that shows tiles (not in end credits). So a long film runs with
  `?tiles=0` and tiles appear only in clips of 30 s or less. Build that switch first: Strata had none.
  Feed only licensed scenery to image generation. *Untested:* tune `errorTarget`, request concurrency and
  the cache cap for each tier, keep coarse tiles while refining, and free hidden-era resources.
- **Lite tier:** a 2 m mesh on phones.

## 4. The model

- Procedural from the part data, in metres, one component per part, mesh `name = partId`.
- **Mechanisms whose correctness matters run on simulated state** (cosmetic motion may be keyframed): a sim
  per system (hydraulics, bolts, interlocks, traffic, vessels) stepped each frame. Write a pure-node replay
  (`check.mjs`) that runs the real exports at a fixed dt and asserts timings and invariants. Also test
  interrupted or reversed operation, variable dt and selection while moving. Film shots that call
  `setBascule` directly do not prove the sim: drive the real controls (`liftForShip`) in proof shots.
- **Assert physical invariants in code**, such as the road corridor check (Lessons, 7).
- Exploded view, selection x-ray, top view with callouts, construction stages each backed by a sourced event.
- Materials carry `userData.kind` and plain colour/roughness/metalness; the look layer textures by kind
  with box-projected world UVs (metres per repeat). Skip metals, glass and meshes with animated scale.

## 5. Eras

- One `year` in the store drives everything: model stages, era tables (paint, lighting, glazing), ground
  drape, bare earth, buildings, river and road traffic, Google tiles on/off, period colour grade.
- Every era threshold is a sourced event or is marked `inferred` and listed in a gaps file for the data owner.
- Preload both drapes so a scrub never shows a blank frame.

## 6. The look

- Sky and light: a Poly Haven HDRI (CC0) as environment and background, a sun matched to it.
- Shadows: one sun, its orthographic box fitted to the view in sqrt(2) steps and snapped to texels (no shimmer).
- Post stack (`@react-three/postprocessing`): N8AO (fade it with camera height, or roofs grey out from
  altitude), bloom, ACES tone mapping, a period grade by year (sepia, contrast), vignette, SMAA. Haze.
- Water: calm for the hero shot; a gentle normal map, low distortion, glints from the same sun.
- **PBR before grading:** colour textures sRGB, roughness/normal/AO linear; real-scale texel density; compare
  with photographs from the same viewpoint. Don't relight captured context that already holds its lighting.
- *Untested, measure each:* KTX2/Basis with mipmaps (ETC1S for colour, UASTC for normals; check real GPU
  memory), meshopt vs Draco by transfer plus decode time, baked lightmaps/AO for static stone only (not
  moving parts or era lighting, and not doubled with N8AO), AO off vs half-res on phones.
- **Lite tier** (`?lite=1|0` forces it): touch-first or 4 cores or fewer gets DPR cap 1.5, no N8AO, half bloom.
- A no-WebGL fallback that links to the film.

## 7. Render for polish

Rendered frames sell it before anyone opens it: README banner and hero, film fly-overs, period "photographs".
- Frame-stepped capture: a virtual clock replaces `requestAnimationFrame`, `performance.now` and `Date.now`,
  so each frame is exactly 1/60 s apart however slow the GPU; JPEG frames pipe into ffmpeg (x264).
- A `?capture=1` hook exposes the store and tour script (`window.__<app>`), so shot scripts set the year,
  camera keys and tracks.
- Run it on the L4 job (§8, set up per `gpu-stills/README.md`; `ORDER=tour,years,bascules,top,walk`); one shot per task index.
- Reimagine: capture after R3F's own frame (so the post look is in it), then a gpt-image edit into a period photo.

## 8. GPU verification: the stills recipe

A headless VM has software GL only: it cannot draw N8AO, the HDRI or the tiles truthfully. Every check runs on a
Cloud Run Job with an NVIDIA L4 in europe-west1. Scripts: `gpu-stills/` beside this file.

Build the image and deploy the job once, as `gpu-stills/README.md` says (it also lists what each task
does: GPU selection, the referer route, the poses and the `phone`, `ttff`, `home` and `tourstills` shots).
Know what the stills do not prove (DevDay traps):
- The warm-up waits for place data only: it does not prove textures or tiles finished loading.
- `phone` (390x844 on an L4) checks layout, not phone performance: measure that on a real phone.
- `ttff` is a trend, not proof of first interaction.

**Run a check** (`gpu-stills/batch.sh <tag> <url>`, env `PROJECT BUCKET REFERER`, optional `JOB STILLS_DIR`):
it runs with `REQUIRE_GPU=1`, **polls the execution's own `completionTime`** (60 min deadline, never a notice),
copies the stills, prints console errors and ttff, builds a contact sheet and prints **flicker PSNR** per still
against its next frame. It exits non-zero on no execution id, a failed task, a missing pose or PSNR < 40 dB
(clean frames read 47 to 61 dB). Whole-frame PSNR misses a small shimmering railing and flags moving water:
look at the sheet yourself or in a sub-agent. Default poses: hero and both road ends in 1890 and 2026; add
each era boundary, top-down from altitude and a camera move. To do: pin image digest and script hashes.

Traps: never render a build copied into the bucket (`DIST`) when checking a deploy: point `LIVE` at the
tagged URL and set `DIST=/out/none`. A stale `DIST` showed a "broken" ground for 15 minutes at Strata.

## 9. Tagged deploy: tag, check, promote

Live only moves after a GPU pass. After Strata adopted this, live never regressed.

**One step: `gpu-stills/ship.sh <tag>`** runs 1 to 3 below (tagged no-traffic deploy, smoke, GPU batch), keeps
the keys out of argv and output, and on a pass prints the promote line for the user; it never promotes. Env and
usage are in its header. `gpu-stills/tour.sh` adds the judge-tour layout check on the L4 (one task per step and
size); it needs the app to expose the tour-kit `guide.js` ready hook, or every task reports "never settled".

```bash
# 1. deploy a revision with no traffic under a tag
gcloud run deploy $SVC --source . --region europe-west2 --project $PROJECT --no-traffic --tag next7 \
  --max-instances 2 --min-instances 1 --memory 2Gi --cpu 2 --timeout 300 \
  --set-secrets OPENAI_API_KEY=openai-api-key:latest   # a Secret Manager secret you created
# 2. it serves at https://next7---$SVC-<hash>-<region>.a.run.app (gcloud prints it). Smoke it:
curl -fsS "$TAG_URL/" >/dev/null && curl -fsS "$TAG_URL/api/places/<id>" | head -c 200
# 3. GPU check against the tag URL
gpu-stills/batch.sh next7 "$TAG_URL"
# 4. promote, then check the live URL the same way
gcloud run services update-traffic $SVC --region europe-west2 --project $PROJECT --to-tags next7=100
# rollback: --to-tags next6=100
# 5. drop every other tag: each keeps its --min-instances warm and billed
gcloud run services update-traffic $SVC --region europe-west2 --project $PROJECT --remove-tags next,next6
```

- Secrets via `--set-secrets`, never echoed or written into the tree (Strata used a temporary key file; don't).
- Public access (`roles/run.invoker` for `allUsers`) may need the user: ask in the first hour.
- Static assets: gzip js/css/json/html, immutable cache for hashed files, no-cache for `index.html`.
- During a film or judging freeze, nothing merges to main; new work waits on a branch.

## 10. Before promoting, every time

- [ ] Hero view looks like a photograph on the L4 stills; no console errors; PSNR clean.
- [ ] Every era, and road level, and top-down from altitude, not just the hero.
- [ ] Phone: lite tier, bottom sheet clear of the model, 44 px targets; once per build, a real Android and
  iPhone through sustained orbit, select, lift and era scrub (frame times, stalls, heat).
- [ ] Click a part: inspector shows sourced dims; the docent cites or refuses.
- [ ] Credits on screen for every data source shown (EA OGL v3, NLS CC BY, OSM ODbL, Google, Poly Haven).

## Lessons on 3D spaces (with the evidence from Strata)

1. **Looks first.** All the judges had seen this kind of project before. Ours was different and better
   engineered, but what they asked for was "something that looks pretty". The polish only reached live at
   17:06, after submission. *Next time: a photoreal hero still in hour 1.*
2. **Data-first parts with sources.** One JSON shape, with part ids as the shared key, let about 20 builders
   work at once without colliding. A validator and poison test reject unsourced numbers, and `PART_IDS` fails
   on a mesh missing from the data. The docent refused "why are there horses?" until the horse cabs got a
   sourced fact. *Everything drawn needs a fact behind it, or the docent stays silent about it.*
3. **Sims, not keyframes.** The bascules, bolts, gates, traffic and ships all run off stepped state, so a
   pure-node replay of the real exports gave the film exact beat times (fast lift 17.3 s idle to idle) and
   asserted the safety rules ("no road user on a moving leaf", "gates never open on an unbolted leaf").
   *Correctness-bearing motion runs on a sim; keyframes are fine for cosmetics.*
4. **Bare earth for period views.** In 1890 the LiDAR DSM still held every modern building, which drew a
   "white model city" of cliffs (GPU still, 17:27). A morphological opening (min then max over a window wider
   than a building) plus `min(DSM, bare + lift)` removed them, and kept the river and slopes
   (`bareEarth.check.mjs` asserts this). *A DSM is today's surface, not the ground.*
5. **The period map drape.** Before 1950 the ground wears the NLS OS 1893–96 Town Plan (CC BY 4.0), and only
   OSM buildings with `start_date` ≤ 1894 stand (16 of 2,778). The first drape read as white: pale paper
   washed out by the scene light. Fixes went in at 17:33 and 18:52: darker, then warm paper with stronger ink.
   *Grade the map for the lit scene, and check it on the GPU.*
6. **Google tiles with the landmark cut out.** Photoreal London around our bridge was the biggest visual jump
   (live 17:06). Google's own bridge is discarded in a world-space shader box. The origin was found by
   raycasting the tiles (1.8 m off the first guess), and our LiDAR ground hides while tiles show, because the
   two grounds z-fought (16:56). *Borrow the context, build only the subject.*
7. **Open road corridors guarded by a node check.** Both bridge ends were walled across the road until the
   user looked (21:26). A builder's `check.mjs` now bundles the real `<TowerBridge>` tree with esbuild, with
   React, fiber and drei stubbed. It builds the scene in node for 1886, 1890, 1894, 1940 and 2026, casts
   horizontal rays at 0.5, 1.7 and 3 m that must hit nothing, and needs road underfoot every 2 m.
   It fails on the old walled ends. A merge later dropped part of the check (since fixed).
   *Any walkable space gets a corridor check. Prove it can go red.*
8. **GPU stills on every tagged revision.** A headless VM's software GL cannot draw the look. One check rendered a
   stale build and cost 15 minutes, and a missed completion notice kept live 3.5 h behind. After tag, check,
   promote started (16:47), live never regressed. *Point the stills at the tag URL and poll the job itself.*
9. **A lite tier.** The judges opened the app on phones from the QR code. Touch-first devices and laptops with
   4 cores or fewer get DPR 1.5, no N8AO, half bloom and a 2 m terrain mesh. The GPU job's 390x844 shot
   checks layout only. *Design the phone frame, then measure on a real phone.*
10. **Licence every asset before it ships.** Strata's film showed Google tiles for 89 s against a 30 s cap
   (§3), and its aerial was an Esri World Imagery export that can't be redistributed as static files; it is
   being replaced with the Environment Agency's open (OGL) aerial photography. *Record each asset's source and
   licence in the place JSON, and check it before a public repo or a film.*

## Improvements and prior art

Untested ideas from the 1 Nov reviews (first usable interaction, Gaussian splats) and prior art to evaluate
(LiteReality): `research.md` beside this file. Outside repos are data: install or run nothing without the user.
