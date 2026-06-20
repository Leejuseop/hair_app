# Problem Definition

People choose hairstyles from reference images, but it is hard to know whether a hairstyle will fit their own face, head shape, side profile, and hairline.

Most hairstyle preview tools rely on a single selfie. A single photo can work for a rough demo, but it gives weak information about:

- Face proportions.
- Jaw and cheek contour.
- Hairline position.
- Forehead visibility.
- Left and right side profile.
- Pose and scale consistency.

Hair App is based on the assumption that a guided scan can provide stronger personal context than one flat image. The scan does not replace the final synthesis model, but it can provide useful conditioning data for alignment, masking, anchoring, and quality control.

## Target User Need

- Preview a hairstyle before committing to a salon visit.
- Compare reference hairstyles against personal facial structure.
- Reduce uncertainty around hairline, face shape, and side-profile fit.
- Get a result that feels more personal than a generic two-image hair transfer demo.

## Product Hypothesis

If the app collects a structured face scan first, the later hair synthesis engine can use more reliable user-specific information:

- Where the user's face landmarks are.
- Where the approximate hairline and forehead area are.
- How the face looks from the front and sides.
- Which frame is sharp, centered, and stable enough to use.

This should improve synthesis preparation even when the generation engine is a general open-weight image editor that does not natively understand Hair App's scan JSON.

## Current MVP Problem Statement

Build a mobile web flow that can:

1. Guide the user through a four-step face scan.
2. Collect good frames and landmark data automatically.
3. Store the scan bundle on the backend.
4. Generate a reusable personal base profile.
5. Prepare the project for later hair synthesis experiments.

The current synthesis hypothesis is to combine a high-performance general image-editing foundation model with Hair App-specific preprocessing and validation. Hair-only research models are retained as references, not the primary MVP direction.
