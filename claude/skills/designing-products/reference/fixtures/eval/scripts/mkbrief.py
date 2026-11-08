# mkbrief.py BRIEF CONTENT_SHEET : writes r2/<n>/brief.md for each kept line from r1-verdict + map + r0 lines
import json, re, sys
from pathlib import Path
S = Path(__file__).parent; b = S / sys.argv[1]
mp = json.loads((b / 'pk1/packet-map.json').read_text())
v = (b / 'r1-verdict.md').read_text()
sec = v.split("Keep:",1)[1].split("Ties",1)[0].strip().splitlines()
keep = re.findall(r's\d\d', sec[0]) if len(re.findall(r's\d\d', sec[0])) >= 8 else [re.search(r's\d\d', l).group(0) for l in sec if re.search(r's\d\d', l)]
keep = keep[:8]
lines = {}
for f in sorted((b / 'r0').glob('lens-*.md')):
    for m in re.finditer(r'^(\d+)\.\s+(.*)$', f.read_text(), re.M): lines[m.group(1)] = m.group(2)
for sid in keep:
    n = mp[sid]; d = b / 'r2' / n; d.mkdir(parents=True, exist_ok=True)
    jl = next((l for l in v.splitlines() if re.match(rf'\|\s*\**{sid}\**\s*\|', l)), '(no line)')
    (d / 'brief.md').write_text(f"# Your direction: line {n}\n\n{n}. {lines[n]}\n\n## Your rough sketch\n\n{b}/r1/{n}.html "
        f"(rendered: {b}/cap1/{n}-desktop.png, {n}-mobile.png)\n\n## The round-1 judge's line on it\n\n{jl}\n\n"
        f"## Content sheet\n\n{sys.argv[2]}\n\n## The field's refs (look at the desktop and mobile of each)\n\n{(b / 'refs.md').read_text()}\n")
    print(sid, n)
