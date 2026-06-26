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
- `은채`: two mesh candidates from `output/은채/models/models_manifest.json`.

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

Eunchae current preview uses frame `00004` as the cleaner front primary and
temporarily drops side/ear labels:

```python
!python experiments/texture_baker/observed_texture_baker.py \
  --private-root /content/drive/MyDrive/hair_app \
  --person 은채 \
  --atlas-size 512 \
  --output-name observed_v6_primary00004_centralface_secondary0_preview \
  --splat-radius 1 \
  --blend-mode weighted \
  --primary-frame-id 00004 \
  --secondary-central-weight 0 \
  --mask-erode-iterations 3 \
  --include-seg-label 2 \
  --include-seg-label 6 \
  --include-seg-label 7 \
  --include-seg-label 8 \
  --include-seg-label 9 \
  --include-seg-label 10 \
  --include-seg-label 12 \
  --include-seg-label 13 \
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
