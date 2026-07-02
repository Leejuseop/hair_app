# Hair App New-Chat Handoff

Last synchronized: 2026-07-01

Expected branch: `main`

Current source of truth:

- product/system plan: `docs/10_3d_hair_app_master_plan.md`
- chronological log: `docs/history.md`
- active mask-aware correction: `experiments/facebuilder_mask_aware_correction/README.md`
- FaceBuilder automation bridge: `experiments/facebuilder_bridge/README.md`
- older Pixel3DMM and Texture Baker details: archived inside `docs/history.md`

## 1. Resume Checklist

At the start of a new chat:

1. run `git status --short --branch --ignored`;
2. read `AGENTS.md`;
3. read this file;
4. inspect the relevant source code before trusting any summary;
5. keep private photos, meshes, textures, masks, landmarks, and renders out of
   Git.

## 2. Current Decision

The project has pivoted from custom Pixel3DMM/FLAME Texture Baker as the main
quality path to FaceBuilder/KeenTools inside headless Blender as the main
face/head-engine candidate.

Pixel3DMM/FLAME and Texture Baker v1/v2/v3 are still useful as history,
review-sheet tooling, and fallback research. Do not spend more time tuning them
unless the user explicitly asks.

## 3. Product Target

Input stays simple:

```text
ordinary user selfies + in-app scan frames
```

The product target is a hair-app avatar, not a perfect measured 3D scan:

- front to about 45-degree likeness;
- plausible scalp/head shape for hair try-on;
- clean bald-head substrate;
- hidden rear-head/scalp handled with plausible fallback;
- interactive mobile GLB preview.

## 4. FaceBuilder Automation Status

Verified locally:

- Blender path: `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`
- Blender version: 5.1.2
- KeenTools version observed: 2026.2.0
- `pykeentools` imports successfully in background Blender.
- FaceBuilder object creation works in background Blender.
- `detect_faces`, `detect_face_pose`, preset pin solving, and TextureBuilder
  are script-reachable.
- Texture bake parity with the Blender UI `Create Texture` button was fixed.
  The old headless raw bake differed from the user's manual `ha.png` by mean
  RGB error about `18.14`; after matching FaceBuilder's UI camera/projection
  update path, the difference dropped to about `0.12`.

Retired paths:

- old FaceBuilder v1/v2/v3 outputs: generated before texture-bake parity fix
  and with over-aggressive cleanup.
- later v1/v2/v3/v4 color-mute outputs: rejected regions were filled with
  skin-like color, which polluted texture bake.
- Stable-Hair stage-1 bald conversion probe: A100 run completed, but visual
  quality was too poor for the current FaceBuilder texture path.

## 5. Active Mask-Aware Correction Status

Experiment folder:

```text
experiments/facebuilder_mask_aware_correction/
```

Completed:

- Step 0: scene data probe.
- Step 1: reprojection smoke test.
- Step 2: UV visibility maps.
- Step 3: parser/object-mask ablation.
- Step 4: clean-pixel UV projection.
- Step 5: raw-versus-clean texture arbitration.
- Step 6 v00/v01: baseline plus conservative hard black skin-hole fill.
- Step 6 v02: central forehead tone normalization.
- Step 6 v03: diagnostic forehead uniform-tone replacement.
- Step 6 v04: forehead region redefinition plus hair/black leftover fill.
- Step 6 v04b: component-scored fixed black eyebrow mask, symmetric broad
  hairline lift, and eyebrow-baseline forehead definition.

Current Step 3 winner:

```text
v2_farl_grounded_sam
```

Why:

- FaRL remained stronger than FaceXFormer on current nose/skin regions.
- Grounded SAM2 helped with object/occlusion candidates.
- Broad face/head/hair detections and oversized masks are rejected before they
  enter `usable_skin`.
- Current user review: the Juseop forehead artifact does not look like hair
  pixels passing through the mask. It is more likely valid skin with baked
  lighting/tone mismatch.

Active Step 4 output for texture correction:

```text
<private_drive>\hair_app\output\facebuilder_mask_aware_step4\20260629_221621
```

Important:

- This is texture-camera-only.
- Do not use the scan/alignment-included Step 4 root as active texture input:
  `<private_drive>\hair_app\output\facebuilder_mask_aware_step4\20260629_222438`
  is diagnostic only.

Active Step 5 output:

```text
<private_drive>\hair_app\output\facebuilder_mask_aware_step5\20260630_213625
```

Step 5 constraints:

- Do not use FaceBuilder cleanup texture.
- Do not use Step 4 color-corrected texture.
- Use FaceBuilder raw texture and Step 4 projected raw texture.
- Completion-needed pixels are black in actual Step 5 output textures.

Step 5 output meanings:

- `step5_select_texture.png`: BOTH_OK pixels choose the higher-trust source.
- `step5_blend_texture.png`: only BOTH_OK pixels blend raw and Step 4 raw.
- `step5_decision_color_map.png`: red/blue/green/yellow diagnostic map.
- red = CLEAN_ONLY
- blue = RAW_ONLY
- green = BOTH_OK
- yellow = COMPLETION_NEEDED

Observed ratios:

- Juseop: CLEAN_ONLY 0.007, RAW_ONLY 0.030, BOTH_OK 0.156,
  COMPLETION_NEEDED 0.807, BOTH_OK near-tie share 0.781.
- Eunchae: CLEAN_ONLY 0.023, RAW_ONLY 0.012, BOTH_OK 0.103,
  COMPLETION_NEEDED 0.862, BOTH_OK near-tie share 0.788.

Visual read:

- `blend` looks better than `select` and should be the main Step 6 base.
- `select` should remain only as a diagnostic comparison.

Active Step 6 output:

```text
<private_drive>\hair_app\output\facebuilder_mask_aware_step6\20260702_155348
```

Step 6 v01/v02/v03/v04/v04b status:

- Script: `experiments/facebuilder_mask_aware_correction/run_step6_postprocess.py`.
- `v00_baseline` copies/renders Step 5 `blend`.
- `v01_hard_skin_holes` is complete as a very conservative safety pass.
- The first broader v01 attempt was rejected because the changed overlay touched
  eye-region candidates.
- The accepted v01 protects dark feature regions near skin before filling.
- Accepted filled texels at 1024 atlas:
  - Juseop: 39
  - Eunchae: 13
- This tiny visible change is intentional. Do not widen v01 before handling the
  bigger visible artifacts as separate material-specific repairs.
- `v02_forehead_tone` is complete as a safe but weak tone pass.
- v02 first used a too-broad forehead ROI, then was corrected by narrowing the
  ROI and keeping only the central connected forehead component.
- Accepted v02 medium metrics:
  - Juseop: 13,220 forehead skin texels, 4,309 tone candidates, 1/9 components
    kept, 10,157 changed texels.
  - Eunchae: 11,468 forehead skin texels, 6,514 tone candidates, 1/3 components
    kept, 10,168 changed texels.
- Visual judgment: v02 masks are much safer, but the forehead patch shape still
  remains. Tone correction alone is not enough.
- `v03_forehead_uniform_tone` is complete as a diagnostic experiment.
- v03 starts from v01, uses the Step 5 `blend` baseline, replaces selected
  central forehead skin with the average tone of reliable non-forehead face
  skin, and writes compact before/after/area review sheets.
- Juseop scan hairline frames are used only as a hairline boundary hint. Scan
  pixels are not used as texture, color reference, or texture bake input.
- Accepted v03 metrics:
  - Juseop: 14,974 edited forehead texels, 49,419 reference face texels.
  - Eunchae: 13,566 edited forehead texels, 28,510 reference face texels.
- Visual judgment: v03 reduces forehead patchiness, but the forehead becomes
  too flat and the edit boundary remains too hard. Treat v03 as diagnostic, not
  final quality.
- Review-sheet rule going forward: main sheets should be simple. Show before
  front/left45/right45, after front/left45/right45, and optionally area map
  front/left45/right45. Keep UV maps/debug maps out of the main human review.
- `v04_forehead_redefined_region` is complete as a region-definition correction.
- v04 restarts from v01, keeps the v03-style uniform-tone idea, but treats the
  upper-face area below a smooth predicted hairline and outside eyes/brows as
  forehead even when current pixels are black/hair/non-skin leftovers.
- Juseop scan hairline frames remain boundary-only; no scan pixels are used as
  texture/color/bake input.
- Accepted v04 metrics:
  - Juseop: 25,855 forehead-region texels, 6,201 filled hair/black texels,
    45,545 reference face texels.
  - Eunchae: 23,009 forehead-region texels, 7,694 filled hair/black texels,
    26,087 reference face texels.
- Visual judgment: v04 better matches the bald-head goal and includes Juseop's
  right eyebrow-side hair remnant as forehead, but the result is still too flat
  and the edited boundary is still visible.
- `v04b_eyebrow_hairline_refine` is complete and is now the current Step 6
  region/guard baseline.
- v04b strengthens the eye/eyebrow guard with component-scored eyebrow source
  selection. The older area-based source picker was rejected because it could
  copy a larger bad blob instead of the cleaner eyebrow component.
- If one side is good and the other side is bad or missing, the bad/missing
  side is discarded and the good component is mirrored as a fixed black
  symmetric mask. This is only a protection/placeholder boundary, not final
  eyebrow texture.
- v04b also runs a second-pass hairline lift: the front hairline is made less
  circular, and reliable forehead-skin pixels above the first smooth curve can
  broadly lift the front segment. The lift delta is mirrored across the frontal
  segment so one-sided skin evidence cannot produce a one-sided hairline.
- v04b now defines the edited forehead as below the final hairline and above
  the eyebrow baseline, excluding only tight eye/eyebrow guards. This replaced
  the central-component-only definition that left upper hairline/temple
  fragments unedited.
- Accepted v04b metrics:
  - Juseop: 20,252 forehead-region texels, 6,826 filled hair/black texels,
    1,708 symmetric eyebrow texels, max hairline lift 48.63 px. Selected brow
    source is the left `61x16` component, score `4.85`.
  - Eunchae: 22,053 forehead-region texels, 10,223 filled hair/black texels,
    1,838 symmetric eyebrow texels, max hairline lift 62.17 px. Selected brow
    source is the right `63x16` component, score `5.00`.
- Visual judgment: v04b now avoids copying the larger bad eyebrow-like blob and
  makes the front hairline lift symmetric. The eyebrow-baseline forehead rule
  reduces central/upper hairline black remnants. Small side/ear-boundary
  artifacts can still remain and should be handled later in side-face/ear
  repair, not by blindly widening the forehead. It still leaves flat forehead
  material and visible boundaries, so v05 should recover edge/detail.

## 6. Next Active Step: Step 6 v05

Step 6 is material-specific post-processing from the Step 5 `blend` texture.
It should be done one element at a time, with a review sheet after each element.
Do not batch many fixes together.

Planned order:

1. Forehead edge/detail recovery
   - Use v04b's broader forehead region and stronger eye/eyebrow/hairline
     guards as the working definition.
   - Feather the boundary between edited forehead and unedited skin.
   - Reintroduce subtle skin detail from nearby reliable forehead or source
     projections where available.
   - Avoid making the forehead one flat material.
   - Keep eyes, eyebrows, hairline, scalp, mouth, and lower face protected.

2. Mouth and lips
   - Repair mouth interior and lips as separate materials.
   - Do not diffuse cheek skin into the mouth.

3. Eyes and brows
   - Repair eye, eyelid, and brow regions separately.
   - Avoid blending eye whites or brow darkness into skin.

4. Neck and lower leakage
   - Remove shirt/background remnants near lower neck using semantic location,
     decision/source maps, and color outlier checks.
   - Replace only after review confirms useful skin is not being removed.

5. Ears and side face
   - Fill low-confidence ear/side gaps conservatively.
   - Use observed pixels first; use fallback only for missing regions.

6. Scalp and hairline
   - Create plausible scalp material and hairline transition.
   - Keep scalp/hairline separate from forehead skin.

7. Final mild color pass
   - Apply only after individual repairs are accepted.
   - Avoid early global color correction because it hides which sub-step helped.

## 7. Privacy/Git Rule

Never commit:

- private photos or scan frames;
- OBJ/MTL/PLY/GLB private exports;
- texture PNGs;
- review renders;
- masks, landmarks, crops, videos, or Drive output folders.

Commit only code, docs, fake examples, and generic manifests.
