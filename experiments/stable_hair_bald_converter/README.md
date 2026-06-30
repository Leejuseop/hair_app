# Stable-Hair Bald Converter Bridge

This folder contains a thin Hair App bridge for using only Stable-Hair's
stage-1 Bald Converter.

It does not vendor Stable-Hair code, checkpoints, or generated private images.
Keep the upstream checkout, model weights, and generated face outputs under
ignored/private folders or private Google Drive folders.

## Why

The previous FaceBuilder v2 texture-input preprocessing muted suspected
hair/background/clothes pixels with skin-like colors. That made FaceBuilder bake
fake skin patches into the head texture. A better experiment is:

```text
original selfie
  -> Stable-Hair stage-1 Bald Converter
  -> natural-looking bald selfie
  -> FaceBuilder texture bake input
```

The original photo should still be used for FaceBuilder auto-align. The
bald-converted photo should be used only as the texture-bake image.

## Upstream Dependency

Upstream repo:

```text
https://github.com/Xiaojiu-z/Stable-Hair
```

Private local checkout used for inspection:

```text
C:\Users\User\Desktop\hair_app\private_outputs\third_party\Stable-Hair
```

Stable-Hair is Apache-2.0 in the checked-out repository, but the pretrained
models still need to be downloaded from the upstream Google Drive link in their
README. Do not commit model files.

Required stage-1 checkpoint:

```text
<stable_hair_root>\models\stage1\pytorch_model.bin
```

The wrapper also loads Stable Diffusion 1.5 through the upstream pipeline:

```text
runwayml/stable-diffusion-v1-5
```

## Local Run

Local CPU is not recommended for real generation. Use this only for smoke tests.

```powershell
python experiments\stable_hair_bald_converter\stable_hair_bald_only.py `
  --stable-hair-root "C:\Users\User\Desktop\hair_app\private_outputs\third_party\Stable-Hair" `
  --input-dir "G:\내 드라이브\hair_app\input\juseop_raw_10_no_glasses" `
  --output-dir "G:\내 드라이브\hair_app\output\stable_hair_bald_probe\juseop" `
  --max-images 3 `
  --device cpu `
  --dtype float32 `
  --preserve-input-size
```

Important options:

- `--size 512`: Stable-Hair's released model was trained on FFHQ-style 512
  aligned/cropped faces.
- `--preserve-input-size`: resizes the generated bald result back to the
  original input size so FaceBuilder camera projection can still be reused.
- `--converter-scale 0.9`: copied from the upstream inference path.
- `--steps 30`, `--guidance-scale 1.5`: copied from upstream `get_bald`.

## Colab A100 Run

Use Colab A100 for real runs. Private input photos should live in Drive:

```text
/content/drive/MyDrive/hair_app/input/juseop_raw_10_no_glasses
```

Then run these cells:

```python
from google.colab import drive
drive.mount("/content/drive")
```

```bash
!rm -rf /content/hair_app /content/Stable-Hair
!git clone https://github.com/Leejuseop/hair_app.git /content/hair_app
!git clone https://github.com/Xiaojiu-z/Stable-Hair.git /content/Stable-Hair
%cd /content/hair_app
```

```bash
!pip -q install \
  gdown==5.2.0 \
  huggingface-hub==0.25.2 \
  transformers==4.45.2 \
  accelerate==1.0.1 \
  safetensors==0.4.5 \
  omegaconf==2.3.0 \
  einops==0.4.1 \
  peft==0.11.1
```

```bash
!mkdir -p /content/Stable-Hair/models/stage1
!gdown "https://drive.google.com/uc?id=1oYNoKPEN0mZpRhZ7s3_xSDlaO209vFn4" \
  -O /content/Stable-Hair/models/stage1/pytorch_model.bin
```

```bash
!python experiments/stable_hair_bald_converter/stable_hair_bald_only.py \
  --stable-hair-root /content/Stable-Hair \
  --input-dir "/content/drive/MyDrive/hair_app/input/juseop_raw_10_no_glasses" \
  --output-dir "/content/drive/MyDrive/hair_app/output/stable_hair_bald_probe/juseop_a100" \
  --device cuda \
  --dtype float16 \
  --size 512 \
  --steps 30 \
  --converter-scale 0.9 \
  --guidance-scale 1.5 \
  --preserve-input-size
```

## Current Status

Code extraction status:

- Found upstream `get_bald()` in `infer_full.py` and `gradio_demo_full.py`.
- Isolated the stage-1 loader:
  - `UNet2DConditionModel.from_pretrained(...)`
  - `ControlNetModel.from_unet(...)`
  - load `models/stage1/pytorch_model.bin`
  - `StableDiffusionControlNetPipeline`
- Stage-2 hair transfer modules are not loaded by this wrapper.
- Stage-1 checkpoint was downloaded locally under `private_outputs` for
  inspection only.
- Juseop's 10 no-glasses images were copied to the private Drive input folder.

Visual probe status:

- A Colab/A100 probe was run on Juseop's 10 no-glasses images.
- The output quality was judged too poor for the current FaceBuilder texture
  path.
- Stable-Hair stage-1 bald conversion remains a paused side experiment, not the
  active pipeline.
- The active path is still FaceBuilder raw texture plus mask-aware Step 4/Step 5
  correction and Step 6 material-specific post-processing.

## Next Experiment

Do not replace the current raw FaceBuilder baseline with Stable-Hair outputs
unless a future visual probe is clearly better. If revisited later, the next
experiment would be:

1. Improve or replace the bald-conversion model/prompt/alignment setup.
2. Re-run on Juseop and Eunchae private crops.
3. Only if identity and alignment are preserved, create a new FaceBuilder
   version:

```text
v2b = original photos for auto-align + Stable-Hair bald photos for texture bake
v4b = v2b + texture post-processing
```
