"""Score private selfie/scan frames for texture baking.

The report is a private runtime artifact. It records quality metrics and paths
only under the private Drive root; it never copies source images into Git.
"""

from __future__ import annotations

import argparse
import csv
import json
import pickle
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import numpy as np
from PIL import Image

from texture_baker_loader import FrameEvidence, default_private_root, load_person


DEFAULT_PEOPLE = ("\uc8fc\uc12d", "\uc740\ucc44")
FACE_LABELS = {2, 4, 5, 6, 7, 8, 9, 10, 12, 13}
SKIN_REFERENCE_LABELS = {2, 10}
OCCLUDER_LABELS = {1, 3, 14, 16, 17, 18}
CENTRAL_FACE_LABELS = {2, 6, 7, 8, 9, 10, 12, 13}

RIGHT_EYE_WFLW = np.arange(60, 68)
LEFT_EYE_WFLW = np.arange(68, 76)
OUTER_MOUTH_WFLW = np.arange(76, 88)
INNER_MOUTH_WFLW = np.arange(88, 96)


@dataclass(frozen=True)
class TrackingDirs:
    root: str | None
    checkpoint_dir: str | None
    mesh_dir: str | None


@dataclass(frozen=True)
class FrameQuality:
    frame_id: str
    crop: str
    tracking_mesh: str | None
    checkpoint: str | None
    overall_score: float
    selected_for_bake: bool
    blur_score: float
    sharpness_laplacian_var: float
    face_size_score: float
    face_area_fraction: float
    face_bbox_fraction: float
    pose_score: float
    yaw_degrees: float | None
    pitch_degrees: float | None
    roll_degrees: float | None
    exposure_score: float
    face_luma_median: float | None
    face_luma_p05: float | None
    face_luma_p95: float | None
    occlusion_score: float
    occlusion_fraction: float
    segmentation_score: float
    landmark_score: float
    eyes_open_score: float | None
    eye_open_ratio: float | None
    mouth_closed_score: float | None
    mouth_open_ratio: float | None
    skin_median_rgb: list[float] | None
    seg_label_counts: dict[str, int]
    warnings: list[str]


def clamp01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def load_segmentation(frame: FrameEvidence) -> np.ndarray | None:
    if not frame.segmentation_files:
        return None
    seg_og = [path for path in frame.segmentation_files if "/seg_og/" in path.replace("\\", "/")]
    selected = Path(seg_og[0] if seg_og else frame.segmentation_files[0])
    return np.asarray(Image.open(selected).convert("L"), dtype=np.uint8)


def load_landmarks(frame: FrameEvidence) -> np.ndarray | None:
    npy_paths = [Path(path) for path in frame.landmark_files if Path(path).suffix.lower() == ".npy"]
    if not npy_paths:
        return None
    landmarks = np.load(npy_paths[0])
    landmarks = np.asarray(landmarks, dtype=np.float32)
    if landmarks.ndim == 3:
        landmarks = landmarks.reshape(-1, landmarks.shape[-1])
    if landmarks.shape[-1] > 2:
        landmarks = landmarks[:, :2]
    return landmarks if landmarks.shape[0] >= 2 else None


def find_tracking_dirs(person_output_dir: Path) -> TrackingDirs:
    tracking_root = person_output_dir / "tracking" / "no_mica"
    candidates: list[Path] = []
    if tracking_root.exists():
        candidates.append(tracking_root)
        candidates.extend(path for path in tracking_root.iterdir() if path.is_dir())

    for root in candidates:
        checkpoint_dir = root / "checkpoint"
        mesh_dir = root / "mesh"
        if checkpoint_dir.exists() and mesh_dir.exists():
            return TrackingDirs(str(root), str(checkpoint_dir), str(mesh_dir))
    return TrackingDirs(None, None, None)


def checkpoint_path_for_frame(tracking_dirs: TrackingDirs, frame_id: str) -> Path | None:
    if tracking_dirs.checkpoint_dir is None:
        return None
    path = Path(tracking_dirs.checkpoint_dir) / f"{frame_id}.frame"
    return path if path.exists() else None


def tracking_mesh_path_for_frame(tracking_dirs: TrackingDirs, frame_id: str) -> Path | None:
    if tracking_dirs.mesh_dir is None:
        return None
    path = Path(tracking_dirs.mesh_dir) / f"{frame_id}.ply"
    return path if path.exists() else None


def load_frame_checkpoint(path: Path | None, frame_id: str) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    with ZipFile(path) as archive:
        data_names = [name for name in archive.namelist() if name.endswith("/data.pkl")]
        if not data_names:
            return None
        preferred = f"{frame_id}/data.pkl"
        data_name = preferred if preferred in data_names else data_names[0]
        return pickle.loads(archive.read(data_name))


def rotation_to_euler_degrees(rotation: np.ndarray) -> tuple[float, float, float]:
    r = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
    yaw = np.degrees(np.arctan2(r[0, 2], r[2, 2]))
    pitch = np.degrees(np.arctan2(-r[1, 2], np.sqrt((r[1, 0] ** 2) + (r[1, 1] ** 2))))
    roll = np.degrees(np.arctan2(r[1, 0], r[0, 0]))
    return float(yaw), float(pitch), float(roll)


def bbox_from_mask(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask)
    if xs.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def dilate_binary_mask(mask: np.ndarray, iterations: int) -> np.ndarray:
    if iterations <= 0:
        return mask.astype(bool, copy=True)
    result = mask.astype(bool, copy=True)
    height, width = result.shape
    for _ in range(iterations):
        padded = np.pad(result, ((1, 1), (1, 1)), mode="constant", constant_values=False)
        neighbors = [
            padded[dy : dy + height, dx : dx + width]
            for dy in range(3)
            for dx in range(3)
        ]
        result = np.logical_or.reduce(neighbors)
    return result


def bbox_area_fraction(bbox: tuple[int, int, int, int] | None, shape: tuple[int, int]) -> float:
    if bbox is None:
        return 0.0
    x0, y0, x1, y1 = bbox
    return float(max(x1 - x0, 0) * max(y1 - y0, 0) / max(shape[0] * shape[1], 1))


def laplacian_variance(rgb: np.ndarray, mask: np.ndarray | None) -> float:
    luma = (0.299 * rgb[..., 0]) + (0.587 * rgb[..., 1]) + (0.114 * rgb[..., 2])
    padded = np.pad(luma, ((1, 1), (1, 1)), mode="edge")
    lap = (
        -4.0 * padded[1:-1, 1:-1]
        + padded[:-2, 1:-1]
        + padded[2:, 1:-1]
        + padded[1:-1, :-2]
        + padded[1:-1, 2:]
    )
    if mask is not None and np.any(mask):
        values = lap[mask]
    else:
        values = lap.reshape(-1)
    return float(np.var(values))


def eye_open_ratio(landmarks: np.ndarray | None) -> float | None:
    if landmarks is None or landmarks.shape[0] <= int(LEFT_EYE_WFLW.max()):
        return None

    def ratio(indices: np.ndarray) -> float:
        pts = landmarks[indices]
        width = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2).max()
        height = float(pts[:, 1].max() - pts[:, 1].min())
        return height / max(float(width), 1e-6)

    return float((ratio(RIGHT_EYE_WFLW) + ratio(LEFT_EYE_WFLW)) * 0.5)


def mouth_open_ratio(landmarks: np.ndarray | None) -> float | None:
    if landmarks is None or landmarks.shape[0] <= int(OUTER_MOUTH_WFLW.max()):
        return None
    outer = landmarks[OUTER_MOUTH_WFLW]
    width = np.linalg.norm(outer[:, None, :] - outer[None, :, :], axis=2).max()
    if landmarks.shape[0] > int(INNER_MOUTH_WFLW.max()):
        inner = landmarks[INNER_MOUTH_WFLW]
        height = float(inner[:, 1].max() - inner[:, 1].min())
    else:
        height = float(outer[:, 1].max() - outer[:, 1].min()) * 0.35
    return float(height / max(float(width), 1e-6))


def landmark_consistency_score(
    landmarks: np.ndarray | None,
    face_bbox: tuple[int, int, int, int] | None,
    image_shape: tuple[int, int],
) -> float:
    if landmarks is None:
        return 0.0
    height, width = image_shape
    in_bounds = (
        (landmarks[:, 0] >= 0)
        & (landmarks[:, 0] < width)
        & (landmarks[:, 1] >= 0)
        & (landmarks[:, 1] < height)
    )
    bounds_score = float(np.mean(in_bounds))
    if face_bbox is None:
        return bounds_score * 0.7
    x0, y0, x1, y1 = face_bbox
    inside = (
        (landmarks[:, 0] >= x0)
        & (landmarks[:, 0] <= x1)
        & (landmarks[:, 1] >= y0)
        & (landmarks[:, 1] <= y1)
    )
    return clamp01((0.55 * bounds_score) + (0.45 * float(np.mean(inside))))


def frame_quality(
    frame: FrameEvidence,
    tracking_dirs: TrackingDirs,
) -> FrameQuality:
    warnings: list[str] = []
    crop_path = Path(frame.crop)
    rgb = load_rgb(crop_path)
    segmentation = load_segmentation(frame)
    landmarks = load_landmarks(frame)
    checkpoint_path = checkpoint_path_for_frame(tracking_dirs, frame.frame_id)
    tracking_mesh_path = tracking_mesh_path_for_frame(tracking_dirs, frame.frame_id)
    checkpoint = load_frame_checkpoint(checkpoint_path, frame.frame_id)

    if segmentation is None:
        warnings.append("missing_segmentation")
        face_mask = np.ones(rgb.shape[:2], dtype=bool)
        central_mask = face_mask
        occluder_mask = np.zeros(rgb.shape[:2], dtype=bool)
        label_counts: dict[str, int] = {}
    else:
        face_mask = np.isin(segmentation, list(FACE_LABELS))
        central_mask = np.isin(segmentation, list(CENTRAL_FACE_LABELS))
        occluder_mask = np.isin(segmentation, list(OCCLUDER_LABELS))
        labels, counts = np.unique(segmentation, return_counts=True)
        label_counts = {str(int(label)): int(count) for label, count in zip(labels, counts)}

    face_bbox = bbox_from_mask(face_mask)
    central_bbox = bbox_from_mask(central_mask)
    face_area_fraction = float(face_mask.mean())
    face_bbox_fraction = bbox_area_fraction(face_bbox, rgb.shape[:2])
    face_size_score = clamp01(1.0 - abs(face_bbox_fraction - 0.34) / 0.30)
    if face_area_fraction < 0.08:
        face_size_score *= 0.45

    sharpness = laplacian_variance(rgb, central_mask if np.any(central_mask) else face_mask)
    blur_score = clamp01((np.log10(sharpness + 1.0) - 1.15) / 1.35)

    if np.any(central_mask):
        face_pixels = rgb[central_mask]
    elif np.any(face_mask):
        face_pixels = rgb[face_mask]
    else:
        face_pixels = rgb.reshape(-1, 3)
    luma = (0.299 * face_pixels[:, 0]) + (0.587 * face_pixels[:, 1]) + (0.114 * face_pixels[:, 2])
    luma_median = float(np.median(luma))
    luma_p05 = float(np.percentile(luma, 5))
    luma_p95 = float(np.percentile(luma, 95))
    exposure_center = 138.0
    exposure_score = clamp01(1.0 - abs(luma_median - exposure_center) / 105.0)
    exposure_score *= clamp01((luma_p95 - luma_p05) / 115.0)

    yaw = pitch = roll = None
    pose_score = 0.55
    if checkpoint is not None:
        rotation = np.asarray(checkpoint["flame"]["R_rotation_matrix"])[0]
        yaw, pitch, roll = rotation_to_euler_degrees(rotation)
        pose_score = clamp01(1.0 - max(abs(yaw) - 55.0, 0.0) / 45.0)
        pose_score *= clamp01(1.0 - max(abs(pitch) - 28.0, 0.0) / 32.0)
        pose_score *= clamp01(1.0 - max(abs(roll) - 24.0, 0.0) / 28.0)
    else:
        warnings.append("missing_tracking_checkpoint")

    if tracking_mesh_path is None:
        warnings.append("missing_tracking_mesh")

    if np.any(central_mask):
        central_region = dilate_binary_mask(central_mask, 10)
    elif np.any(face_mask):
        central_region = dilate_binary_mask(face_mask, 6)
    else:
        central_region = np.ones(rgb.shape[:2], dtype=bool)
    occlusion_band = central_region & ~face_mask
    occlusion_pixels = int((occluder_mask & occlusion_band).sum())
    reference_area = int(central_mask.sum()) if np.any(central_mask) else int(face_mask.sum())
    occlusion_fraction = float(occlusion_pixels / max(reference_area, 1))
    occlusion_score = clamp01(1.0 - occlusion_fraction * 2.5)

    segmentation_score = clamp01((face_area_fraction - 0.06) / 0.18)
    segmentation_score *= clamp01(1.0 - max(face_area_fraction - 0.52, 0.0) / 0.28)
    if segmentation is None:
        segmentation_score = 0.0

    landmark_score = landmark_consistency_score(landmarks, face_bbox, rgb.shape[:2])
    eye_ratio = eye_open_ratio(landmarks)
    eyes_score = None if eye_ratio is None else clamp01((eye_ratio - 0.12) / 0.16)
    mouth_ratio = mouth_open_ratio(landmarks)
    mouth_score = None if mouth_ratio is None else clamp01(1.0 - max(mouth_ratio - 0.14, 0.0) / 0.22)

    skin_median_rgb: list[float] | None = None
    if segmentation is not None:
        skin_mask = np.isin(segmentation, list(SKIN_REFERENCE_LABELS))
        if int(skin_mask.sum()) > 50:
            skin_median_rgb = [float(value) for value in np.median(rgb[skin_mask], axis=0)]

    overall_score = (
        (0.18 * blur_score)
        + (0.14 * face_size_score)
        + (0.14 * exposure_score)
        + (0.12 * pose_score)
        + (0.16 * occlusion_score)
        + (0.12 * segmentation_score)
        + (0.08 * landmark_score)
        + (0.03 * (eyes_score if eyes_score is not None else 0.6))
        + (0.03 * (mouth_score if mouth_score is not None else 0.6))
    )
    selected = overall_score >= 0.45 and checkpoint is not None and tracking_mesh_path is not None

    return FrameQuality(
        frame_id=frame.frame_id,
        crop=str(crop_path),
        tracking_mesh=str(tracking_mesh_path) if tracking_mesh_path is not None else None,
        checkpoint=str(checkpoint_path) if checkpoint_path is not None else None,
        overall_score=float(overall_score),
        selected_for_bake=bool(selected),
        blur_score=float(blur_score),
        sharpness_laplacian_var=float(sharpness),
        face_size_score=float(face_size_score),
        face_area_fraction=float(face_area_fraction),
        face_bbox_fraction=float(face_bbox_fraction),
        pose_score=float(pose_score),
        yaw_degrees=yaw,
        pitch_degrees=pitch,
        roll_degrees=roll,
        exposure_score=float(exposure_score),
        face_luma_median=luma_median,
        face_luma_p05=luma_p05,
        face_luma_p95=luma_p95,
        occlusion_score=float(occlusion_score),
        occlusion_fraction=float(occlusion_fraction),
        segmentation_score=float(segmentation_score),
        landmark_score=float(landmark_score),
        eyes_open_score=eyes_score,
        eye_open_ratio=eye_ratio,
        mouth_closed_score=mouth_score,
        mouth_open_ratio=mouth_ratio,
        skin_median_rgb=skin_median_rgb,
        seg_label_counts=label_counts,
        warnings=warnings,
    )


def analyze_person(person: str, private_root: Path, min_score: float) -> dict[str, Any]:
    bundle = load_person(person, private_root=private_root)
    tracking_dirs = find_tracking_dirs(Path(bundle.output_dir))
    frames = [frame_quality(frame, tracking_dirs) for frame in bundle.frames]
    frames = [
        FrameQuality(**{**asdict(frame), "selected_for_bake": frame.overall_score >= min_score and not frame.warnings})
        if min_score != 0.45
        else frame
        for frame in frames
    ]
    selected = [frame for frame in frames if frame.selected_for_bake]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "person": person,
        "private_root": str(private_root),
        "tracking_dirs": asdict(tracking_dirs),
        "min_score": min_score,
        "frame_count": len(frames),
        "selected_count": len(selected),
        "frames": [asdict(frame) for frame in frames],
    }


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "quality_report.json"
    csv_path = output_dir / "quality_report.csv"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    frame_rows = report["frames"]
    if frame_rows:
        fieldnames = [
            "frame_id",
            "overall_score",
            "selected_for_bake",
            "blur_score",
            "face_size_score",
            "pose_score",
            "yaw_degrees",
            "exposure_score",
            "occlusion_score",
            "segmentation_score",
            "landmark_score",
            "eyes_open_score",
            "mouth_closed_score",
            "warnings",
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for row in frame_rows:
                writer.writerow({name: row.get(name) for name in fieldnames})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score private frames for Texture Baker v2.")
    parser.add_argument("--private-root", type=Path, default=None)
    parser.add_argument("--person", action="append", default=None)
    parser.add_argument("--min-score", type=float, default=0.45)
    parser.add_argument("--output-name", default="quality_v2")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    private_root = args.private_root or default_private_root()
    people = args.person or list(DEFAULT_PEOPLE)
    summaries = []
    for person in people:
        report = analyze_person(person, private_root, args.min_score)
        output_dir = private_root / "output" / person / "texture_baker" / args.output_name
        write_report(report, output_dir)
        summaries.append(
            {
                "person": person,
                "output_dir": str(output_dir),
                "frame_count": report["frame_count"],
                "selected_count": report["selected_count"],
            }
        )
    print(json.dumps({"private_root": str(private_root), "people": summaries}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
