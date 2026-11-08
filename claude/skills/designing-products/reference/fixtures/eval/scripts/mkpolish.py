# mkpolish.py BRIEF : r3/<n>/{start.html,fonts,verdict.md} for the two kept specimens
import json, re, shutil, sys
from pathlib import Path
S = Path(__file__).parent; b = S / sys.argv[1]
mp = json.loads((b / 'pk2/packet-map.json').read_text())
v = (b / 'r2-verdict.md').read_text()
keep = re.findall(r'p\d\d', v.split('Keep:', 1)[1].splitlines()[0])[:2]
for pid in keep:
    n = mp[pid]; d = b / 'r3' / n; d.mkdir(parents=True, exist_ok=True)
    src = b / 'r2' / n
    shutil.copy(src / 'index.html', d / 'start.html')
    if (src / 'fonts').exists(): shutil.copytree(src / 'fonts', d / 'fonts', dirs_exist_ok=True)
    sec = re.search(rf'^##\s*{pid}\b.*?(?=^##\s)', v, re.S | re.M)
    ch = re.search(rf'^\**{pid}\**\s*Changes:.*?(?=^\S*p\d\d\S*\s*Changes:|^\**Ties|\Z)', v, re.S | re.M)
    (d / 'verdict.md').write_text(f"# The round-2 judge on your specimen (you were {pid})\n\n{sec.group(0) if sec else ''}\n{ch.group(0) if ch else 'CHANGES NOT FOUND'}\n")
    print(pid, n, 'changes' if ch else 'NO CHANGES', 'section' if sec else 'NO SECTION')
