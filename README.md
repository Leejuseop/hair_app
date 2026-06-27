# Hair App

Hair App is a research/product prototype for building a personal bald head and
hair try-on experience from ordinary selfies plus an in-app face/head scan.

The product target is not a perfect forensic 360-degree scan. The useful target
is a believable personal head for hairstyle preview:

- strong likeness from the front through about 45 degrees;
- good enough head shape for hair placement, hairline judgment, and collision;
- plausible fallback for hidden scalp/rear-head regions;
- honest separation between observed photo evidence and inferred material;
- mobile-friendly GLB delivery for interactive viewing.

## Current Direction

As of 2026-06-28, the main face/head engine candidate is:

```text
ordinary selfies + app scan frames
  -> automated FaceBuilder/KeenTools solve inside headless Blender
  -> private raw FaceBuilder mesh and texture
  -> optional texture-input preprocessing
  -> optional texture-output post-processing
  -> mobile GLB + review sheets
```

The earlier Pixel3DMM/FLAME + custom Texture Baker path remains valuable as a
research baseline and backup, but it is no longer the main quality path right
now. Texture Baker v1/v2/v3 proved useful for understanding UV evidence,
visibility, completion, and review tooling, but the visible identity quality is
far below product standard.

The current working hypothesis is that FaceBuilder gives a stronger automated
geometry-and-texture starting point, while Hair App should own:

- camera/projection-faithful FaceBuilder automation;
- texture-input preprocessing before bake;
- texture-output post-processing after bake;
- hairline/scalp preparation;
- hair fitting, collision, and GLB export;
- privacy-safe storage and deletion.

## Verified Locally

The following automation checks have been completed on the local Windows
machine:

- Blender 5.1.2 runs in background mode.
- KeenTools 2026.2.0 loads in headless Blender.
- The local `pykeentools` core imports successfully.
- A FaceBuilder head can be constructed from script.
- `detect_faces`, `detect_face_pose`, preset pin solving, and TextureBuilder
  APIs are reachable from script.
- An existing user-made FaceBuilder `.blend` scene can be inspected and partly
  auto-aligned in background mode.
- A new empty Blender scene can be created from a private photo folder, add
  photos as FaceBuilder cameras, auto-align at least one photo, bake a texture,
  and save a private `.blend`.
- FaceBuilder texture automation now matches the Blender UI `Create Texture`
  path for the tested Juseop 10-photo case. The old automated raw bake differed
  from the manual texture by mean RGB error about `18.14`; after restoring the
  UI-equivalent camera/projection/focal updates, the difference fell to about
  `0.12`.
- The old FaceBuilder v1/v2/v3 outputs were retired because they were generated
  before the texture-bake parity fix and with an over-aggressive cleanup pass.
- New private FaceBuilder v1/v2/v3/v4 batches run for Juseop and Eunchae,
  write Drive outputs, export OBJ/GLB, and build individual plus cross-version
  review sheets.

Private test outputs are written under `private_outputs/` and are ignored by
Git. Current FaceBuilder version outputs are written under the private Drive
layout:

```text
<drive_root>/output/facebuilder_v1/<person>/
<drive_root>/output/facebuilder_v2/<person>/
<drive_root>/output/facebuilder_v3/<person>/
<drive_root>/output/facebuilder_v4/<person>/
<drive_root>/output/_comparison/facebuilder_v1_v4/
<drive_root>/output/facebuilder_versions_summary.md
```

## Implemented Repository Pieces

Product-side implementation already includes:

- React 18 + Vite mobile-first frontend;
- browser camera capture;
- MediaPipe Face Landmarker guidance;
- guided scan steps: `front`, `left_45`, `right_45`, `left_profile`,
  `right_profile`, `hairline`;
- FastAPI `POST /api/scan`;
- file-based scan storage;
- backend-created `selected_3dmm/` reconstruction input bundles;
- `base_profile.json` version `0.2`.

Research-side implementation includes:

- Pixel3DMM V4 research notebook and freeze utilities;
- Texture Baker v1/v2/v3 experiments and review sheets;
- FaceBuilder bridge scripts for export inspection, headless smoke testing,
  scene probing, empty-scene automation, v1/v2/v3/v4 batch comparison, private
  review outputs, and GLB export.

## Not Implemented Yet

- production selfie upload and automatic photo scoring UI;
- production FaceBuilder job orchestration;
- semantic scalp/skin/occlusion masks for FaceBuilder post-processing;
- clean eye/mouth/scalp materials after FaceBuilder export;
- hair reconstruction or imported hairstyle processing;
- scalp retargeting and collision correction;
- production GLB builder/viewer;
- production privacy, retention, deletion, auth, billing, and deployment.

## Important Privacy Rule

Never commit private biometric data or generated private assets:

- selfies and scan frames;
- landmarks, masks, crops, tracking frames;
- private meshes, OBJ/MTL/PLY/GLB files;
- textures, renders, review sheets, videos;
- private Drive or local output folders.

Allowed in Git:

- source code;
- documentation;
- scripts that operate on private data;
- JSON schema/manifest examples with fake or generic paths.

Ignored private folders:

```text
private_exports/
private_outputs/
```

## Key Documents

- `newchat.md`: compact handoff for the next chat.
- `AGENTS.md`: working rules for coding agents.
- `docs/10_3d_hair_app_master_plan.md`: full product/system plan.
- `docs/history.md`: chronological decisions, detailed experiment log, and
  archived old-engine docs for Pixel3DMM/FLAME and Texture Baker.
- `experiments/facebuilder_bridge/README.md`: current FaceBuilder automation
  bridge and commands.

## Next Immediate Work

1. Review the private v1/v2/v3/v4 FaceBuilder sheets and GLBs.
2. Replace the current heuristic texture-input preprocessing with semantic
   masks. The first same-size preprocessed-photo pass reduces some background
   and hair leakage but creates visible neutral-color patches, so it is not yet
   product quality.
3. Build semantic post-processing around the FaceBuilder output:
   scalp/hair/skin/neck/ear/eye/mouth/occlusion masks, not only color
   heuristics.
4. Improve the bald-head substrate: remove remaining hair/background/shirt
   leakage, fill scalp and rear head with plausible skin, and add clean
   eye/mouth materials.
5. Decide whether FaceBuilder exported mesh can be used directly for the hair
   app, or whether a transfer/retopology step is required.
6. After the bald head is credible, move to hair asset reconstruction/fitting,
   collision, and mobile GLB viewer work.
