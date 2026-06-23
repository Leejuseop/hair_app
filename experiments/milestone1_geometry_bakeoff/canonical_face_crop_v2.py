"""Robust per-image canonical face crops for independent Hair App photos.

Version 2 keeps the successful parts of ``canonical_face_crop.py`` while
hardening the cases found in the first eight-photo visual test:

* every photo is still detected and cropped independently;
* all five RetinaFace points are retained instead of keeping only two eyes;
* profile-like or anatomically implausible eye pairs do not drive roll;
* the primary face is selected using size, detector confidence, and centrality;
* rotation outside the source image uses reflected pixels instead of black;
* an observed-source validity mask prevents reflected pixels from later being
  mistaken for real evidence; and
* uncertain inputs are preserved with warnings rather than rejected.

The pretrained face detector is supplied by the open-source ``facer`` package.
The candidate selection, plausibility checks, affine crop, padding accounting,
metadata contract, and Pixel3DMM directory adapter are Hair App code.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from PIL import Image, ImageOps


SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
LANDMARK_NAMES = ("left_eye", "right_eye", "nose", "left_mouth", "right_mouth")
DERIVED_DIRECTORIES = (
    "arcface",
    "crop_meta",
    "crop_validity",
    "cropped",
    "mica",
    "p3dmm",
    "pipnet",
    "PIPnet_annotated_images",
    "PIPnet_landmarks",
    "rgb",
    "seg_non_crop_annotations",
    "seg_og",
)
DERIVED_FILES = ("crop_ymin_ymax_xmin_xmax.npy",)


@dataclass(frozen=True)
class FaceObservationV2:
    """One detector candidate in oriented source-image pixel coordinates."""

    bbox_xyxy: tuple[float, float, float, float]
    landmarks5_xy: tuple[tuple[float, float], ...]
    score: float

    def validate(self) -> None:
        x1, y1, x2, y2 = self.bbox_xyxy
        flattened = [value for point in self.landmarks5_xy for value in point]
        if len(self.landmarks5_xy) != 5:
            raise ValueError("landmarks5_xy must contain five points")
        if not all(math.isfinite(value) for value in (*self.bbox_xyxy, *flattened)):
            raise ValueError("face observation contains a non-finite coordinate")
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"invalid face bbox: {self.bbox_xyxy}")
        if self.landmarks5_xy[1][0] <= self.landmarks5_xy[0][0]:
            raise ValueError("eyes must be ordered from image-left to image-right")
        if not math.isfinite(self.score):
            raise ValueError("detection score must be finite")

    @property
    def left_eye_xy(self) -> tuple[float, float]:
        return self.landmarks5_xy[0]

    @property
    def right_eye_xy(self) -> tuple[float, float]:
        return self.landmarks5_xy[1]


@dataclass
class FaceSelectionV2:
    observation: FaceObservationV2
    selected_index: int
    candidate_rankings: list[dict]


@dataclass
class CanonicalCropResultV2:
    image: Image.Image
    observed_source_mask: Image.Image
    source_to_crop: np.ndarray
    crop_to_source: np.ndarray
    metadata: dict


def load_oriented_rgb(path: Path) -> Image.Image:
    """Apply EXIF orientation without changing the raw source file."""

    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def transform_points(matrix: np.ndarray, points: Sequence[Sequence[float]]) -> np.ndarray:
    points_array = np.asarray(points, dtype=np.float64)
    if points_array.ndim != 2 or points_array.shape[1] != 2:
        raise ValueError("points must have shape [N, 2]")
    homogeneous = np.concatenate(
        [points_array, np.ones((points_array.shape[0], 1), dtype=np.float64)],
        axis=1,
    )
    return (matrix @ homogeneous.T).T[:, :2]


def select_primary_face(
    observations: Sequence[FaceObservationV2],
    image_size: tuple[int, int],
) -> FaceSelectionV2:
    """Select the likely selfie subject while retaining every candidate score."""

    if not observations:
        raise ValueError("at least one face observation is required")
    width, height = image_size
    if width <= 0 or height <= 0:
        raise ValueError("image_size must be positive")

    areas = []
    for observation in observations:
        observation.validate()
        x1, y1, x2, y2 = observation.bbox_xyxy
        areas.append((x2 - x1) * (y2 - y1))
    max_area = max(areas)
    image_center = np.asarray([width / 2.0, height / 2.0])
    half_diagonal = math.hypot(width, height) / 2.0

    rankings = []
    for index, (observation, area) in enumerate(zip(observations, areas)):
        x1, y1, x2, y2 = observation.bbox_xyxy
        face_center = np.asarray([(x1 + x2) / 2.0, (y1 + y2) / 2.0])
        distance = float(np.linalg.norm(face_center - image_center))
        area_score = area / max_area
        confidence_score = float(np.clip(observation.score, 0.0, 1.0))
        center_score = max(0.0, 1.0 - distance / half_diagonal)
        # A selfie subject is normally the largest face. Confidence and
        # centrality break close calls without allowing a tiny background face
        # to win only because its detector score is marginally higher.
        selection_score = 0.65 * area_score + 0.20 * confidence_score + 0.15 * center_score
        rankings.append(
            {
                "detector_index": index,
                "selection_score": selection_score,
                "area_score": area_score,
                "confidence_score": confidence_score,
                "center_score": center_score,
                "bbox_xyxy": list(observation.bbox_xyxy),
            }
        )

    selected_index = max(range(len(rankings)), key=lambda index: rankings[index]["selection_score"])
    return FaceSelectionV2(
        observation=observations[selected_index],
        selected_index=selected_index,
        candidate_rankings=rankings,
    )


def analyze_landmark_geometry(observation: FaceObservationV2) -> dict:
    """Estimate whether the detector's two eye points are safe for roll."""

    observation.validate()
    x1, y1, x2, y2 = observation.bbox_xyxy
    bbox_width = x2 - x1
    bbox_height = y2 - y1
    left_eye, right_eye, nose, left_mouth, right_mouth = (
        np.asarray(point, dtype=np.float64) for point in observation.landmarks5_xy
    )
    eye_vector = right_eye - left_eye
    eye_span = float(np.linalg.norm(eye_vector))
    raw_roll = math.degrees(math.atan2(float(eye_vector[1]), float(eye_vector[0])))
    eye_unit = eye_vector / max(eye_span, 1e-9)
    image_down_unit = np.asarray([-eye_unit[1], eye_unit[0]])
    eye_midpoint = (left_eye + right_eye) / 2.0
    mouth_midpoint = (left_mouth + right_mouth) / 2.0

    left_eye_nose = float(np.linalg.norm(nose - left_eye))
    right_eye_nose = float(np.linalg.norm(nose - right_eye))
    eye_nose_balance = min(left_eye_nose, right_eye_nose) / max(
        max(left_eye_nose, right_eye_nose), 1e-9
    )
    nose_down_ratio = float(np.dot(nose - eye_midpoint, image_down_unit) / bbox_height)
    mouth_down_ratio = float(np.dot(mouth_midpoint - eye_midpoint, image_down_unit) / bbox_height)
    eye_span_ratio = eye_span / bbox_width

    slack_x = bbox_width * 0.10
    slack_y = bbox_height * 0.10
    points_inside_expanded_bbox = all(
        x1 - slack_x <= point[0] <= x2 + slack_x and y1 - slack_y <= point[1] <= y2 + slack_y
        for point in (left_eye, right_eye, nose, left_mouth, right_mouth)
    )

    failure_reasons = []
    if eye_span_ratio < 0.18:
        failure_reasons.append("eye_span_too_small")
    if eye_nose_balance < 0.35:
        failure_reasons.append("eye_nose_geometry_asymmetric")
    if not 0.04 <= nose_down_ratio <= 0.48:
        failure_reasons.append("nose_not_below_eye_line")
    if mouth_down_ratio <= nose_down_ratio + 0.02:
        failure_reasons.append("mouth_not_below_nose")
    if not points_inside_expanded_bbox:
        failure_reasons.append("landmark_outside_face_bbox")
    if abs(raw_roll) > 45.0:
        failure_reasons.append("roll_estimate_extreme")

    profile_candidate = eye_span_ratio < 0.20 or eye_nose_balance < 0.42
    return {
        "raw_eye_roll_degrees": raw_roll,
        "eye_span_ratio": eye_span_ratio,
        "eye_nose_balance": eye_nose_balance,
        "nose_down_ratio": nose_down_ratio,
        "mouth_down_ratio": mouth_down_ratio,
        "points_inside_expanded_bbox": points_inside_expanded_bbox,
        "profile_candidate": profile_candidate,
        "roll_reliable": not failure_reasons,
        "roll_failure_reasons": failure_reasons,
    }


def _make_reflected_source(
    image: Image.Image,
    crop_to_source: np.ndarray,
    output_size: int,
) -> tuple[Image.Image, np.ndarray, dict]:
    """Reflect only the source edges needed by the output crop."""

    width, height = image.size
    output_corners = ((0, 0), (output_size - 1, 0), (output_size - 1, output_size - 1), (0, output_size - 1))
    source_corners = transform_points(crop_to_source, output_corners)
    interpolation_guard = 3
    left = max(0, int(math.ceil(-float(source_corners[:, 0].min()))) + interpolation_guard)
    top = max(0, int(math.ceil(-float(source_corners[:, 1].min()))) + interpolation_guard)
    right = max(
        0,
        int(math.ceil(float(source_corners[:, 0].max()) - (width - 1))) + interpolation_guard,
    )
    bottom = max(
        0,
        int(math.ceil(float(source_corners[:, 1].max()) - (height - 1))) + interpolation_guard,
    )
    if not any((left, top, right, bottom)):
        return image, crop_to_source, {"left": 0, "top": 0, "right": 0, "bottom": 0}

    pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
    mode = "reflect" if width > 1 and height > 1 else "edge"
    padded = np.pad(pixels, ((top, bottom), (left, right), (0, 0)), mode=mode)
    source_to_padded = np.asarray(
        [[1.0, 0.0, float(left)], [0.0, 1.0, float(top)], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    return (
        Image.fromarray(padded, mode="RGB"),
        source_to_padded @ crop_to_source,
        {"left": left, "top": top, "right": right, "bottom": bottom},
    )


def canonical_crop_v2(
    image: Image.Image,
    observation: FaceObservationV2,
    *,
    output_size: int = 512,
    bbox_margin: float = 1.50,
    vertical_center_offset: float = -0.04,
) -> CanonicalCropResultV2:
    """Create a robust 512x512 crop without discarding uncertain photos."""

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

    landmark_geometry = analyze_landmark_geometry(observation)
    raw_roll_degrees = landmark_geometry["raw_eye_roll_degrees"]
    applied_roll_degrees = raw_roll_degrees if landmark_geometry["roll_reliable"] else 0.0
    roll_radians = math.radians(applied_roll_degrees)
    cosine = math.cos(roll_radians)
    sine = math.sin(roll_radians)
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

    # This mask is transformed from the unpadded source. White pixels are real
    # observations; black pixels are reflected context and must not contribute
    # to UV baking or geometry losses as measured evidence.
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

    warnings = []
    if observation.score < 0.55:
        warnings.append("low_detection_confidence")
    if min(bbox_width, bbox_height) < 64:
        warnings.append("low_source_face_resolution")
    if not landmark_geometry["roll_reliable"]:
        warnings.append("roll_skipped_unreliable_landmarks")
    elif abs(applied_roll_degrees) > 25.0:
        warnings.append("large_roll_corrected")
    if landmark_geometry["profile_candidate"]:
        warnings.append("profile_candidate")
    if reflected_fraction > 0.001:
        warnings.append("reflected_padding_used")
    if reflected_fraction > 0.15:
        warnings.append("high_reflected_padding_fraction")
    if np.any(transformed_landmarks < 0) or np.any(transformed_landmarks >= output_size):
        warnings.append("landmark_outside_crop")

    metadata = {
        "version": "0.2",
        "engine": "hair_app_per_image_canonical_crop_v2",
        "source_size": [source_width, source_height],
        "output_size": [output_size, output_size],
        "bbox_margin": bbox_margin,
        "vertical_center_offset": vertical_center_offset,
        "crop_side_source_pixels": crop_side,
        "face_occupancy_target": 1.0 / bbox_margin,
        "raw_eye_roll_degrees": raw_roll_degrees,
        "roll_degrees_applied": applied_roll_degrees,
        "source_to_crop": source_to_crop.tolist(),
        "crop_to_source": crop_to_source.tolist(),
        "observation": asdict(observation),
        "landmark_names": list(LANDMARK_NAMES),
        "transformed_landmarks5": transformed_landmarks.tolist(),
        "transformed_bbox_corners": bbox_corners.tolist(),
        "landmark_geometry": landmark_geometry,
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


class FacerRetinaFaceDetectorV2:
    """Retain and rank every face returned by Facer RetinaFace/MobileNet."""

    def __init__(self, *, device: str | None = None, threshold: float = 0.5):
        import facer
        import torch

        self._facer = facer
        self._torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.detector = facer.face_detector("retinaface/mobilenet", device=self.device)
        self.detector.threshold = threshold

    def detect(self, image: Image.Image) -> FaceSelectionV2:
        pixels = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
        tensor = self._facer.hwc2bchw(self._torch.from_numpy(pixels)).to(self.device)
        with self._torch.inference_mode():
            faces = self.detector(tensor)
        if faces["scores"].numel() == 0:
            raise RuntimeError("RetinaFace returned no face")

        observations = []
        count = int(faces["scores"].numel())
        for index in range(count):
            bbox = faces["rects"][index].detach().cpu().tolist()
            points = faces["points"][index].detach().cpu().tolist()
            score = float(faces["scores"][index].detach().cpu().item())
            eye_points = sorted(
                (tuple(float(value) for value in points[0]), tuple(float(value) for value in points[1])),
                key=lambda point: point[0],
            )
            mouth_points = sorted(
                (tuple(float(value) for value in points[3]), tuple(float(value) for value in points[4])),
                key=lambda point: point[0],
            )
            landmarks = (
                eye_points[0],
                eye_points[1],
                tuple(float(value) for value in points[2]),
                mouth_points[0],
                mouth_points[1],
            )
            observations.append(
                FaceObservationV2(
                    bbox_xyxy=tuple(float(value) for value in bbox),
                    landmarks5_xy=landmarks,
                    score=score,
                )
            )
        return select_primary_face(observations, image.size)


def iter_input_images(input_dir: Path) -> Iterable[Path]:
    return sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    )


def _safe_clean_output(output_root: Path) -> None:
    resolved = output_root.resolve()
    if resolved == Path(resolved.anchor) or len(resolved.parts) < 3:
        raise ValueError(f"refusing to clean unsafe output root: {resolved}")
    for directory_name in DERIVED_DIRECTORIES:
        shutil.rmtree(resolved / directory_name, ignore_errors=True)
    for file_name in DERIVED_FILES:
        (resolved / file_name).unlink(missing_ok=True)


def prepare_directory_v2(
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
        try:
            selection = detector.detect(image)
        except Exception as error:
            raise RuntimeError(f"face detection failed for {source_path.name}: {error}") from error
        result = canonical_crop_v2(
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
            f"CROP V2 PASS {source_path.name} -> {derived_name} "
            f"score={selection.observation.score:.3f} "
            f"roll={result.metadata['roll_degrees_applied']:.2f} "
            f"warnings={warnings}"
        )

    manifest = {
        "version": "0.2",
        "engine": "hair_app_per_image_canonical_crop_v2",
        "detector": "facer_retinaface_mobilenet",
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
    manifest = prepare_directory_v2(
        input_dir=args.input_dir,
        output_root=args.output_root,
        detector=detector,
        output_size=args.output_size,
        bbox_margin=args.bbox_margin,
        vertical_center_offset=args.vertical_center_offset,
        clean_output=args.clean_output,
    )
    print(f"CANONICAL CROP V2 COMPLETE: {manifest['count']} images")


if __name__ == "__main__":
    main()
