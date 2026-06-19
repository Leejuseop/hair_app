# Hair Synthesis Pipeline

The hair synthesis pipeline is not implemented yet.

The current project has completed the first foundation: scan collection, backend storage, and personal base profile generation. The next step is to test open-source hair transfer models and decide how our scan-derived data can improve their inputs or inference flow.

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

## Model Research Priority

Performance-first candidate order:

1. `StableHairV2` / `HairPort`
2. `Stable-Hair`
3. `HairFusion`
4. `HairFastGAN`

The immediate next experiment should run these models in Colab, starting with the best practical candidate and comparing:

- identity preservation.
- hairstyle similarity.
- hairline consistency.
- face distortion.
- support for masks or landmarks.
- code modifiability.
- GPU cost and inference speed.

## Where the Base Profile Can Help

The base profile may be useful even if the selected model originally expects only two images.

Potential integration points:

- Pre-align the user image before inference.
- Build a better face/hair mask.
- Use hairline anchors to constrain the generated hair boundary.
- Select the best scan frame as the identity source.
- Reject bad input frames before generation.
- Add landmark or mask conditioning if the model code can be modified.
- Compare generated output against expected face landmarks.

## Candidate Pipeline

First practical pipeline:

1. Choose the best user source frame from `base_profile.assets.best_front_image`.
2. Generate or estimate a hair/face mask from landmarks and later segmentation.
3. Align the hairstyle reference image to the user's face scale and pose.
4. Run the selected open-source hair transfer model.
5. Use base profile anchors to inspect or correct the output.
6. Save the generated result under backend storage.
7. Return a result URL through `GET /api/result/{result_id}`.

## Key Challenges

- Preserving the user's identity.
- Handling existing hair that covers the forehead or side areas.
- Matching reference hairstyle scale and orientation.
- Avoiding blurry or pasted-looking hair.
- Respecting the user's hairline and temples.
- Keeping face shape stable.
- Supporting future real-time AR without rebuilding everything.

## Next Work

The next code-facing milestone is not to build a custom model from scratch. It is to create a controlled Colab experiment for the top candidate models, document input/output requirements, and identify where our scan bundle can be injected.
