# Idea Evolution

Hair App started as a simple mobile web MVP: scan the user, upload a hairstyle reference, and show a generated preview.

## Stage 1: Structured Scan Foundation

The first implementation focused on data collection instead of generation quality:

1. Guide the user through `front`, `left`, `right`, and `hairline` scans.
2. Capture good frames automatically with MediaPipe Face Landmarker.
3. Store raw landmarks and frame images in a backend scan bundle.
4. Generate a reusable personal `base_profile.json`.

This foundation is implemented. The base profile is not a complete 3D avatar; it is a structured representation for alignment, masking, controls, and quality checks.

## Stage 2: Hair-Specific Model Experiment

The project initially prioritized hair-transfer research models such as StableHairV2, Stable-Hair, HairFusion, HairFastGAN, and HairPort.

StableHairV2 was eventually executed in Colab, but a normal portrait plus hairstyle reference produced heavy artifacts and poor identity preservation. The official model also targets bald or hair-cleared source inputs and multi-view video rather than the first still-image MVP.

This experiment showed that a model can be academically hair-specific while still being a weak product foundation.

## Stage 3: General Image Editing Foundation

The current direction is:

1. Use a high-performance general open-weight image-editing model for photorealistic editing.
2. Keep the user portrait and hairstyle reference as separate inputs when multi-reference editing is supported.
3. Convert scan data into frame selection, masks, hairline guides, layout or skeleton controls, and post-generation validation.
4. Preserve identity using face similarity, landmark displacement, protected-region comparison, retry, and ranking.
5. Fine-tune the winning baseline with LoRA or editing SFT.

The active quality candidates are `Qwen-Image-Edit-2511` and `HiDream-O1-Image`. `FLUX.2 [klein] Base 4B` and `LongCat-Image-Edit` are practical adaptation candidates if their quality is competitive.

## Why Not Only A Closed API

Closed editors such as GPT Image are useful quality references, but they do not give the project enough control over training, internal conditioning, identity losses, or deployment. Hair App therefore uses closed systems only as benchmarks while targeting an open-weight foundation for the actual engine.

## Current Decision

Keep the existing scan and base-profile implementation. Do not build a foundation model from scratch and do not continue directly to another hair-only model. First run a controlled Qwen-versus-HiDream baseline with identical portrait, hairstyle reference, prompt, and evaluation criteria. Fine-tune only after the raw-quality winner is known.
