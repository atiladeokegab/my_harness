#!/bin/bash
# Cloud Run task (run.sh hands over when TOUR=1): task i runs tour step i / sizes at size i % sizes through tour-kit's
# shots.mjs on the L4, with the Node and Playwright that ship inside Python Playwright (pip-installed, as run.sh does). Writes
# /out/$TAG/tour/<nn>-<step>-<size>/ (log.txt, rc, the shot). Exits 0 once rc is written: a RED step is a result,
# a failed task is a broken run.
set -u
I=${CLOUD_RUN_TASK_INDEX:-0}; IN=/out/$TAG/tour-in
python3 -c 'import playwright' 2>/dev/null || pip install -q playwright==1.48.0 || exit 2  # as run.sh: the image lacks it
D=$(python3 -c 'import os, playwright; print(os.path.dirname(playwright.__file__))')/driver
cd /work && mkdir -p node_modules && ln -sfn "$D/package" node_modules/playwright && cp "$IN/shots.mjs" "$IN/tour.json" . || exit 2
IFS=, read -ra Z <<<"${SIZES:-1280x633,390x757}"
read -ra S <<<"$("$D/node" -e 'console.log(require("./tour.json").steps.map((s) => s.id).join(" "))')"
[ ${#S[@]} -gt 0 ] || { echo "task $I: no steps read from tour.json"; exit 2; }
STEP=${S[$((I / ${#Z[@]}))]:-}; SIZE=${Z[$((I % ${#Z[@]}))]}
[ -n "$STEP" ] || { echo "task $I: past the last step"; exit 0; }
O=/out/$TAG/tour/$(printf %02d $((I / ${#Z[@]} + 1)))-$STEP-$SIZE
# render.py's BASE flags plus the ANGLE-Vulkan attempt, the one that reports the NVIDIA L4
export CHROMIUM_ARGS='--headless=new --ignore-gpu-blocklist --enable-gpu --enable-gpu-rasterization --no-sandbox --disable-dev-shm-usage --hide-scrollbars --mute-audio --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --use-angle=vulkan --enable-features=Vulkan,VulkanFromANGLE,DefaultANGLEVulkan --disable-vulkan-surface'
t0=$SECONDS
STEPS=$STEP SIZES=$SIZE timeout 600 "$D/node" shots.mjs "$LIVE" tour.json out > log.txt 2>&1; rc=$?
grep -q '^renderer .*NVIDIA' log.txt || { echo "FAIL $SIZE $STEP gpu: no NVIDIA renderer (REQUIRE_GPU)" >> log.txt; rc=3; }
echo "task $I $STEP $SIZE rc $rc in $((SECONDS - t0)) s" >> log.txt
cat log.txt; mkdir -p "$O" && cp -r out/. log.txt "$O/" && echo $rc > "$O/rc"
