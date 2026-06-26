# Pixel3DMM V4 Research Baseline

Last updated: 2026-06-27

## 1. Current Status

Pixel3DMM/FLAME is no longer the main near-term product-quality path. It remains
a valuable research baseline and backup.

The current main head-generation candidate is FaceBuilder/KeenTools automation
inside headless Blender. See:

```text
experiments/facebuilder_bridge/README.md
docs/10_3d_hair_app_master_plan.md
```

Do not restart Pixel3DMM geometry tuning unless the user explicitly asks or the
FaceBuilder path fails a named gate.

## 2. Why This Baseline Still Matters

Pixel3DMM V4 work should be kept because it provides:

- a known multi-photo FLAME/Pixel3DMM reconstruction path;
- crop, landmark, segmentation, normal, UV, and tracking lessons;
- comparison data for future geometry engines;
- possible fallback geometry;
- possible teacher or diagnostic signals;
- model-trio manifests used by the Texture Baker experiments.

It should not block FaceBuilder automation work.

## 3. Audited Source

Primary repository:

```text
https://github.com/SimonGiebenhain/pixel3dmm
```

Audited commit:

```text
fcd1fa973c7715b02a8948dfc679dff53cf85924
```

Important source areas:

- official FaceBoxes crop;
- PIPNet WFLW-98 landmarks;
- FaRL CelebM segmentation;
- normal/UV inference;
- FLAME tracking and `canonical.ply` output.

## 4. Completed Workflow

The private Colab/A100 workflow completed the following stages:

```text
private photos
  -> FaceBoxes crop
  -> PIPNet landmarks
  -> FaRL segmentation
  -> Pixel3DMM normal maps
  -> Pixel3DMM UV correspondence maps
  -> multi-photo FLAME tracking
  -> canonical mesh
```

Early 8-photo run:

- FaceBoxes crop: 8/8;
- PIPNet landmarks: 8/8;
- FaRL segmentation: 8/8;
- normal inference: 8/8;
- UV correspondence inference: 8/8;
- tracking: complete;
- `canonical.ply`: 5,023 vertices, 9,976 faces.

Measured diagnostic result:

- fitted identity landmark error: about `5.8803 px`;
- mean FLAME control error: about `7.1109 px`;
- apparent improvement: about `1.2306 px`, roughly `17.3%`.

Later private input expansion included a 19-view run. It produced a no-MICA
canonical mesh and a refitted mean-shape control, but the no-MICA identity shape
was not strong enough in the gates to declare a permanent winner.

## 5. MICA Decision

MICA prior / init-only experiments did not pass the adoption gate in the current
private tests. The working baseline stayed no-MICA Pixel3DMM V4 for historical
comparison.

This is not a statement that MICA is generally bad. It only means the local
Hair App private test did not justify adopting it at that stage.

## 6. Model Trio for Texture Experiments

The Texture Baker experiments used a model trio:

- raw/base FLAME;
- refitted mean-shape FLAME control;
- no-MICA Pixel3DMM fitted personal shape.

Historical private entrypoint:

```text
output/<person>/models/model_trio_for_texture/model_trio_manifest.json
```

This entrypoint is private and should not be committed with real person data.

## 7. Known Limitations

Pixel3DMM/FLAME path limitations observed in this project:

- camera/photo alignment was not accurate enough for high-quality direct
  texture baking;
- UV correspondence helped but did not solve visible seams;
- base mesh selection was hard because texture quality was too poor;
- hidden scalp/rear-head areas still need priors or completion;
- eyes, mouth, brows, and occlusions need separate handling;
- the product backend/frontend does not yet run the Pixel3DMM notebook as a
  production worker.

## 8. Relationship to Texture Baker v3

Texture Baker v3 used Pixel3DMM/FLAME outputs to test direct avatar texture
construction:

- no-lighting and lighting-normalized variants;
- frame scoring;
- weighted UV evidence;
- whole-face repair;
- per-iteration review sheets and metrics.

Result: cleaner than v1/v2 but not product-quality. Later iterations reduced
some metrics while visually flattening identity. Therefore Texture Baker v3 is
kept as research, not as the current product path.

## 9. Private Drive/Data Rules

Preserve this private Drive layout:

```text
MyDrive/hair_app/input/
MyDrive/hair_app/output/
MyDrive/hair_app/shared/
MyDrive/hair_app/data_layout_manifest.json
```

Never commit private:

- photos or scans;
- crop/landmark/segmentation outputs;
- normal/UV maps;
- tracking videos;
- `.ply`, `.obj`, `.mtl`, `.glb`, or `.blend` outputs;
- textures or review sheets;
- Drive output folders containing identity data.

## 10. When to Return to Pixel3DMM

Return to this path only if one of these is true:

- FaceBuilder automation fails a hard quality or licensing gate;
- controlled mesh topology becomes mandatory and FaceBuilder transfer fails;
- Pixel3DMM provides useful initialization for another solver;
- the user explicitly asks for a new Pixel3DMM comparison.

Otherwise, prioritize FaceBuilder automation and post-processing.
