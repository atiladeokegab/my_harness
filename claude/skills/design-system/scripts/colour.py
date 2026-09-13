#!/usr/bin/env python3
"""Colour checks for a design system. Standard library only.

    python3 colour.py contrast 00D46A 09090B          # WCAG ratio and verdicts
    python3 colour.py matrix  00D46A,A1A1AA 09090B,18181B,F4F4F5
    python3 colour.py p3      00D46A                  # what a P3-tagged screenshot shows
    python3 colour.py from-p3 60D175                  # recover the sRGB hex from a sample

Why the P3 pair exists: macOS screenshots are tagged Display P3. Sampling their raw
pixels shifts saturated colours while every neutral round-trips unchanged, so one accent
appears to have "changed" while the greys confirm the reading. Never take a brand hex
from a screenshot without running `from-p3` on it first.
"""
import sys

SRGB_TO_XYZ = ((0.4124564, 0.3575761, 0.1804375),
               (0.2126729, 0.7151522, 0.0721750),
               (0.0193339, 0.1191920, 0.9503041))
XYZ_TO_P3 = ((2.4934969, -0.9313836, -0.4027108),
             (-0.8294890, 1.7626641, 0.0236247),
             (0.0358458, -0.0761724, 0.9568845))
P3_TO_XYZ = ((0.4865709, 0.2656677, 0.1982173),
             (0.2289746, 0.6917385, 0.0792869),
             (0.0000000, 0.0451134, 1.0439444))
XYZ_TO_SRGB = ((3.2404542, -1.5371385, -0.4985314),
               (-0.9692660, 1.8760108, 0.0415560),
               (0.0556434, -0.2040259, 1.0572252))


def parse(hexstr):
    h = hexstr.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        sys.exit(f"not a hex colour: {hexstr}")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def fmt(rgb):
    return "#" + "".join(f"{round(min(max(c, 0), 1) * 255):02X}" for c in rgb)


def to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def from_linear(c):
    c = max(c, 0)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def mul(m, v):
    return tuple(sum(m[r][k] * v[k] for k in range(3)) for r in range(3))


def convert(rgb, m1, m2):
    # sRGB and Display P3 share the same transfer curve, so only the primaries differ.
    lin = tuple(to_linear(c) for c in rgb)
    return tuple(from_linear(c) for c in mul(m2, mul(m1, lin)))


def luminance(rgb):
    r, g, b = (to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg):
    a, b = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def verdict(r):
    text = "AAA" if r >= 7 else "AA" if r >= 4.5 else "fail"
    large = "AAA" if r >= 4.5 else "AA" if r >= 3 else "fail"
    ui = "pass" if r >= 3 else "fail"
    return f"text {text:<4}  large {large:<4}  UI/graphics {ui}"


def main(argv):
    if len(argv) < 2 or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "contrast" and len(args) == 2:
        r = ratio(parse(args[0]), parse(args[1]))
        print(f"{fmt(parse(args[0]))} on {fmt(parse(args[1]))}: {r:.2f}:1  {verdict(r)}")
    elif cmd == "matrix" and len(args) == 2:
        for fg in args[0].split(","):
            for bg in args[1].split(","):
                r = ratio(parse(fg), parse(bg))
                print(f"{fmt(parse(fg))} on {fmt(parse(bg))}: {r:5.2f}:1  {verdict(r)}")
    elif cmd == "p3":
        for h in args:
            print(f"sRGB {fmt(parse(h))} -> as sampled from a P3 screenshot {fmt(convert(parse(h), SRGB_TO_XYZ, XYZ_TO_P3))}")
    elif cmd == "from-p3":
        for h in args:
            print(f"sampled {fmt(parse(h))} -> sRGB {fmt(convert(parse(h), P3_TO_XYZ, XYZ_TO_SRGB))}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
