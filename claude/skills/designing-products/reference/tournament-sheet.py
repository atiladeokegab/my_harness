# Blind a tournament round: copy <id>-desktop.png and <id>-mobile.png under shuffled neutral names,
# lay the desktops out as contact sheets, and keep the mapping beside the packet (never in it).
# Every other <id>-* file goes along renamed: the final's screens 2 to 4 (<id>-s2-desktop.png ...) and the
# measured evidence (<id>-evidence.md, <id>-focus-desktop.png, judge.md §2).
#   uv run --with pillow python tournament-sheet.py SRC_DIR PACKET_DIR PREFIX [PER_SHEET]
# An id named `standard` keeps its name (judge.md §4). Writes PACKET_DIR-map.json next to PACKET_DIR.
import json, random, re, shutil, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

src, out, prefix = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
per = int(sys.argv[4]) if len(sys.argv) > 4 else 6
out.mkdir(parents=True, exist_ok=True)
ids = sorted(p.name.removesuffix("-desktop.png") for p in src.glob("*-desktop.png")
             if not re.search(r"-(s\d+|focus)-desktop\.png$", p.name))
missing = [i for i in ids if not (src / f"{i}-mobile.png").exists()]
assert not missing, f"no mobile capture for {missing}: recapture, never a partial round"
shuffled = [i for i in ids if i != "standard"]
random.shuffle(shuffled)
mapping = {f"{prefix}{n + 1:02d}": orig for n, orig in enumerate(shuffled)}
if "standard" in ids:
    mapping["standard"] = "standard"
for name, orig in mapping.items():
    for f in src.glob(f"{orig}-*"):
        shutil.copy(f, out / f"{name}{f.name[len(orig):]}")

font, (w, h, lab) = ImageFont.load_default(size=22), (640, 316, 30)
names = list(mapping)
for s in range(0, len(names), per):
    chunk = names[s:s + per]
    sheet = Image.new("RGB", (2 * w + 30, ((len(chunk) + 1) // 2) * (h + lab + 10) + 10), "white")
    draw = ImageDraw.Draw(sheet)
    for n, name in enumerate(chunk):
        x, y = 10 + (n % 2) * (w + 10), 10 + (n // 2) * (h + lab + 10)
        draw.text((x, y), name, fill="black", font=font)
        sheet.paste(Image.open(out / f"{name}-desktop.png").convert("RGB").resize((w, h)), (x, y + lab))
    sheet.save(out / f"sheet-{s // per + 1}.png")
(out.parent / f"{out.name}-map.json").write_text(json.dumps(mapping, indent=1))
print(f"{len(mapping)} blinded into {out}; {(len(names) + per - 1) // per} contact sheets")
