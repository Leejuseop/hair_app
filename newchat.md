# Hair App New-Chat Handoff

Last synchronized: 2026-06-27

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

Verified locally on 2026-06-27:

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
- v1/v2/v3 FaceBuilder batches now run for private Juseop/Eunchae folders.
  They write manifests, `.blend`, OBJ, GLB, baked textures, cleanup textures,
  logs, and review sheets under private Drive output folders.
- Latest private batch summary:
  - v1 Juseop: 11 selected, 10 aligned, 1 failed, 10 texture cameras.
  - v1 Eunchae: 8 selected, 7 aligned, 1 failed, 7 texture cameras.
  - v2 Juseop: 7 selected, 6 aligned, 1 failed, 6 texture cameras.
  - v2 Eunchae: 7 selected, 6 aligned, 1 failed, 6 texture cameras.
  - v3 Juseop: 7 selected, 7 aligned, 0 failed, 2 texture cameras.
  - v3 Eunchae: 7 selected, 7 aligned, 0 failed, 1 texture camera.
- v3 uses photo scoring, face-crop candidates, and a texture gate that lets
  frontal/color-clean crops contribute to texture while profile photos can
  still help alignment.

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
They now prove that the v1/v2/v3 comparison loop can be generated without
manual Blender clicking.

## 6. Next Work Plan

Immediate next stage:

1. Review the private v1/v2/v3 sheets and GLBs with the user.
   - v3 is the current best automated baseline.
   - It is still not product quality.
   - Main remaining issues: hair/scalp patches, eyes, mouth/nostrils, neck/ear
     seams, and occasional texture leakage.

2. Replace heuristic cleanup with semantic post-processing.
   - Need face/skin/scalp/hair/background/neck/ear masks.
   - Need eye, iris, eyelid, mouth, lip, brow, and nostril materials.
   - Need observed-versus-filled confidence/provenance maps.

3. Improve photo/frame analysis before FaceBuilder.
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
