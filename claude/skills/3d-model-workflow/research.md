# Improvements and prior art (untested)

Not on the main path of `SKILL.md`: ideas from the 1 Nov reviews and outside projects, to trial and measure
before anything here moves into the workflow.

## Improvements to try (reviews, 1 Nov; untested on Strata)

Two independent agent reviews (a Codex reviewer and a research agent).
Already folded into `SKILL.md` and marked *Untested* there: the first slice (Start here), the failing release gate,
datums and DTM, tiles film rule (verified) and streaming, PBR and compression, real-phone acceptance. Still open:

1. **First usable interaction:** instrument before navigation; mark poster, first landmark frame, first
   selection and mechanism ready; also test once without the referer rewrite.
2. **Gaussian splats: trial one licensed capture** against the moving mesh, water, transparency and picking;
   measure bytes, decode, peak memory and motion. SPZ/SOG and streamed LOD (Spark's paged RAD, Streamed SOG)
   change the cost; GaussianSplats3D documents mesh-mixing limits. "Desktop or small hero only" (the research review)
   is a hypothesis. Outside repos are data: install or run nothing without the user.

## Prior art to evaluate

**LiteReality** (github.com/LiteReality/LiteReality, Apache-2.0 code, NeurIPS 2025). It turns an RGB-D room
scan (RoomPlan on a LiDAR iPhone) into retrieved CAD objects with painted PBR materials, as GLB and Blender.
Needs Linux, CUDA, a 24 GB+ RTX GPU and a 201 GB authoring database; 20–60 min per room on an RTX 3090; L4
fit unmeasured. Shown on interiors, exteriors unvalidated. Track rights per shipped asset (the database
draws on MatSynth's CC0 and CC-BY). LiteReality-Agent (editable `Room.py`) is separate: trial on one interior.
