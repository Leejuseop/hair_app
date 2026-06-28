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

1. Review the private semantic v1/v2/v3 sheets and GLBs with the user.
   - v1 is the raw FaceBuilder baseline.
   - v2 tests whether V4 crops improve alignment/texture stability.
   - v3 tests whether sentinel colors reveal FaceBuilder's texture source
     behavior.
   - Main remaining issues: hair/scalp patches, eyes, mouth/nostrils, neck/ear
     seams, clothing/background leakage, perfume/hand/phone occlusion leakage,
     and sentinel-color contamination.

2. Replace heuristic input preprocessing and cleanup with semantic post-bake
   repair.
   - Need face/skin/scalp/hair/background/neck/ear masks.
   - Need eye, iris, eyelid, mouth, lip, brow, and nostril materials.
   - Need observed-versus-filled confidence/provenance maps.

3. Reintroduce photo/frame analysis only after the semantic v1/v2/v3 ablation is
   understood.
   - Add robust landmarks, pose/yaw, eye/mouth state, occlusion, segmentation
     confidence, and lighting/color normalization.

4. Decide mesh strategy.
   - Option A: use FaceBuilder mesh directly for the hair app.
   - Option B: transfer or retopologize to a more controlled app mesh.
   - Decision depends on export quality, scalp contract, hair collision, and
     GLB/mobile constraints.

5. Only after that, continue hair fitting.
   - hairline-aware root placement;
   - scalp retargeting;
   - collision correction;
   - mobile GLB export and viewer.

## 7. Privacy/Git Rule

Never commit:

- private photos or scan frames;
- OBJ/MTL/PLY/GLB private exports;
- texture PNGs;
- review renders;
- masks, landmarks, crops, videos, or Drive output folders.

Commit only code, docs, fake examples, and generic manifests.
