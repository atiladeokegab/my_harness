Paths and commands below resolve from the [skill root](../SKILL.md). Read only the current stage.

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
