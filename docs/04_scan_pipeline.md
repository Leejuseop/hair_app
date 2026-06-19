# Scan Pipeline

The scan pipeline converts a guided camera session into a structured scan bundle.

The current implementation runs in the frontend. It uses MediaPipe Face Landmarker to read facial landmarks from the live camera feed, scores each frame, captures good frames automatically, and sends the complete bundle to the backend after all scan steps finish.

## Scan Steps

The frontend scans these steps in order:

1. `front`
2. `left`
3. `right`
4. `hairline`

Each step targets `20` good samples. Progress is calculated as:

```text
samples_collected / 20 * 100
```

The user does not manually capture photos. The app samples frames automatically when the frame passes quality checks.

## Front Step

Purpose:

- Primary face proportions.
- Symmetry proxy.
- Face centerline.
- Jaw and cheek anchor points.
- Representative preview image.

Quality requirements include:

- Face detected.
- Face centered.
- Good distance from camera.
- Front-facing yaw.
- Low roll.
- Stable frame.
- Bright and sharp enough.

## Left and Right Steps

Purpose:

- Side-profile cues.
- Yaw consistency.
- Face width and height comparison.
- Symmetry proxy between left and right scans.

Quality requirements include:

- Face detected.
- User turned in the expected direction.
- Enough side angle, but not too much.
- Face centered.
- Stable and upright frame.
- Bright and sharp enough.

## Hairline Step

Purpose:

- Forehead and hairline visibility.
- Hairline guide points.
- Temple and brow anchors.
- Better constraints for later hair masking and synthesis.

Quality requirements include:

- Face detected.
- Mostly front-facing.
- Forehead/hairline visible.
- Face not too close or too far.
- Stable, bright, and sharp enough.

## Captured Sample Data

Each good sample contains:

- `id`
- `capturedAt`
- `scanStep`
- `imageDataUrl`
- compact MediaPipe landmarks
- selected key points
- bounding box
- quality metrics
- pose proxy
- facial transformation matrix when available

The backend removes `imageDataUrl` from stored JSON, writes the actual image file, and replaces it with:

- `image_path`
- `image_url`

## Scan Bundle Shape

The frontend uploads one completed bundle after all four steps are done:

```text
{
  scanSessionId,
  completedAt,
  steps: {
    front: { status, progress, samples },
    left: { status, progress, samples },
    right: { status, progress, samples },
    hairline: { status, progress, samples }
  }
}
```

## Backend Storage

The backend stores scan data under:

```text
backend/storage/scans/{scan_id}/
  metadata.json
  base_profile.json
  front/
    front_001.jpg
    front_001.json
  left/
  right/
  hairline/
```

`backend/storage/` is local runtime data and is ignored by git.
