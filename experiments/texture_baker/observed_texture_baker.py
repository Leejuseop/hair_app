"""Create a first observed-photo UV texture atlas from Pixel3DMM UV maps.

This is the smallest useful texture-baker milestone:

crop RGB + Pixel3DMM UV correspondence PNG + segmentation label mask
  -> base_color_observed.png
  -> coverage.png
  -> confidence.png
  -> source_view_map.png
  -> texture_manifest.json

Outputs are private biometric artifacts and are written under the private Drive
root by default, never into the Git repository.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from texture_baker_loader import FrameEvidence, default_private_root, load_person


DEFAULT_EXCLUDED_SEG_LABELS = (0, 1, 3, 14)
DEFAULT_INCLUDED_SEG_LABELS = (2, 4, 5, 6, 7, 8, 9, 10, 12, 13)
DEFAULT_SEGMENT_WEIGHTS = {
    2: 2.0,   # face skin in the current FaRL/CelebM palette
    10: 1.8,  # nose
    12: 1.6,  # lower lip / mouth region
    13: 1.6,  # upper lip / mouth region
    7: 1.25,  # brow-like region
    8: 1.25,  # eye-shadow / brow-like region
    6: 1.0,   # eye-like region
    9: 1.0,   # eye-like region
    4: 0.9,   # ear/side region
    5: 0.9,   # ear/side region
}
CENTRAL_FACE_LABELS = {2, 6, 7, 8, 9, 10, 12, 13}
SIDE_FACE_LABELS = {4, 5}
SKIN_REFERENCE_LABELS = {2, 10}
SKIN_OCCLUSION_FILTER_LABELS = {2, 4, 5}
OCCLUSION_MARGIN_LABELS = {1, 16, 17, 18}


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def load_uv(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def load_segmentation(frame: FrameEvidence) -> np.ndarray | None:
    if frame.segmentation_files:
        seg_og = [path for path in frame.segmentation_files if "/seg_og/" in path.replace("\\", "/")]
        selected = Path(seg_og[0] if seg_og else frame.segmentation_files[0])
        return np.asarray(Image.open(selected).convert("L"), dtype=np.uint8)
    return None


def erode_binary_mask(mask: np.ndarray, iterations: int) -> np.ndarray:
    if iterations <= 0:
        return mask

    result = mask.astype(bool, copy=True)
    height, width = result.shape
    for _ in range(iterations):
        padded = np.pad(result, ((1, 1), (1, 1)), mode="constant", constant_values=False)
        neighbors = [
            padded[dy : dy + height, dx : dx + width]
            for dy in range(3)
            for dx in range(3)
        ]
        result = np.logical_and.reduce(neighbors)
        if not np.any(result):
            break
    return result


def dilate_binary_mask(mask: np.ndarray, iterations: int) -> np.ndarray:
    if iterations <= 0:
        return mask

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


def valid_pixel_mask(
    uv: np.ndarray,
    segmentation: np.ndarray | None,
    included_seg_labels: set[int] | None,
    excluded_seg_labels: set[int],
    mask_erode_iterations: int,
) -> np.ndarray:
    # The current Pixel3DMM UV PNG stores U/V in red/green; blue is zero.
    valid = (uv[..., 0] > 0) | (uv[..., 1] > 0)

    if segmentation is not None:
        if included_seg_labels:
            valid &= np.isin(segmentation, list(included_seg_labels))
        if excluded_seg_labels:
            for label in excluded_seg_labels:
                valid &= segmentation != label

    valid = erode_binary_mask(valid, mask_erode_iterations)
    return valid


def occlusion_margin_keep_mask(
    segmentation: np.ndarray | None,
    valid: np.ndarray,
    *,
    labels: set[int],
    iterations: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    stats: dict[str, Any] = {
        "enabled": iterations > 0,
        "labels": sorted(labels),
        "iterations": iterations,
        "removed_pixels": 0,
    }
    if segmentation is None or iterations <= 0 or not labels:
        return np.ones_like(valid, dtype=bool), stats

    margin = dilate_binary_mask(np.isin(segmentation, list(labels)), iterations)
    removed = valid & margin
    keep = np.ones_like(valid, dtype=bool)
    keep[removed] = False
    stats["removed_pixels"] = int(removed.sum())
    if int(removed.sum()) > 0:
        removed_labels, counts = np.unique(segmentation[removed], return_counts=True)
        stats["removed_seg_label_counts"] = {
            str(int(label)): int(count) for label, count in zip(removed_labels, counts)
        }
    return keep, stats


def ycbcr_like(crop: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    y = (0.299 * crop[..., 0]) + (0.587 * crop[..., 1]) + (0.114 * crop[..., 2])
    cb = crop[..., 2] - y
    cr = crop[..., 0] - y
    return y, cb, cr


def skin_occlusion_keep_mask(
    crop: np.ndarray,
    segmentation: np.ndarray | None,
    valid: np.ndarray,
    *,
    enabled: bool,
    reference_labels: set[int],
    filter_labels: set[int],
    chroma_threshold: float,
    luma_threshold: float,
    min_reference_pixels: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    stats: dict[str, Any] = {"enabled": enabled, "removed_pixels": 0}
    if not enabled or segmentation is None or not reference_labels or not filter_labels:
        return np.ones_like(valid, dtype=bool), stats

    height, width = valid.shape
    yy, xx = np.mgrid[0:height, 0:width]
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    norm_x = np.abs((xx - center_x) / max(center_x, 1.0))
    norm_y = np.abs((yy - center_y) / max(center_y, 1.0))
    central_crop = (norm_x <= 0.48) & (norm_y <= 0.58)

    reference = valid & np.isin(segmentation, list(reference_labels))
    central_reference = reference & central_crop
    if int(central_reference.sum()) >= min_reference_pixels:
        reference = central_reference

    reference_count = int(reference.sum())
    stats["reference_pixels"] = reference_count
    if reference_count < min_reference_pixels:
        stats["skipped_reason"] = "not_enough_reference_pixels"
        return np.ones_like(valid, dtype=bool), stats

    y, cb, cr = ycbcr_like(crop)
    reference_y = float(np.median(y[reference]))
    reference_cb = float(np.median(cb[reference]))
    reference_cr = float(np.median(cr[reference]))

    chroma_distance = np.sqrt((cb - reference_cb) ** 2 + (cr - reference_cr) ** 2)
    luma_distance = np.abs(y - reference_y)
    filtered = valid & np.isin(segmentation, list(filter_labels))
    occluded = filtered & (
        (chroma_distance > chroma_threshold) | (luma_distance > luma_threshold)
    )

    keep = np.ones_like(valid, dtype=bool)
    keep[occluded] = False
    stats.update(
        {
            "reference_ycbcr_like": [reference_y, reference_cb, reference_cr],
            "filter_labels": sorted(filter_labels),
            "chroma_threshold": chroma_threshold,
            "luma_threshold": luma_threshold,
            "removed_pixels": int(occluded.sum()),
        }
    )
    if int(occluded.sum()) > 0:
        labels, counts = np.unique(segmentation[occluded], return_counts=True)
        stats["removed_seg_label_counts"] = {
            str(int(label)): int(count) for label, count in zip(labels, counts)
        }
    return keep, stats


def secondary_central_keep_mask(
    segmentation: np.ndarray | None,
    valid: np.ndarray,
    *,
    enabled: bool,
    radius_x: float,
    radius_y: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    stats: dict[str, Any] = {
        "enabled": enabled,
        "radius_x": radius_x,
        "radius_y": radius_y,
        "removed_pixels": 0,
    }
    if not enabled or segmentation is None or (radius_x >= 1.0 and radius_y >= 1.0):
        return np.ones_like(valid, dtype=bool), stats

    height, width = valid.shape
    yy, xx = np.mgrid[0:height, 0:width]
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    norm_x = np.abs((xx - center_x) / max(center_x, 1.0))
    norm_y = np.abs((yy - center_y) / max(center_y, 1.0))
    central_crop = (norm_x <= radius_x) & (norm_y <= radius_y)
    gated = valid & np.isin(segmentation, list(CENTRAL_FACE_LABELS))
    removed = gated & ~central_crop

    keep = np.ones_like(valid, dtype=bool)
    keep[removed] = False
    stats["removed_pixels"] = int(removed.sum())
    if int(removed.sum()) > 0:
        labels, counts = np.unique(segmentation[removed], return_counts=True)
        stats["removed_seg_label_counts"] = {
            str(int(label)): int(count) for label, count in zip(labels, counts)
        }
    return keep, stats


def pixel_scores(
    crop: np.ndarray,
    segmentation: np.ndarray | None,
    valid: np.ndarray,
    *,
    is_primary_frame: bool,
    has_primary_frames: bool,
    primary_central_weight: float,
    secondary_central_weight: float,
    primary_side_weight: float,
    secondary_side_weight: float,
) -> np.ndarray:
    height, width = valid.shape
    yy, xx = np.mgrid[0:height, 0:width]
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    norm_x = (xx - center_x) / max(center_x, 1.0)
    norm_y = (yy - center_y) / max(center_y, 1.0)
    center_weight = np.exp(-((norm_x * norm_x) + (norm_y * norm_y)) / (2.0 * 0.58 * 0.58))

    luma = (0.299 * crop[..., 0]) + (0.587 * crop[..., 1]) + (0.114 * crop[..., 2])
    exposure_weight = 1.0 - np.clip(np.abs(luma - 128.0) / 128.0, 0.0, 0.75)

    score = (0.35 + 0.65 * center_weight) * (0.45 + 0.55 * exposure_weight)

    if segmentation is not None:
        label_weight = np.ones_like(score, dtype=np.float32)
        for label, weight in DEFAULT_SEGMENT_WEIGHTS.items():
            label_weight[segmentation == label] = weight
        # Ears and side regions should not be over-penalized just because they are
        # away from the crop center.
        side_mask = np.isin(segmentation, [4, 5])
        score[side_mask] = np.maximum(score[side_mask], 0.65) * label_weight[side_mask]
        score[~side_mask] *= label_weight[~side_mask]

        if has_primary_frames:
            central_mask = np.isin(segmentation, list(CENTRAL_FACE_LABELS))
            side_mask = np.isin(segmentation, list(SIDE_FACE_LABELS))
            if is_primary_frame:
                score[central_mask] *= primary_central_weight
                score[side_mask] *= primary_side_weight
            else:
                score[central_mask] *= secondary_central_weight
                score[side_mask] *= secondary_side_weight

    score[~valid] = -1.0
    return score.astype(np.float32)


def accumulate_frame(
    *,
    frame: FrameEvidence,
    frame_index: int,
    atlas_rgb_sum: np.ndarray,
    atlas_weight_sum: np.ndarray,
    atlas_best_rgb: np.ndarray,
    atlas_best_score: np.ndarray,
    atlas_source_map: np.ndarray,
    atlas_source_score: np.ndarray,
    included_seg_labels: set[int] | None,
    excluded_seg_labels: set[int],
    mask_erode_iterations: int,
    flip_v: bool,
    splat_radius: int,
    blend_mode: str,
    primary_frame_ids: set[str],
    primary_central_weight: float,
    secondary_central_weight: float,
    primary_side_weight: float,
    secondary_side_weight: float,
    occlusion_margin_labels: set[int],
    occlusion_margin_iterations: int,
    skin_occlusion_filter: bool,
    skin_occlusion_chroma_threshold: float,
    skin_occlusion_luma_threshold: float,
    skin_occlusion_min_reference_pixels: int,
    secondary_central_crop_radius_x: float,
    secondary_central_crop_radius_y: float,
) -> dict[str, Any]:
    crop_path = Path(frame.crop)
    uv_path = Path(frame.uv_map) if frame.uv_map is not None else None
    if uv_path is None or not uv_path.exists():
        return {"frame_id": frame.frame_id, "used": False, "reason": "missing_uv_map"}

    crop = load_rgb(crop_path)
    uv = load_uv(uv_path)
    segmentation = load_segmentation(frame)

    if crop.shape[:2] != uv.shape[:2]:
        raise ValueError(f"Shape mismatch for frame {frame.frame_id}: crop={crop.shape}, uv={uv.shape}")
    if segmentation is not None and segmentation.shape != crop.shape[:2]:
        raise ValueError(
            f"Segmentation shape mismatch for frame {frame.frame_id}: "
            f"crop={crop.shape[:2]}, seg={segmentation.shape}"
        )

    valid = valid_pixel_mask(
        uv,
        segmentation,
        included_seg_labels,
        excluded_seg_labels,
        mask_erode_iterations,
    )
    margin_keep, margin_stats = occlusion_margin_keep_mask(
        segmentation,
        valid,
        labels=occlusion_margin_labels,
        iterations=occlusion_margin_iterations,
    )
    valid &= margin_keep
    occlusion_keep, occlusion_stats = skin_occlusion_keep_mask(
        crop,
        segmentation,
        valid,
        enabled=skin_occlusion_filter,
        reference_labels=SKIN_REFERENCE_LABELS,
        filter_labels=SKIN_OCCLUSION_FILTER_LABELS,
        chroma_threshold=skin_occlusion_chroma_threshold,
        luma_threshold=skin_occlusion_luma_threshold,
        min_reference_pixels=skin_occlusion_min_reference_pixels,
    )
    valid &= occlusion_keep
    secondary_gate_stats: dict[str, Any] = {"enabled": False, "removed_pixels": 0}
    if primary_frame_ids and frame.frame_id not in primary_frame_ids:
        secondary_keep, secondary_gate_stats = secondary_central_keep_mask(
            segmentation,
            valid,
            enabled=True,
            radius_x=secondary_central_crop_radius_x,
            radius_y=secondary_central_crop_radius_y,
        )
        valid &= secondary_keep
    if not np.any(valid):
        return {
            "frame_id": frame.frame_id,
            "used": False,
            "reason": "no_valid_pixels",
            "occlusion_margin": margin_stats,
            "occlusion_filter": occlusion_stats,
            "secondary_central_crop_gate": secondary_gate_stats,
        }
    scores = pixel_scores(
        crop,
        segmentation,
        valid,
        is_primary_frame=frame.frame_id in primary_frame_ids,
        has_primary_frames=bool(primary_frame_ids),
        primary_central_weight=primary_central_weight,
        secondary_central_weight=secondary_central_weight,
        primary_side_weight=primary_side_weight,
        secondary_side_weight=secondary_side_weight,
    )

    atlas_size = atlas_weight_sum.shape[0]
    u = uv[..., 0].astype(np.float32) / 255.0
    v = uv[..., 1].astype(np.float32) / 255.0

    x = np.clip(np.rint(u * (atlas_size - 1)).astype(np.int32), 0, atlas_size - 1)
    if flip_v:
        y_float = (1.0 - v) * (atlas_size - 1)
    else:
        y_float = v * (atlas_size - 1)
    y = np.clip(np.rint(y_float).astype(np.int32), 0, atlas_size - 1)

    valid_y = y[valid]
    valid_x = x[valid]
    valid_rgb = crop[valid]
    valid_scores = scores[valid]

    for dy in range(-splat_radius, splat_radius + 1):
        yy = valid_y + dy
        yy_valid = (yy >= 0) & (yy < atlas_size)
        if not np.any(yy_valid):
            continue
        for dx in range(-splat_radius, splat_radius + 1):
            xx = valid_x + dx
            in_bounds = yy_valid & (xx >= 0) & (xx < atlas_size)
            if not np.any(in_bounds):
                continue
            target_y = yy[in_bounds]
            target_x = xx[in_bounds]
            target_rgb = valid_rgb[in_bounds]
            target_scores = valid_scores[in_bounds]
            if blend_mode == "weighted":
                weights = np.maximum(target_scores.astype(np.float64), 0.0)
                positive = weights > 0
                if not np.any(positive):
                    continue
                target_y = target_y[positive]
                target_x = target_x[positive]
                target_rgb = target_rgb[positive]
                target_scores = target_scores[positive]
                weights = weights[positive]
                np.add.at(
                    atlas_rgb_sum,
                    (target_y, target_x),
                    target_rgb * weights[:, None],
                )
                np.add.at(atlas_weight_sum, (target_y, target_x), weights)
            else:
                np.add.at(atlas_rgb_sum, (target_y, target_x), target_rgb)
                np.add.at(atlas_weight_sum, (target_y, target_x), 1.0)
            source_replace = target_scores > atlas_source_score[target_y, target_x]
            if np.any(source_replace):
                atlas_source_score[target_y[source_replace], target_x[source_replace]] = target_scores[source_replace]
                atlas_source_map[target_y[source_replace], target_x[source_replace]] = frame_index + 1
            if blend_mode == "best":
                positive = target_scores > 0
                if not np.any(positive):
                    continue
                best_y = target_y[positive]
                best_x = target_x[positive]
                best_score = target_scores[positive]
                replace = best_score > atlas_best_score[best_y, best_x]
                if np.any(replace):
                    atlas_best_score[best_y[replace], best_x[replace]] = best_score[replace]
                    atlas_best_rgb[best_y[replace], best_x[replace]] = target_rgb[positive][replace]
                    atlas_source_map[best_y[replace], best_x[replace]] = frame_index + 1

    if segmentation is not None:
        labels, counts = np.unique(segmentation[valid], return_counts=True)
        label_counts = {str(int(label)): int(count) for label, count in zip(labels, counts)}
    else:
        label_counts = {}

    return {
        "frame_id": frame.frame_id,
        "used": True,
        "valid_pixels": int(valid.sum()),
        "uv_min": [int(uv[..., 0][valid].min()), int(uv[..., 1][valid].min())],
        "uv_max": [int(uv[..., 0][valid].max()), int(uv[..., 1][valid].max())],
        "seg_label_counts": label_counts,
        "occlusion_margin": margin_stats,
        "occlusion_filter": occlusion_stats,
        "secondary_central_crop_gate": secondary_gate_stats,
    }


def write_outputs(
    *,
    output_dir: Path,
    atlas_rgb_sum: np.ndarray,
    atlas_weight_sum: np.ndarray,
    atlas_best_rgb: np.ndarray,
    atlas_best_score: np.ndarray,
    atlas_source_map: np.ndarray,
    manifest: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    observed = np.zeros_like(atlas_rgb_sum, dtype=np.uint8)
    covered = atlas_weight_sum > 0
    if manifest["blend_mode"] == "best":
        best_covered = atlas_best_score > 0
        observed[best_covered] = np.clip(atlas_best_rgb[best_covered], 0, 255).astype(np.uint8)
    else:
        observed[covered] = np.clip(
            atlas_rgb_sum[covered] / atlas_weight_sum[covered, None],
            0,
            255,
        ).astype(np.uint8)

    coverage = np.clip(atlas_weight_sum, 0, 255).astype(np.uint8)
    max_weight = float(atlas_weight_sum.max()) if np.any(covered) else 1.0
    confidence = np.zeros_like(atlas_weight_sum, dtype=np.uint8)
    confidence[covered] = np.clip((atlas_weight_sum[covered] / max_weight) * 255.0, 0, 255).astype(np.uint8)

    source_view = np.zeros_like(atlas_source_map, dtype=np.uint8)
    if atlas_source_map.max() > 0:
        source_view = np.clip(
            (atlas_source_map.astype(np.float32) / atlas_source_map.max()) * 255.0,
            0,
            255,
        ).astype(np.uint8)

    Image.fromarray(observed, mode="RGB").save(output_dir / "base_color_observed.png")
    preview_fill_iterations = int(manifest.get("preview_fill_iterations", 0))
    if preview_fill_iterations > 0:
        preview_fill_min_neighbors = int(manifest.get("preview_fill_min_neighbors", 5))
        preview_filled = fill_preview_holes(
            observed,
            covered,
            preview_fill_iterations,
            preview_fill_min_neighbors,
        )
        Image.fromarray(preview_filled, mode="RGB").save(output_dir / "base_color_preview_filled.png")
    Image.fromarray(coverage, mode="L").save(output_dir / "coverage.png")
    Image.fromarray(confidence, mode="L").save(output_dir / "confidence.png")
    Image.fromarray(source_view, mode="L").save(output_dir / "source_view_map.png")

    manifest["outputs"] = {
        "base_color_observed": str(output_dir / "base_color_observed.png"),
        "coverage": str(output_dir / "coverage.png"),
        "confidence": str(output_dir / "confidence.png"),
        "source_view_map": str(output_dir / "source_view_map.png"),
        "texture_manifest": str(output_dir / "texture_manifest.json"),
    }
    if preview_fill_iterations > 0:
        manifest["outputs"]["base_color_preview_filled"] = str(output_dir / "base_color_preview_filled.png")
    (output_dir / "texture_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def fill_preview_holes(
    observed: np.ndarray,
    covered: np.ndarray,
    iterations: int,
    min_neighbors: int,
) -> np.ndarray:
    filled = observed.astype(np.float32, copy=True)
    filled_mask = covered.astype(bool, copy=True)
    height, width = filled_mask.shape

    for _ in range(iterations):
        padded_rgb = np.pad(filled, ((1, 1), (1, 1), (0, 0)), mode="constant", constant_values=0)
        padded_mask = np.pad(filled_mask, ((1, 1), (1, 1)), mode="constant", constant_values=False)
        neighbor_sum = np.zeros_like(filled)
        neighbor_count = np.zeros((height, width), dtype=np.float32)

        for dy in range(3):
            for dx in range(3):
                if dy == 1 and dx == 1:
                    continue
                neighbor_mask = padded_mask[dy : dy + height, dx : dx + width]
                neighbor_rgb = padded_rgb[dy : dy + height, dx : dx + width]
                neighbor_sum += neighbor_rgb * neighbor_mask[..., None]
                neighbor_count += neighbor_mask.astype(np.float32)

        fillable = (~filled_mask) & (neighbor_count >= min_neighbors)
        if not np.any(fillable):
            break
        filled[fillable] = neighbor_sum[fillable] / neighbor_count[fillable][:, None]
        filled_mask[fillable] = True

    return np.clip(filled, 0, 255).astype(np.uint8)


def bake_person(
    *,
    person: str,
    private_root: Path,
    atlas_size: int,
    included_seg_labels: set[int] | None,
    excluded_seg_labels: set[int],
    mask_erode_iterations: int,
    output_name: str,
    max_frames: int | None,
    flip_v: bool,
    splat_radius: int,
    blend_mode: str,
    primary_frame_ids: set[str],
    primary_central_weight: float,
    secondary_central_weight: float,
    primary_side_weight: float,
    secondary_side_weight: float,
    occlusion_margin_labels: set[int],
    occlusion_margin_iterations: int,
    skin_occlusion_filter: bool,
    skin_occlusion_chroma_threshold: float,
    skin_occlusion_luma_threshold: float,
    skin_occlusion_min_reference_pixels: int,
    secondary_central_crop_radius_x: float,
    secondary_central_crop_radius_y: float,
    preview_fill_iterations: int,
    preview_fill_min_neighbors: int,
) -> dict[str, Any]:
    bundle = load_person(person, private_root=private_root)
    frames = bundle.frames[:max_frames] if max_frames is not None else bundle.frames

    atlas_rgb_sum = np.zeros((atlas_size, atlas_size, 3), dtype=np.float64)
    atlas_weight_sum = np.zeros((atlas_size, atlas_size), dtype=np.float64)
    atlas_best_rgb = np.zeros((atlas_size, atlas_size, 3), dtype=np.float32)
    atlas_best_score = np.full((atlas_size, atlas_size), -1.0, dtype=np.float32)
    atlas_source_map = np.zeros((atlas_size, atlas_size), dtype=np.uint16)
    atlas_source_score = np.full((atlas_size, atlas_size), -1.0, dtype=np.float32)

    frame_reports = [
        accumulate_frame(
            frame=frame,
            frame_index=index,
            atlas_rgb_sum=atlas_rgb_sum,
            atlas_weight_sum=atlas_weight_sum,
            atlas_best_rgb=atlas_best_rgb,
            atlas_best_score=atlas_best_score,
            atlas_source_map=atlas_source_map,
            atlas_source_score=atlas_source_score,
            included_seg_labels=included_seg_labels,
            excluded_seg_labels=excluded_seg_labels,
            mask_erode_iterations=mask_erode_iterations,
            flip_v=flip_v,
            splat_radius=splat_radius,
            blend_mode=blend_mode,
            primary_frame_ids=primary_frame_ids,
            primary_central_weight=primary_central_weight,
            secondary_central_weight=secondary_central_weight,
            primary_side_weight=primary_side_weight,
            secondary_side_weight=secondary_side_weight,
            occlusion_margin_labels=occlusion_margin_labels,
            occlusion_margin_iterations=occlusion_margin_iterations,
            skin_occlusion_filter=skin_occlusion_filter,
            skin_occlusion_chroma_threshold=skin_occlusion_chroma_threshold,
            skin_occlusion_luma_threshold=skin_occlusion_luma_threshold,
            skin_occlusion_min_reference_pixels=skin_occlusion_min_reference_pixels,
            secondary_central_crop_radius_x=secondary_central_crop_radius_x,
            secondary_central_crop_radius_y=secondary_central_crop_radius_y,
        )
        for index, frame in enumerate(frames)
    ]

    used_frames = [report for report in frame_reports if report.get("used")]
    covered = atlas_weight_sum > 0
    output_dir = private_root / "output" / person / "texture_baker" / output_name

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "person": person,
        "purpose": "First observed-photo UV texture atlas from Pixel3DMM UV maps.",
        "privacy": "Private biometric runtime artifact. Keep in Drive/private storage; do not commit generated textures or manifests.",
        "private_root": str(private_root),
        "output_dir": str(output_dir),
        "atlas_size": atlas_size,
        "uv_encoding": "Pixel3DMM PNG red/green channels interpreted as U/V in [0, 255].",
        "flip_v": flip_v,
        "splat_radius": splat_radius,
        "blend_mode": blend_mode,
        "primary_frame_ids": sorted(primary_frame_ids),
        "primary_central_weight": primary_central_weight,
        "secondary_central_weight": secondary_central_weight,
        "primary_side_weight": primary_side_weight,
        "secondary_side_weight": secondary_side_weight,
        "occlusion_margin_labels": sorted(occlusion_margin_labels),
        "occlusion_margin_iterations": occlusion_margin_iterations,
        "skin_occlusion_filter": skin_occlusion_filter,
        "skin_occlusion_reference_labels": sorted(SKIN_REFERENCE_LABELS),
        "skin_occlusion_filter_labels": sorted(SKIN_OCCLUSION_FILTER_LABELS),
        "skin_occlusion_chroma_threshold": skin_occlusion_chroma_threshold,
        "skin_occlusion_luma_threshold": skin_occlusion_luma_threshold,
        "skin_occlusion_min_reference_pixels": skin_occlusion_min_reference_pixels,
        "secondary_central_crop_radius_x": secondary_central_crop_radius_x,
        "secondary_central_crop_radius_y": secondary_central_crop_radius_y,
        "included_seg_labels": sorted(included_seg_labels) if included_seg_labels else None,
        "excluded_seg_labels": sorted(excluded_seg_labels),
        "mask_erode_iterations": mask_erode_iterations,
        "preview_fill_iterations": preview_fill_iterations,
        "preview_fill_min_neighbors": preview_fill_min_neighbors,
        "bundle_summary": {
            "manifest_path": bundle.manifest_path,
            "manifest_kind": bundle.manifest_kind,
            "mesh_keys": [mesh.key for mesh in bundle.meshes],
            "frame_count_available": len(bundle.frames),
            "frame_count_attempted": len(frames),
            "frame_count_used": len(used_frames),
        },
        "coverage_summary": {
            "covered_texels": int(covered.sum()),
            "total_texels": int(atlas_size * atlas_size),
            "covered_fraction": float(covered.mean()),
            "max_observations_per_texel": float(atlas_weight_sum.max()) if np.any(covered) else 0.0,
        },
        "frame_reports": frame_reports,
        "limitations": [
            "Average mode uses equal per-pixel weights; weighted and best modes use heuristic preview scores.",
            "Weighted and best blend modes use heuristic segmentation, center, and exposure scores; they are preview policies, not validated photometric models.",
            "Primary frame mode strongly prefers selected frame IDs for central face labels and keeps side labels available from all frames.",
            "Occlusion margin removes pixels near configured hair/headwear labels before baking.",
            "Skin occlusion filtering is a color-distance heuristic that removes likely hair/headband pixels from skin and side labels before baking.",
            "Preview hole fill is saved as a separate visualization and is not treated as observed photo evidence.",
            "MVP splat radius is a nearest-neighbor preview fill, not true triangle rasterization.",
            "MVP excludes only configured segmentation labels and does not yet score view angle, exposure, sharpness, or occlusion.",
            "MVP source_view_map stores the highest-scoring single contributor per texel, not a full dominant-view vote.",
            "MVP does not perform hole completion or seam blending.",
        ],
    }

    write_outputs(
        output_dir=output_dir,
        atlas_rgb_sum=atlas_rgb_sum,
        atlas_weight_sum=atlas_weight_sum,
        atlas_best_rgb=atlas_best_rgb,
        atlas_best_score=atlas_best_score,
        atlas_source_map=atlas_source_map,
        manifest=manifest,
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bake a first observed-photo UV texture atlas.")
    parser.add_argument("--private-root", type=Path, default=None)
    parser.add_argument("--person", action="append", default=None)
    parser.add_argument("--atlas-size", type=int, default=1024)
    parser.add_argument("--output-name", default="observed_v0")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--include-seg-label", type=int, action="append", default=None)
    parser.add_argument("--exclude-seg-label", type=int, action="append", default=list(DEFAULT_EXCLUDED_SEG_LABELS))
    parser.add_argument(
        "--all-seg-labels",
        action="store_true",
        help="Disable the default face-label whitelist and rely only on excluded labels.",
    )
    parser.add_argument(
        "--mask-erode-iterations",
        type=int,
        default=0,
        help="Shrink the valid crop-space mask before splatting to reduce hair/background edge leaks.",
    )
    parser.add_argument("--flip-v", action="store_true")
    parser.add_argument("--splat-radius", type=int, default=0)
    parser.add_argument("--blend-mode", choices=["average", "weighted", "best"], default="average")
    parser.add_argument(
        "--primary-central-weight",
        type=float,
        default=4.0,
        help="Central-face score multiplier for selected primary frames.",
    )
    parser.add_argument(
        "--secondary-central-weight",
        type=float,
        default=0.08,
        help="Central-face score multiplier for non-primary frames when primary frames are selected.",
    )
    parser.add_argument(
        "--primary-side-weight",
        type=float,
        default=1.0,
        help="Side/ear score multiplier for selected primary frames.",
    )
    parser.add_argument(
        "--secondary-side-weight",
        type=float,
        default=1.0,
        help="Side/ear score multiplier for non-primary frames when primary frames are selected.",
    )
    parser.add_argument(
        "--occlusion-margin-label",
        type=int,
        action="append",
        default=None,
        help="Segmentation label whose dilated margin should be removed as likely hair/headwear occlusion.",
    )
    parser.add_argument(
        "--occlusion-margin-iterations",
        type=int,
        default=0,
        help="Dilate occlusion-margin labels by this many crop pixels before removing valid pixels.",
    )
    parser.add_argument(
        "--skin-occlusion-filter",
        action="store_true",
        help="Remove likely hair/headband occluders from skin and side segmentation labels.",
    )
    parser.add_argument(
        "--skin-occlusion-chroma-threshold",
        type=float,
        default=42.0,
        help="Maximum skin-reference chroma distance for labels filtered by --skin-occlusion-filter.",
    )
    parser.add_argument(
        "--skin-occlusion-luma-threshold",
        type=float,
        default=68.0,
        help="Maximum skin-reference luma distance for labels filtered by --skin-occlusion-filter.",
    )
    parser.add_argument(
        "--skin-occlusion-min-reference-pixels",
        type=int,
        default=400,
        help="Minimum skin-reference pixels needed before the occlusion filter is applied.",
    )
    parser.add_argument(
        "--secondary-central-crop-radius-x",
        type=float,
        default=1.0,
        help="For non-primary frames, keep central-face labels only within this normalized crop X radius.",
    )
    parser.add_argument(
        "--secondary-central-crop-radius-y",
        type=float,
        default=1.0,
        help="For non-primary frames, keep central-face labels only within this normalized crop Y radius.",
    )
    parser.add_argument(
        "--preview-fill-iterations",
        type=int,
        default=0,
        help="Save a separate preview image with limited neighbor propagation into holes.",
    )
    parser.add_argument(
        "--preview-fill-min-neighbors",
        type=int,
        default=5,
        help="Minimum observed neighbors needed before preview hole fill can propagate into a texel.",
    )
    parser.add_argument(
        "--primary-frame-id",
        action="append",
        default=None,
        help="Prefer this frame for central face labels. May be passed more than once.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    private_root = args.private_root or default_private_root()
    people = args.person or ["주섭", "은채"]
    if args.all_seg_labels:
        included_seg_labels = None
    elif args.include_seg_label is not None:
        included_seg_labels = set(args.include_seg_label)
    else:
        included_seg_labels = set(DEFAULT_INCLUDED_SEG_LABELS)
    excluded_seg_labels = set(args.exclude_seg_label or [])
    occlusion_margin_labels = (
        set(args.occlusion_margin_label)
        if args.occlusion_margin_label is not None
        else set(OCCLUSION_MARGIN_LABELS)
    )

    reports = [
        bake_person(
            person=person,
            private_root=private_root,
            atlas_size=args.atlas_size,
            included_seg_labels=included_seg_labels,
            excluded_seg_labels=excluded_seg_labels,
            mask_erode_iterations=args.mask_erode_iterations,
            output_name=args.output_name,
            max_frames=args.max_frames,
            flip_v=args.flip_v,
            splat_radius=args.splat_radius,
            blend_mode=args.blend_mode,
            primary_frame_ids=set(args.primary_frame_id or []),
            primary_central_weight=args.primary_central_weight,
            secondary_central_weight=args.secondary_central_weight,
            primary_side_weight=args.primary_side_weight,
            secondary_side_weight=args.secondary_side_weight,
            occlusion_margin_labels=occlusion_margin_labels,
            occlusion_margin_iterations=args.occlusion_margin_iterations,
            skin_occlusion_filter=args.skin_occlusion_filter,
            skin_occlusion_chroma_threshold=args.skin_occlusion_chroma_threshold,
            skin_occlusion_luma_threshold=args.skin_occlusion_luma_threshold,
            skin_occlusion_min_reference_pixels=args.skin_occlusion_min_reference_pixels,
            secondary_central_crop_radius_x=args.secondary_central_crop_radius_x,
            secondary_central_crop_radius_y=args.secondary_central_crop_radius_y,
            preview_fill_iterations=args.preview_fill_iterations,
            preview_fill_min_neighbors=args.preview_fill_min_neighbors,
        )
        for person in people
    ]

    print(
        json.dumps(
            {
                "private_root": str(private_root),
                "people": [
                    {
                        "person": report["person"],
                        "output_dir": report["output_dir"],
                        "frame_count_used": report["bundle_summary"]["frame_count_used"],
                        "covered_fraction": report["coverage_summary"]["covered_fraction"],
                        "covered_texels": report["coverage_summary"]["covered_texels"],
                    }
                    for report in reports
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
