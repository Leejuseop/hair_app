"""Per-image canonical face crops for the Pixel3DMM bake-off.

The upstream Pixel3DMM preprocessing averages face boxes in absolute pixel
coordinates.  That is useful for a consistently framed video, but invalid for
independent photos with different resolutions and face positions.  This module
keeps every photo independent and applies one affine resampling that:

1. centers the detected face;
2. normalizes its scale with a fixed bbox margin;
3. removes image-plane head roll; and
4. writes a 512x512 crop plus reversible transform metadata.

The crop geometry is detector-agnostic.  The CLI adapter uses the RetinaFace
detector already installed with Pixel3DMM/FaRL, but product code can provide
MediaPipe observations to ``canonical_crop`` instead.
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
DERIVED_DIRECTORIES = (
    "arcface",
    "crop_meta",
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
class FaceObservation:
    """One face observation in oriented source-image pixel coordinates."""

    bbox_xyxy: tuple[float, float, float, float]
    left_eye_xy: tuple[float, float]
    right_eye_xy: tuple[float, float]
    score: float

    def validate(self) -> None:
        x1, y1, x2, y2 = self.bbox_xyxy
        if not all(math.isfinite(value) for value in (*self.bbox_xyxy, *self.left_eye_xy, *self.right_eye_xy)):
            raise ValueError("face observation contains a non-finite coordinate")
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"invalid face bbox: {self.bbox_xyxy}")
        if self.right_eye_xy[0] <= self.left_eye_xy[0]:
            raise ValueError("eyes must be ordered from image-left to image-right")
        if not math.isfinite(self.score):
            raise ValueError("detection score must be finite")


@dataclass
class CanonicalCropResult:
    image: Image.Image
    source_to_crop: np.ndarray
    crop_to_source: np.ndarray
    metadata: dict


def load_oriented_rgb(path: Path) -> Image.Image:
    """Load pixels in the orientation a user sees, without modifying the raw file."""

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


def canonical_crop(
    image: Image.Image,
    observation: FaceObservation,
    *,
    output_size: int = 512,
    bbox_margin: float = 1.42,
    fill_color: tuple[int, int, int] = (0, 0, 0),
) -> CanonicalCropResult:
    """Create one centered, scale-normalized and roll-corrected face crop.

    ``source_to_crop`` maps oriented source pixels into the output crop.  The
    inverse matrix is stored because later UV baking must be able to trace a
    crop pixel back to its observed source pixel.
    """

    observation.validate()
    if output_size <= 0:
        raise ValueError("output_size must be positive")
    if bbox_margin <= 1.0:
        raise ValueError("bbox_margin must be greater than 1")

    image = image.convert("RGB")
    source_width, source_height = image.size
    x1, y1, x2, y2 = observation.bbox_xyxy
    bbox_width = x2 - x1
    bbox_height = y2 - y1
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    crop_side = max(bbox_width, bbox_height) * bbox_margin
    scale = output_size / crop_side

    eye_dx = observation.right_eye_xy[0] - observation.left_eye_xy[0]
    eye_dy = observation.right_eye_xy[1] - observation.left_eye_xy[1]
    roll_degrees = math.degrees(math.atan2(eye_dy, eye_dx))
    roll_radians = math.radians(roll_degrees)
    cosine = math.cos(roll_radians)
    sine = math.sin(roll_radians)
    output_center = output_size / 2.0

    # Image coordinates have a downward-positive y axis.  This rotation makes
    # the eye vector horizontal while preserving yaw and pitch evidence.
    source_to_crop = np.array(
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

    # Pillow expects the inverse mapping from output pixels to source pixels.
    affine = tuple(float(value) for value in crop_to_source[:2, :].reshape(-1))
    crop = image.transform(
        (output_size, output_size),
        Image.Transform.AFFINE,
        affine,
        resample=Image.Resampling.BICUBIC,
        fillcolor=fill_color,
    )

    transformed_eyes = transform_points(
        source_to_crop,
        [observation.left_eye_xy, observation.right_eye_xy],
    )
    bbox_corners = transform_points(
        source_to_crop,
        [(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
    )

    warnings: list[str] = []
    if observation.score < 0.55:
        warnings.append("low_detection_confidence")
    if min(bbox_width, bbox_height) < 64:
        warnings.append("low_source_face_resolution")
    if abs(roll_degrees) > 25:
        warnings.append("extreme_roll_recapture_preferred")
    if np.any(transformed_eyes < 0) or np.any(transformed_eyes >= output_size):
        warnings.append("eye_landmark_outside_crop")

    metadata = {
        "version": "0.1",
        "source_size": [source_width, source_height],
        "output_size": [output_size, output_size],
        "bbox_margin": bbox_margin,
        "crop_side_source_pixels": crop_side,
        "face_occupancy_target": 1.0 / bbox_margin,
        "roll_degrees_removed": roll_degrees,
        "source_to_crop": source_to_crop.tolist(),
        "crop_to_source": crop_to_source.tolist(),
        "observation": asdict(observation),
        "transformed_eye_points": transformed_eyes.tolist(),
        "transformed_bbox_corners": bbox_corners.tolist(),
        "warnings": warnings,
    }

    return CanonicalCropResult(
        image=crop,
        source_to_crop=source_to_crop,
        crop_to_source=crop_to_source,
        metadata=metadata,
    )


class FacerRetinaFaceDetector:
    """Thin adapter around the detector already installed by Pixel3DMM."""

    def __init__(self, *, device: str | None = None, threshold: float = 0.5):
        import facer
        import torch

        self._facer = facer
        self._torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.detector = facer.face_detector("retinaface/mobilenet", device=self.device)
        self.detector.threshold = threshold

    def detect(self, image: Image.Image) -> FaceObservation:
        pixels = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
        tensor = self._facer.hwc2bchw(self._torch.from_numpy(pixels)).to(self.device)

        with self._torch.inference_mode():
            faces = self.detector(tensor)

        if faces["scores"].numel() == 0:
            raise RuntimeError("RetinaFace returned no face")

        index = int(self._torch.argmax(faces["scores"]).item())
        bbox = faces["rects"][index].detach().cpu().tolist()
        points = faces["points"][index].detach().cpu().tolist()
        score = float(faces["scores"][index].detach().cpu().item())

        # RetinaFace provides two eye points first.  Sorting by image x avoids
        # a 180-degree roll if a backend labels left/right from the subject's
        # rather than the viewer's perspective.
        eye_a = tuple(float(value) for value in points[0])
        eye_b = tuple(float(value) for value in points[1])
        left_eye, right_eye = sorted((eye_a, eye_b), key=lambda point: point[0])

        return FaceObservation(
            bbox_xyxy=tuple(float(value) for value in bbox),
            left_eye_xy=left_eye,
            right_eye_xy=right_eye,
            score=score,
        )


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


def prepare_directory(
    *,
    input_dir: Path,
    output_root: Path,
    detector: FacerRetinaFaceDetector,
    output_size: int,
    bbox_margin: float,
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
    for directory in (rgb_dir, crop_dir, metadata_dir):
        directory.mkdir(parents=True, exist_ok=True)

    items = []
    for index, source_path in enumerate(files):
        image = load_oriented_rgb(source_path)
        try:
            observation = detector.detect(image)
        except Exception as error:
            raise RuntimeError(f"face detection failed for {source_path.name}: {error}") from error

        result = canonical_crop(
            image,
            observation,
            output_size=output_size,
            bbox_margin=bbox_margin,
        )
        derived_name = f"{index:05d}.jpg"
        # Pixel3DMM's legacy PIPNet runner reads ``rgb`` and writes ``cropped``.
        # Both receive the already canonical image so that running landmark
        # extraction with cropping disabled cannot reintroduce a shared bbox.
        # The untouched source remains in ``input_dir`` and is referenced by
        # the reversible transform metadata below.
        result.image.save(rgb_dir / derived_name, format="JPEG", quality=95)
        result.image.save(crop_dir / derived_name, format="JPEG", quality=95)

        item_metadata = {
            "source_name": source_path.name,
            "derived_name": derived_name,
            **result.metadata,
        }
        (metadata_dir / f"{index:05d}.json").write_text(
            json.dumps(item_metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        items.append(item_metadata)
        print(
            f"CROP PASS {source_path.name} -> {derived_name} "
            f"score={observation.score:.3f} roll={result.metadata['roll_degrees_removed']:.2f} "
            f"warnings={result.metadata['warnings']}"
        )

    manifest = {
        "version": "0.1",
        "engine": "hair_app_per_image_canonical_crop",
        "detector": "facer_retinaface_mobilenet",
        "input_dir": str(input_dir),
        "output_root": str(output_root),
        "output_size": output_size,
        "bbox_margin": bbox_margin,
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
    parser.add_argument("--bbox-margin", type=float, default=1.42)
    parser.add_argument("--detection-threshold", type=float, default=0.5)
    parser.add_argument("--device", default=None)
    parser.add_argument("--clean-output", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    detector = FacerRetinaFaceDetector(
        device=args.device,
        threshold=args.detection_threshold,
    )
    manifest = prepare_directory(
        input_dir=args.input_dir,
        output_root=args.output_root,
        detector=detector,
        output_size=args.output_size,
        bbox_margin=args.bbox_margin,
        clean_output=args.clean_output,
    )
    print(f"CANONICAL CROP COMPLETE: {manifest['count']} images")


if __name__ == "__main__":
    main()
