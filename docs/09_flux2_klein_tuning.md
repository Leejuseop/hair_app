# FLUX.2 Klein Tuning Decision Record and Current Role

Original decision date: 2026-06-20
Reclassified: 2026-06-21
Status: 2D tuning plan preserved but superseded as the immediate top priority by the true 3D architecture; no training run completed

## Why This Document Still Exists

Hair App은 2026-06-20에 `FLUX.2 [klein] base-9B`를 user portrait + hairstyle reference 2D editing의 first tuning target으로 선택했다. User가 Hugging Face Space에서 가능성을 확인했고, H100에서 fine-tuning 가능한 undistilled multi-reference base를 원했다.

그 다음 product requirement가 더 명확해졌다. 최종 목표는 한 장의 edited portrait가 아니라:

- editable hairless head mesh;
- actual-photo face UV texture;
- independent 3D strand hair;
- scalp/hairline fitting;
- rotatable 3D result

이다.

따라서 FLUX.2 tuning은 immediate top priority가 아니다. 이 문서는 당시 선택 근거와 재사용 가능한 기술 아이디어를 보존한다. 현재 source of truth는 `10_3d_hair_app_master_plan.md`다.

## Original Decision

Original target:

- model: `black-forest-labs/FLUX.2-klein-base-9B`;
- task: two-image hairstyle compositing;
- method: LoRA on DiT transformer;
- frozen components: VAE and text encoder;
- optimization: cached text embeddings and image latents;
- hardware: single Colab H100;
- data: portrait + hairstyle reference -> target edited portrait;
- evaluation: identity, style, hairline, landmarks, protected regions, artifacts.

No actual LoRA run, checkpoint, or benchmark result was produced before the architecture changed.

## Why It Was Chosen at the Time

1. Undistilled base variant was more appropriate for fine-tuning than a few-step distilled checkpoint.
2. Reference images entered through the VAE path, making cached/empty text conditioning experiments plausible.
3. Native multi-reference editing matched portrait + style input.
4. 9B offered a higher ceiling than 4B while fitting H100-class hardware.
5. Diffusers and ecosystem tooling supported edit-LoRA experimentation.
6. The user had H100 access, so quality mattered more than minimal VRAM.

These arguments remain relevant for future 2D work. They do not make FLUX.2 a 3D geometry or strand-hair model.

## Current Valid Roles

### 1. 2D Quality Benchmark

Compare a polished 2D result against the true 3D render to understand the visual gap.

### 2. Auxiliary Hairstyle Views

Generate several plausible side/rear hypotheses from one hairstyle image. These are priors, not observed truth, and must be tagged with uncertainty.

### 3. Render Refinement

Improve a server-rendered still while preserving face, hairline, camera, and protected regions. Refined pixels should not silently become geometry or UV evidence.

### 4. Temporary 2D Fallback

Offer a clearly labeled 2D preview if the 3D path is not yet product-ready.

### 5. Training Data Bootstrap Research

Generate candidate targets for controlled experiments. Synthetic targets require filtering and must not be assumed equivalent to real paired data.

## Roles FLUX.2 Does Not Fill

- It does not replace Pixel3DMM/KaoLRM for editable head geometry.
- It does not replace the multi-photo UV baker for actual user skin pixels.
- It does not output trustworthy 3D strand hair like the intended DiffLocks/Im2Haircut path.
- It does not perform deterministic scalp retargeting or collision correction.
- Independently edited views do not guarantee one consistent rotatable asset.

## If Tuning Is Reactivated

### Revalidation First

Before executing the old plan:

1. re-check current official model cards, code, weights, and licenses;
2. reproduce untuned inference on a fixed Hair App 2D set;
3. define the exact role: fallback, auxiliary views, or render refinement;
4. ensure that the target data matches that role;
5. compare with Qwen Image Edit, HiDream, HairPort-like methods, or newer candidates;
6. decide whether LoRA beats prompt/control/compositing solutions.

### Original Planned Training Shape

- LoRA on the transformer core.
- VAE frozen.
- Text encoder frozen and optionally removed from resident memory by cached embeddings.
- Source portrait and style reference as image conditions.
- Fixed or limited instruction vocabulary.
- Face/hair masks, landmarks, hairline, camera/render metadata as side information.
- bf16 on H100; FP8/offload only if useful, not by default.

### Role-Specific Dataset

For 2D fallback:

- user portrait;
- hairstyle reference;
- target edited portrait;
- identity/protected-region masks.

For auxiliary views:

- one or more source style images;
- real multi-view hairstyle targets where legally available;
- camera/pose labels;
- uncertainty and consistency supervision.

For render refinement:

- raw 3D render;
- depth, normal, face, hair, and protected-region masks;
- high-quality target render;
- same camera and geometry.

Do not use one mixed dataset without recording the role.

### Evaluation

- identity embedding similarity;
- landmark displacement;
- hairstyle reference similarity;
- hairline/temple fit;
- protected-region preservation;
- cross-view consistency;
- deviation from depth/normal evidence;
- artifacts, time, VRAM, failure rate;
- whether the result improves user decisions beyond the unrefined 3D render.

## License Note

The earlier plan treated `klein base-9B` as research/non-commercial and `base-4B` as the more permissive commercial fallback, subject to exact current license verification. This must be re-audited when tuning resumes. Code license, weight license, dataset license, LoRA derivative terms, and generated-data use are separate questions.

## Current Decision Gate

Do not start FLUX.2 LoRA merely because the old plan exists. Reactivate only if a controlled experiment shows that 2D fallback, auxiliary views, or render refinement is a measured bottleneck or valuable parallel product path.

Immediate project priority remains:

1. Pixel3DMM/KaoLRM geometry comparison;
2. multi-photo UV prototype;
3. 3D hair model comparison;
4. geometric fitting;
5. interactive asset.

This priority can change after results, and any change should update `newchat.md`, `README.md`, and the master plan.

## Preserved Sources

- FLUX.2 repository: <https://github.com/black-forest-labs/flux2>
- FLUX.2 klein LoRA guide: <https://huggingface.co/blog/black-forest-labs/flux-2-klein-lora>
- Diffusers FLUX.2 training: <https://github.com/huggingface/diffusers/blob/main/examples/dreambooth/README_flux2.md>
- Black Forest Labs training docs: <https://docs.bfl.ml/flux_2/flux2_klein_training>
- SimpleTuner FLUX.2 quickstart: <https://github.com/bghira/SimpleTuner/blob/main/documentation/quickstart/FLUX2.md>
