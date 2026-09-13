# Brand colour looks "changed" when sampled from a screenshot

**Symptom.** You sample the pixels of a design screenshot to recover brand colours.
Every neutral matches the design file exactly, but one saturated accent comes back
noticeably different — enough that it reads as a deliberate palette change. On
Refinery this surfaced as green `#00D46A` reading as `#60D175` across five separate
reference PNGs, consistently, which made it look confirmed.

**Confirm it.** Convert the design file's stated sRGB value into Display P3 and compare
against what you sampled. If they match to the byte, the colour never changed:

```bash
uv run --with numpy python - <<'PY'
import numpy as np
def s2l(c): return np.where(c<=0.04045, c/12.92, ((c+0.055)/1.055)**2.4)
def l2s(c): return np.where(c<=0.0031308, c*12.92, 1.055*np.power(np.clip(c,0,None),1/2.4)-0.055)
SRGB2XYZ=np.array([[0.4124564,0.3575761,0.1804375],[0.2126729,0.7151522,0.0721750],[0.0193339,0.1191920,0.9503041]])
XYZ2P3=np.array([[2.4934969,-0.9313836,-0.4027108],[-0.8294890,1.7626641,0.0236247],[0.0358458,-0.0761724,0.9568845]])
h="00D46A"                      # the design file's sRGB hex
v=np.array([int(h[i:i+2],16)/255 for i in (0,2,4)])
print("#%02X%02X%02X" % tuple(int(round(x*255)) for x in np.clip(l2s(XYZ2P3 @ (SRGB2XYZ @ s2l(v))),0,1)))
PY
```

**Cause.** macOS screen captures are tagged Display P3. Reading their raw RGB without
converting back to sRGB shifts saturated colours. Neutrals are unaffected — the P3
transform is identity on the grey axis — so the greys all "confirm" your reading while
the one accent appears to have moved. That asymmetry is the tell.

**Fix.** Take hexes from the design file, the CSS, or a stated token. Never from a
screenshot. If you must sample, convert first and check whether the stated value maps
onto what you measured before concluding anything changed.

**Cost when missed.** Would have shipped the wrong brand green across a whole site
rebrand — every button, every accent, the wordmark dot, the favicon and the OG image.
Caught only because the design file was inspected afterwards and disagreed.
