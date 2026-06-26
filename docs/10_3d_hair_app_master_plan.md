# Hair App Master Plan

Last updated: 2026-06-27

## 1. Product Goal

Hair App should let a user provide ordinary selfies plus an in-app face/head
scan, then receive a believable personal bald head that can be used for
hairstyle try-on.

The goal is not perfect forensic 3D scanning. The product goal is:

- front to about 45-degree personal likeness;
- stable enough head/scalp shape for hair fitting;
- plausible fallback for hidden scalp and rear head;
- clean bald-head material that does not leak hair, glasses, shirt, or
  background into the skin;
- mobile GLB preview with rotation/zoom;
- honest confidence/provenance for observed versus inferred regions.

## 2. Input Contract

The user-facing input must stay simple:

```text
ordinary selfies + app camera scan
```

Do not require:

- studio lighting;
- exact prescribed photo angles;
- manual pin/landmark editing;
- a human operator to align photos.

The system can still internally score, reject, downweight, crop, align, and
select frames.

## 3. Current Main Direction

As of 2026-06-27, the main head-generation candidate is:

```text
photo/frame scoring
  -> automated FaceBuilder/KeenTools solve inside headless Blender
  -> private mesh/texture/blend export
  -> Hair App bald-head post-processing
  -> review sheets and metrics
  -> hairline/scalp fitting
  -> collision correction
  -> mobile GLB + Three.js viewer
```

Pixel3DMM/FLAME and the custom Texture Baker remain research baselines and
fallbacks, not the current main quality path.

## 4. Why the Direction Changed

The Pixel3DMM/FLAME Texture Baker path produced valuable knowledge but poor
visual quality:

- camera alignment errors caused texture seams and misplaced pixels;
- low-confidence repair filled holes but flattened identity;
- repeated iterations could reduce numeric loss while making the face look
  worse;
- eyes, mouth, brows, scalp, and occlusions were not solved by simple texture
  baking;
- the output was too weak to fairly choose among base mesh candidates.

The user's manual FaceBuilder test in Blender produced a visibly stronger
starting point. Therefore the near-term work should focus on automating
FaceBuilder and cleaning its output for Hair App.

## 5. FaceBuilder / Blender Engine Role

FaceBuilder/KeenTools is treated as a black-box fitting engine:

- it fits face/head geometry from multiple photos;
- it aligns photos/cameras to that face model;
- it can build a texture from multiple views;
- it runs inside Blender through the KeenTools add-on and compiled
  `pykeentools` core.

Blender is the likely server-side 3D production engine for now. The mobile app
should not run Blender. The app/server split is:

```text
app/frontend
  -> upload selfies and scan frames

backend job
  -> prepare/scoring
  -> run Blender headless + FaceBuilder automation
  -> post-process
  -> export GLB/review assets

app/frontend
  -> view final GLB through Three.js or native 3D viewer
```

## 6. Verified FaceBuilder Automation

Local verification completed on 2026-06-27:

- Blender 5.1.2 runs in background mode.
- KeenTools 2026.2.0 loads in background mode.
- `pykeentools` imports successfully.
- FaceBuilder object creation works from script.
- `detect_faces`, `detect_face_pose`, preset pin solving, and TextureBuilder
  APIs are reachable.
- Existing private `blender.blend` FaceBuilder scene could be inspected.
- Re-aligning an already pinned camera succeeded.
- Four of five unpinned camera auto-align attempts succeeded; one failed with
  no detected face, likely a glasses photo.
- Empty-scene automation v0 created a FaceBuilder head from two private Juseop
  photos, aligned one photo, failed one no-face photo, baked a texture, and
  saved a private `.blend`.

Conclusion: automation is feasible. Product automation still needs scoring,
batch handling, retry/reject policy, export, review, and post-processing.

## 7. Photo and Frame Scoring

Scoring has two uses:

- reject clearly bad inputs before FaceBuilder;
- downweight or deprioritize weaker inputs if they can still provide limited
  evidence.

Score dimensions:

- blur/sharpness;
- face detection confidence;
- face crop coverage;
- yaw/pitch/roll;
- lighting and exposure;
- glasses, hair, headwear, hand, phone, and shadow occlusion;
- eyes closed;
- mouth open;
- landmark stability;
- segmentation confidence where available.

For FaceBuilder specifically, a frame that fails face detection or produces bad
alignment should be removed or retried with another candidate, not forced into
the solve.

## 8. FaceBuilder Automation v1 Plan

The next implementation target is a v1 batch runner:

1. Load a private person photo folder.
2. Score and sort candidate photos.
3. Create a clean Blender scene.
4. Add FaceBuilder head.
5. Add selected photos as cameras.
6. Run code-only face detection and pose alignment.
7. Add preset pins and solve where alignment succeeds.
8. Reject failed/no-face photos.
9. Bake texture.
10. Save private `.blend`, texture, export candidates, and JSON manifest.
11. Generate review sheets.

The v1 runner should report:

- selected photos;
- rejected photos and reasons;
- alignment success/failure per photo;
- pin count;
- texture bake status;
- output paths;
- warnings for likely low-quality results.

## 9. Review Sheets

Review sheets should prioritize the product-critical range:

```text
0, +-15, +-30, +-45 degrees
```

Each sheet should show:

- rendered bald head views;
- source photo thumbnails or references;
- alignment status;
- failure/reject reasons;
- simple metrics, but visual quality should remain the main gate.

The previous 360-style review was less useful because Hair App does not need a
perfect rear-head scan at this stage.

## 10. Bald-Head Post-Processing

FaceBuilder output is not automatically Hair-App-ready. Post-processing must
produce a clean bald-head substrate:

- remove hair, headwear, glasses, shirt, and background leakage;
- fill scalp, rear head, neck, and low-confidence regions;
- create plausible skin material where photos cannot observe the surface;
- improve eyes, iris, eyelids, mouth interior, lips, ears, and brows;
- smooth lighting seams without erasing identity details;
- mark observed/generated/confidence regions in a manifest;
- keep original private exports for comparison.

This is where Hair App adds product-specific value beyond FaceBuilder.

## 11. Mesh Strategy

Two strategies remain open:

### Option A: use FaceBuilder mesh directly

Pros:

- fastest path;
- preserves the fitted result;
- lower engineering burden.

Risks:

- topology may not match hair/scalp/collision assumptions;
- eye/mouth/scalp regions may need custom cleanup;
- mobile GLB constraints may require retopology or simplification.

### Option B: transfer to a controlled app mesh

Pros:

- stable scalp/hairline/collision contract;
- easier long-term GLB and animation rules;
- easier consistent materials across users.

Risks:

- transfer can lose likeness;
- adds complexity;
- requires reliable correspondence.

Decision should be based on FaceBuilder v1 exports and hair fitting tests, not
on the failed Texture Baker results.

## 12. Hair Pipeline

Hair remains separate from the bald head.

The long-term hair path needs:

- hairstyle reference input;
- hairline-aware scalp root placement;
- strand/guide representation or mobile hair cards;
- retargeting from canonical hair to personal scalp;
- collision correction against scalp, forehead, ears, face, neck, and shoulders;
- LOD/mobile GLB export.

The head pipeline should output enough scalp/hairline structure for this to
work.

## 13. Mobile Output

The app should receive:

- optimized GLB;
- texture/material assets;
- optional review stills;
- manifest with source/confidence/provenance;
- quality warnings if result is low confidence.

Three.js is the likely browser/mobile viewer path. Blender is a server-side
production tool, not the runtime viewer.

## 14. Privacy and Storage

Never commit:

- private photos or app scan frames;
- crops, landmarks, masks, UV maps, tracking videos;
- private OBJ/MTL/PLY/GLB exports;
- private textures and renders;
- private `.blend` files;
- private Drive output folders.

Private local paths should stay under ignored folders such as:

```text
private_exports/
private_outputs/
```

Private Drive layout to preserve:

```text
MyDrive/hair_app/input/
MyDrive/hair_app/output/
MyDrive/hair_app/shared/
MyDrive/hair_app/data_layout_manifest.json
```

Historical texture-baker entrypoint:

```text
output/<person>/models/model_trio_for_texture/model_trio_manifest.json
```

## 15. Pixel3DMM / Texture Baker Status

Pixel3DMM V4 no-MICA produced a real research baseline:

- 8/8 or later 19-view private runs completed depending on dataset;
- `canonical.ply` was produced;
- FLAME tracking completed;
- no-MICA did not clearly beat the refitted mean-shape control enough to lock
  in a final base mesh.

Texture Baker v3 produced cleaner sheets than v1/v2 but still failed product
quality. Keep the code and docs for reference. Do not choose a final base mesh
from v3 review sheets.

## 16. Immediate Milestones

1. FaceBuilder automation v1 over Juseop/Eunchae folders.
2. Photo scoring and reject/retry policy.
3. Private FaceBuilder export and review sheets.
4. Bald-head post-processing plan and first implementation.
5. Decide direct FaceBuilder mesh versus transfer/retopology.
6. Begin hair/scalp fitting only after the head substrate is credible.
