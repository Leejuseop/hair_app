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

As of 2026-06-27, the main face/head engine candidate is:

```text
ordinary selfies + app scan frames
  -> photo/frame scoring and filtering
  -> automated FaceBuilder/KeenTools solve inside headless Blender
  -> private bald-head mesh and texture
  -> Hair App post-processing
  -> mobile GLB + review sheets
```

The earlier Pixel3DMM/FLAME + custom Texture Baker path remains valuable as a
research baseline and backup, but it is no longer the main quality path right
now. Texture Baker v1/v2/v3 proved useful for understanding UV evidence,
visibility, completion, and review tooling, but the visible identity quality is
far below product standard.

The current working hypothesis is that FaceBuilder gives a stronger automated
geometry-and-texture starting point, while Hair App should own:

- input quality scoring;
- automatic retry/reject logic around FaceBuilder alignment;
- post-processing of the exported bald head;
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

Private test outputs are written under `private_outputs/` and are ignored by
Git.

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
  scene probing, empty-scene automation, and private review outputs.

## Not Implemented Yet

- production selfie upload and automatic photo scoring UI;
- production FaceBuilder job orchestration;
- automatic full-photo FaceBuilder solve for all accepted Juseop/Eunchae inputs;
- post-processed bald-head export contract;
- eye/mouth/scalp cleanup after FaceBuilder export;
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
- `docs/history.md`: chronological decisions and experiment log.
- `docs/pixel3dmm_v4.md`: Pixel3DMM/FLAME research baseline.
- `experiments/texture_baker/README.md`: Texture Baker experiment history.
- `experiments/facebuilder_bridge/README.md`: current FaceBuilder automation
  bridge and commands.

## Next Immediate Work

1. Promote `experiments/facebuilder_bridge/blender_facebuilder_auto_scene_v0.py`
   into a v1 batch runner for all accepted Juseop/Eunchae photos.
2. Add photo/frame scoring and automatic reject/retry logic before passing
   frames to FaceBuilder.
3. Generate private review sheets for FaceBuilder outputs from 0, +-15, +-30,
   and +-45 degrees.
4. Define the bald-head post-processing contract: remove hair/shirt/background
   leakage, prepare scalp, eyes, mouth, neck, and material regions.
5. Decide whether FaceBuilder exported mesh can be used directly for the hair
   app, or whether a transfer/retopology step is required.
