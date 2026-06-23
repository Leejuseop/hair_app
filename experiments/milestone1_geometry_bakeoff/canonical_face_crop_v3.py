"""Five-point constellation roll for Hair App canonical face crops.

V3 keeps V2's face selection, reflect padding, validity mask, and metadata
contract.  Its only intentional experiment change is roll estimation: instead
of trusting the two-eye line, it fits the complete eye/nose/mouth landmark
constellation to a canonical upright constellation using one similarity
rotation and scale around the nose anchor.

Only rotation is applied to the image.  The fit does not warp the face or
remove yaw/pitch, so multi-view geometry evidence remains available.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image

from canonical_face_crop_v2 import (
    DERIVED_DIRECTORIES,
    DERIVED_FILES,
    LANDMARK_NAMES,
    CanonicalCropResultV2,
    FaceObservationV2,
    FacerRetinaFaceDetectorV2,
    _make_reflected_source,
    _safe_clean_output,
    iter_input_images,
    load_oriented_rgb,
    transform_points,
)


# left eye, right eye, nose tip, left mouth corner, right mouth corner.
# Absolute values are not identity targets.  They only define an upright,
# symmetric orientation for the single rotation/scale least-squares fit.
CANONICAL_FIVE_POINT_TEMPLATE = np.asarray(
    [
        [-0.90, -0.70],
        [0.90, -0.70],
        [0.00, 0.00],
        [-0.65, 0.75],
        [0.65, 0.75],
    ],
    dtype=np.float64,
)


def _axis_roll_degrees(vector: np.ndarray, expected_axis: str) -> float:
    dx, dy = (float(value) for value in vector)
    if expected_axis == "horizontal":
        return math.degrees(math.atan2(dy, dx))
    if expected_axis == "vertical":
        return math.degrees(math.atan2(-dx, dy))
    raise ValueError(f"unsupported expected_axis: {expected_axis}")


def estimate_five_point_roll(
    observation: FaceObservationV2,
    *,
    template: np.ndarray = CANONICAL_FIVE_POINT_TEMPLATE,
) -> dict:
    """Fit the full five-point shape to an upright template around the nose."""

    observation.validate()
    source = np.asarray(observation.landmarks5_xy, dtype=np.float64)
    target = np.asarray(template, dtype=np.float64)
    if target.shape != (5, 2):
        raise ValueError("template must have shape [5, 2]")

    nose_index = 2
    outer_indices = np.asarray([0, 1, 3, 4])
    source_rays = source[outer_indices] - source[nose_index]
    target_rays = target[outer_indices] - target[nose_index]
    source_energy = float(np.sum(source_rays**2))
    if source_energy <= 1e-9:
        raise ValueError("five-point constellation is degenerate")

    covariance = source_rays.T @ target_rays
    left, singular_values, right_transpose = np.linalg.svd(covariance)
    rotation = left @ right_transpose
    if np.linalg.det(rotation) < 0:
        left[:, -1] *= -1.0
        rotation = left @ right_transpose

    roll_degrees = math.degrees(math.atan2(float(rotation[1, 0]), float(rotation[0, 0])))
    scale = float(np.sum(singular_values) / source_energy)
    aligned_rays = scale * source_rays @ rotation
    residual_vectors = aligned_rays - target_rays
    target_rms = math.sqrt(float(np.mean(np.sum(target_rays**2, axis=1))))
    normalized_residual = math.sqrt(
        float(np.mean(np.sum(residual_vectors**2, axis=1)))
    ) / max(target_rms, 1e-9)

    left_eye, right_eye, nose, left_mouth, right_mouth = source
    eye_midpoint = (left_eye + right_eye) / 2.0
    mouth_midpoint = (left_mouth + right_mouth) / 2.0
    component_rolls = {
        "eye_line": _axis_roll_degrees(right_eye - left_eye, "horizontal"),
        "mouth_line": _axis_roll_degrees(right_mouth - left_mouth, "horizontal"),
        "eye_to_nose_axis": _axis_roll_degrees(nose - eye_midpoint, "vertical"),
        "nose_to_mouth_axis": _axis_roll_degrees(mouth_midpoint - nose, "vertical"),
        "eye_to_mouth_axis": _axis_roll_degrees(mouth_midpoint - eye_midpoint, "vertical"),
    }
    component_values = list(component_rolls.values())
    component_spread = max(component_values) - min(component_values)

    warnings = []
    if normalized_residual > 0.30:
        warnings.append("five_point_shape_mismatch")
    if component_spread > 20.0:
        warnings.append("five_point_axis_disagreement")
    if abs(roll_degrees) > 45.0:
        warnings.append("five_point_roll_extreme")

    return {
        "method": "nose_anchored_five_point_similarity",
        "roll_degrees": roll_degrees,
        "fit_scale": scale,
        "normalized_fit_residual": normalized_residual,
        "component_roll_degrees": component_rolls,
        "component_roll_spread_degrees": component_spread,
        "canonical_template": target.tolist(),
        "rotation_matrix_2x2": rotation.tolist(),
        "warnings": warnings,
    }


def canonical_crop_v3(
    image: Image.Image,
    observation: FaceObservationV2,
    *,
    output_size: int = 512,
    bbox_margin: float = 1.50,
    vertical_center_offset: float = -0.04,
) -> CanonicalCropResultV2:
    """Create a V2-compatible crop driven by the five-point roll fit."""

    observation.validate()
    if output_size <= 0:
        raise ValueError("output_size must be positive")
    if bbox_margin <= 1.0:
        raise ValueError("bbox_margin must be greater than 1")
    if not -0.25 <= vertical_center_offset <= 0.25:
        raise ValueError("vertical_center_offset is outside the supported range")

    image = image.convert("RGB")
    source_width, source_height = image.size
    x1, y1, x2, y2 = observation.bbox_xyxy
    bbox_width = x2 - x1
    bbox_height = y2 - y1
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0 + vertical_center_offset * bbox_height
    crop_side = max(bbox_width, bbox_height) * bbox_margin
    scale = output_size / crop_side

    five_point_fit = estimate_five_point_roll(observation)
    proposed_roll = five_point_fit["roll_degrees"]
    # A rotation beyond 45 degrees is more likely a detector ordering failure
    # than an intended selfie roll. Preserve the photo and skip only rotation.
    applied_roll = proposed_roll if abs(proposed_roll) <= 45.0 else 0.0
    angle = math.radians(applied_roll)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    output_center = output_size / 2.0

    source_to_crop = np.asarray(
        [
            [
                scale * cosine,
                scale * sine,
                output_center - scale * cosine * center_x - scale * sine * center_y,
            ],
            [
                -scale * sine,
                scale * cosine,
                output_center + scale * sine * center_x - scale * cosine * center_y,
            ],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    crop_to_source = np.linalg.inv(source_to_crop)

    padded_image, crop_to_padded, reflected_padding = _make_reflected_source(
        image,
        crop_to_source,
        output_size,
    )
    affine = tuple(float(value) for value in crop_to_padded[:2, :].reshape(-1))
    crop = padded_image.transform(
        (output_size, output_size),
        Image.Transform.AFFINE,
        affine,
        resample=Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0),
    )

    original_validity = Image.new("L", image.size, color=255)
    validity_affine = tuple(float(value) for value in crop_to_source[:2, :].reshape(-1))
    observed_source_mask = original_validity.transform(
        (output_size, output_size),
        Image.Transform.AFFINE,
        validity_affine,
        resample=Image.Resampling.NEAREST,
        fillcolor=0,
    )
    observed_fraction = float(np.mean(np.asarray(observed_source_mask) > 127))
    reflected_fraction = 1.0 - observed_fraction
    transformed_landmarks = transform_points(source_to_crop, observation.landmarks5_xy)
    bbox_corners = transform_points(
        source_to_crop,
        ((x1, y1), (x2, y1), (x2, y2), (x1, y2)),
    )

    warnings = list(five_point_fit["warnings"])
    if observation.score < 0.55:
        warnings.append("low_detection_confidence")
    if min(bbox_width, bbox_height) < 64:
        warnings.append("low_source_face_resolution")
    if abs(proposed_roll) > 45.0:
        warnings.append("roll_skipped_extreme_five_point_fit")
    elif abs(applied_roll) > 25.0:
        warnings.append("large_roll_corrected")
    if reflected_fraction > 0.001:
        warnings.append("reflected_padding_used")
    if reflected_fraction > 0.15:
        warnings.append("high_reflected_padding_fraction")
    if np.any(transformed_landmarks < 0) or np.any(transformed_landmarks >= output_size):
        warnings.append("landmark_outside_crop")

    metadata = {
        "version": "0.3",
        "engine": "hair_app_per_image_canonical_crop_v3",
        "source_size": [source_width, source_height],
        "output_size": [output_size, output_size],
        "bbox_margin": bbox_margin,
        "vertical_center_offset": vertical_center_offset,
        "crop_side_source_pixels": crop_side,
        "face_occupancy_target": 1.0 / bbox_margin,
        "roll_method": five_point_fit["method"],
        "roll_degrees_proposed": proposed_roll,
        "roll_degrees_applied": applied_roll,
        "five_point_fit": five_point_fit,
        "source_to_crop": source_to_crop.tolist(),
        "crop_to_source": crop_to_source.tolist(),
        "observation": asdict(observation),
        "landmark_names": list(LANDMARK_NAMES),
        "transformed_landmarks5": transformed_landmarks.tolist(),
        "transformed_bbox_corners": bbox_corners.tolist(),
        "padding_mode": "reflect_with_observed_source_mask",
        "reflected_padding_pixels": reflected_padding,
        "observed_source_fraction": observed_fraction,
        "reflected_padding_fraction": reflected_fraction,
        "warnings": warnings,
    }
    return CanonicalCropResultV2(
        image=crop,
        observed_source_mask=observed_source_mask,
        source_to_crop=source_to_crop,
        crop_to_source=crop_to_source,
        metadata=metadata,
    )


def prepare_directory_v3(
    *,
    input_dir: Path,
    output_root: Path,
    detector: FacerRetinaFaceDetectorV2,
    output_size: int,
    bbox_margin: float,
    vertical_center_offset: float,
    clean_output: bool,
) -> dict:
    files = list(iter_input_images(input_dir))
    if not files:
        raise ValueError(f"no supported images found in {input_dir}")
    if clean_output:
        _safe_clean_output(output_root)

    rgb_dir = output_root / "rgb"
    crop_dir = output_root / "cropped"
    metadata_dir = output_root / "crop_meta"
    validity_dir = output_root / "crop_validity"
    for directory in (rgb_dir, crop_dir, metadata_dir, validity_dir):
        directory.mkdir(parents=True, exist_ok=True)

    items = []
    for index, source_path in enumerate(files):
        image = load_oriented_rgb(source_path)
        selection = detector.detect(image)
        result = canonical_crop_v3(
            image,
            selection.observation,
            output_size=output_size,
            bbox_margin=bbox_margin,
            vertical_center_offset=vertical_center_offset,
        )
        derived_name = f"{index:05d}.jpg"
        validity_name = f"{index:05d}.png"
        result.image.save(rgb_dir / derived_name, format="JPEG", quality=95)
        result.image.save(crop_dir / derived_name, format="JPEG", quality=95)
        result.observed_source_mask.save(validity_dir / validity_name, format="PNG")

        warnings = result.metadata["warnings"]
        if len(selection.candidate_rankings) > 1:
            warnings.append("multiple_faces_detected")
        item_metadata = {
            "source_name": source_path.name,
            "derived_name": derived_name,
            "validity_mask_name": validity_name,
            "face_selection": {
                "selected_detector_index": selection.selected_index,
                "candidate_count": len(selection.candidate_rankings),
                "candidate_rankings": selection.candidate_rankings,
            },
            **result.metadata,
        }
        (metadata_dir / f"{index:05d}.json").write_text(
            json.dumps(item_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        items.append(item_metadata)
        print(
            f"CROP V3 PASS {source_path.name} -> {derived_name} "
            f"score={selection.observation.score:.3f} "
            f"roll={result.metadata['roll_degrees_applied']:.2f} "
            f"fit={result.metadata['five_point_fit']['normalized_fit_residual']:.3f} "
            f"warnings={warnings}"
        )

    manifest = {
        "version": "0.3",
        "engine": "hair_app_per_image_canonical_crop_v3",
        "detector": "facer_retinaface_mobilenet",
        "roll_method": "nose_anchored_five_point_similarity",
        "input_dir": str(input_dir),
        "output_root": str(output_root),
        "output_size": output_size,
        "bbox_margin": bbox_margin,
        "vertical_center_offset": vertical_center_offset,
        "count": len(items),
        "items": items,
    }
    (metadata_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--output-size", type=int, default=512)
    parser.add_argument("--bbox-margin", type=float, default=1.50)
    parser.add_argument("--vertical-center-offset", type=float, default=-0.04)
    parser.add_argument("--detection-threshold", type=float, default=0.5)
    parser.add_argument("--device", default=None)
    parser.add_argument("--clean-output", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    detector = FacerRetinaFaceDetectorV2(
        device=args.device,
        threshold=args.detection_threshold,
    )
    manifest = prepare_directory_v3(
        input_dir=args.input_dir,
        output_root=args.output_root,
        detector=detector,
        output_size=args.output_size,
        bbox_margin=args.bbox_margin,
        vertical_center_offset=args.vertical_center_offset,
        clean_output=args.clean_output,
    )
    print(f"CANONICAL CROP V3 COMPLETE: {manifest['count']} images")


if __name__ == "__main__":
    main()
