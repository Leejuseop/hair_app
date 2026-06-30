# Hair App New-Chat Handoff

Last synchronized: 2026-06-28

Expected branch: `main`

Current source of truth:

- product/system plan: `docs/10_3d_hair_app_master_plan.md`
- chronological log: `docs/history.md`
- current head-engine bridge: `experiments/facebuilder_bridge/README.md`
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

The project has pivoted from "custom Texture Baker is the main head-quality
path" to "FaceBuilder/KeenTools inside headless Blender is the main
face/head-engine candidate."

Pixel3DMM/FLAME and Texture Baker v1/v2/v3 are still useful:

- they document what failed and why;
- they provide review-sheet tooling and texture-completion lessons;
- they remain backup/baseline research.

But the visible quality from the custom texture baker is currently far below
the product bar, so do not spend more time tuning it unless the user explicitly
asks.

## 3. Product Target

Input stays simple:

```text
ordinary user selfies + in-app scan frames
```

No strict photo guide should be required from users. The product should aim for:

- front to about 45-degree likeness;
- plausible scalp/head shape for hair try-on;
- clean bald-head substrate;
- hidden rear-head/scalp handled with plausible fallback;
- interactive mobile GLB preview.

The goal is a hair-app avatar, not a perfect measured 3D scan.

## 4. FaceBuilder Automation Status

Verified locally on 2026-06-27 and updated on 2026-06-28:

- Blender path: `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`
- Blender version: 5.1.2
- KeenTools version observed: 2026.2.0
- `pykeentools` imports successfully in background Blender.
- FaceBuilder object creation works in background Blender.
- `detect_faces`, `detect_face_pose`, preset pin solving, and TextureBuilder
  are script-reachable.
- Existing user-created `C:\Users\User\Desktop\blender.blend` could be probed.
- Re-aligning an already pinned camera succeeded.
- Among five unpinned cameras in that blend, four auto-align attempts succeeded
  and one failed with no detected face, likely an eyeglasses photo.
- Empty-scene automation v0 succeeded from a private Juseop photo folder with
  two selected photos: one aligned, one failed face detection, texture baking
  succeeded, and a private `.blend` was saved.
- Texture bake parity with the Blender UI `Create Texture` button was fixed.
  The old headless raw bake differed from the user's manual `ha.png` by mean
  RGB error about `18.14`; after matching FaceBuilder's UI camera/projection
  update path, the difference dropped to about `0.12`.
- The old private v1/v2/v3 outputs were retired because they were generated
  before this texture-bake parity fix and with an over-aggressive cleanup pass.
  Representative private review sheets were archived at:
  `G:\내 드라이브\hair_app\output\history_archive\retired_facebuilder_v1_v2_v3_20260628\`.
- The later FaceBuilder v1/v2/v3/v4 color-mute ablation was also retired
  because the preprocessor filled rejected regions with skin-like colors. That
  made fake skin enter the FaceBuilder texture bake and polluted the result.
  Its private bulk outputs were moved to:
  `G:\내 드라이브\hair_app\output\history_archive\retired_facebuilder_color_mute_v1_v4_20260628T091346Z\`.
- Current FaceBuilder semantic ablation runs through
  `experiments/facebuilder_semantic_ablation/run_facebuilder_semantic_ablation.py`.
  It reuses the previous Pixel3DMM V4 crop/FaRL segmentation artifacts instead
  of inventing a new crop/segmentation engine.
- Current version definitions:
  - `semantic_v1`: raw V4-validated photos + raw FaceBuilder texture.
  - `semantic_v2`: V4 FaceBoxes crops + raw FaceBuilder texture.
  - `semantic_v3`: V4 FaceBoxes crops for alignment plus sentinel-colored FaRL
    semantic texture inputs.
- Latest private semantic batch summary:
  - Juseop: 19 input rows; 9 scan frames are alignment-only by default; 10
    selfie rows enter texture bake.
  - Eunchae: 8 input rows; all 8 enter texture bake.
  - All six version/person runs have `.blend`, OBJ, GLB, baked texture, cleanup
    texture, yaw renders, `run_manifest.json`, and `semantic_review_sheet.png`.
- Private review sheets:
  - `G:\내 드라이브\hair_app\output\_preprocess_review\juseop\juseop_crop_segmentation_sentinel_review.png`
  - `G:\내 드라이브\hair_app\output\_preprocess_review\eunchae\eunchae_crop_segmentation_sentinel_review.png`
  - `G:\내 드라이브\hair_app\output\_comparison\facebuilder_semantic_v1_v3\facebuilder_semantic_v1_v3_comparison.png`
- Visual conclusion: crop is useful and v2 is a cleaner controlled baseline
  than raw v1. Sentinel v3 is not a usable final look; it proves FaceBuilder
  consumes/blends the colored bad-region pixels. The next real improvement is
  semantic post-bake repair and better occlusion masks, not another skin-color
  fill before bake.

Private v0 outputs were written under:

```text
C:\Users\User\Desktop\hair_app\private_outputs\facebuilder_bridge\
```

That folder is ignored by Git.

## 5. Current FaceBuilder Bridge Code

Tracked tools:

- `experiments/facebuilder_bridge/inspect_facebuilder_export.py`
- `experiments/facebuilder_bridge/blender_facebuilder_smoke.py`
- `experiments/facebuilder_bridge/blender_facebuilder_scene_probe.py`
- `experiments/facebuilder_bridge/blender_facebuilder_auto_scene_v0.py`
- `experiments/facebuilder_bridge/facebuilder_version_runner.py`
- `experiments/facebuilder_bridge/blender_facebuilder_batch_scene.py`
- `experiments/facebuilder_semantic_ablation/run_facebuilder_semantic_ablation.py`

These scripts are still research/bridge code, not production job orchestration.
They now prove that FaceBuilder, crop reuse, semantic sentinel preprocessing,
OBJ/GLB export, and review-sheet generation can be run without manual Blender
clicking.

## 6. Next Work Plan

Immediate next stage:

1. Continue the active mask-aware FaceBuilder correction path in
   `experiments/facebuilder_mask_aware_correction/`.
   - Step 0 scene probe completed:
     `G:\내 드라이브\hair_app\output\facebuilder_mask_aware_step0\20260629_194117`
   - Step 1 reprojection completed:
     `G:\내 드라이브\hair_app\output\facebuilder_mask_aware_step1\20260629_195513`
   - Step 2 UV visibility completed:
     `G:\내 드라이브\hair_app\output\facebuilder_mask_aware_step2\20260629_200519`
   - Step 3 mask scaffold/current v0 completed:
     `G:\내 드라이브\hair_app\output\facebuilder_mask_aware_step3\20260629_203236`

2. Run the Colab cells in:
   `experiments\facebuilder_mask_aware_correction\STEP3_COLAB.md`
   to generate:
   - FaceXFormer parser labels for `v1_facexformer_only`;
   - Grounded SAM2 object masks for `v2_farl_grounded_sam`;
   - both together for `v3_facexformer_grounded_sam`.

3. After Colab writes masks to
   `G:\내 드라이브\hair_app\output\facebuilder_mask_aware_step3_external`,
   rerun:
   `python experiments\facebuilder_mask_aware_correction\run_step3_masks.py --source-version facebuilder_semantic_v2`
   and review the four Step 3 versions side by side.

4. Use the best Step 3 mask version with Step 2 UV visibility for Step 4:
   clean-pixel UV projection and raw-vs-projected texture arbitration.

5. Decide mesh strategy.
   - Option A: use FaceBuilder mesh directly for the hair app.
   - Option B: transfer or retopologize to a more controlled app mesh.
   - Decision depends on export quality, scalp contract, hair collision, and
     GLB/mobile constraints.

6. Only after that, continue hair fitting.
   - hairline-aware root placement;
   - scalp retargeting;
   - collision correction;
   - mobile GLB export and viewer.

### 6.1 2026-06-29 Latest Mask-Aware Status

Current source of truth for the next task:

- Step 3 full mask ablation is complete at
  `<private_drive>\hair_app\output\facebuilder_mask_aware_step3\20260629_212612`.
- Current Step 3 winner for the next stage is `v2_farl_grounded_sam`.
- FaceXFormer remains experimental because it under-segments some nose/skin
  regions on the current private photos.
- Step 4 clean-pixel UV projection is complete at:
  - `<private_drive>\hair_app\output\facebuilder_mask_aware_step4\20260629_221621`
  - `<private_drive>\hair_app\output\facebuilder_mask_aware_step4\20260629_222438`

Step 4 meaning:

- It uses FaceBuilder mesh/cameras/UV plus Step 3 `usable_skin` masks.
- It projects only trusted skin pixels into UV.
- It writes clean projected texture maps, coverage maps, confidence maps,
  source-count maps, per-camera contribution maps, review sheets, and render
  sheets.
- It is not the final texture. It is the clean evidence layer for Step 5.

Next active step:

```text
Step 5: raw FaceBuilder texture vs clean projected texture arbitration
```

Step 5 should keep raw FaceBuilder pixels where they are clean, use clean
projected pixels where they are reliable, blend where both are usable, and mark
eyes, mouth, scalp/hairline, neck, ears, and unresolved holes for completion or
material-specific treatment.

### 6.2 2026-06-30 Step 5 Latest

Step 5 was implemented in:

```text
experiments/facebuilder_mask_aware_correction/run_step5_arbitration.py
```

Current private Step 5 output:

```text
<private_drive>\hair_app\output\facebuilder_mask_aware_step5\20260630_200156
```

Important constraints:

- Do not use FaceBuilder cleanup texture.
- Do not use Step 4 color-corrected texture.
- Use only FaceBuilder raw texture and Step 4 projected raw texture.
- Completion-needed pixels are black in actual Step 5 output textures.

Step 5 outputs:

- `step5_select_texture.png`: BOTH_OK pixels choose the higher-trust source.
- `step5_blend_texture.png`: only BOTH_OK pixels blend raw and Step 4 raw.
- `step5_decision_color_map.png`: red/blue/green/yellow diagnostic map.
- `step5_uv_review_sheet.png`: UV map review.
- `step5_select_render_review_sheet.png`: 3D render for select texture.
- `step5_blend_render_review_sheet.png`: 3D render for blend texture.
- `step5_decision_render_review_sheet.png`: 3D render for decision map.

Decision colors:

- red = CLEAN_ONLY
- blue = RAW_ONLY
- green = BOTH_OK
- yellow = COMPLETION_NEEDED

Observed ratios:

- Juseop: CLEAN_ONLY 0.030, RAW_ONLY 0.028, BOTH_OK 0.165,
  COMPLETION_NEEDED 0.777, BOTH_OK near-tie share 0.797.
- Eunchae: CLEAN_ONLY 0.023, RAW_ONLY 0.012, BOTH_OK 0.103,
  COMPLETION_NEEDED 0.862, BOTH_OK near-tie share 0.788.

Next active step:

```text
Step 6: completion/material-specific repair
```

Step 6 should fill black completion-needed regions by semantic region rather
than reintroducing fake global skin cleanup.

## 7. Privacy/Git Rule

Never commit:

- private photos or scan frames;
- OBJ/MTL/PLY/GLB private exports;
- texture PNGs;
- review renders;
- masks, landmarks, crops, videos, or Drive output folders.

Commit only code, docs, fake examples, and generic manifests.
