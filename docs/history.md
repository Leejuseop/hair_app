# Hair App History

Last updated: 2026-06-27

This document records the major decisions, experiments, and direction changes.
It is intentionally chronological. For the current plan, read
`docs/10_3d_hair_app_master_plan.md`.

## 1. Product Definition

Hair App started as a 3D hairstyle try-on project. The core product idea is:

```text
user selfies + app scan
  -> personal bald head
  -> hairstyle fitting
  -> interactive mobile preview
```

The target is not perfect 360-degree scanning. The useful product target is a
front-to-45-degree believable head for hairstyle judgment, with plausible
fallback for hidden regions.

## 2. App Capture Foundation

The repository implemented a mobile-first React/Vite frontend and FastAPI
backend pieces:

- browser camera capture;
- MediaPipe Face Landmarker;
- guided scan steps: `front`, `left_45`, `right_45`, `left_profile`,
  `right_profile`, `hairline`;
- 8-12 accepted samples per step;
- `POST /api/scan`;
- file-based scan storage;
- selected reconstruction input bundle under `selected_3dmm/`;
- `base_profile.json` version `0.2`.

This created the product-side capture/provenance foundation, but not a finished
3D reconstruction worker.

## 3. Pixel3DMM V4 Geometry Research

The project then explored Pixel3DMM/FLAME as the first multi-photo head
baseline.

Key audited source:

```text
https://github.com/SimonGiebenhain/pixel3dmm
commit fcd1fa973c7715b02a8948dfc679dff53cf85924
```

The private Colab/A100 workflow completed:

- FaceBoxes crop;
- PIPNet WFLW-98 landmarks;
- FaRL CelebM segmentation;
- Pixel3DMM normal inference;
- Pixel3DMM UV correspondence inference;
- multi-photo FLAME tracking;
- `canonical.ply` output.

An early 8-photo run produced:

- 5,023 vertices;
- 9,976 faces;
- fitted identity landmark error about `5.8803 px`;
- mean FLAME control about `7.1109 px`;
- apparent improvement about `1.2306 px` or `17.3%`.

Later checks showed the no-MICA personal identity shape was not clearly better
than the refitted mean-shape control in every gate, so the base mesh decision
remained open.

## 4. Base Mesh Candidates

The project kept three base candidates active:

- raw/base FLAME;
- refitted mean-shape FLAME control;
- no-MICA Pixel3DMM personal fitted shape.

The decision was intentionally delayed because texture quality was too weak to
judge which base mesh was actually best for the product.

## 5. Texture Baker v1

The first texture baker focused on loading private model-trio manifests and
producing diagnostic review sheets.

Important historical entrypoint:

```text
output/<person>/models/model_trio_for_texture/model_trio_manifest.json
```

v1 proved that model candidates and private assets could be loaded and rendered,
but the result contained large black/unfilled regions and obvious texture
coverage failures.

## 6. Texture Baker v2

v2 added a more serious texture pipeline:

- evidence quality scoring;
- segmentation confidence;
- Pixel3DMM UV correspondence use;
- fitted-camera projection experiments;
- z-buffer visibility diagnostics;
- front-to-45 review sheets;
- material fallback and cleanup passes.

v2 improved diagnostics but did not reach product quality. Major issues:

- unreliable camera projection calibration;
- face area differences between people;
- headwear/hair leakage;
- eye/mouth placeholder artifacts;
- visible seams between observed pixels and fallback skin.

## 7. Cleanup and Completion

The next pass added cleanup/completion logic:

- remove low-confidence or outlier pixels;
- replace hidden forehead/scalp/neck/ear regions with fallback material;
- reduce black holes;
- preserve observed texture separately from completed texture.

This made sheets easier to inspect, but it also made hidden regions flatter and
did not solve central identity quality.

## 8. Texture Baker v3

v3 was built after the user rejected v2 quality as far below product standard.
It tried to make a more controlled iterative avatar texture:

- `v3_no_lighting` variant;
- `v3_lighting_normalized` variant;
- frame filtering with a stricter score gate;
- weighted multi-frame seed texture;
- whole-face bad/empty texel repair;
- neighbor fill, mirror fill, material fallback;
- seam smoothing;
- per-iteration outputs from 0 to 5;
- metrics and review sheets for each iteration;
- final selection from the earliest clean enough iteration.

Private-run summary:

| Person | Variant | Selected final | Mean luma error | Seam score | Observed coverage |
| --- | --- | ---: | ---: | ---: | ---: |
| Juseop | no lighting | 1 | 27.48 | 0.640 | 34.2% |
| Juseop | lighting normalized | 1 | 27.12 | 0.631 | 34.3% |
| Eunchae | no lighting | 1 | 36.99 | 1.027 | 23.5% |
| Eunchae | lighting normalized | 1 | 37.16 | 1.114 | 23.6% |

Key lesson: loss could improve while visual identity got worse. Later
iterations often smoothed away nose, mouth, and skin detail. The result was
cleaner than v1/v2 but still not usable for the product.

## 9. Discussion: Why the Original Approach Was Failing

The user correctly pushed back on why 11 selfies still produced such low
coverage and quality. The main explanation:

- it is not enough to segment a 2D face and paste it onto a 3D head;
- every photo needs accurate camera/pose alignment to the mesh;
- small projection errors put pixels on the wrong UV areas;
- occlusions and lighting differences can poison the texture;
- hidden regions cannot be observed and need controlled completion;
- fixed geometry limits how well texture alone can match the photo.

The next proposed custom path was a photo-render comparison loop, but this was
paused because the FaceBuilder result looked more promising.

## 10. External Engine Review

The user asked about MetaHuman, Polycam, and KeenTools.

Findings:

- MetaHuman can create high-quality avatars but is not the immediate lightweight
  server pipeline for Hair App's automatic bald-head output.
- Polycam is useful as a scanning product reference, but not directly aligned
  with the app's selfie-plus-face-scan contract.
- KeenTools FaceBuilder is highly relevant because it fits face geometry and
  cameras from multiple photos in Blender.

The biggest conceptual difference:

- FaceBuilder adjusts head shape and camera/photo alignment together.
- Our Texture Baker v3 mostly kept the mesh fixed and tried to fix texture.

That difference explains why FaceBuilder can produce a better starting head.

## 11. FaceBuilder Manual Test

The user manually created a FaceBuilder result in Blender from Juseop photos and
exported OBJ/MTL/texture assets. The visible result was much stronger than the
custom baker output.

The discussion clarified:

- the exported bald head might be usable directly;
- transfer to FLAME/Pixel3DMM is only needed if hair fitting, scalp mapping,
  collision, or GLB constraints require a controlled mesh;
- FaceBuilder output still needs Hair App cleanup and post-processing.

## 12. FaceBuilder / Blender Automation Investigation

The project then investigated whether Codex could automate Blender/FaceBuilder.

Important local facts:

- Blender executable:
  `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`
- KeenTools extension folder:
  `C:\Users\User\AppData\Roaming\Blender Foundation\Blender\5.1\extensions\user_default\keentools`
- Core FaceBuilder logic is compiled in `pykeentools` `.pyd`, not readable
  Python source.

The conclusion was to use KeenTools as a licensed black-box dependency, not to
extract or reverse-engineer the core algorithm.

## 13. Automation Verification

On 2026-06-27 the bridge was verified:

- headless Blender loaded KeenTools;
- `pykeentools` imported successfully;
- a FaceBuilder object could be constructed;
- `detect_faces`, `detect_face_pose`, preset pins, and TextureBuilder were
  reachable from script;
- an existing private FaceBuilder scene with 11 cameras could be probed;
- re-aligning an already pinned camera succeeded;
- four of five unpinned auto-align attempts succeeded;
- one failed no-face case likely came from a glasses photo;
- empty-scene automation v0 created a FaceBuilder head from private Juseop
  photos, aligned one photo, failed one, baked texture, and saved private
  outputs.

This proved automation feasibility.

## 14. Current Decision

As of this document update:

- FaceBuilder/KeenTools automation through Blender is the main near-term
  head-generation candidate.
- Pixel3DMM/FLAME remains a baseline/backup.
- Texture Baker v3 remains a research artifact, not the product path.
- The next build should be FaceBuilder automation v1 for Juseop/Eunchae photo
  folders.
- The system must add photo scoring, retry/reject logic, review sheets, and
  bald-head post-processing.
- Mesh strategy remains undecided: use FaceBuilder mesh directly if it works
  for hair fitting, or transfer/retopologize only if necessary.

## 15. Privacy Lessons

Private data must stay out of Git:

- photos;
- scan frames;
- landmarks;
- masks;
- crops;
- meshes;
- textures;
- render sheets;
- `.blend` files;
- private Drive/local output folders.

Tracked files should contain code, docs, and generic examples only.
