Paths and commands below resolve from the [skill root](../SKILL.md). Read only the current stage.

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
