# FaceBuilder Semantic Preprocess Ablation

This experiment replaces the retired FaceBuilder v1-v4 color-mute ablation.

The goal is to observe how much quality changes when FaceBuilder receives:

```text
v1: raw photos for auto-align and raw texture bake
v2: Pixel3DMM V4 crops for auto-align and raw texture bake
v3: Pixel3DMM V4 crops for auto-align, sentinel-colored semantic inputs for texture bake
```

The crop and segmentation inputs are reused from the previous Pixel3DMM V4
preprocessing run:

- per-image FaceBoxesV2 no-roll crop;
- 512x512 crop;
- margin 1.42;
- FaRL face parsing label maps.

The current controlled input set is the existing V4 manifest rows:

- Juseop: 19 rows, with 9 `scan_*` rows and 10 selfie rows;
- Eunchae: 8 selfie rows.

Juseop `scan_*` rows are alignment-only by default. They help FaceBuilder fit
the head, but they are not allowed into texture bake unless
`--texture-scan-frames` is set. This avoids a reproducible headless FaceBuilder
stall seen when all 19 mixed scan/selfie cameras were allowed into one texture
bake, and it matches the product plan where scan frames stabilize geometry while
selfies provide appearance texture.

Private images, crops, masks, textures, renders, OBJ/GLB files, and review
sheets must stay in private Drive output folders and must not be committed.

## Why Sentinel Colors

The retired v2/v4 preprocessing filled bad pixels with skin-like color. That was
wrong for FaceBuilder texture baking because the baker could treat fake skin as
real skin. This experiment instead paints bad semantic regions with impossible
colors:

- background: green;
- hair: purple;
- clothes: blue;
- eyeglasses: cyan;
- hat/misc: yellow;
- accessories/unknown: red/orange.

If those colors appear in the baked texture, the result tells us how FaceBuilder
uses or blends input image pixels. This is an observation step before writing a
real postprocess cleanup.

Current observation: sentinel colors do appear in the baked texture and renders.
Therefore v3 is diagnostic, not a product-looking output. It proves that bad
semantic regions cannot be fixed simply by painting the input before bake.
Future cleanup should mask or repair bad regions after bake and should use
better hand/object/phone/perfume occlusion detection.

Current project use:

- `semantic_v2` is the controlled FaceBuilder source baseline for the active
  mask-aware correction experiment.
- Juseop scan rows remain alignment-only by default; texture correction should
  use selfie/texture-enabled cameras, not scan/alignment-only frames.
- The active post-bake path is now Step 3/4/5/6 under
  `experiments/facebuilder_mask_aware_correction/`.

## Run

```powershell
python experiments\facebuilder_semantic_ablation\run_facebuilder_semantic_ablation.py `
  --archive-old `
  --clean
```

Useful dry run:

```powershell
python experiments\facebuilder_semantic_ablation\run_facebuilder_semantic_ablation.py `
  --skip-blender `
  --clean
```

Expected private outputs:

```text
G:\내 드라이브\hair_app\output\facebuilder_semantic_v1
G:\내 드라이브\hair_app\output\facebuilder_semantic_v2
G:\내 드라이브\hair_app\output\facebuilder_semantic_v3
G:\내 드라이브\hair_app\output\_preprocess_review
G:\내 드라이브\hair_app\output\_comparison\facebuilder_semantic_v1_v3
```

Generate or refresh review sheets without rerunning Blender:

```powershell
python experiments\facebuilder_semantic_ablation\run_facebuilder_semantic_ablation.py `
  --drive-root "G:\내 드라이브\hair_app" `
  --skip-existing
```
