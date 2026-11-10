Paths and commands below resolve from the [skill root](../SKILL.md). Read only the current stage.

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
Cloud Run Job with an NVIDIA L4 in europe-west1. Scripts: `gpu-stills/` under the skill root.

Build the image and deploy the job once, as `gpu-stills/README.md` says (it also lists what each task
does: GPU selection, the referer route, the poses and the `phone`, `ttff`, `home` and `tourstills` shots).
Know what the stills do not prove (traps from a past event):
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
