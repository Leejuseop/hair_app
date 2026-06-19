# Base Model Design

The current "base model" is implemented as a personal base profile JSON. It is not a full 3D head model yet.

The profile is designed to preserve user-specific scan data in a reusable structure that can later support hair synthesis, preprocessing, masking, alignment, and model conditioning.

## Current Implementation

Implemented in `ai_engine/base_profile.py`:

```python
build_base_profile(scan_record)
```

The backend calls this after saving a scan bundle. The output is written to:

```text
backend/storage/scans/{scan_id}/base_profile.json
```

## Inputs

The base profile is built from the stored scan record:

- `scan_id`
- client scan session id
- upload timestamp
- scan step data
- stored frame image URLs
- compact MediaPipe landmarks
- selected key points
- quality metrics
- pose proxies

## Output Sections

The current `base_profile.json` contains:

- `scan_id`
- `version`
- `status`
- `assets`
- `raw_landmark_samples`
- `derived_metrics`
- `synthesis_anchors`
- `preview`

## Assets

`assets` stores the best image from each scan step:

- `best_front_image`
- `best_left_image`
- `best_right_image`
- `best_hairline_image`

Each asset includes:

- sample id
- image path
- image URL
- quality score

## Raw Landmark Samples

`raw_landmark_samples` intentionally keeps detailed per-sample data instead of only storing a small summary.

This matters because later synthesis experiments may need the original landmark points, not just averaged metrics.

Each raw sample keeps:

- sample id
- image path and URL
- selected key points
- compact face landmarks
- pose data
- quality metrics

## Derived Metrics

`derived_metrics` is a convenience layer for quick preview and later model preparation.

Current metrics include:

- average quality by scan step
- face width
- face height
- face ratio
- jaw width proxy
- mouth symmetry proxy
- forehead height proxy
- hairline visibility proxy
- left/right side profile metrics
- side symmetry proxy

These metrics do not replace the raw landmarks. They are summaries built on top of them.

## Synthesis Anchors

`synthesis_anchors` exposes important points for future hairstyle synthesis:

- face centerline
- hairline guide
- jaw guide
- temple points

These anchors can help later with:

- aligning generated hair to the face.
- building masks.
- preserving forehead and hairline constraints.
- checking whether output hair crosses important facial areas.

## Preview

`preview` supports the current frontend base profile panel:

- representative front image URL
- front sample id
- hairline points
- front landmarks
- quality score

The frontend draws the image, landmark dots, and hairline polyline so the user can see that the scan created real structured output.

## Future Base Model Direction

Possible next versions:

- Better face and head measurements.
- Hairline segmentation instead of landmark proxy only.
- Multi-frame averaging and outlier rejection.
- More reliable side-profile metrics.
- Optional user-uploaded selfie/video data.
- 3D head or avatar reconstruction experiments.

The current profile should stay simple, but it should preserve enough raw data so later experiments are not blocked.
