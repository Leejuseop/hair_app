# FaceBuilder Mask-Aware Correction

This experiment keeps FaceBuilder for geometry/camera alignment and replaces
the weak part of the pipeline: texture pixel trust, repair, and completion.

Private generated assets belong in Drive only. Do not commit photos, crops,
masks, textures, renders, meshes, GLB/OBJ exports, or review sheets.

## Current Source Baseline

The current FaceBuilder source baseline is:

```text
<private_drive>/hair_app/output/facebuilder_semantic_v2
```

That baseline uses Pixel3DMM V4 crops for FaceBuilder alignment and raw
FaceBuilder texture baking.

## Completed Steps

### Step 0: Scene Data Probe

Script:

```text
experiments/facebuilder_mask_aware_correction/run_step0_probe.py
```

Purpose:

- open existing FaceBuilder `.blend` files;
- verify mesh, UV, raw texture, OBJ/GLB, camera image paths;
- extract camera projection/model matrices;
- export triangulated mesh/UV arrays for later rasterization.

Latest private output:

```text
<private_drive>/hair_app/output/facebuilder_mask_aware_step0/20260629_194117
```

### Step 1: Reprojection Smoke Test

Script:

```text
experiments/facebuilder_mask_aware_correction/run_step1_reprojection.py
```

Purpose:

- project the solved FaceBuilder head mesh back onto each input crop image;
- verify that eyes/nose/mouth/jaw roughly line up.

Latest private output:

```text
<private_drive>/hair_app/output/facebuilder_mask_aware_step1/20260629_195513
```

### Step 2: UV Visibility

Script:

```text
experiments/facebuilder_mask_aware_correction/run_step2_uv_visibility.py
```

Purpose:

- compute which UV atlas regions each input image can see;
- estimate per-camera view-angle confidence;
- build per-camera and combined UV coverage/source-count maps.

Latest private output:

```text
<private_drive>/hair_app/output/facebuilder_mask_aware_step2/20260629_200519
```

### Step 3: Parser/Object Mask Ablation

Script:

```text
experiments/facebuilder_mask_aware_correction/run_step3_masks.py
```

Versions:

```text
v0_farl_only
v1_facexformer_only
v2_farl_grounded_sam
v3_facexformer_grounded_sam
```

Current private output:

```text
<private_drive>/hair_app/output/facebuilder_mask_aware_step3/20260629_212612
```

Current state:

- all four versions are generated;
- current working parser/object-mask candidate is `v2_farl_grounded_sam`;
- FaceXFormer remains experimental because it under-segments some nose/skin
  regions compared with FaRL;
- Grounded SAM is used conservatively: broad face/head/hair detections and
  oversized masks are rejected before object masks enter `usable_skin`.

Colab instructions for regenerating external masks:

```text
experiments/facebuilder_mask_aware_correction/STEP3_COLAB.md
```

### Step 4: Clean-Pixel UV Projection

Scripts:

```text
experiments/facebuilder_mask_aware_correction/blender_step4_uv_sample_coords.py
experiments/facebuilder_mask_aware_correction/blender_step4_render_texture.py
experiments/facebuilder_mask_aware_correction/run_step4_clean_projection.py
```

Purpose:

- keep FaceBuilder's solved head mesh and per-photo cameras;
- build UV texel to image-pixel coordinate maps in Blender;
- sample only Step 3 `v2_farl_grounded_sam` usable-skin pixels in host Python;
- write raw and median color-corrected clean projected textures;
- write diagnostic coverage, confidence, source-count, and best-source-camera
  maps;
- create atlas review sheets, source contribution sheets, and overlay render
  sheets.

Current private outputs:

```text
texture-camera-only, active for texture correction:
<private_drive>/hair_app/output/facebuilder_mask_aware_step4/20260629_221621

include-alignment-cameras, diagnostic only:
<private_drive>/hair_app/output/facebuilder_mask_aware_step4/20260629_222438
```

Current observations:

- Texture-camera-only Step 4 removes a lot of raw FaceBuilder contamination, but
  coverage is still sparse: Juseop about 19.9%, Eunchae about 15.5% at 1024
  atlas.
- Including Juseop alignment/scan cameras increases Juseop coverage to about
  23.2%, but it is not the active texture source because scan/alignment frames
  should not drive final texture.
- Eunchae has no extra alignment-only scan set in this baseline, so both Step 4
  variants are effectively the same for her.
- Step 4 is not a final texture. Eye, mouth, hairline/scalp, neck, and
  low-confidence regions still need arbitration/completion.

### Step 5: Raw-vs-Clean Arbitration

Script:

```text
experiments/facebuilder_mask_aware_correction/run_step5_arbitration.py
```

Purpose:

- compare FaceBuilder raw texture against Step 4 `projected_clean_texture_raw`;
- do not use `facebuilder_texture_bald_cleanup.png`;
- do not use Step 4 `projected_clean_texture_color_corrected`;
- classify every UV texel into four decision categories;
- produce two outputs:
  - `select`: BOTH_OK texels choose the higher-trust source;
  - `blend`: only BOTH_OK texels blend raw and Step 4 projected raw;
- leave COMPLETION_NEEDED texels black in both output textures;
- render the select texture, blend texture, and decision color map on the
  FaceBuilder mesh.

Decision colors:

```text
red    = CLEAN_ONLY, Step 4 projected raw is trusted and raw is not
blue   = RAW_ONLY, raw FaceBuilder texture is trusted and Step 4 is weak/absent
green  = BOTH_OK, both sources are acceptable
yellow = COMPLETION_NEEDED, neither source is trusted; output texture is black
```

Current private Step 5 output:

```text
<private_drive>/hair_app/output/facebuilder_mask_aware_step5/20260630_213625
```

Current Step 5 observations:

- The active Step 5 run uses the texture-camera-only Step 4 root:
  `<private_drive>/hair_app/output/facebuilder_mask_aware_step4/20260629_221621`.
- The earlier run at
  `<private_drive>/hair_app/output/facebuilder_mask_aware_step5/20260630_200156`
  used the scan/alignment-included Step 4 root and is diagnostic/retired, not
  the active texture result.
- Cleanup texture is explicitly excluded.
- Step 4 color-corrected texture is explicitly excluded.
- Raw texture is only allowed where Step 4 had at least some projected clean
  skin support. This prevents raw hair/clothing/background from filling unknown
  UV regions too aggressively.
- Juseop category ratios at 1024 atlas:
  - CLEAN_ONLY: 0.007
  - RAW_ONLY: 0.030
  - BOTH_OK: 0.156
  - COMPLETION_NEEDED: 0.807
  - BOTH_OK near-tie 40:60-60:40: 0.781 of BOTH_OK
- Eunchae category ratios at 1024 atlas:
  - CLEAN_ONLY: 0.023
  - RAW_ONLY: 0.012
  - BOTH_OK: 0.103
  - COMPLETION_NEEDED: 0.862
  - BOTH_OK near-tie 40:60-60:40: 0.788 of BOTH_OK
- Visual review favors `blend` over `select` as the Step 6 base.

Important visual interpretation:

- The selected Step 3 mask, `v2_farl_grounded_sam`, looks strong in review.
- The current Juseop forehead artifact is not treated as confirmed hair leakage.
- It is more likely valid skin with baked lighting/tone mismatch, darkened by
  blending and render lighting.

### Step 6: Material-Specific Postprocess

Script:

```text
experiments/facebuilder_mask_aware_correction/run_step6_postprocess.py
```

Step 6 starts from the Step 5 `blend` texture. It is intentionally run one
element at a time, with a fresh review sheet after each individual repair.

Planned process:

1. Start from Step 5 `blend`; keep `select` only for side-by-side diagnostics.
2. Fill black skin holes first, but exclude eyes, mouth, brows, nostrils, scalp,
   and clothing from skin diffusion.
3. Repair forehead tone as lighting/tone mismatch, not as automatic hair
   removal. Preserve valid forehead detail.
4. Repair mouth/lips, eyes/brows, neck/lower leakage, ears/side-face, and
   scalp/hairline as separate material regions.
5. Apply only mild final color smoothing after the individual repairs are
   visually accepted.

Current private Step 6 output:

```text
<private_drive>/hair_app/output/facebuilder_mask_aware_step6/20260701_153519
```

Implemented sub-steps:

```text
v00_baseline = Step 5 blend texture
v01_hard_skin_holes = conservative black-hole skin fill
v02_forehead_tone = central forehead tone normalization
v03_forehead_uniform_tone = diagnostic forehead uniform-tone replacement
v04_forehead_redefined_region = forehead region redefinition plus hair-leftover fill
v04b_eyebrow_hairline_refine = component-scored fixed black eyebrow mask plus symmetric broad hairline lift
```

v01 logic:

- use Step 5 `blend` as the baseline;
- detect reliable observed skin from non-completion texels and broad skin-color
  gates;
- only consider `COMPLETION_NEEDED` texels that sit very close to reliable
  skin after a small skin-mask closing pass;
- protect dark completion-needed feature regions near skin, shown in magenta in
  the UV review sheet;
- fill only tiny remaining dot-like holes from the nearest reliable skin pixel;
- smooth only the changed texels locally;
- leave eyes, mouth, brows, nostrils, scalp, and clothing effectively
  untouched.

Observed v01 metrics at 1024 atlas:

| Person | Filled texels | Feature-protected texels | Read |
| --- | ---: | ---: | --- |
| Juseop | 39 | 80,403 | Safe but visually tiny change |
| Eunchae | 13 | 85,922 | Safe but visually tiny change |

Interpretation:

- The first naive v01 attempt filled thousands of texels but touched eye-region
  candidates, so it was rejected.
- The accepted v01 is deliberately conservative. It does not materially improve
  the current look, but it establishes a safe rule: skin-hole filling must not
  leak into eyes, lips, brows, nostrils, scalp, or clothing.

v02 logic:

- keep Step 5 `blend` as the baseline and apply v01 first;
- build a feature guard for eyes, brows, mouth/lip gaps, nostrils, hairline,
  scalp boundary, and other dark feature-like islands;
- select only the central forehead component, instead of every skin-colored UV
  island inside a rectangular atlas window;
- reject side/ear islands with a connected-component filter;
- estimate a target forehead tone from reliable forehead skin, tempered by
  midface skin;
- write `light`, `medium`, and `strong` texture variants plus UV and render
  review sheets.

Observed v02 metrics at 1024 atlas:

| Person | Forehead skin texels | Tone candidates | Forehead components kept | Medium changed texels | Read |
| --- | ---: | ---: | ---: | ---: | --- |
| Juseop | 13,220 | 4,309 | 1 / 9 | 10,157 | Safe mask, small visual gain |
| Eunchae | 11,468 | 6,514 | 1 / 3 | 10,168 | Safe mask, small visual gain |

Interpretation:

- v02 successfully narrowed the repair region to the central forehead and
  stopped the earlier broad ROI from touching ears, nose, cheeks, or lower face.
- Visual improvement is limited. The forehead patch shape remains visible
  because tone normalization changes color but does not replace the underlying
  contaminated/patchy texture structure.

v03 logic:

- use the v01 output as the before baseline;
- build a narrower forehead ROI and keep only the central forehead component;
- exclude the lower eye/brow feature guard and hairline boundary from the
  edited forehead skin;
- for Juseop only, read app-scan hairline frames as a boundary hint only;
  scan pixels are never used as texture/color/bake input;
- compute the target color from reliable non-forehead face skin, mainly the
  stable midface/cheek area;
- replace selected forehead skin toward that uniform target color;
- write a compact main review sheet with only before front/left45/right45,
  after front/left45/right45, and area front/left45/right45. UV maps remain
  debug-only and are not part of the main human review.

v03 color legend in the compact review sheet:

```text
green  = edited forehead skin
yellow = hairline edge visual hint
blue   = eye/brow guard, not edited as forehead skin
dark   = not touched by v03
```

Observed v03 metrics at 1024 atlas:

| Person | Edited forehead texels | Reference face texels | Scan hairline hint | Read |
| --- | ---: | ---: | --- | --- |
| Juseop | 14,974 | 49,419 | yes, boundary only | Patchiness reduced, but forehead becomes too flat |
| Eunchae | 13,566 | 28,510 | no | Patchiness reduced, but flat patch/edge remains visible |

v03 interpretation:

- v03 confirms that forcing the forehead to a single non-forehead skin tone can
  remove much of the noisy patch structure.
- It is not final quality. The result looks artificial because the forehead
  loses local detail and the boundary between edited/un-edited skin remains too
  hard.
- The next useful Step 6 sub-step should keep v03 as a diagnostic reference,
  then add edge blending/detail recovery or region-aware inpainting before
  moving to mouth/lips and eye/brow material repair.

v04 logic:

- restart from the accepted v01 texture instead of building on the already-flat
  v03 texture;
- keep the v03-style uniform-tone replacement idea, but redefine the forehead
  by position instead of by "already skin-looking" pixels;
- fit a smooth, human-like hairline curve from the observed upper-face skin
  boundary and the Juseop scan hairline hint when available;
- use scan frames only as a hairline boundary hint, never as texture/color/bake
  input;
- define forehead as upper face below the smooth predicted hairline and above
  or around the eye/brow guard;
- include black/hair/non-skin leftovers inside that forehead region and fill
  them as forehead instead of leaving them black;
- keep eyes and eyebrows protected as blue guard regions;
- write the same compact before/after/area render review sheet. UV/debug maps
  stay private diagnostics.

v04 color legend in the compact review sheet:

```text
green  = redefined forehead region
orange = hair/black/non-skin leftovers filled as forehead
yellow = smooth predicted hairline
blue   = eye/brow guard, not edited as forehead skin
dark   = not touched by v04
```

Observed v04 metrics at 1024 atlas:

| Person | Forehead region texels | Filled hair/black texels | Reference face texels | Hairline hint | Read |
| --- | ---: | ---: | ---: | --- | --- |
| Juseop | 25,855 | 6,201 | 45,545 | scan boundary hint used | Better region definition; right eyebrow-side hair remnant is now included, but forehead remains flat |
| Eunchae | 23,009 | 7,694 | 26,087 | no scan hint | Wider forehead fill works, but flat material and hard boundary remain |

v04 interpretation:

- v04 matches the revised product intent better than v03: if a pixel is in the
  upper-face forehead region, hair leftovers should be removed and filled as
  skin.
- The smooth hairline curve is more human-like than the previous jagged
  observed edge, but it is still a geometric prediction and must be reviewed.
- v04 is still not final quality. It solves region definition better than v03,
  but it increases the flat-forehead/material problem. The next pass should
  focus on edge blending, skin-detail recovery, and making the filled forehead
  look less like one flat patch.

v04b logic:

- restart from v01, like v04;
- keep the v04 broader forehead definition;
- strengthen eye/eyebrow protection with a component-scored eyebrow source
  check. The older area-based source selection was rejected because a large
  dark hair/occlusion blob can be larger than the real eyebrow;
- score each eyebrow candidate by position in the brow band, width, height,
  area, aspect ratio, and high/hairline-touch penalties;
- if one side is good and the other is bad or missing, discard the bad/missing
  side and mirror only the good component. If both sides are good and similar,
  keep the component masks. This stage still does not color-transfer eyebrow
  texture because eye/brow material repair is a later stage;
- keep Juseop app-scan frames as hairline-boundary hints only, never as
  texture/color/bake input;
- first fit the smooth predicted hairline, reduce the front curvature so it is
  less like a perfect circular arc, then perform a second pass: if reliable
  forehead-skin pixels exist above that first line, use those pixels as lift
  evidence but mirror the lift amount across the front segment so one-sided
  evidence cannot create a one-sided hairline;
- keep the main review sheet compact: before v01, after v04b, area map, and a
  bottom row for the second-pass hairline correction at front/left45/right45.

v04b compact review colors:

```text
area row:
green  = redefined forehead region
orange = hair/black/non-skin leftovers filled as forehead
yellow = final second-pass hairline
blue   = eye/brow guard
cyan   = fixed black symmetric eyebrow mask
dark   = not touched by v04b

2nd hairline row:
purple = first-pass smooth hairline
yellow = second-pass lifted hairline
cyan   = reliable forehead skin used as broad-lift evidence
green  = resulting forehead region
blue   = eye/brow guard
```

Observed v04b metrics at 1024 atlas:

| Person | Forehead region texels | Filled hair/black texels | Symmetric eyebrow texels | Hairline lift columns | Max hairline lift px | Read |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Juseop | 26,448 | 6,428 | 1,708 | 197 supported / 312 smoothed | 43.61 | Brow source is the smaller good component (`61x16`) mirrored to both sides; front hairline lift is symmetric |
| Eunchae | 22,146 | 6,104 | 1,838 | 135 supported / 212 smoothed | 63.43 | Right good brow component (`63x16`) is mirrored; lower face and neck still need separate repair |

v04b interpretation:

- v04b fixes the specific failure seen after the first v04b attempt: a large
  dark blob is no longer automatically considered the best eyebrow. For Juseop,
  the selected source is component `label=4`, side `left`, score `4.85`,
  bbox `[434, 417, 495, 433]`.
- The second-pass hairline now still uses observed skin above the first smooth
  curve as evidence, but the actual lift is mirrored across the frontal segment
  before rendering the final hairline. This prevents the previous one-sided
  lift artifact.
- This is still not final quality. The forehead repair remains a broad tone
  replacement and needs edge blending plus skin-detail recovery before moving
  on to mouth, eyes, neck, ears, and scalp.
