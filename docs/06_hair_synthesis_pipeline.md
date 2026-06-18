# Hair Synthesis Pipeline

The hair synthesis pipeline will combine a personal base model with a hairstyle reference image.

## Planned Flow

1. Parse hairstyle reference.
2. Align reference style to the user's base profile.
3. Generate hairstyle preview.
4. Blend generated hair with user face context.
5. Post-process lighting, edges, and artifacts.

## Key Challenges

- Preserving identity.
- Matching head pose and scale.
- Respecting hairline constraints.
- Avoiding unnatural blending artifacts.
- Keeping mobile latency acceptable.

## MVP Status

The current MVP returns placeholder responses only. No model inference is included yet.

