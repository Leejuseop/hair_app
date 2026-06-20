# Hair Engine Experiment Plan

This document preserves the hair-specific model experiment history, including the reproducible StableHairV2 Colab run. It is no longer the active model-selection plan.

The active direction has moved to general image-editing foundation models with Hair App-specific identity, mask, landmark, and hairline controls. See `docs/08_general_image_editing_strategy.md`.

## Historical Priority At The Time Of The Experiment

Original performance-first candidate order:

1. `StableHairV2` / `HairPort`
2. `Stable-Hair`
3. `HairFusion`
4. `HairFastGAN`

StableHairV2 was tested first and is now deprioritized for the current MVP input style. The remaining list below records the planned order at that time and is not the active execution order.

Historical follow-up order:

1. `Stable-Hair`
2. `HairFusion`
3. `HairFastGAN`
4. `HairPort`

`HairPort` remains interesting for the long-term 3D-aware direction, but it is heavier than the next practical baseline candidates.

## StableHairV2 Baseline Goal

Run the official StableHairV2 model with its original inference path and evaluate raw output quality before adding any Hair App-specific logic.

Baseline means:

- No fine-tuning.
- No Hair App base profile injection.
- No custom model changes.
- No custom mask conditioning unless the official repo already requires it.
- Only minimal input preparation needed to satisfy the official script.

## Official Source

- Repository: `https://github.com/sunkymepro/StableHairV2`
- Paper: `https://arxiv.org/abs/2507.07591`

The official README shows inference through:

```bash
python test_stablehairv2.py \
  --pretrained_model_name_or_path "stable-diffusion-v1-5/stable-diffusion-v1-5" \
  --image_encoder "openai/clip-vit-large-patch14" \
  --output_dir [Your_output_dir] \
  --num_validation_images 1 \
  --validation_ids ./test_imgs/bald.jpg \
  --validation_hairs ./test_imgs/ref1.jpg \
  --model_path [Your_model_path]
```

Important implication: the baseline identity input is named `bald.jpg` in the official test path. That means StableHairV2 may expect a bald or hair-cleared identity image, not a normal selfie with existing hair. This is one of the first things to validate.

## Execution Environment

Use Colab for the first run.

Recommended:

- Colab Pro GPU runtime.
- A100 or H100 if available.
- Python 3.10-compatible environment.
- Hugging Face access for `stable-diffusion-v1-5/stable-diffusion-v1-5` if required.
- Google Drive mounted only for private input/output storage.

Local Windows laptop execution is not the target for the first run because StableHairV2 is a diffusion-based GPU workflow.

## Baseline Run Stages

### Stage 1: Official Test Pair

Purpose: confirm the repo, checkpoints, and inference script work.

Inputs:

- `./test_imgs/bald.jpg`
- `./test_imgs/ref1.jpg`

Expected output:

- `generated_video_0.mp4` or equivalent validation output under the selected output directory.

Do not judge product quality from this stage alone. This stage only proves the original code runs.

### Stage 2: Hair App-Like Private Inputs

Purpose: test whether StableHairV2 can handle our product-like inputs.

Inputs:

- One high-quality user source image.
- One best front scan frame from Hair App if available.
- Three to five hairstyle reference images.

Keep private user photos out of git.

Test cases:

- Short hairstyle reference.
- Medium hairstyle reference.
- Long hairstyle reference.
- Bangs/fringe reference.
- Curly or high-volume reference.

### Stage 3: Scan-Aware Feasibility Check

Purpose: decide whether our scan/base-profile data can realistically help StableHairV2.

Check whether the model code can be modified or wrapped to use:

- Hairline anchors.
- Face landmarks.
- Better face/hair masks.
- Best-frame selection.
- Side-profile scan frames.
- Output validation against expected landmarks.

No tuning starts until baseline quality is reviewed.

## Colab Baseline Checklist

Initial notebook steps:

```bash
git clone https://github.com/sunkymepro/StableHairV2.git
cd StableHairV2
pip install gdown
pip install -r requirements.txt
```

If `requirements.txt` fails because of environment-specific `file://` package references, create a clean Colab install cell from the real Python imports used by `test_stablehairv2.py`.

Likely required packages include:

```bash
pip install diffusers transformers accelerate peft einops omegaconf \
  opencv-python-headless pillow safetensors scipy sentencepiece tqdm \
  av kornia prodigyopt gdown
```

PyTorch should match the active Colab CUDA runtime. Do not pin a different CUDA build unless the default Colab torch version fails.

## Pretrained Checkpoints

The official README lists these checkpoint files:

- `motion_module-41400000.pth`
- `pytorch_model_1.bin`
- `pytorch_model_2.bin`
- `pytorch_model_3.bin`
- `pytorch_model.bin`

Download them into one model directory, for example:

```text
/content/stablehairv2_models/
```

Known risk: the current inference script appears to load `motion_module-4140000.pth`, while the README table lists `motion_module-41400000.pth`. If the run fails with a missing motion module file, first fix it by copying or renaming the downloaded file to the name expected by the script. Do not treat that as model tuning.

## Baseline Command

Use this shape for the first run:

```bash
python test_stablehairv2.py \
  --pretrained_model_name_or_path "stable-diffusion-v1-5/stable-diffusion-v1-5" \
  --image_encoder "openai/clip-vit-large-patch14" \
  --output_dir /content/stablehairv2_outputs/official_test \
  --num_validation_images 1 \
  --validation_ids ./test_imgs/bald.jpg \
  --validation_hairs ./test_imgs/ref1.jpg \
  --model_path /content/stablehairv2_models \
  --use_fp16
```

If memory fails, retry without increasing image size or inference steps. The baseline should stay close to the official settings.

## Quality Evaluation

Score each output from 1 to 5.

| Category | What to Check | Score |
| --- | --- | --- |
| Identity preservation | Does the person still look like the source? | 1-5 |
| Hairstyle similarity | Does the generated hair match the reference? | 1-5 |
| Hairline naturalness | Does the hairline fit the face? | 1-5 |
| Face stability | Is the face shape distorted? | 1-5 |
| Boundary quality | Are hair edges/blends clean? | 1-5 |
| Texture realism | Does the hair look realistic? | 1-5 |
| Multi-view consistency | Does the generated video stay stable across views? | 1-5 |
| Execution reliability | Did the model run without fragile manual fixes? | 1-5 |

## Result Log Template

| Run | Source Image | Hair Reference | Output Path | Identity | Style | Hairline | Artifacts | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SHV2-001 | official bald | official ref1 | TBD | TBD | TBD | TBD | TBD | Sanity check |

## StableHairV2 Baseline Result

Status: baseline inference succeeded, but the model is not a good immediate fit for the current Hair App MVP.

What worked:

- Official repository cloned successfully in Colab.
- StableHairV2 checkpoints downloaded from Google Drive after correcting the file IDs to the official README IDs.
- Stable Diffusion v1.5 was downloaded locally and used as a filesystem path.
- Official test inference produced `generated_video_0.mp4`.
- Private two-image test also produced an output video.

What failed or required fixes:

- The first checkpoint download attempt used incorrect Google Drive file IDs.
- `huggingface_hub` was too new for the repository's bundled `diffusers` copy. Pinning `huggingface-hub==0.30.0` fixed the missing `hf_cache_home` import.
- The official command passes a Hugging Face model ID, but `UNet3DConditionModel.from_pretrained_2d()` expected a local folder containing `unet/config.json`. Downloading `stable-diffusion-v1-5/stable-diffusion-v1-5` to `/content/models/stable-diffusion-v1-5` fixed this.
- `--use_fp16` caused a VAE dtype mismatch: `Input type (c10::Half) and bias type (float) should be the same`. Patching `test_stablehairv2.py` so all major modules are converted to `.half()` before inference fixed this.
- The output video originally appeared duplicated because the script used `torch.cat([result.videos, result.videos], dim=0)` before saving.

Quality observation:

- The model expects a bald or hair-cleared identity image. The official input is named `bald.jpg`.
- A normal source portrait with existing hair produced poor identity preservation and heavy facial/background artifacts.
- The output looked like the whole face and scene were regenerated, not like a controlled hairstyle-only transfer.

Decision:

- Do not continue StableHairV2 as the immediate MVP engine.
- Keep the record because it may be useful later if we build a bald-conversion or 3D/multi-view pipeline.
- At the time of this experiment, the planned next step was `Stable-Hair`. That decision was later replaced by the general image-editing strategy in `docs/08_general_image_editing_strategy.md`.

## StableHairV2 One-Pass Colab Recipe

This is the known working Colab flow from the first experiment. It should be used if StableHairV2 needs to be rerun later.

### Cell 1: Install Compatible Packages and Restart

```python
!pip -q install "huggingface-hub==0.30.0" "transformers==4.52.3" "peft==0.15.2" \
  "omegaconf==2.3.0" "einops==0.8.1" "prodigyopt==1.1.2" \
  "diffusers==0.33.1" "accelerate" "safetensors" "opencv-python-headless" \
  "pillow" "scipy" "sentencepiece" "tqdm" "av" "kornia" "gdown"

import os
os.kill(os.getpid(), 9)
```

### Cell 2: Check GPU and Clone Repository

```python
!nvidia-smi

import os
import torch
import huggingface_hub

print("torch:", torch.__version__)
print("cuda:", torch.cuda.is_available())
print("huggingface_hub:", huggingface_hub.__version__)
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0))

%cd /content
if not os.path.exists("/content/StableHairV2"):
    !git clone https://github.com/sunkymepro/StableHairV2.git

%cd /content/StableHairV2
```

### Cell 3: Download StableHairV2 Checkpoints

```python
%cd /content/StableHairV2

!mkdir -p /content/stablehairv2_models

!gdown --id 1AZMhui9jNRF3Z0N72VDPOwDd0JafLQ3B -O /content/stablehairv2_models/motion_module-41400000.pth
!gdown --id 1FwKPZI8lvdlZqu8R1aJ-QbE55kxHPHjU -O /content/stablehairv2_models/pytorch_model_1.bin
!gdown --id 1h3dXlo8lhZN3ee5aN0shZmpLfn5itVou -O /content/stablehairv2_models/pytorch_model_2.bin
!gdown --id 1jARfXaU6wiur85Vm1JxZ_xye0FfrUiqb -O /content/stablehairv2_models/pytorch_model_3.bin
!gdown --id 1zXXf13pV5IOn2vrV6DGI9hliEFvuPrYf -O /content/stablehairv2_models/pytorch_model.bin

!cp /content/stablehairv2_models/motion_module-41400000.pth /content/stablehairv2_models/motion_module-4140000.pth
!ls -lh /content/stablehairv2_models
```

### Cell 4: Download Stable Diffusion v1.5 Locally

```python
from huggingface_hub import snapshot_download
import os

sd15_path = "/content/models/stable-diffusion-v1-5"
os.makedirs(sd15_path, exist_ok=True)

snapshot_download(
    repo_id="stable-diffusion-v1-5/stable-diffusion-v1-5",
    local_dir=sd15_path,
)

print("unet config exists:", os.path.exists(f"{sd15_path}/unet/config.json"))
print("vae config exists:", os.path.exists(f"{sd15_path}/vae/config.json"))
print("tokenizer exists:", os.path.exists(f"{sd15_path}/tokenizer/tokenizer_config.json"))
```

### Cell 5: Patch StableHairV2 fp16 Module Dtypes

```python
from pathlib import Path

path = Path("/content/StableHairV2/test_stablehairv2.py")
text = path.read_text()

if "HAIR_APP_FP16_PATCH" not in text:
    marker = "    # Run validation inference\n    log_validation("
    patch = """    # HAIR_APP_FP16_PATCH: keep model modules on the same dtype during fp16 inference.
    if args.use_fp16:
        vae = vae.half()
        image_encoder = image_encoder.half()
        controlnet = controlnet.half()
        denoising_unet = denoising_unet.half()
        cc_projection = cc_projection.half()
        Hair_Encoder = Hair_Encoder.half()

"""
    text = text.replace(marker, patch + marker)
    path.write_text(text)
    print("patched")
else:
    print("already patched")
```

Optional clean video patch:

```python
from pathlib import Path

path = Path("/content/StableHairV2/test_stablehairv2.py")
text = path.read_text()
text = text.replace(
    "        video = torch.cat([result.videos, result.videos], dim=0)",
    "        video = result.videos",
)
path.write_text(text)
```

### Cell 6: Run Official Baseline

```python
%cd /content/StableHairV2

!python test_stablehairv2.py \
  --pretrained_model_name_or_path "/content/models/stable-diffusion-v1-5" \
  --image_encoder "openai/clip-vit-large-patch14" \
  --output_dir /content/stablehairv2_outputs/official_test_fp16_patched \
  --num_validation_images 1 \
  --validation_ids ./test_imgs/bald.jpg \
  --validation_hairs ./test_imgs/ref1.jpg \
  --model_path /content/stablehairv2_models \
  --use_fp16
```

### Cell 7: Run Private Two-Image Test

Upload the private source and hairstyle reference images to `/content`, then either use English filenames or copy them:

```python
# Replace these paths with the actual uploaded filenames if needed.
!cp "/content/source_uploaded.jpg" /content/source.jpg
!cp "/content/style_uploaded.jpg" /content/style.jpg
```

```python
%cd /content/StableHairV2

!python test_stablehairv2.py \
  --pretrained_model_name_or_path "/content/models/stable-diffusion-v1-5" \
  --image_encoder "openai/clip-vit-large-patch14" \
  --output_dir /content/stablehairv2_outputs/my_test_001 \
  --num_validation_images 1 \
  --validation_ids /content/source.jpg \
  --validation_hairs /content/style.jpg \
  --model_path /content/stablehairv2_models \
  --use_fp16
```

### Cell 8: View Output

```python
import glob
from IPython.display import Video, display

videos = glob.glob("/content/stablehairv2_outputs/**/*.mp4", recursive=True)
print("videos:", videos)

if videos:
    display(Video(videos[-1], embed=True))
else:
    print("No video output found.")
```

## StableHairV2 Decision

StableHairV2 should not be the immediate MVP engine.

Reason:

- The official baseline can run, but the model is built around bald or hair-cleared source images.
- Normal portrait inputs with existing hair produced severe artifacts.
- Identity preservation was too weak for product use.
- The model returns multi-view video, while the first MVP needs reliable still-image synthesis.
- A useful StableHairV2 path would require a separate bald conversion and masking pipeline first.

StableHairV2 can be revisited later if Hair App moves toward:

- bald conversion.
- multi-view or AR output.
- 3D-aware face/hair synthesis.
- scan-driven source preprocessing.

## Next Project Step

Do not continue directly to `Stable-Hair`. Run the general image-editing benchmark defined in `docs/08_general_image_editing_strategy.md` first. Hair-specific models remain available as research references if a later experiment needs an explicit hair-transfer architecture.
