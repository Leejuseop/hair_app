# General Image Editing Strategy

## Decision

Hair App will prioritize a high-performance open-weight general image-editing foundation model instead of using a hair-only research model as the main MVP engine.

The foundation model will handle photorealistic editing. Hair App will provide the domain-specific layer:

- guided scan and best-frame selection.
- face, hair, and protected-region masks.
- facial landmarks and hairline anchors.
- identity and geometry validation.
- hairstyle-reference preparation.
- retry, ranking, compositing, and post-processing.

This is the current technical direction. Real synthesis is not implemented in the application yet.

## Experiment Status

- `StableHairV2`: completed negative baseline. The official Colab inference ran, but product-like portrait inputs produced poor identity preservation and severe artifacts. See `docs/07_hair_engine_experiment_plan.md`.
- `FLUX.1 Kontext [dev]`: one informal Hugging Face Space test produced an unsatisfactory result. This is not a controlled benchmark of FLUX.2.
- `Qwen-Image-Edit-2511`: not yet run in Colab; first planned controlled baseline.
- `HiDream-O1-Image`: not yet run in Colab; second planned controlled baseline.
- `FLUX.2 [klein] Base 4B` and `LongCat-Image-Edit`: researched but not yet run.
- `HunyuanImage-3.0-Instruct`: researched and excluded from active selection because of infrastructure and license constraints.

## Candidate Shortlist

### Qwen-Image-Edit-2511

- 20B image foundation model with multi-image editing support.
- Useful for the exact MVP input shape: user portrait, hairstyle reference, and instruction.
- Apache 2.0 repository license.
- LoRA training recipes are available through ModelScope DiffSynth-Studio.
- Primary concern: memory and training cost are higher than smaller candidates.

### HiDream-O1-Image

- 8B unified model released in May 2026.
- Supports image editing, multi-reference subject personalization, layout control, skeleton conditioning, and native output up to 2048 x 2048.
- MIT licensed model and inference code.
- Promising for identity preservation and scan-derived controls.
- Primary concern: it is new, and its editing/fine-tuning ecosystem is less mature than Qwen's.

### FLUX.2 [klein] Base 4B

- Apache 2.0 base checkpoint designed for LoRA and fine-tuning.
- Supports single-reference and multi-reference image editing.
- Small enough to iterate quickly compared with 20B-32B models.
- Strong candidate for the first custom Hair App training experiment.
- Primary concern: raw maximum quality may be below the larger quality-first candidates.

### LongCat-Image-Edit

- 6B image-editing model with strong reported open-model benchmark results.
- Official repository includes edit SFT, LoRA, DPO, and edit DPO training code.
- Apache 2.0 license and practical memory requirements with CPU offload.
- Primary concern: the documented edit pipeline uses one reference image, so hairstyle-reference transfer may require input adaptation or training changes.

### Step1X-Edit-v1p2

- Apache 2.0 instruction-editing model with reasoning and reflection modes.
- Useful as an additional quality baseline for difficult instructions.
- Lower priority because direct multi-reference hairstyle transfer is less clearly supported.

### HunyuanImage-3.0-Instruct

- 80B-total, 13B-active MoE model with reasoning-based editing and fusion of up to three input images.
- Technically well matched to a portrait plus hairstyle-reference workflow.
- Official execution guidance recommends at least eight 80 GB GPUs for the Instruct and Instruct-Distil checkpoints, so a normal single-GPU Colab session is not a practical baseline environment. The text-to-image-only checkpoint has a lower recommendation of three 80 GB GPUs.
- The Tencent Hunyuan Community License explicitly excludes South Korea from its licensed territory.
- Keep it as a quality reference only; do not select it as the Hair App implementation or fine-tuning base under the current license and infrastructure constraints.

## Desk-Research Scoring (Non-Benchmark, 2026-06)

The following 1-10 scores compare the user-requested subset from public documentation only. They are desk research, not the Phase 1 controlled benchmark, and do not replace the Hair App-specific test below.

Scale direction:

- Performance: higher is better (10 = best quality/capability for the portrait + hairstyle-reference + instruction shape).
- Tuning difficulty: higher is harder (lower is more favorable).
- GPU requirement: higher is heavier (lower is more favorable).

| Model | Performance (higher = better) | Tuning difficulty (higher = harder) | GPU requirement (higher = heavier) |
| --- | :---: | :---: | :---: |
| Qwen-Image-Edit-2511 (20B) | 9 | 5 | 8 |
| FLUX.2 [klein] 4B | 6 | 3 | 2 |
| HiDream-O1-Image (8B) | 8 | 6 | 5 |

Notes:

- Qwen-Image-Edit-2511: strongest native multi-image editing match and the most mature LoRA ecosystem (DiffSynth-Studio), but the heaviest model (~40 GB full precision; 12-24 GB only with quantization).
- FLUX.2 [klein] 4B: smallest and cheapest to fine-tune (Apache 2.0 base built for LoRA), runs on 8 GB-class GPUs, but a lower raw quality ceiling. "FLUX.2" varies widely by variant: `dev` 32B would score higher on performance but needs 141 GB+ (H200/B200); `klein` 9B sits in between.
- HiDream-O1-Image: pixel-native unified transformer with layout/skeleton controls useful for scan-derived conditioning; newer and less proven for the exact portrait + hairstyle-reference shape, mid-weight (~24 GB full, ~10 GB FP8).

These are June 2026 figures from model cards and hardware guides; re-verify exact VRAM numbers before relying on them.

## Selected Tuning Target (2026-06-20)

The first tuning target is now decided: **`FLUX.2 [klein] base-9B`**. The user validated promising quality hands-on in a Hugging Face Space and chose to start adaptation directly on a tunable, architecturally-fitting base, ahead of completing the full untuned Qwen/HiDream benchmark above.

Key reasons: base (undistilled) is the correct fine-tuning starting point; FLUX.2's text encoder is cleanly separable from the VAE image path, matching the goal of bypassing the text encoder (`Qwen-Image-Edit` fuses text and image in `Qwen2.5-VL` and cannot be cleanly stripped); native multi-reference editing; 9B raises the quality ceiling while fitting a single H100; mature official edit-LoRA tooling. `klein base-9B` is non-commercial, so a commercial launch would switch to `klein base-4B` (Apache 2.0) or license 9B.

Full decision record and planned tuning approach: `docs/09_flux2_klein_tuning.md`.

## Recommended Experiment Order

### Phase 1: Untuned Quality Benchmark

Run identical inputs through:

1. `Qwen-Image-Edit-2511`.
2. `HiDream-O1-Image` full model.
3. `FLUX.2 [klein] 4B` or Base 4B.
4. `LongCat-Image-Edit` using a text-described hairstyle baseline.

Each test must use the same source portrait, hairstyle reference where supported, prompt, output size, and seed count.

### Phase 2: Hair App Scoring

Evaluate each result with:

- face identity similarity.
- face landmark displacement.
- background and clothing preservation.
- hairstyle-reference similarity.
- hairline and temple fit.
- visible artifacts.
- inference time and GPU memory.

No single public benchmark substitutes for this project-specific test.

### Phase 3: First Adaptation

If Qwen or HiDream clearly wins raw quality, begin with its LoRA path. If quality is close, prefer `FLUX.2 [klein] Base 4B` or `LongCat-Image-Edit` for faster and more transparent training iteration.

The first dataset format should preserve:

- source portrait.
- hairstyle reference when supported.
- target edited portrait.
- edit instruction.
- face/hair masks.
- landmarks and hairline anchors as side metadata.

Start with LoRA or edit SFT. Add custom auxiliary losses only after the basic training loop is reproducible.

## Control Integration

Masks and landmarks are not automatically understood as raw JSON by every model. Integrate them through the least invasive supported path:

1. Use a native mask, layout, skeleton, or multi-reference input when available.
2. Otherwise render an annotated control image or crop from the scan data.
3. Composite original protected pixels back after generation when strict preservation is required.
4. Score identity and landmarks after generation and reject weak outputs.
5. Modify the training loss or architecture only when wrapper-level controls are insufficient.

## Immediate Next Step

Create one clean Colab notebook for `Qwen-Image-Edit-2511` and run a two-image hairstyle-transfer baseline before any fine-tuning. Repeat the same test with `HiDream-O1-Image`, then choose the first adaptation target from measured results.

## Official Sources

- Qwen Image: `https://github.com/QwenLM/Qwen-Image`
- Qwen LoRA recipes: `https://github.com/modelscope/DiffSynth-Studio`
- HiDream O1 Image: `https://github.com/HiDream-ai/HiDream-O1-Image`
- FLUX.2: `https://github.com/black-forest-labs/flux2`
- LongCat Image: `https://github.com/meituan-longcat/LongCat-Image`
- Step1X Edit: `https://github.com/stepfun-ai/Step1X-Edit`
- HunyuanImage 3.0: `https://github.com/Tencent-Hunyuan/HunyuanImage-3.0`
