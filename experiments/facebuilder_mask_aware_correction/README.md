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
<private_drive>/hair_app/output/facebuilder_mask_aware_step6/20260701_084010
```

Implemented sub-steps:

```text
v00_baseline = Step 5 blend texture
v01_hard_skin_holes = conservative black-hole skin fill
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
- The next useful Step 6 sub-step is forehead tone repair, because the biggest
  visible artifact is not a small black skin hole.
