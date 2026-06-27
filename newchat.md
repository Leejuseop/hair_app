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
- New v1/v2/v3/v4 FaceBuilder batches now run for private Juseop/Eunchae
  folders. They write manifests, `.blend`, OBJ, GLB, baked textures, cleanup
  textures, logs, individual review sheets, and cross-version comparison sheets
  under private Drive output folders.
- Current version definitions:
  - `v1`: original photos + raw FaceBuilder texture.
  - `v2`: original photos for auto-align, same-size preprocessed photos for
    texture bake, raw FaceBuilder texture material.
  - `v3`: original photos + postprocessed cleanup texture material.
  - `v4`: preprocessed texture photos + postprocessed cleanup texture material.
- Latest private batch summary:
  - v1 Juseop: 11 selected, 10 aligned, 1 failed, 10 texture cameras.
  - v1 Eunchae: 8 selected, 7 aligned, 1 failed, 7 texture cameras.
  - v2 Juseop: 11 selected, 10 aligned, 1 failed, 10 texture cameras.
  - v2 Eunchae: 8 selected, 7 aligned, 1 failed, 7 texture cameras.
  - v3 Juseop: 11 selected, 10 aligned, 1 failed, 10 texture cameras.
  - v3 Eunchae: 8 selected, 7 aligned, 1 failed, 7 texture cameras.
  - v4 Juseop: 11 selected, 10 aligned, 1 failed, 10 texture cameras.
  - v4 Eunchae: 8 selected, 7 aligned, 1 failed, 7 texture cameras.
- Cross-version comparison sheets:
  - `G:\내 드라이브\hair_app\output\_comparison\facebuilder_v1_v4\juseop_facebuilder_v1_v4_comparison.png`
  - `G:\내 드라이브\hair_app\output\_comparison\facebuilder_v1_v4\eunchae_facebuilder_v1_v4_comparison.png`
- Visual conclusion: v1 is now the correct raw FaceBuilder baseline. The first
  v2/v4 same-size preprocessing reduces some contamination but creates large
  neutral patches. v3/v4 cleanup is less destructive than before but still not
  product quality. The next improvement needs semantic masks, not broader color
  heuristics.

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

These scripts are still research/bridge code, not production job orchestration.
They now prove that the v1/v2/v3/v4 comparison loop can be generated without
manual Blender clicking.

## 6. Next Work Plan

Immediate next stage:

1. Review the private v1/v2/v3/v4 sheets and GLBs with the user.
   - v1 is the correct raw baseline.
   - v2/v4 preprocessing is not good enough yet; it introduces obvious neutral
     patches.
   - v3/v4 cleanup is useful as a controlled comparison, but still not product
     quality.
   - Main remaining issues: hair/scalp patches, eyes, mouth/nostrils, neck/ear
     seams, clothing/background leakage, and non-semantic over-replacement.

2. Replace heuristic input preprocessing and cleanup with semantic processing.
   - Need face/skin/scalp/hair/background/neck/ear masks.
   - Need eye, iris, eyelid, mouth, lip, brow, and nostril materials.
   - Need observed-versus-filled confidence/provenance maps.

3. Reintroduce photo/frame analysis only after the v1/v2/v3/v4 ablation is
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
