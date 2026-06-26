# Texture Baker Loader

This folder contains the first generic loader for the observed-photo face
texture baker. It resolves private Drive paths and reports the frozen mesh
candidates plus per-frame crop, UV, segmentation, landmark, and crop metadata
inputs.

It does not copy private photos, meshes, masks, textures, or renders into Git.

## Local Windows Check

```powershell
python experiments\texture_baker\texture_baker_loader.py `
  --private-root "G:\내 드라이브\hair_app"
```

## Colab Check

Run this after cloning or pulling the repository in Colab:

```python
from google.colab import drive
drive.mount("/content/drive")

%cd /content/hair_app
!git pull --ff-only
!python experiments/texture_baker/texture_baker_loader.py \
  --private-root /content/drive/MyDrive/hair_app
```

Expected current bundles:

- `주섭`: three frozen mesh candidates from
  `output/주섭/models/model_trio_for_texture/model_trio_manifest.json`.
- `은채`: three frozen mesh candidates from
  `output/은채/models/model_trio_for_texture/model_trio_manifest.json`:
  `raw_flame_template`, `base_flame2023`, and `personal_no_mica`.

The loader accepts both Colab paths such as
`/content/drive/MyDrive/hair_app/...` and local Windows paths such as
`G:\내 드라이브\hair_app\...`.

## First Observed-Texture Smoke Test

Run a tiny one-frame bake before running every frame:

```python
!python experiments/texture_baker/observed_texture_baker.py \
  --private-root /content/drive/MyDrive/hair_app \
  --person 주섭 \
  --atlas-size 256 \
  --max-frames 1 \
  --output-name observed_v0_smoke \
  --splat-radius 1
```

## Current Preview Bake

The cleaner preview path is to pick one good primary front frame for central
face texels, then let secondary frames contribute only where explicitly useful.
This keeps the observed layer reproducible while avoiding blurry multi-view
ghosting.

Juseop current preview:

```python
!python experiments/texture_baker/observed_texture_baker.py \
  --private-root /content/drive/MyDrive/hair_app \
  --person 주섭 \
  --atlas-size 512 \
  --output-name observed_v6_primary00000_faceonly_secondary0_preview \
  --splat-radius 1 \
  --blend-mode weighted \
  --primary-frame-id 00000 \
  --secondary-central-weight 0 \
  --mask-erode-iterations 2 \
  --preview-fill-iterations 8 \
  --preview-fill-min-neighbors 5
```

Eunchae current preview uses frame `00004` as the cleaner front primary, keeps
side/ear labels available, and removes likely hair/headwear occlusion before
baking:

```python
!python experiments/texture_baker/observed_texture_baker.py \
  --private-root /content/drive/MyDrive/hair_app \
  --person 은채 \
  --atlas-size 512 \
  --output-name observed_v15_primary00004_wideface_strict_occlusion_preview \
  --splat-radius 1 \
  --blend-mode weighted \
  --primary-frame-id 00004 \
  --secondary-central-weight 0.02 \
  --primary-side-weight 1.0 \
  --secondary-side-weight 0.0 \
  --mask-erode-iterations 2 \
  --occlusion-margin-iterations 10 \
  --skin-occlusion-filter \
  --skin-occlusion-chroma-threshold 30 \
  --skin-occlusion-luma-threshold 52 \
  --secondary-central-crop-radius-x 0.52 \
  --secondary-central-crop-radius-y 0.78 \
  --preview-fill-iterations 8 \
  --preview-fill-min-neighbors 5
```

Current MVP assumptions:

- Pixel3DMM UV PNG red/green channels are interpreted as U/V.
- V is not flipped by default. Use `--flip-v` only for an explicit A/B.
- Face-label whitelist `2`, `4`, `5`, `6`, `7`, `8`, `9`, `10`, `12`, and
  `13` is enabled by default. Segmentation labels `0`, `1`, `3`, and `14`
  remain excluded by default.
- `--splat-radius 1` is useful for a visible preview. `--splat-radius 0`
  preserves the raw point-splat observations.
- `--blend-mode weighted` uses segmentation, center, exposure, and primary
  frame heuristics. It is still a preview policy, not a validated photometric
  model.
- `--occlusion-margin-iterations` removes pixels near configured hair/headwear
  labels, and `--skin-occlusion-filter` removes skin-label pixels that are too
  far from the frame's skin reference color. These are review heuristics for
  reducing hair/headband leaks, not semantic matting.
- `--secondary-central-crop-radius-x/y` lets non-primary frames contribute only
  from the crop center when a primary frame is selected.
- `base_color_observed.png` is the real observed-photo layer. Optional
  `base_color_preview_filled.png` is only a conservative visualization and
  should not be treated as evidence.
- The baker does not yet perform true triangle rasterization, view-angle
  scoring, seam blending, or completion.

Outputs are written only under the private Drive person folder:

```text
output/<person>/texture_baker/<output-name>/
  base_color_observed.png
  coverage.png
  confidence.png
  source_view_map.png
  base_color_preview_filled.png  # only when preview fill is requested
  texture_manifest.json
```

## Mesh Texture Preview

The flat atlas is a debug artifact. Use the mesh preview script to attach the
observed atlas to FLAME-topology PLY candidates and render quick orthographic
front/oblique checks:

```python
!python experiments/texture_baker/textured_mesh_preview.py \
  --private-root /content/drive/MyDrive/hair_app \
  --person 주섭 \
  --person 은채 \
  --texture-kind preview_filled \
  --uv-mode flip_y \
  --depth-mode max \
  --view front \
  --view left_35 \
  --view right_35 \
  --material-fallback \
  --fallback-confidence-threshold 5 \
  --eye-overlay \
  --write-obj
```

This expects the Pixel3DMM FLAME UV asset at:

```text
shared/models/pixel3dmm_assets/flame_uv_coords.npy
```

Current local Drive preview outputs:

```text
output/<person>/texture_baker/<texture-name>/mesh_texture_preview/<mesh-key>/
  front_flip_y_depth_max.png
  left_35_flip_y_depth_max.png
  right_35_flip_y_depth_max.png
  contact_sheet.png
  <mesh-key>_uv_direct.obj
  <mesh-key>_uv_direct.mtl
  mesh_texture_preview_manifest.json
```

The preview renderer is intentionally simple: CPU orthographic rasterization,
no lighting model, no fitted tracking cameras, and no perspective intrinsics.
For the current Pixel3DMM UV atlas, `--uv-mode flip_y --depth-mode max` is the
visually correct orientation.

Eunchae's current private model trio was normalized to match the Juseop
comparison shape: a shared raw FLAME template baseline, the existing
`base_flame2023` candidate, and the no-MICA canonical candidate. The generated
PLY copies and `model_trio_manifest.json` are private Drive artifacts, not Git
files.

## One-File 8-View Comparison Sheet

For manual model selection, generate one large private PNG with rows as model
candidates and columns as 45-degree yaw views:

```python
!python experiments/texture_baker/make_texture_comparison_sheet.py \
  --private-root /content/drive/MyDrive/hair_app \
  --texture-kind preview_filled \
  --image-size 512 \
  --padding 42 \
  --uv-mode flip_y \
  --depth-mode max \
  --mask-mode none \
  --material-fallback \
  --fallback-confidence-threshold 5 \
  --eye-overlay
```

Local output:

```text
output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.png
output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.json
```

`--material-fallback` fills texture-black sampled areas with simple FLAME-mask
review colors for scalp, neck, ears, lips, and eyeballs. This is currently
better for model choice than full UV diffusion because it reduces black holes
without creating large misleading rear-head streaks.
`--eye-overlay` adds diagnostic iris/pupil markers over the FLAME eyeball
masks, and `--fallback-confidence-threshold 5` replaces only very
low-confidence texture samples with the same material fallback so neck/jaw
speckles are less visually distracting.

For an explicit UV hole-fill A/B, first create private visual completions:

```python
!python experiments/texture_baker/complete_texture_for_review.py \
  --private-root /content/drive/MyDrive/hair_app
```

Then pass `--texture-kind visual_completed` to the sheet generator. Treat that
output as a rough review artifact, not a production texture.

## 2026-06-26 Review Result

The v1 baker proved the private data layout, loader, observed atlas outputs,
mesh preview renderer, fallback materials, eye overlay, and comparison-sheet
workflow. It did not produce product-usable face quality.

Key private outputs from the current review round:

```text
output/은채/texture_baker/observed_v15_primary00004_wideface_strict_occlusion_preview/
output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.png
output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.json
```

Observed problems:

- the raw UV splat baker still leaks hair, headwear, and low-confidence pixels;
- orthographic debug renders do not match actual selfie cameras;
- material fallback reduces black holes but does not make the texture realistic;
- eye overlays are diagnostic markers, not final eye rendering;
- full UV visual completion created misleading rear-head streaks;
- the three base meshes cannot be fairly judged while the texture layer is this weak.

Keep the three mesh candidates active for now. The current front-facing quality
is the limiting factor, not a proven base-mesh winner.

## Texture Baker v2 Plan

The next baker should be camera-aware and front-focused. The product target is
not a perfect 360-degree scan; it is a personal bald head substrate that looks
credible from front through roughly 45 degrees and supports later hair fitting.
Back-of-head and hidden scalp regions may use generic fallback or completion.

Inputs remain unchanged:

- unconstrained user selfies;
- the app scan frame bundle.

Planned v2 stages:

1. score each selfie and scan frame for face size, blur, pose, exposure, eye and
   mouth state, landmark stability, segmentation quality, and occlusion from
   hair, hands, phones, glasses, or headphones;
2. use the app scan as the stable geometry/camera coordinate source;
3. use selfies mainly as high-detail texture evidence;
4. fit or load per-image camera/expression/lighting before comparing photos;
5. project mesh triangles into each source image with z-buffer visibility;
6. weight samples by view angle, texel resolution, sharpness, exposure,
   segmentation confidence, occlusion, and cross-view consistency;
7. maintain observed texture, confidence, source-photo provenance, and
   observed-versus-fallback masks separately;
8. render a front-focused review sheet at `0`, `±15`, `±30`, and `±45` degrees;
9. after the observed layer is stable, add per-user optimization that renders
   the textured model into the selfie camera and minimizes masked losses for
   landmarks, silhouette, skin color, perceptual identity, smoothness, and safe
   low-frequency geometry/detail corrections.

This is initially per-user optimization logic, not training a neural network.
Later, accumulated optimization results can train a network that predicts a
better initial texture/shape update and reduces runtime.

## 2026-06-26 Texture Baker v2 Hybrid Run

Implemented v2 code:

- `evidence_quality_report.py`: scores each private frame for blur, face size,
  pose, exposure, eye/mouth state, landmark stability, segmentation quality,
  occlusion, and skin-color reference.
- `texture_baker_v2.py`: writes a camera-aware/hybrid observed atlas. It keeps
  fitted-camera projection and z-buffer visibility as a diagnostic/fill source,
  but also uses Pixel3DMM UV correspondence maps for central face detail because
  the current checkpoint camera crop calibration is still too rough for a pure
  mesh-projection bake.
- `make_texture_comparison_sheet.py --texture-name`: allows explicit texture
  run selection for one-file review sheets.
- `textured_mesh_preview.py`: defaults now point both people to
  `observed_v2_camera_visibility_front45_preview`.

Current private v2 outputs:

```text
output/Juseop-or-Korean-person-name/texture_baker/observed_v2_camera_visibility_front45_preview/
output/Eunchae-or-Korean-person-name/texture_baker/observed_v2_camera_visibility_front45_preview/
output/_comparison/face_texture_model_comparison_front45_v2.png
output/_comparison/face_texture_model_comparison_front45_v2.json
```

Local command used for the current front-focused sheet:

```powershell
python experiments\texture_baker\make_texture_comparison_sheet.py `
  --private-root "G:\내 드라이브\hair_app" `
  --texture-name observed_v2_camera_visibility_front45_preview `
  --texture-kind preview_filled `
  --image-size 512 `
  --padding 58 `
  --uv-mode flip_y `
  --depth-mode max `
  --mask-mode none `
  --material-fallback `
  --fallback-confidence-threshold 5 `
  --eye-overlay `
  --yaw-degree -45 --yaw-degree -30 --yaw-degree -15 `
  --yaw-degree 0 `
  --yaw-degree 15 --yaw-degree 30 --yaw-degree 45 `
  --output-path "G:\내 드라이브\hair_app\output\_comparison\face_texture_model_comparison_front45_v2.png"
```

Observed result:

- black holes are much less distracting in review renders because material
  fallback and confidence fallback cover low-observation regions;
- front/near-front face identity is more readable than the first pure camera
  v2 attempt;
- Juseop still has strong lighting/color seams on forehead and face;
- Eunchae still has forehead/headband or hair contamination;
- diagnostic eye overlay makes eyes visible but is not product-quality;
- the base mesh winner still should not be chosen purely from this sheet.

Next texture work should focus on completion/occlusion cleanup, not simply more
v1-style UV splat tuning: remove hair/headwear from observed skin regions,
replace low-confidence forehead/scalp/neck with plausible skin material, improve
eye assets, and then return to fitted-camera selfie comparison.
