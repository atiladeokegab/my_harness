#!/usr/bin/env bash
# mkfin.sh BRIEF N ROUND : render BRIEF/r3/N's four screens into BRIEF/fin/rROUND/ under neutral names, measure, detect
set -u
S=$(dirname "$0"); B=$S/$1; W=$B/r3/$2; O=$B/fin/r$3; R=$HOME/.claude/skills/designing-products/reference
CAP=$R/fixtures/capture.sh; I=$HOME/.local/share/impeccable/0.1.18/impeccable
rm -rf $O; mkdir -p $O
printf '%s\n' "file://$W/screen-1.html $O/screen" "file://$W/screen-2.html $O/screen-s2" "file://$W/screen-3.html $O/screen-s3" "file://$W/screen-4.html $O/screen-s4" | xargs -P 4 -L 1 $CAP
for s in screen screen-s2 screen-s3 screen-s4; do mv $O/$s-desktop.png $O/${s/screen/desktop}.png 2>/dev/null; mv $O/$s-mobile.png $O/${s/screen/mobile}.png 2>/dev/null; done
(cd $R && node evidence.mjs $O/screen $W/screen-1.html $W/screen-2.html $W/screen-3.html $W/screen-4.html >/dev/null)
mv $O/screen-evidence.md $O/evidence.md; mv $O/screen-focus-desktop.png $O/focus-desktop.png; mv $O/screen-focus-mobile.png $O/focus-mobile.png
n=$(cd $W && DO_NOT_TRACK=1 timeout 120 $I detect --json screen-1.html screen-2.html screen-3.html screen-4.html | python3 -c "import json,sys;d=json.load(sys.stdin);print(len(d), ' '.join(sorted({x.get('antipattern',x.get('ruleId','?')) for x in d})))")
echo "detector: $n (impeccable 0.1.18 detect on the four screens' HTML, same revision)" > $O/detector.txt
ls $O | tr '\n' ' '; echo; grep -c FAIL $O/evidence.md; cat $O/detector.txt
