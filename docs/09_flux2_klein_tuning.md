# FLUX.2 [klein] base-9B — Tuning Target Decision and Plan

Decision date: 2026-06-20. Status: decision recorded. No training code or runs yet; the reference repo was cloned for architecture study only.

This document records which model Hair App will fine-tune first, why, and the planned tuning approach. It builds on `docs/08_general_image_editing_strategy.md`.

## Decision

The first tuning target and synthesis base is **`FLUX.2 [klein] base-9B`** (`black-forest-labs/FLUX.2-klein-base-9B`), used for two-image hairstyle compositing (user portrait + hairstyle reference) and general portrait editing.

This is a decision to **start adaptation directly on FLUX.2**, ahead of completing the full untuned `Qwen-Image-Edit-2511` / `HiDream-O1-Image` benchmark described in `docs/08`. The user validated promising quality hands-on in a Hugging Face Space and prioritizes iterating on a tunable, architecturally-fitting base.

## Requirements that drove the choice

- Input is two images composited: user portrait + reference (multi-reference editing).
- Synthesis quality is the number-one priority.
- Text understanding is not needed at inference; the user wants to bypass/remove the text encoder.
- Plan is to fine-tune the synthesis core (LoRA), not train from scratch.
- Current phase is testing (commercial later). The user has a single Colab H100.

## Why FLUX.2 [klein] base-9B

1. **Base (undistilled) = correct fine-tuning starting point.** Distilled variants (`dev`, `klein` distilled) bake in few-step and guidance behavior and are poor LoRA bases. The base variant keeps the full training signal and runs with real CFG and arbitrary steps.
2. **Clean text-encoder separability (matches the "remove text encoder" approach).** FLUX.2 routes text only through the text encoder, while reference images enter through the VAE as separate image tokens. So the text encoder can be dropped at inference (`text_encoder=None` plus precomputed or empty embeddings) without losing image conditioning. Verified in the reference code: text enters via `txt_in`; reference images are VAE-encoded into tokens (`encode_image_refs`). By contrast, `Qwen-Image-Edit` feeds the input image through both `Qwen2.5-VL` and the VAE, so its "text encoder" also performs image semantics and cannot be cleanly stripped.
3. **Native multi-reference editing** for the portrait + hairstyle-reference shape.
4. **9B (vs 4B) raises the quality ceiling** while still fitting a single H100 (~18-29 GB), matching the quality-first priority. 4B is the cheaper, commercial-safe fallback.
5. **Mature, official edit-LoRA tooling:** diffusers `train_dreambooth_lora_flux2_img2img.py` (text-to-image and image-to-image), Black Forest Labs klein training docs, SimpleTuner FLUX.2, ostris ai-toolkit, and a hosted `flux-2-klein-9b-base-trainer` on fal.
6. **H100-friendly:** one GPU is sufficient for both inference and LoRA.

## Alternatives considered (and why not first)

- `Qwen-Image-Edit-2511` (20B): highest quality ceiling and the most mature LoRA ecosystem, Apache 2.0, but its `Qwen2.5-VL` encoder fuses text and image semantics, so the text encoder cannot be cleanly removed (conflicts with the lightweight approach); also the heaviest model. Kept as a quality reference and possible later comparison.
- `FLUX.2 [dev]` (32B): higher ceiling but distilled (poor tuning base), non-commercial license, and needs FP8 or sequential offload on a single H100. Quality reference only.
- `FLUX.2 [klein]` distilled 4B / 9B / 9b-kv: distilled, so good for fast inference but not ideal as a fine-tuning base.
- `FLUX.2 [klein] base-4B`: Apache 2.0, lightest and cheapest iteration; the commercial-safe and prototyping fallback, but a lower quality ceiling than 9B.
- `HiDream-O1-Image` (8B): strong, MIT, with scan-friendly layout/skeleton controls, but a newer ecosystem and less proven for this exact shape.

## License and commercial note

- `klein base-9B` is under the FLUX.2 Non-Commercial License: fine for testing and research, not for commercial launch.
- For commercialization: switch to `klein base-4B` (Apache 2.0) and retrain the LoRA, or obtain a Black Forest Labs commercial license for 9B/dev.
- The inference code (the `flux2` repo) and diffusers are Apache 2.0.

## Planned tuning approach (not yet implemented)

- **Method:** LoRA on the DiT transformer (the synthesis core). VAE and text encoder frozen.
- **Text/VAE caching:** precompute the fixed instruction's text embedding once and cache image latents, so the text encoder is not resident during training. This implements the "remove text encoder" goal and saves VRAM.
- **Dataset = triplets:** condition image(s) (portrait, plus hairstyle reference) -> target image (desired edited result) + caption (one fixed instruction). Hair App scan assets (best front frame, landmarks, hairline, masks) are preserved as side metadata for identity/hairline conditioning and evaluation.
- **Data sourcing (the main open decision and blocker):** (a) same-person different-hairstyle pairs, (b) bootstrap targets from a stronger model (for example `dev`) then distill, or (c) public hairstyle datasets.
- **Tooling:** diffusers img2img LoRA script (primary); SimpleTuner, ai-toolkit, or the fal hosted trainer as alternatives.
- **Hardware:** single H100, bf16 (plus FP8). The base variant needs roughly 50 inference steps for a clean preview.
- **Evaluation (Hair App-specific, per `docs/08` Phase 2):** identity similarity, hairstyle-reference similarity, hairline and temple fit, landmark displacement, background and clothing preservation, visible artifacts, time and VRAM. Compare pre- versus post-tuning on fixed seeds.
- **Iteration:** if LoRA is insufficient, add data, then edit-SFT, then identity/landmark auxiliary losses. Defend outputs with protected-region compositing plus retry and ranking.

## Sources

- FLUX.2 klein LoRA guide: `https://huggingface.co/blog/black-forest-labs/flux-2-klein-lora`
- diffusers FLUX.2 training: `https://github.com/huggingface/diffusers/blob/main/examples/dreambooth/README_flux2.md`
- Black Forest Labs klein training docs: `https://docs.bfl.ml/flux_2/flux2_klein_training`
- SimpleTuner FLUX.2 quickstart: `https://github.com/bghira/SimpleTuner/blob/main/documentation/quickstart/FLUX2.md`
- FLUX.2 model variants and licensing: `https://deepwiki.com/black-forest-labs/flux2/2.2-model-variants`
