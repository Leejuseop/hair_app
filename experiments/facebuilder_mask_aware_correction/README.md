# FaceBuilder Mask-Aware Correction

This experiment keeps FaceBuilder for geometry/camera alignment and replaces
the weak part of the pipeline: texture pixel trust/selection.

Private generated assets belong in Drive only. Do not commit photos, crops,
masks, textures, renders, meshes, GLB/OBJ exports, or review sheets.

## Current Source Baseline

The current source scene is:

```text
G:/내 드라이브/hair_app/output/facebuilder_semantic_v2
```

That baseline uses Pixel3DMM V4 crops for FaceBuilder alignment and raw
FaceBuilder texture baking.

## Step 0: Scene Data Probe

Script:

```text
experiments/facebuilder_mask_aware_correction/run_step0_probe.py
```

Purpose:

- open existing FaceBuilder `.blend` files
- verify mesh, UV, raw texture, OBJ/GLB, camera image paths
- extract camera projection/model matrices
- export triangulated mesh/UV arrays for later rasterization

Latest private output:

```text
G:/내 드라이브/hair_app/output/facebuilder_mask_aware_step0/20260629_194117
```

## Step 1: Reprojection Smoke Test

Script:

```text
experiments/facebuilder_mask_aware_correction/run_step1_reprojection.py
```

Purpose:

- project the solved FaceBuilder head mesh back onto each input crop image
- verify that eyes/nose/mouth/jaw roughly line up

Latest private output:

```text
G:/내 드라이브/hair_app/output/facebuilder_mask_aware_step1/20260629_195513
```

## Step 2: UV Visibility

Script:

```text
experiments/facebuilder_mask_aware_correction/run_step2_uv_visibility.py
```

Purpose:

- compute which UV atlas regions each input image can see
- estimate per-camera view-angle confidence
- build per-camera and combined UV coverage/source-count maps

Latest private output:

```text
G:/내 드라이브/hair_app/output/facebuilder_mask_aware_step2/20260629_200519
```

## Step 3: Parser/Object Mask Ablation

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
G:/내 드라이브/hair_app/output/facebuilder_mask_aware_step3/20260629_203236
```

Current state:

- `v0_farl_only` is ready for Juseop/Eunchae.
- `v1_facexformer_only` waits for Colab FaceXFormer label masks.
- `v2_farl_grounded_sam` waits for Colab Grounded SAM object masks.
- `v3_facexformer_grounded_sam` waits for both external outputs.

Colab cells:

```text
experiments/facebuilder_mask_aware_correction/STEP3_COLAB.md
```

After Colab writes external masks to:

```text
G:/내 드라이브/hair_app/output/facebuilder_mask_aware_step3_external
```

rerun:

```powershell
python experiments\facebuilder_mask_aware_correction\run_step3_masks.py --source-version facebuilder_semantic_v2
```

## Latest Status: Step 3 and Step 4

The older Step 3 status above is retained as historical context. The current
working Step 3 output is:

```text
G:/???쒕씪?대툕/hair_app/output/facebuilder_mask_aware_step3/20260629_212612
```

Current Step 3 state:

- `v0_farl_only`, `v1_facexformer_only`, `v2_farl_grounded_sam`,
  and `v3_facexformer_grounded_sam` are all ready for comparison.
- Current working parser/object-mask candidate is `v2_farl_grounded_sam`.
- FaceXFormer remains experimental because it under-segments some nose/skin
  regions compared with FaRL.
- Grounded SAM is used conservatively: broad face/head/hair detections and
  oversized masks are rejected before object masks enter `usable_skin`.

## Step 4: Clean-Pixel UV Projection

Scripts:

```text
experiments/facebuilder_mask_aware_correction/blender_step4_uv_sample_coords.py
experiments/facebuilder_mask_aware_correction/blender_step4_render_texture.py
experiments/facebuilder_mask_aware_correction/run_step4_clean_projection.py
```

Purpose:

- keep FaceBuilder's solved head mesh and per-photo cameras
- build UV texel to image-pixel coordinate maps in Blender
- sample only Step 3 `v2_farl_grounded_sam` usable-skin pixels in host Python
- write raw and median color-corrected clean projected textures
- write diagnostic coverage, confidence, source-count, and best-source-camera maps
- create atlas review sheets, source contribution sheets, and overlay render sheets

Current private outputs:

```text
texture-camera-only:
G:/???쒕씪?대툕/hair_app/output/facebuilder_mask_aware_step4/20260629_221621

include-alignment-cameras:
G:/???쒕씪?대툕/hair_app/output/facebuilder_mask_aware_step4/20260629_222438
```

Current observations:

- Texture-camera-only Step 4 removes a lot of raw FaceBuilder contamination, but
  coverage is still sparse: Juseop about 19.9%, Eunchae about 15.5% at 1024 atlas.
- Including Juseop alignment/scan cameras increases Juseop coverage to about
  23.2% and gives stronger frontal evidence, but also introduces cooler scan
  lighting that must be handled in Step 5.
- Eunchae has no extra alignment-only scan set in this baseline, so both Step 4
  variants are effectively the same for her.
- The output is not a final texture. Eye, mouth, hairline/scalp, neck, and
  low-confidence regions still need arbitration/completion.

## Step 5: Raw-vs-Clean Arbitration

Script:

```text
experiments/facebuilder_mask_aware_correction/run_step5_arbitration.py
```

Purpose:

- compare FaceBuilder raw texture against Step 4 `projected_clean_texture_raw`
- do not use `facebuilder_texture_bald_cleanup.png`
- do not use Step 4 `projected_clean_texture_color_corrected`
- classify every UV texel into four decision categories
- produce two outputs:
  - `select`: BOTH_OK texels choose the higher-trust source
  - `blend`: only BOTH_OK texels blend raw and Step 4 projected raw
- leave COMPLETION_NEEDED texels black in both output textures
- render the select texture, blend texture, and decision color map on the
  FaceBuilder mesh

Decision colors:

```text
red    = CLEAN_ONLY, Step 4 projected raw is trusted and raw is not
blue   = RAW_ONLY, raw FaceBuilder texture is trusted and Step 4 is weak/absent
green  = BOTH_OK, both sources are acceptable
yellow = COMPLETION_NEEDED, neither source is trusted; output texture is black
```

Current private Step 5 output:

```text
<private_drive>/hair_app/output/facebuilder_mask_aware_step5/20260630_200156
```

Current Step 5 observations:

- Cleanup texture is explicitly excluded.
- Step 4 color-corrected texture is explicitly excluded.
- Raw texture is only allowed where Step 4 had at least some projected clean
  skin support. This prevents raw hair/clothing/background from filling unknown
  UV regions too aggressively.
- Juseop category ratios at 1024 atlas:
  - CLEAN_ONLY: 0.030
  - RAW_ONLY: 0.028
  - BOTH_OK: 0.165
  - COMPLETION_NEEDED: 0.777
  - BOTH_OK near-tie 40:60-60:40: 0.797 of BOTH_OK
- Eunchae category ratios at 1024 atlas:
  - CLEAN_ONLY: 0.023
  - RAW_ONLY: 0.012
  - BOTH_OK: 0.103
  - COMPLETION_NEEDED: 0.862
  - BOTH_OK near-tie 40:60-60:40: 0.788 of BOTH_OK

Current next step:

```text
Step 6: completion/material-specific repair
```

Step 6 should fill/repair the black completion-needed regions by semantic
region: scalp/hairline, skin gaps, neck, ears, eyes, mouth, lips, nostrils,
brows, and other material-specific areas.
