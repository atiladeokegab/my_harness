#!/bin/bash
# Usage: batch.sh <tag> <url>  - the overnight check: Home, orbit 2026, hero 1890, phone lite, road-level ends 2026+1890, phone first-frame timing.
# Env: PROJECT, BUCKET (mounted at /out in the job), REFERER (the live origin the Google key allows), JOB (default strata-render).
set -u; T=$1; URL=$2; : "${PROJECT:?}" "${BUCKET:?}" "${REFERER:?}"; JOB=${JOB:-strata-render}; B=gs://$BUCKET
cd /tmp
E=$(timeout 90 gcloud run jobs execute $JOB --project $PROJECT --region europe-west1 --async --tasks 4 "--update-env-vars=^;^REQUIRE_GPU=1;LIVE=$URL;REFERER=$REFERER;DIST=/out/none;OUTDIR=/out/$T;PFX=$T;ORDER=stills,ttff,phone,home;POSES_ONLY=orbit-default-2026,hero-1890,north-end-out-2026,north-end-back-2026,south-end-out-2026,south-end-back-2026,north-end-out-1890,north-end-back-1890,south-end-out-1890,south-end-back-1890;PHONE_YEAR=" 2>&1 | grep -o "$JOB-[a-z0-9]*" | head -1)
case "$E" in $JOB-?*) ;; *) echo "FAIL: no execution id"; exit 2;; esac
echo "execution $E started $(date -u +%T)"; END=$((SECONDS + 3600))
until [ "$(timeout 30 gcloud run jobs executions describe $E --project $PROJECT --region europe-west1 --format='value(status.completionTime)' 2>/dev/null)" ]; do [ $SECONDS -lt $END ] || { echo "FAIL: no completion in 60 min"; exit 3; }; sleep 20; done
read OK FAILED <<<"$(timeout 30 gcloud run jobs executions describe $E --project $PROJECT --region europe-west1 --format='value(status.succeededCount,status.failedCount)')"
echo "done $(date -u +%T): ${OK:-0} succeeded, ${FAILED:-0} failed"; RC=0; [ "${FAILED:-0}" = 0 ] || RC=1
D=${STILLS_DIR:-$HOME/work/stills}/$T; mkdir -p $D
timeout 120 gcloud storage cp "$B/$T/stills/*" $D/ 2>&1 | tail -1
cd $D && cat $T-ttff.txt 2>/dev/null; grep -hv ReadPixels *console.txt | cut -c1-200 | sort | uniq -c
uv run --no-project --with pillow --with numpy python - "$T" <<'PY'
import sys; from PIL import Image
bad = 0
T = sys.argv[1]; s = Image.new("RGB", (1920, 1080))
for i, n in enumerate(['north-end-out-2026', 'north-end-back-2026', 'south-end-out-2026', 'south-end-back-2026', 'north-end-out-1890', 'north-end-back-1890', 'south-end-out-1890', 'south-end-back-1890', 'orbit-default-2026']):
    try: s.paste(Image.open(f'{T}-{n}.png').convert('RGB').resize((640, 360)), ((i % 3) * 640, (i // 3) * 360))
    except FileNotFoundError: print(f'MISSING {T}-{n}.png'); bad = 1
s.save(f'{T}-ends-sheet.png')
import glob, numpy as np  # flicker: PSNR between each still and the very next frame; clean frames read 47 to 61 dB
for a in sorted(glob.glob(f'{T}-*-next.png')):
    x, y = (np.asarray(Image.open(f).convert('RGB'), float) for f in (a.replace('-next', ''), a))
    mse = ((x - y) ** 2).mean(); db = 99 if mse == 0 else 10 * np.log10(255 ** 2 / mse)
    print(f'{db:5.1f} dB {"FLICKER " if db < 40 else ""}{a}'); bad |= bool(db < 40)
sys.exit(int(bad))
PY
[ $? = 0 ] || RC=1; [ $RC = 0 ] && echo "PASS (mechanical gates only; still look at the sheet)" || echo FAIL; exit $RC
