# Hair Synthesis Pipeline

The hair synthesis pipeline is not implemented yet.

The current project has completed the first foundation: scan collection, backend storage, and personal base profile generation. The next step is to evaluate high-performance open-weight image-editing models and build Hair App-specific controls around the best foundation.

## Intended Product Flow

Long-term user flow:

1. User completes a guided scan.
2. The backend creates a personal base profile.
3. User uploads a hairstyle reference image.
4. The synthesis engine uses:
   - user photo or best scan frame
   - hairstyle reference image
   - face landmarks
   - hairline anchors
   - masks or segmentation maps
   - base profile metrics
5. The engine generates a personalized hairstyle preview.
6. The app post-processes and returns the final image.

## Current Implementation Status

Implemented:

- Scan bundle collection.
- Backend scan storage.
- `base_profile.json` generation.
- Placeholder API routes for style reference, generation, and result lookup.

Not implemented:

- Style reference image persistence.
- Hair segmentation.
- Face/hair masks.
- Model inference.
- Generated output image.
- Post-processing.

## Model Research Direction

StableHairV2 was tested first. The original baseline ran in Colab after dependency and script patches, but normal portrait inputs produced poor identity preservation and severe artifacts. It is no longer the immediate MVP candidate.

Hair-only research models are now secondary references rather than the primary implementation path. The active shortlist is:

1. `Qwen-Image-Edit-2511`: multi-image editing and a mature LoRA ecosystem.
2. `HiDream-O1-Image`: native 2K editing, multi-reference personalization, layout, and skeleton conditioning.
3. `FLUX.2 [klein] Base 4B`: multi-reference editing and a compact base checkpoint intended for fine-tuning.
4. `LongCat-Image-Edit`: strong editing results with official SFT, LoRA, DPO, and edit-training code.
5. `Step1X-Edit-v1p2`: a reasoning-oriented instruction-editing fallback.

The immediate next experiment should run these models in Colab, starting with the best practical candidate and comparing:

- identity preservation.
- hairstyle similarity.
- hairline consistency.
- face distortion.
- multi-reference input support.
- support for masks, annotated control images, layout, or landmarks.
- code modifiability.
- LoRA or editing SFT feasibility.
- GPU cost and inference speed.

## Where the Base Profile Can Help

The base profile is not expected to be passed as raw JSON to a foundation model. Hair App should convert it into model-friendly controls and validation signals.

Potential integration points:

- Pre-align the user image before inference.
- Build a better face/hair mask.
- Use hairline anchors to constrain the generated hair boundary.
- Select the best scan frame as the identity source.
- Reject bad input frames before generation.
- Render landmarks, hairline guides, masks, or layout controls into supported conditioning inputs.
- Compare generated output against expected face landmarks.
- Reject outputs whose face embedding or protected-region similarity is too low.

## Candidate Pipeline

First practical pipeline:

1. Choose the best user source frame from `base_profile.assets.best_front_image`.
2. Generate or estimate a hair/face mask from landmarks and later segmentation.
3. Keep the user portrait and hairstyle reference as separate inputs when the model supports multi-reference editing.
4. Run the selected general image-editing foundation model.
5. Restore pixels outside the editable region when strict preservation is needed.
6. Score identity, landmarks, hairstyle similarity, hairline fit, and artifacts.
7. Retry or reject weak candidates, then post-process the best result.
8. Save the generated result under backend storage.
9. Return a result URL through `GET /api/result/{result_id}`.

## Key Challenges

- Preserving the user's identity.
- Handling existing hair that covers the forehead or side areas.
- Matching reference hairstyle scale and orientation.
- Avoiding blurry or pasted-looking hair.
- Respecting the user's hairline and temples.
- Keeping face shape stable.
- Supporting future real-time AR without rebuilding everything.

## Next Work

The next code-facing milestone is a controlled Colab benchmark using the same source portrait, hairstyle reference, prompt, and evaluation sheet for every candidate. No fine-tuning should begin until the raw baselines are compared.

`docs/07_hair_engine_experiment_plan.md` preserves the completed StableHairV2 experiment. The active strategy and new candidate order are tracked in `docs/08_general_image_editing_strategy.md`.

Update (2026-06-20): the first tuning target is now `FLUX.2 [klein] base-9B` (see `docs/09_flux2_klein_tuning.md`). The controlled benchmark above stays as the reference plan, but adaptation will start on this base directly.
