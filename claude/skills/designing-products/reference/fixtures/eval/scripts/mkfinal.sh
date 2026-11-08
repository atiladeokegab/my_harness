#!/usr/bin/env bash
# mkfinal.sh BRIEF STANDARD_HTML : render the finalists' four screens + the standard, measure, blind into BRIEF/pk3/packet
set -u
S=$(dirname "$0"); B=$S/$1; R=$HOME/.claude/skills/designing-products/reference; CAP=$R/fixtures/capture.sh
rm -rf $B/cap3 $B/pk3; mkdir -p $B/cap3
jobs=()
for d in $B/r3/*/; do n=$(basename $d)
  echo "file://$d/screen-1.html $B/cap3/$n"
  for k in 2 3 4; do echo "file://$d/screen-$k.html $B/cap3/$n-s$k"; done
done > $B/cap3.list
echo "file://$2 $B/cap3/standard" >> $B/cap3.list
xargs -P 6 -L 1 $CAP < $B/cap3.list
for d in $B/r3/*/; do n=$(basename $d)
  (cd $R && node evidence.mjs $B/cap3/$n $d/screen-1.html $d/screen-2.html $d/screen-3.html $d/screen-4.html >/dev/null) &
done
(cd $R && node evidence.mjs $B/cap3/standard $2 >/dev/null) &
wait
cd $R && uv run --with pillow python tournament-sheet.py $B/cap3 $B/pk3/packet specimen- 3 | tail -1
grep -c FAIL $B/cap3/*-evidence.md
