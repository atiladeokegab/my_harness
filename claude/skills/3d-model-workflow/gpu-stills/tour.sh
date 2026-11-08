#!/bin/bash
# Usage: tour.sh <tag> <url> [tour.json]  - the judge-tour layout check (designing-products/tour-kit/shots.mjs) on the L4
# job: one Cloud Run task per step x size, as many at once as the job's parallelism (the L4 quota) allows.
# Env: PROJECT BUCKET, optional JOB (strata-render), REFERER (a tagged URL needs it for referrer-locked tiles),
# SIZES (1280x633,390x757). Results: gs://$BUCKET/<tag>/tour/<nn>-<step>-<size>/. Prints every FAIL and RED line
# and each task's exit code; exits 1 on any RED, 2 or 3 on a broken run.
set -u; T=$1; URL=$2; H=$(cd "$(dirname "$0")" && pwd); KIT=$H/../../designing-products/tour-kit
TJ=${3:-$KIT/strata.tour.json}; : "${PROJECT:?}" "${BUCKET:?}"; JOB=${JOB:-strata-render}; B=gs://$BUCKET
SIZES=${SIZES:-1280x633,390x757}; R="--project $PROJECT --region europe-west1"
N=$(( $(python3 -c 'import json, sys; print(len(json.load(open(sys.argv[1]))["steps"]))' "$TJ") * $(tr , '\n' <<<"$SIZES" | wc -l) ))
timeout 120 gcloud storage rm -r -q "$B/$T/tour" >/dev/null 2>&1  # an earlier run's results under this tag
{ timeout 120 gcloud storage cp -q "$H/run.sh" "$H/tour-task.sh" "$B/scripts/" && timeout 120 gcloud storage cp -q "$KIT/shots.mjs" "$B/$T/tour-in/shots.mjs" \
  && timeout 120 gcloud storage cp -q "$TJ" "$B/$T/tour-in/tour.json"; } >/dev/null 2>&1 || { echo "FAIL: upload"; exit 2; }
S0=$SECONDS
E=$(timeout 90 gcloud run jobs execute $JOB $R --async --tasks $N "--update-env-vars=^;^TOUR=1;TAG=$T;LIVE=$URL;REFERER=${REFERER:-};SIZES=$SIZES" 2>&1 | grep -o "$JOB-[a-z0-9]*" | head -1)
case "$E" in $JOB-?*) ;; *) echo "FAIL: no execution id"; exit 2;; esac
echo "execution $E: $N tasks, started $(date -u +%T)"; END=$((SECONDS + 3600))
until [ "$(timeout 30 gcloud run jobs executions describe $E $R --format='value(status.completionTime)' 2>/dev/null)" ]; do [ $SECONDS -lt $END ] || { echo "FAIL: no completion in 60 min"; exit 3; }; sleep 15; done
read OK FAILED <<<"$(timeout 30 gcloud run jobs executions describe $E $R --format='value(status.succeededCount,status.failedCount)')"
echo "done $(date -u +%T) in $((SECONDS - S0)) s: ${OK:-0} tasks succeeded, ${FAILED:-0} failed"
D=${TOUR_DIR:-$HOME/work/stills}/$T-tour; rm -rf "$D"; mkdir -p "$D"
timeout 300 gcloud storage cp -r -q "$B/$T/tour/*" "$D/" >/dev/null 2>&1 || { echo "FAIL: download"; exit 3; }
RC=0; [ "${FAILED:-0}" = 0 ] || RC=3
for d in "$D"/*/; do
  n=$(basename "$d"); rc=$(cat "$d/rc" 2>/dev/null || echo none)
  echo "rc $rc  $n  $(grep -o 'in [0-9]* s$' "$d/log.txt" 2>/dev/null)"
  grep -h '^FAIL [0-9]' "$d/log.txt"  # the step x size failures; story FAILs are the same in every task, printed once below
  case $rc in 0) ;; 1) [ $RC = 0 ] && RC=1;; *) RC=3;; esac
done
grep -h '^FAIL story' "$D"/*/log.txt 2>/dev/null | sort -u
[ "$(ls -d "$D"/*/ 2>/dev/null | wc -l)" = $N ] || { echo "FAIL: $(ls -d "$D"/*/ 2>/dev/null | wc -l) of $N results"; RC=3; }
echo "$([ $RC = 0 ] && echo GREEN || echo RED): rc $RC, shots in $D"; exit $RC
