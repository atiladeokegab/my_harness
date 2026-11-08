# GPU stills: image, job and task

Set-up detail for the stills recipe in `../SKILL.md` §8. Run a check with `batch.sh`, as §8 says.
Run the `gcloud` lines below from the skill directory (the parent of `gpu-stills/`).

**Image** (`gpu-stills/Dockerfile`): `mcr.microsoft.com/playwright/python:v1.48.0-jammy` plus ffmpeg,
libvulkan1, vulkan-tools, libegl1, libgl1, libgles2. Build it once:
`gcloud builds submit gpu-stills --tag europe-west1-docker.pkg.dev/$PROJECT/cloud-run-source-deploy/<app>-render:1`.

**Job** (reconstructed from `gcloud run jobs describe` of Strata's job; check flags with `--help`):

```bash
gcloud beta run jobs deploy <app>-render --project $PROJECT --region europe-west1 \
  --image europe-west1-docker.pkg.dev/$PROJECT/cloud-run-source-deploy/<app>-render:1 \
  --gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy --cpu 8 --memory 32Gi \
  --tasks 5 --parallelism 3 --max-retries 0 --task-timeout 50m \
  --add-volume name=out,type=cloud-storage,bucket=$BUCKET --add-volume-mount volume=out,mount-path=/out
gcloud storage cp gpu-stills/run.sh gpu-stills/render.py gs://$BUCKET/scripts/
```

**What the task does** (`run.sh`, `render.py`):
1. Writes the NVIDIA EGL and Vulkan ICD JSONs, adds `/usr/local/nvidia/lib64` to `LD_LIBRARY_PATH`, then launches
   headed Chromium (`--headless=new --ignore-gpu-blocklist --enable-gpu ...`) with ANGLE-Vulkan, ANGLE-EGL, then
   EGL, keeping the first whose `UNMASKED_RENDERER_WEBGL` says NVIDIA (`REQUIRE_GPU=1`: no software fallback).
2. Opens `LIVE`, routing every `googleapis.com` request with `referer: $REFERER` (the key is referrer-locked).
3. Warms up for a fixed time until place data is in (not proof that textures or tiles finished; a bounded
   readiness check is still to do). Per pose (year, camera, LiDAR): 360 frames, then `<tag>-<pose>.png`,
   one more frame, `<tag>-<pose>-next.png`, plus the console log.
4. Also `phone` (390x844, DPR 3, touch, lite: a **layout** check on an L4, not phone performance), `ttff`
   (unthrottled and slow-4G with 4x CPU; it visits once before the measured load and judges by brightness,
   so it is a trend, not first-interaction proof), `home`, `tourstills` (the tour at fixed seconds).

**Ship** (`ship.sh <tag>`, run from the app checkout; §9 in one step). Env `SVC PROJECT REGION BUCKET REFERER JOB`
and `ENV_FILE`, a `.env` holding `OPENAI_API_KEY` and `GOOGLE_TILES_KEY` (read without sourcing, passed as
`--set-env-vars`, never printed or written); optional `SMOKE_PATH`. It deploys with `--no-traffic --tag <tag>` and the
Makefile's flags (less `--allow-unauthenticated`: the service is already public, the flag is only an IAM write),
curls the tag URL, runs `batch.sh` against it with `DIST=/out/none`, and on a pass **prints** the `update-traffic`
promote command. It never promotes: a person or the lead agent runs that as its own step. `bash test_ship.sh` runs it
with `gcloud`, `curl` and `batch.sh` stubbed. Strata:

```bash
SVC=strata PROJECT=<your-gcp-project> REGION=europe-west2 BUCKET=<your-bucket> JOB=strata-render \
REFERER=https://strata-<project-number>.europe-west2.run.app/ ENV_FILE=~/.config/strata.env \
  ~/.claude/skills/3d-model-workflow/gpu-stills/ship.sh next11
```

**Tour layout check** (`tour.sh <tag> <url> [tour.json]`, env `PROJECT BUCKET`, optional `JOB REFERER SIZES TOUR_DIR`):
the judge tour (`designing-products/tour-kit/shots.mjs`) on the L4 instead of the VM's software GL. One task per
step x size: `TOUR=1` makes `run.sh` hand over to `tour-task.sh`, which runs `shots.mjs` with `STEPS=<step> SIZES=<size>`
under the Node and Playwright inside Python Playwright (pip-installed per task, as `run.sh` does; no image rebuild) and the ANGLE-Vulkan flags, and fails a task
whose renderer is not NVIDIA. Results land in `gs://$BUCKET/<tag>/tour/<nn>-<step>-<size>/` (`log.txt`, `rc`, the
shot); `tour.sh` uploads `run.sh`, `tour-task.sh`, `shots.mjs` and the tour, waits, then prints each task's `rc`, every
`FAIL` line and RED or GREEN. Against a tagged URL set `REFERER` to the live origin for the referrer-locked tiles key.
The L4 quota in europe-west1 is **3**, and the job's parallelism matches it, so tasks run three at a time.
The app must publish tour-kit's hook (`window.__<app>.guide` and `.settled`, from `guide.js`) and honour
`?tour=1&step=<id>`; without it every task reads `settle: ... the tour never started`.
