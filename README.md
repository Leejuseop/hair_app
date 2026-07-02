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

As of 2026-06-30, the main face/head engine candidate is:

```text
ordinary selfies + app scan frames
  -> automated FaceBuilder/KeenTools solve inside headless Blender
  -> private raw FaceBuilder mesh and texture
  -> mask-aware texture correction from FaceBuilder cameras/UV
  -> material-specific texture post-processing
  -> mobile GLB + review sheets
```

The earlier Pixel3DMM/FLAME + custom Texture Baker path remains valuable as a
research baseline and backup, but it is no longer the main quality path right
now. Texture Baker v1/v2/v3 proved useful for understanding UV evidence,
visibility, completion, and review tooling, but the visible identity quality is
far below product standard.

The current working hypothesis is that FaceBuilder gives a stronger automated
geometry-and-camera starting point, while Hair App should own:

- camera/projection-faithful FaceBuilder automation;
- mask-aware texture trust, repair, and completion after bake;
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
- The later FaceBuilder v1/v2/v3/v4 color-mute batches were also retired: the
  same-size preprocessor filled rejected regions with skin-like color, which
  made the texture bake dirtier rather than cleaner.
- The private FaceBuilder semantic ablation runs for Juseop and
  Eunchae, reusing the previous Pixel3DMM V4 FaceBoxes crops and FaRL
  segmentations:
  - `semantic_v1`: raw validated photos + raw FaceBuilder texture;
  - `semantic_v2`: V4 crops + raw FaceBuilder texture;
  - `semantic_v3`: V4 crops + sentinel-colored semantic texture inputs.
  It writes Drive outputs, OBJ/GLB, per-version review sheets, crop/segmentation
  review sheets, and a cross-version comparison sheet.
- The active mask-aware correction experiment has completed Step 3 parser/object
  mask comparison, Step 4 clean-pixel UV projection, Step 5 raw-versus-clean
  arbitration, and Step 6 v01/v02/v03/v04/v04b/v05 postprocess passes. The
  current v05 revision keeps v04b as the forehead/eyebrow/hairline baseline,
  then fills side/temple/ear dark fragments and neck/jaw/clothing contamination
  with temporary skin material before later global skin blending.
  `v2_farl_grounded_sam` is the current mask candidate, and Step 6 is using
  the Step 5 `blend` texture as its fixed baseline.

Private test outputs are written under `private_outputs/` and are ignored by
Git. Current FaceBuilder version outputs are written under the private Drive
layout:

```text
<drive_root>/output/facebuilder_semantic_v1/<person>/
<drive_root>/output/facebuilder_semantic_v2/<person>/
<drive_root>/output/facebuilder_semantic_v3/<person>/
<drive_root>/output/_preprocess_review/<person>/
<drive_root>/output/_comparison/facebuilder_semantic_v1_v3/
<drive_root>/output/facebuilder_mask_aware_step3/<stamp>/
<drive_root>/output/facebuilder_mask_aware_step4/<stamp>/
<drive_root>/output/facebuilder_mask_aware_step5/<stamp>/
<drive_root>/output/facebuilder_mask_aware_step6/<stamp>/
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
  scene probing, empty-scene automation, batch comparison, private review
  outputs, and GLB export.
- FaceBuilder semantic ablation scripts that reuse Pixel3DMM V4 crop/FaRL
  preprocessing and test raw versus cropped versus sentinel-colored texture
  inputs.
- FaceBuilder mask-aware correction scripts for parser/object-mask comparison,
  clean-pixel UV projection, raw-versus-clean arbitration, Step 6 postprocess,
  and review sheets.

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

1. Continue Step 6 from the Step 5 `blend` texture, one post-process element at
   a time, with a review sheet after each element.
2. Keep v01 hard black skin-hole fill as a conservative safety pass. It fills
   only tiny dot-like holes and protects eyes, mouth, brows, nostrils, scalp,
   and clothing.
3. Keep v02 forehead tone as a safe but weak pass. It now uses only the central
   forehead component, but tone correction alone did not remove the visible
   patch structure.
4. Treat v03 forehead uniform tone as a diagnostic experiment, not final
   quality: it replaces selected forehead skin with the average non-forehead
   face tone, uses Juseop scan frames only as a hairline boundary hint, and
   produces compact before/after/area review sheets.
5. Treat v04b forehead/eyebrow/hairline refinement as the current region
   baseline: it keeps v04's broader forehead, uses a fixed black symmetric
   eyebrow mask as a protection placeholder, chooses the brow source by
   component quality instead of area, adds a symmetric flatter front-hairline
   lift, defines the forehead as the region below the hairline and above the
   eyebrow baseline except tight eye/brow guards, and still looks too flat.
6. Treat v05 side/neck temporary skin cleanup as the current lower/side repair
   baseline: it fills ear/temple/side-face dark fragments and neck/jaw/clothing
   contamination, while protecting eyes, brows, mouth, and hairline. It is not
   final skin blending.
7. Next, lock the eye/brow/mouth/lip protection masks, then run global skin
   blending over all confirmed skin regions. After that, repair eye/brow,
   mouth/lips, scalp/hairline, and final mild color smoothing.
8. Keep `select` as a diagnostic comparison, but use `blend` as the main Step 6
   candidate unless visual review proves otherwise.
9. Preserve confidence/provenance maps so observed pixels, blended pixels, and
   generated/fallback pixels remain distinguishable.
10. After the bald head is credible, decide whether the FaceBuilder mesh can be
   used directly for hair fitting or needs retopology/transfer.
