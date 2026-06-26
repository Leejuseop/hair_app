"""Texture Baker v3: direct pose-fitted selfie bake with iterative repair.

This is still an experiment, but unlike the earlier weak residual pass it tries
to put reliable source photo pixels into the FLAME UV atlas first, then repairs
empty/bad texels over iterations. All generated images are private runtime
artifacts under the private Drive root.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from evidence_quality_report import (
    CENTRAL_FACE_LABELS,
    FACE_LABELS,
    OCCLUDER_LABELS,
    SKIN_REFERENCE_LABELS,
    analyze_person,
    checkpoint_path_for_frame,
    dilate_binary_mask,
    find_tracking_dirs,
    load_frame_checkpoint,
    load_segmentation,
    tracking_mesh_path_for_frame,
    write_report,
)
from fitted_camera_selfie_compare import (
    FrameRender,
    accumulate_residual,
    color_match_to_crop,
    error_metrics,
    make_diff_image,
    optimize_texture_from_residual,
    render_fitted_frame,
)
from observed_texture_baker import fill_preview_holes, load_uv
from texture_baker_loader import FrameEvidence, default_private_root, load_person
from texture_baker_v2 import (
    accumulate_visible_triangles,
    project_tracking_vertices,
    rasterize_zbuffer,
)
from texture_cleanup_completion import (
    build_region_masks,
    material_canvas,
    union_masks,
)
from textured_mesh_preview import (
    apply_uv_mode,
    build_material_vertex_colors,
    estimate_skin_color,
    load_flame_masks,
    read_ply,
    render_mesh,
    resolve_flame_masks,
    resolve_uv_coords,
    resolve_valid_vertices,
)


DEFAULT_PEOPLE = ("\uc8fc\uc12d", "\uc740\ucc44")
VARIANTS = ("v3_no_lighting", "v3_lighting_normalized")
DEFAULT_IMAGE_SIZE = 512
DEFAULT_ATLAS_SIZE = 512
DEFAULT_ITERATIONS = 5
DEFAULT_OUTPUT_PREFIX = "v3"
FRONT45_YAWS = (-45, -30, -15, 0, 15, 30, 45)
SKINLIKE_MASKS = (
    "face",
    "forehead",
    "nose",
    "neck",
    "left_ear",
    "right_ear",
    "boundary",
    "scalp",
)
FEATURE_MASKS = (
    "lips",
    "eye_region",
    "left_eye_region",
    "right_eye_region",
    "left_eyeball",
    "right_eyeball",
)
REGION_FILL_GROUPS = (
    ("face", ("face", "nose", "forehead")),
    ("nose", ("nose", "face")),
    ("forehead", ("forehead", "face", "scalp")),
    ("neck", ("neck", "boundary")),
    ("left_ear", ("left_ear", "face")),
    ("right_ear", ("right_ear", "face")),
    ("scalp", ("scalp", "forehead")),
)
SEGMENT_WEIGHTS_V3 = {
    2: 2.7,
    10: 2.35,
    6: 1.35,
    7: 1.6,
    8: 1.6,
    9: 1.35,
    12: 1.1,
    13: 1.1,
    4: 1.0,
    5: 1.0,
}
PERSON_LABELS = {
    "\uc8fc\uc12d": "Juseop",
    "\uc740\ucc44": "Eunchae",
}


@dataclass(frozen=True)
class FramePacket:
    frame: FrameEvidence
    quality: dict[str, Any]
    raw_rgb: np.ndarray
    bake_rgb: np.ndarray
    segmentation: np.ndarray | None
    uv_map: np.ndarray | None
    keep_mask: np.ndarray
    score_map: np.ndarray
    lighting: dict[str, Any]
    checkpoint: dict[str, Any] | None
    mesh_path: Path | None


@dataclass(frozen=True)
class VariantConfig:
    name: str
    lighting_normalized: bool
    residual_strength: float
    repair_strength: float


def as_uint8_rgb(image: np.ndarray) -> np.ndarray:
    return np.clip(image, 0, 255).astype(np.uint8)


def load_rgb(path: Path, image_size: int) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    if image.size != (image_size, image_size):
        image = image.resize((image_size, image_size), Image.BILINEAR)
    return np.asarray(image, dtype=np.uint8)


def resize_segmentation(segmentation: np.ndarray | None, image_size: int) -> np.ndarray | None:
    if segmentation is None:
        return None
    if segmentation.shape == (image_size, image_size):
        return segmentation
    return np.asarray(
        Image.fromarray(segmentation.astype(np.uint8), mode="L").resize((image_size, image_size), Image.NEAREST),
        dtype=np.uint8,
    )


def robust_luma(rgb: np.ndarray) -> np.ndarray:
    return (0.299 * rgb[..., 0]) + (0.587 * rgb[..., 1]) + (0.114 * rgb[..., 2])


def ycbcr_like(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    y = robust_luma(rgb)
    return y, rgb[..., 2] - y, rgb[..., 0] - y


def blurred_mask(mask: np.ndarray, radius: float) -> np.ndarray:
    if radius <= 0:
        return mask.astype(np.float32)
    image = Image.fromarray(mask.astype(np.uint8) * 255, mode="L").filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(image, dtype=np.float32) / 255.0


def blurred_rgb(image: np.ndarray, radius: float) -> np.ndarray:
    if radius <= 0:
        return image.astype(np.float32)
    return np.asarray(
        Image.fromarray(as_uint8_rgb(image), mode="RGB").filter(ImageFilter.GaussianBlur(radius)),
        dtype=np.float32,
    )


def safe_median_rgb(rgb: np.ndarray, mask: np.ndarray, fallback: np.ndarray) -> np.ndarray:
    if int(mask.sum()) < 40:
        return fallback.astype(np.float32)
    return np.median(rgb[mask].astype(np.float32), axis=0)


def image_regions(segmentation: np.ndarray | None, image_size: int) -> dict[str, np.ndarray]:
    shape = (image_size, image_size)
    empty = np.zeros(shape, dtype=bool)
    if segmentation is None:
        return {name: empty.copy() for name in ("skin", "left_cheek", "right_cheek", "nose_side", "chin", "forehead")}

    skin = np.isin(segmentation, list(SKIN_REFERENCE_LABELS))
    face = np.isin(segmentation, list(CENTRAL_FACE_LABELS))
    ys, xs = np.where(face)
    if xs.size == 0:
        return {
            "skin": skin,
            "left_cheek": empty.copy(),
            "right_cheek": empty.copy(),
            "nose_side": empty.copy(),
            "chin": empty.copy(),
            "forehead": empty.copy(),
        }

    x0, x1 = float(xs.min()), float(xs.max())
    y0, y1 = float(ys.min()), float(ys.max())
    width = max(x1 - x0, 1.0)
    height = max(y1 - y0, 1.0)
    yy, xx = np.mgrid[0:image_size, 0:image_size]
    xn = (xx - x0) / width
    yn = (yy - y0) / height

    return {
        "skin": skin,
        "left_cheek": skin & (xn >= 0.18) & (xn <= 0.46) & (yn >= 0.36) & (yn <= 0.70),
        "right_cheek": skin & (xn >= 0.54) & (xn <= 0.82) & (yn >= 0.36) & (yn <= 0.70),
        "nose_side": skin & (xn >= 0.38) & (xn <= 0.62) & (yn >= 0.30) & (yn <= 0.66),
        "chin": skin & (xn >= 0.33) & (xn <= 0.67) & (yn >= 0.67) & (yn <= 0.90),
        "forehead": skin & (xn >= 0.26) & (xn <= 0.74) & (yn >= 0.08) & (yn <= 0.32),
    }


def estimate_reference_regions(frames: list[FrameEvidence], quality_by_id: dict[str, dict[str, Any]], image_size: int) -> dict[str, Any]:
    values: dict[str, list[np.ndarray]] = {name: [] for name in ("skin", "left_cheek", "right_cheek", "nose_side", "chin", "forehead")}
    weights: dict[str, list[float]] = {name: [] for name in values}

    fallback = np.asarray([168.0, 132.0, 118.0], dtype=np.float32)
    for frame in frames:
        quality = quality_by_id.get(frame.frame_id)
        if quality is None or not quality.get("selected_for_bake"):
            continue
        rgb = load_rgb(Path(frame.crop), image_size).astype(np.float32)
        segmentation = resize_segmentation(load_segmentation(frame), image_size)
        regions = image_regions(segmentation, image_size)
        frame_weight = max(float(quality.get("overall_score", 0.0)), 0.05)
        for name, mask in regions.items():
            if int(mask.sum()) < 80:
                continue
            values[name].append(np.median(rgb[mask], axis=0))
            weights[name].append(frame_weight * min(int(mask.sum()) / 900.0, 1.5))

    references: dict[str, Any] = {}
    for name, region_values in values.items():
        if not region_values:
            references[name] = [float(value) for value in fallback]
            continue
        stacked = np.stack(region_values, axis=0)
        w = np.asarray(weights[name], dtype=np.float32)
        references[name] = [float(value) for value in np.average(stacked, axis=0, weights=np.maximum(w, 1e-4))]
    return references


def normalize_lighting(
    rgb: np.ndarray,
    segmentation: np.ndarray | None,
    references: dict[str, Any],
    *,
    enabled: bool,
) -> tuple[np.ndarray, dict[str, Any]]:
    if not enabled or segmentation is None:
        return rgb.astype(np.float32), {"enabled": False}

    working = rgb.astype(np.float32, copy=True)
    regions = image_regions(segmentation, rgb.shape[0])
    reference_skin = np.asarray(references.get("skin", [168.0, 132.0, 118.0]), dtype=np.float32)
    skin_mask = regions["skin"]
    if int(skin_mask.sum()) < 160:
        return working, {"enabled": False, "reason": "not_enough_skin_pixels"}

    current_skin = np.median(working[skin_mask], axis=0)
    current_std = np.maximum(np.std(working[skin_mask], axis=0), 1.0)
    target_std = np.clip(current_std, 18.0, 44.0)
    scale = np.clip(target_std / current_std, 0.90, 1.12)
    shift = np.clip(reference_skin - (current_skin * scale), -26.0, 26.0)
    working = (working * scale[None, None, :]) + shift[None, None, :]

    local_stats = {}
    for name, base_weight in (
        ("left_cheek", 0.34),
        ("right_cheek", 0.34),
        ("nose_side", 0.22),
        ("chin", 0.18),
        ("forehead", 0.14),
    ):
        mask = regions[name]
        if int(mask.sum()) < 90:
            local_stats[name] = {"used": False, "pixels": int(mask.sum())}
            continue
        target = np.asarray(references.get(name, reference_skin), dtype=np.float32)
        current = np.median(working[mask], axis=0)
        delta = np.clip(target - current, -18.0, 18.0)
        alpha = blurred_mask(mask, 14.0)[..., None] * base_weight
        working = working + (delta[None, None, :] * alpha)
        local_stats[name] = {
            "used": True,
            "pixels": int(mask.sum()),
            "delta_rgb": [float(value) for value in delta],
            "weight": base_weight,
        }

    return np.clip(working, 0, 255).astype(np.float32), {
        "enabled": True,
        "skin_pixels": int(skin_mask.sum()),
        "current_skin_rgb": [float(value) for value in current_skin],
        "reference_skin_rgb": [float(value) for value in reference_skin],
        "scale_rgb": [float(value) for value in scale],
        "shift_rgb": [float(value) for value in shift],
        "local": local_stats,
    }


def frame_keep_mask_v3(rgb: np.ndarray, segmentation: np.ndarray | None, reference_skin: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    if segmentation is None:
        return np.ones(rgb.shape[:2], dtype=bool), {"segmentation": False}

    valid = np.isin(segmentation, list(FACE_LABELS))
    occluder = np.isin(segmentation, list(OCCLUDER_LABELS))
    valid &= ~dilate_binary_mask(occluder, 3)

    luma, cb, cr = ycbcr_like(rgb.astype(np.float32))
    skin_reference_mask = valid & np.isin(segmentation, list(SKIN_REFERENCE_LABELS))
    if int(skin_reference_mask.sum()) >= 180:
        local_skin = np.median(rgb[skin_reference_mask].astype(np.float32), axis=0)
    else:
        local_skin = reference_skin
    ref_y = float((0.299 * local_skin[0]) + (0.587 * local_skin[1]) + (0.114 * local_skin[2]))
    ref_cb = float(local_skin[2] - ref_y)
    ref_cr = float(local_skin[0] - ref_y)
    chroma_distance = np.sqrt((cb - ref_cb) ** 2 + (cr - ref_cr) ** 2)
    luma_distance = np.abs(luma - ref_y)

    skin_labels = np.isin(segmentation, [2, 10, 4, 5])
    extreme = skin_labels & ((luma < 24) | (luma > 248) | (chroma_distance > 44) | (luma_distance > 78))
    valid &= ~extreme

    return valid, {
        "segmentation": True,
        "valid_pixels": int(valid.sum()),
        "removed_occluder_margin": int(dilate_binary_mask(occluder, 3).sum()),
        "removed_extreme_skin": int(extreme.sum()),
        "local_skin_rgb": [float(value) for value in local_skin],
    }


def frame_score_map_v3(
    *,
    rgb: np.ndarray,
    segmentation: np.ndarray | None,
    keep_mask: np.ndarray,
    quality: dict[str, Any],
    reference_skin: np.ndarray,
    pass_weight: float,
) -> np.ndarray:
    height, width = keep_mask.shape
    yy, xx = np.mgrid[0:height, 0:width]
    center_x = (width - 1) * 0.5
    center_y = (height - 1) * 0.5
    norm_x = (xx - center_x) / max(center_x, 1.0)
    norm_y = (yy - center_y) / max(center_y, 1.0)
    center_weight = np.exp(-((norm_x * norm_x) + (norm_y * norm_y)) / (2.0 * 0.70 * 0.70))
    score = pass_weight * max(float(quality.get("overall_score", 0.0)), 0.03) * (0.48 + (0.52 * center_weight))
    score = score.astype(np.float32)

    if segmentation is not None:
        label_weight = np.full_like(score, 0.65, dtype=np.float32)
        for label, weight in SEGMENT_WEIGHTS_V3.items():
            label_weight[segmentation == label] = weight
        score *= label_weight

        mouth_score = quality.get("mouth_closed_score")
        if mouth_score is not None:
            mouth = np.isin(segmentation, [12, 13])
            score[mouth] *= 0.55 + (0.45 * float(np.clip(mouth_score, 0.0, 1.0)))
        eye_score = quality.get("eyes_open_score")
        if eye_score is not None:
            eyes = np.isin(segmentation, [6, 9])
            score[eyes] *= 0.70 + (0.30 * float(np.clip(eye_score, 0.0, 1.0)))

    luma, cb, cr = ycbcr_like(rgb.astype(np.float32))
    ref_y = float((0.299 * reference_skin[0]) + (0.587 * reference_skin[1]) + (0.114 * reference_skin[2]))
    ref_cb = float(reference_skin[2] - ref_y)
    ref_cr = float(reference_skin[0] - ref_y)
    chroma_distance = np.sqrt((cb - ref_cb) ** 2 + (cr - ref_cr) ** 2)
    luma_distance = np.abs(luma - ref_y)
    color_reliability = np.clip(1.0 - (chroma_distance / 64.0), 0.06, 1.0) * np.clip(
        1.0 - (luma_distance / 92.0), 0.08, 1.0
    )
    color_reliability[(chroma_distance > 62) | (luma_distance > 106)] = 0.0
    score *= color_reliability.astype(np.float32)
    score[~keep_mask] = 0.0
    return score


def update_best_samples(
    *,
    best_rgb: np.ndarray,
    best_score: np.ndarray,
    rgb_sum: np.ndarray,
    weight_sum: np.ndarray,
    source_map: np.ndarray,
    target_y: np.ndarray,
    target_x: np.ndarray,
    colors: np.ndarray,
    weights: np.ndarray,
    frame_index: int,
) -> int:
    positive = weights > 0
    if not np.any(positive):
        return 0
    target_y = target_y[positive]
    target_x = target_x[positive]
    colors = colors[positive]
    weights = weights[positive].astype(np.float32)
    np.add.at(rgb_sum, (target_y, target_x), colors.astype(np.float32) * weights[:, None])
    np.add.at(weight_sum, (target_y, target_x), weights)
    replace = weights > best_score[target_y, target_x]
    if np.any(replace):
        best_score[target_y[replace], target_x[replace]] = weights[replace]
        best_rgb[target_y[replace], target_x[replace]] = colors[replace]
        source_map[target_y[replace], target_x[replace]] = frame_index + 1
    return int(target_y.size)


def accumulate_uv_map_samples(
    *,
    packet: FramePacket,
    frame_index: int,
    atlas_size: int,
    best_rgb: np.ndarray,
    best_score: np.ndarray,
    rgb_sum: np.ndarray,
    weight_sum: np.ndarray,
    source_map: np.ndarray,
    splat_radius: int,
) -> dict[str, Any]:
    if packet.uv_map is None:
        return {"used_pixels": 0, "reason": "missing_uv_map"}
    uv_map = packet.uv_map
    valid = packet.keep_mask & ((uv_map[..., 0] > 0) | (uv_map[..., 1] > 0)) & (packet.score_map > 0)
    if not np.any(valid):
        return {"used_pixels": 0, "reason": "no_valid_uv_pixels"}

    u = uv_map[..., 0].astype(np.float32) / 255.0
    v = uv_map[..., 1].astype(np.float32) / 255.0
    tex_x = np.clip(np.rint(u * (atlas_size - 1)).astype(np.int32), 0, atlas_size - 1)
    tex_y = np.clip(np.rint(v * (atlas_size - 1)).astype(np.int32), 0, atlas_size - 1)
    base_y = tex_y[valid]
    base_x = tex_x[valid]
    colors = packet.bake_rgb[valid]
    weights = packet.score_map[valid]
    written = 0
    for dy in range(-splat_radius, splat_radius + 1):
        yy = base_y + dy
        y_ok = (yy >= 0) & (yy < atlas_size)
        if not np.any(y_ok):
            continue
        for dx in range(-splat_radius, splat_radius + 1):
            xx = base_x + dx
            ok = y_ok & (xx >= 0) & (xx < atlas_size)
            if not np.any(ok):
                continue
            distance_penalty = 1.0 / (1.0 + abs(dx) + abs(dy))
            written += update_best_samples(
                best_rgb=best_rgb,
                best_score=best_score,
                rgb_sum=rgb_sum,
                weight_sum=weight_sum,
                source_map=source_map,
                target_y=yy[ok],
                target_x=xx[ok],
                colors=colors[ok],
                weights=weights[ok] * distance_penalty,
                frame_index=frame_index,
            )
    return {"used_pixels": int(valid.sum()), "written_samples": written}


def build_seed_texture(
    *,
    best_rgb: np.ndarray,
    best_score: np.ndarray,
    rgb_sum: np.ndarray,
    weight_sum: np.ndarray,
    material: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    covered = best_score > 0
    average = np.zeros_like(best_rgb, dtype=np.float32)
    weighted = weight_sum > 0
    average[weighted] = rgb_sum[weighted] / weight_sum[weighted, None]
    texture = material.astype(np.float32, copy=True)
    # A single "best" source frame often creates atlas-sized patchwork because
    # neighboring texels can come from different lighting/poses. Bias the seed
    # toward the weighted multi-frame color, then keep only a small pull from
    # the sharpest sample.
    texture[weighted] = average[weighted]
    texture[covered] = (average[covered] * 0.72) + (best_rgb[covered] * 0.28)
    confidence = np.zeros(best_score.shape, dtype=np.uint8)
    if np.any(covered):
        best_conf = best_score[covered] / max(float(np.percentile(best_score[covered], 98)), 1e-5)
        weight_conf = weight_sum[covered] / max(float(np.percentile(weight_sum[covered], 98)), 1e-5)
        confidence[covered] = np.clip(((best_conf * 0.35) + (weight_conf * 0.65)) * 255.0, 0, 255)
    return as_uint8_rgb(texture), confidence


def color_distance_to_reference(rgb: np.ndarray, reference: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    y, cb, cr = ycbcr_like(rgb.astype(np.float32))
    ref_y = float((0.299 * reference[0]) + (0.587 * reference[1]) + (0.114 * reference[2]))
    ref_cb = float(reference[2] - ref_y)
    ref_cr = float(reference[0] - ref_y)
    chroma_distance = np.sqrt((cb - ref_cb) ** 2 + (cr - ref_cr) ** 2)
    luma_distance = np.abs(y - ref_y)
    return chroma_distance, luma_distance


def stabilize_avatar_texture(
    *,
    texture: np.ndarray,
    confidence: np.ndarray,
    filled_mask: np.ndarray,
    region_masks: dict[str, np.ndarray],
    material: np.ndarray,
    iteration: int,
    repair_strength: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Turn the raw photo atlas into a calmer avatar albedo.

    This deliberately sacrifices some per-photo lighting/detail. At this stage
    the user-facing priority is a coherent bald head texture, not exact scanned
    albedo fidelity from noisy casual selfies.
    """
    shape = texture.shape[:2]
    skinlike = union_masks(region_masks, SKINLIKE_MASKS, shape)
    features = union_masks(region_masks, FEATURE_MASKS, shape)
    cleanup_region = skinlike & ~features
    output = texture.astype(np.float32, copy=True)
    material_f = material.astype(np.float32)
    stats: dict[str, Any] = {"skin_groups": {}, "feature_texels": 0}

    total_unstable = 0
    for group_name, names in REGION_FILL_GROUPS:
        group = union_masks(region_masks, names, shape) & cleanup_region
        if int(group.sum()) < 20:
            continue

        seed = group & (confidence >= 44) & ~filled_mask
        if int(seed.sum()) >= 80:
            anchor = np.median(output[seed], axis=0)
            chroma_seed, luma_seed = color_distance_to_reference(output, anchor)
            stable_seed = seed & (chroma_seed <= 26) & (luma_seed <= 42)
            if int(stable_seed.sum()) >= 60:
                anchor = np.median(output[stable_seed], axis=0)
        else:
            anchor = np.median(material_f[group], axis=0)

        chroma_distance, luma_distance = color_distance_to_reference(output, anchor)
        material_chroma, material_luma = color_distance_to_reference(output, np.median(material_f[group], axis=0))
        threshold_chroma = 26.0 if group_name in {"face", "nose", "forehead"} else 34.0
        threshold_luma = 46.0 if group_name in {"face", "nose", "forehead"} else 58.0
        unstable = group & (
            (confidence < 32)
            | filled_mask
            | (chroma_distance > threshold_chroma)
            | (luma_distance > threshold_luma)
            | (material_chroma > threshold_chroma + 12.0)
            | (material_luma > threshold_luma + 18.0)
        )
        total_unstable += int(unstable.sum())

        if np.any(unstable):
            target_color = (material_f[unstable] * 0.68) + (anchor[None, :] * 0.32)
            alpha = min(0.82 + (iteration * 0.025), 0.94) * repair_strength
            output[unstable] = (output[unstable] * (1.0 - alpha)) + (target_color * alpha)

        group_alpha = 0.08 if group_name in {"left_ear", "right_ear", "neck", "scalp"} else 0.14
        group_alpha = min(group_alpha + (iteration * 0.018), 0.24) * repair_strength
        output[group] = (output[group] * (1.0 - group_alpha)) + (anchor[None, :] * group_alpha)
        stats["skin_groups"][group_name] = {
            "texels": int(group.sum()),
            "unstable_texels": int(unstable.sum()),
            "anchor_rgb": [float(value) for value in anchor],
        }

    if np.any(cleanup_region):
        # Smooth after outlier replacement so blue/orange fragments do not get
        # diffused into otherwise stable skin.
        smoothed = blurred_rgb(as_uint8_rgb(output), 2.2 + (iteration * 0.20))
        broad = blurred_rgb(as_uint8_rgb(output), 6.5 + (iteration * 0.35))
        low_confidence = cleanup_region & ((confidence < 58) | filled_mask)
        base_alpha = blurred_mask(cleanup_region, 1.3)[..., None] * min(0.26 + (iteration * 0.018), 0.38)
        low_alpha = blurred_mask(low_confidence, 1.9)[..., None] * min(0.42 + (iteration * 0.028), 0.62)
        output = (output * (1.0 - base_alpha)) + (smoothed * base_alpha)
        output = (output * (1.0 - low_alpha)) + (broad * low_alpha)

        material_alpha = blurred_mask(low_confidence, 2.4)[..., None] * min(0.18 + (iteration * 0.025), 0.34)
        output = (output * (1.0 - material_alpha)) + (material_f * material_alpha)

    # Keep eyes/lips from turning into random photo noise. The renderer also has
    # an eye overlay, but the atlas itself should not contain broken dark holes.
    skin_anchor_mask = cleanup_region & (confidence >= 32)
    if int(skin_anchor_mask.sum()) >= 80:
        skin_anchor = np.median(output[skin_anchor_mask], axis=0)
    elif np.any(cleanup_region):
        skin_anchor = np.median(material_f[cleanup_region], axis=0)
    else:
        skin_anchor = np.median(material_f.reshape(-1, 3), axis=0)

    feature_decay = 1.0 / (1.0 + (iteration * 0.22))
    lips = region_masks.get("lips")
    if lips is not None and np.any(lips):
        lip_target = (material_f * 0.55) + (skin_anchor[None, None, :] * 0.45)
        lip_smooth = blurred_rgb(as_uint8_rgb(output), 1.15)
        alpha = blurred_mask(lips, 1.25)[..., None] * (0.26 * feature_decay)
        smooth_alpha = blurred_mask(lips, 0.8)[..., None] * 0.24
        output = (output * (1.0 - smooth_alpha)) + (lip_smooth * smooth_alpha)
        output = (output * (1.0 - alpha)) + (lip_target * alpha)
        stats["feature_texels"] += int(lips.sum())

    eye_regions = union_masks(region_masks, ("eye_region", "left_eye_region", "right_eye_region"), shape)
    if np.any(eye_regions):
        eye_target = (material_f * 0.34) + (skin_anchor[None, None, :] * 0.66)
        alpha = blurred_mask(eye_regions, 1.1)[..., None] * (0.24 * feature_decay)
        output = (output * (1.0 - alpha)) + (eye_target * alpha)
        stats["feature_texels"] += int(eye_regions.sum())

    eyeballs = union_masks(region_masks, ("left_eyeball", "right_eyeball"), shape)
    if np.any(eyeballs):
        alpha = blurred_mask(eyeballs, 0.65)[..., None] * 0.92
        output = (output * (1.0 - alpha)) + (material_f * alpha)
        stats["feature_texels"] += int(eyeballs.sum())

    stats["cleanup_region_texels"] = int(cleanup_region.sum())
    stats["unstable_texels"] = total_unstable
    return as_uint8_rgb(output), stats


def detect_bad_texels(
    *,
    texture: np.ndarray,
    confidence: np.ndarray,
    region_masks: dict[str, np.ndarray],
    material: np.ndarray,
    iteration: int,
) -> dict[str, np.ndarray]:
    shape = texture.shape[:2]
    skinlike = union_masks(region_masks, SKINLIKE_MASKS, shape)
    features = union_masks(region_masks, FEATURE_MASKS, shape)
    repair_region = skinlike & ~features
    empty = repair_region & (confidence <= max(2, 9 - iteration))

    rgb = texture.astype(np.float32)
    luma, cb, cr = ycbcr_like(rgb)
    material_luma, material_cb, material_cr = ycbcr_like(material.astype(np.float32))
    chroma_distance = np.sqrt((cb - material_cb) ** 2 + (cr - material_cr) ** 2)
    luma_distance = np.abs(luma - material_luma)
    extreme = repair_region & ((luma < 28) | (luma > 246) | (chroma_distance > 74) | (luma_distance > 104))

    patchy = np.zeros(shape, dtype=bool)
    for _group_name, names in REGION_FILL_GROUPS:
        group = union_masks(region_masks, names, shape) & repair_region
        trusted = group & (confidence > 24) & ~extreme
        if int(trusted.sum()) < 80:
            continue
        median = np.median(rgb[trusted], axis=0)
        y = robust_luma(rgb)
        ref_y = float((0.299 * median[0]) + (0.587 * median[1]) + (0.114 * median[2]))
        ref_cb = float(median[2] - ref_y)
        ref_cr = float(median[0] - ref_y)
        distance = np.sqrt(((rgb[..., 2] - y) - ref_cb) ** 2 + ((rgb[..., 0] - y) - ref_cr) ** 2)
        patchy |= group & ((distance > 34) | (np.abs(y - ref_y) > 54))

    bad = repair_region & (empty | extreme | patchy)
    bad = dilate_binary_mask(bad, 1) & repair_region
    return {
        "skinlike": skinlike,
        "features": features,
        "repair_region": repair_region,
        "empty": empty,
        "extreme": extreme,
        "patchy": patchy,
        "bad": bad,
    }


def neighbor_fill_once(texture: np.ndarray, source_mask: np.ndarray, target_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    height, width = target_mask.shape
    padded_rgb = np.pad(texture.astype(np.float32), ((1, 1), (1, 1), (0, 0)), mode="edge")
    padded_mask = np.pad(source_mask, ((1, 1), (1, 1)), mode="constant", constant_values=False)
    neighbor_sum = np.zeros_like(texture, dtype=np.float32)
    neighbor_count = np.zeros((height, width), dtype=np.float32)
    for dy in range(3):
        for dx in range(3):
            if dy == 1 and dx == 1:
                continue
            mask = padded_mask[dy : dy + height, dx : dx + width]
            rgb = padded_rgb[dy : dy + height, dx : dx + width]
            neighbor_sum += rgb * mask[..., None]
            neighbor_count += mask.astype(np.float32)
    fillable = target_mask & (neighbor_count >= 2)
    output = texture.astype(np.float32, copy=True)
    output[fillable] = neighbor_sum[fillable] / neighbor_count[fillable, None]
    return as_uint8_rgb(output), fillable


def mirror_fill(texture: np.ndarray, good_mask: np.ndarray, target_mask: np.ndarray, alpha: float) -> tuple[np.ndarray, np.ndarray]:
    width = texture.shape[1]
    yy, xx = np.where(target_mask)
    if yy.size == 0:
        return texture, np.zeros_like(target_mask)
    mx = width - 1 - xx
    usable = good_mask[yy, mx]
    if not np.any(usable):
        return texture, np.zeros_like(target_mask)
    output = texture.astype(np.float32, copy=True)
    y = yy[usable]
    x = xx[usable]
    src = texture[y, width - 1 - x].astype(np.float32)
    output[y, x] = (output[y, x] * (1.0 - alpha)) + (src * alpha)
    filled = np.zeros_like(target_mask)
    filled[y, x] = True
    return as_uint8_rgb(output), filled


def repair_iteration(
    *,
    texture: np.ndarray,
    confidence: np.ndarray,
    filled_mask: np.ndarray,
    region_masks: dict[str, np.ndarray],
    material: np.ndarray,
    iteration: int,
    repair_strength: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    masks = detect_bad_texels(
        texture=texture,
        confidence=confidence,
        region_masks=region_masks,
        material=material,
        iteration=iteration,
    )
    output = texture.copy()
    confidence_out = confidence.copy()
    filled_out = filled_mask.copy()
    total_neighbor_filled = 0

    target = masks["bad"].copy()
    for _group_name, names in REGION_FILL_GROUPS:
        group = union_masks(region_masks, names, texture.shape[:2]) & masks["repair_region"]
        group_target = target & group
        for _ in range(10 + (iteration * 3)):
            source = group & ~masks["bad"] & ~group_target & (confidence_out > 14)
            output, newly = neighbor_fill_once(output, source, group_target)
            if not np.any(newly):
                break
            group_target &= ~newly
            target &= ~newly
            confidence_out[newly] = np.maximum(confidence_out[newly], 34 + iteration * 8)
            filled_out[newly] = True
            total_neighbor_filled += int(newly.sum())

    good = masks["repair_region"] & ~target & (confidence_out > 18)
    output, mirrored = mirror_fill(output, good, target & masks["repair_region"], alpha=0.42)
    if np.any(mirrored):
        confidence_out[mirrored] = np.maximum(confidence_out[mirrored], 24)
        filled_out[mirrored] = True
        target &= ~mirrored

    if np.any(target):
        alpha = min(0.78 + (iteration * 0.04), 0.94) * repair_strength
        output_float = output.astype(np.float32)
        output_float[target] = (output_float[target] * (1.0 - alpha)) + (material[target].astype(np.float32) * alpha)
        output = as_uint8_rgb(output_float)
        confidence_out[target] = np.maximum(confidence_out[target], 12)
        filled_out[target] = True

    seam = dilate_binary_mask(masks["bad"], 3) & masks["repair_region"]
    if np.any(seam):
        smooth = blurred_rgb(output, 1.15 + (iteration * 0.12))
        seam_alpha = blurred_mask(seam, 1.8)[..., None] * min(0.30 + iteration * 0.035, 0.48)
        output = as_uint8_rgb((output.astype(np.float32) * (1.0 - seam_alpha)) + (smooth * seam_alpha))

    output, coherence_stats = stabilize_avatar_texture(
        texture=output,
        confidence=confidence_out,
        filled_mask=filled_out,
        region_masks=region_masks,
        material=material,
        iteration=iteration,
        repair_strength=repair_strength,
    )

    stats = {
        "bad_texels": int(masks["bad"].sum()),
        "empty_texels": int(masks["empty"].sum()),
        "extreme_texels": int(masks["extreme"].sum()),
        "patchy_texels": int(masks["patchy"].sum()),
        "neighbor_filled_texels": total_neighbor_filled,
        "mirror_filled_texels": int(mirrored.sum()),
        "material_blended_texels": int(target.sum()),
        "coherence": coherence_stats,
    }
    return output, confidence_out, filled_out, stats


def seam_score(texture: np.ndarray, mask: np.ndarray) -> float:
    if not np.any(mask):
        return 0.0
    boundary = dilate_binary_mask(mask, 2) & ~mask
    if not np.any(boundary):
        return 0.0
    luma = robust_luma(texture.astype(np.float32))
    smooth_luma = robust_luma(blurred_rgb(texture, 2.0))
    return float(np.mean(np.abs(luma[boundary] - smooth_luma[boundary])))


def load_frame_packets(
    *,
    bundle: Any,
    quality_report: dict[str, Any],
    tracking_dirs: Any,
    variant: VariantConfig,
    references: dict[str, Any],
    reference_skin: np.ndarray,
    image_size: int,
    min_score: float,
    max_abs_yaw: float,
) -> tuple[list[FramePacket], list[dict[str, Any]]]:
    quality_by_id = {frame["frame_id"]: frame for frame in quality_report["frames"]}
    packets: list[FramePacket] = []
    packet_reports: list[dict[str, Any]] = []

    for frame in bundle.frames:
        quality = quality_by_id.get(frame.frame_id)
        if quality is None:
            continue
        yaw = quality.get("yaw_degrees")
        if not quality.get("selected_for_bake") or float(quality.get("overall_score", 0.0)) < min_score:
            continue
        if yaw is not None and abs(float(yaw)) > max_abs_yaw:
            continue

        raw_rgb = load_rgb(Path(frame.crop), image_size)
        segmentation = resize_segmentation(load_segmentation(frame), image_size)
        bake_rgb, lighting_stats = normalize_lighting(
            raw_rgb,
            segmentation,
            references,
            enabled=variant.lighting_normalized,
        )
        keep_mask, keep_stats = frame_keep_mask_v3(bake_rgb, segmentation, reference_skin)
        score_map = frame_score_map_v3(
            rgb=bake_rgb,
            segmentation=segmentation,
            keep_mask=keep_mask,
            quality=quality,
            reference_skin=reference_skin,
            pass_weight=1.0,
        )

        uv_map = None
        if frame.uv_map is not None and Path(frame.uv_map).exists():
            uv_map = load_uv(Path(frame.uv_map))
            if uv_map.shape[:2] != raw_rgb.shape[:2]:
                uv_map = np.asarray(
                    Image.open(frame.uv_map).convert("RGB").resize((image_size, image_size), Image.NEAREST),
                    dtype=np.uint8,
                )

        checkpoint = load_frame_checkpoint(checkpoint_path_for_frame(tracking_dirs, frame.frame_id), frame.frame_id)
        mesh_path = tracking_mesh_path_for_frame(tracking_dirs, frame.frame_id)
        packets.append(
            FramePacket(
                frame=frame,
                quality=quality,
                raw_rgb=raw_rgb,
                bake_rgb=np.clip(bake_rgb, 0, 255).astype(np.float32),
                segmentation=segmentation,
                uv_map=uv_map,
                keep_mask=keep_mask,
                score_map=score_map,
                lighting=lighting_stats,
                checkpoint=checkpoint,
                mesh_path=mesh_path,
            )
        )
        packet_reports.append(
            {
                "frame_id": frame.frame_id,
                "overall_score": float(quality.get("overall_score", 0.0)),
                "yaw_degrees": quality.get("yaw_degrees"),
                "keep_mask": keep_stats,
                "lighting": lighting_stats,
                "uv_map": str(frame.uv_map) if frame.uv_map is not None else None,
                "checkpoint": str(checkpoint_path_for_frame(tracking_dirs, frame.frame_id)),
                "tracking_mesh": str(mesh_path) if mesh_path is not None else None,
            }
        )
    return packets, packet_reports


def direct_bake_seed(
    *,
    packets: list[FramePacket],
    uv_coords: np.ndarray,
    valid_vertex_mask: np.ndarray,
    flame_masks: dict[str, np.ndarray],
    atlas_size: int,
    image_size: int,
    splat_radius: int,
    camera_pass_weight: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[dict[str, Any]]]:
    best_rgb = np.zeros((atlas_size, atlas_size, 3), dtype=np.float32)
    best_score = np.full((atlas_size, atlas_size), -np.inf, dtype=np.float32)
    rgb_sum = np.zeros((atlas_size, atlas_size, 3), dtype=np.float32)
    weight_sum = np.zeros((atlas_size, atlas_size), dtype=np.float32)
    source_map = np.zeros((atlas_size, atlas_size), dtype=np.int32)
    frame_reports = []

    for frame_index, packet in enumerate(packets):
        uv_stats = accumulate_uv_map_samples(
            packet=packet,
            frame_index=frame_index,
            atlas_size=atlas_size,
            best_rgb=best_rgb,
            best_score=best_score,
            rgb_sum=rgb_sum,
            weight_sum=weight_sum,
            source_map=source_map,
            splat_radius=splat_radius,
        )
        camera_stats = {"used_pixels": 0, "reason": "camera_pass_disabled" if camera_pass_weight <= 0 else "missing_tracking"}
        if camera_pass_weight > 0 and packet.checkpoint is not None and packet.mesh_path is not None:
            mesh = read_ply(packet.mesh_path)
            if mesh.vertices.shape[0] == uv_coords.shape[0]:
                points, depth, camera_vertices, calibration = project_tracking_vertices(
                    mesh.vertices,
                    packet.checkpoint,
                    packet.segmentation,
                    flame_masks,
                    image_size,
                )
                zbuffer = rasterize_zbuffer(mesh.faces, points, depth, image_size)
                camera_stats = accumulate_visible_triangles(
                    rgb=packet.bake_rgb,
                    segmentation=packet.segmentation,
                    keep_mask=packet.keep_mask,
                    faces=mesh.faces,
                    uv_coords=uv_coords,
                    valid_vertex_mask=valid_vertex_mask,
                    points=points,
                    depth=depth,
                    camera_vertices=camera_vertices,
                    image_size=image_size,
                    atlas_rgb_sum=rgb_sum,
                    atlas_weight_sum=weight_sum,
                    atlas_best_rgb=best_rgb,
                    atlas_best_score=best_score,
                    atlas_source_map=source_map,
                    atlas_source_score=best_score,
                    frame_index=frame_index,
                    frame_score=float(packet.quality.get("overall_score", 0.0)),
                    zbuffer=zbuffer,
                    splat_radius=max(1, splat_radius),
                    pass_weight=camera_pass_weight,
                )
                camera_stats["projection_calibration"] = calibration
        frame_reports.append({"frame_id": packet.frame.frame_id, "uv_correspondence": uv_stats, "camera_projection": camera_stats})

    best_score[best_score < 0] = 0.0
    return best_rgb, best_score, rgb_sum, weight_sum, frame_reports


def apply_residual_step(
    *,
    texture: np.ndarray,
    packets: list[FramePacket],
    compare_packets: list[FramePacket],
    uv_coords: np.ndarray,
    flame_masks: dict[str, np.ndarray],
    confidence: np.ndarray,
    material_vertex_colors: np.ndarray,
    region_masks: dict[str, np.ndarray],
    variant: VariantConfig,
    iteration: int,
    image_size: int,
    uv_mode: str,
) -> tuple[np.ndarray, dict[str, Any]]:
    residual_sum = np.zeros((*texture.shape[:2], 3), dtype=np.float32)
    residual_weight = np.zeros(texture.shape[:2], dtype=np.float32)
    frame_stats = []
    packet_by_id = {packet.frame.frame_id: packet for packet in packets}

    for packet in compare_packets:
        if packet.checkpoint is None or packet.mesh_path is None:
            continue
        mesh = read_ply(packet.mesh_path)
        compare_rgb = packet.bake_rgb.astype(np.uint8) if variant.lighting_normalized else packet.raw_rgb
        render, points, depth, zbuffer, calibration = render_fitted_frame(
            crop=compare_rgb,
            segmentation=packet.segmentation,
            mesh=mesh,
            checkpoint=packet.checkpoint,
            flame_masks=flame_masks,
            uv_coords=uv_coords,
            texture=texture,
            confidence=confidence,
            material_vertex_colors=material_vertex_colors,
            image_size=image_size,
            uv_mode=uv_mode,
            eye_overlay=True,
            fallback_confidence_threshold=0,
            projection_flip_y=True,
        )
        foreground = np.isfinite(zbuffer)
        metric_mask = foreground
        if packet.segmentation is not None:
            metric_mask &= np.isin(packet.segmentation, list(CENTRAL_FACE_LABELS))
        metric_mask &= packet.keep_mask
        frame_render = FrameRender(
            frame_id=packet.frame.frame_id,
            quality=packet.quality,
            crop=compare_rgb,
            segmentation=packet.segmentation,
            mesh=mesh,
            points=points,
            depth=depth,
            zbuffer=zbuffer,
            render=render,
            foreground=foreground,
            metric_mask=metric_mask,
            calibration=calibration,
        )
        stats = accumulate_residual(
            frame_render=frame_render,
            uv_coords=uv_coords,
            uv_mode=uv_mode,
            residual_sum=residual_sum,
            residual_weight=residual_weight,
            splat_radius=1,
        )
        frame_stats.append({"frame_id": packet.frame.frame_id, "residual": stats})

    optimized, opt_stats = optimize_texture_from_residual(
        base_texture=texture,
        residual_sum=residual_sum,
        residual_weight=residual_weight,
        strength=variant.residual_strength * (0.88 ** max(iteration - 1, 0)),
        max_shift=max(9.0, 22.0 - (iteration * 1.8)),
        blur_radius=1.7 + (iteration * 0.25),
    )
    skinlike = union_masks(region_masks, SKINLIKE_MASKS, texture.shape[:2])
    features = union_masks(region_masks, FEATURE_MASKS, texture.shape[:2])
    residual_region = skinlike & ~features & (residual_weight > 0.001)
    output = texture.astype(np.float32, copy=True)
    correction = optimized.astype(np.float32) - texture.astype(np.float32)
    output[residual_region] = output[residual_region] + correction[residual_region]
    return as_uint8_rgb(output), {"optimization": opt_stats, "frame_stats": frame_stats, "packet_count": len(packet_by_id)}


def compute_metrics(
    *,
    texture: np.ndarray,
    confidence: np.ndarray,
    filled_mask: np.ndarray,
    observed_mask: np.ndarray,
    region_masks: dict[str, np.ndarray],
    material: np.ndarray,
    compare_packets: list[FramePacket],
    uv_coords: np.ndarray,
    flame_masks: dict[str, np.ndarray],
    material_vertex_colors: np.ndarray,
    image_size: int,
    uv_mode: str,
) -> dict[str, Any]:
    masks = detect_bad_texels(
        texture=texture,
        confidence=confidence,
        region_masks=region_masks,
        material=material,
        iteration=99,
    )
    repair_region = masks["repair_region"]
    observed = observed_mask & repair_region
    filled = filled_mask & repair_region & ~observed
    fallback = repair_region & ~(observed | filled) & (confidence <= 18)
    compare = []
    for packet in compare_packets:
        if packet.checkpoint is None or packet.mesh_path is None:
            continue
        mesh = read_ply(packet.mesh_path)
        render, _points, _depth, zbuffer, _calibration = render_fitted_frame(
            crop=packet.raw_rgb,
            segmentation=packet.segmentation,
            mesh=mesh,
            checkpoint=packet.checkpoint,
            flame_masks=flame_masks,
            uv_coords=uv_coords,
            texture=texture,
            confidence=confidence,
            material_vertex_colors=material_vertex_colors,
            image_size=image_size,
            uv_mode=uv_mode,
            eye_overlay=True,
            fallback_confidence_threshold=0,
            projection_flip_y=True,
        )
        foreground = np.isfinite(zbuffer)
        metric_mask = foreground
        if packet.segmentation is not None:
            metric_mask &= np.isin(packet.segmentation, list(CENTRAL_FACE_LABELS))
        raw_metrics = error_metrics(packet.raw_rgb, render, metric_mask)
        matched, _match_stats = color_match_to_crop(
            render=render,
            crop=packet.raw_rgb,
            foreground=foreground,
            metric_mask=metric_mask,
        )
        matched_metrics = error_metrics(packet.raw_rgb, matched, metric_mask)
        compare.append(
            {
                "frame_id": packet.frame.frame_id,
                "raw": raw_metrics,
                "lighting_matched": matched_metrics,
            }
        )

    luma_values = [item["raw"]["mean_abs_luma"] for item in compare if item["raw"]["mean_abs_luma"] is not None]
    rgb_values = [
        float(np.mean(item["raw"]["mean_abs_rgb"]))
        for item in compare
        if item["raw"]["mean_abs_rgb"] is not None
    ]
    return {
        "repair_region_texels": int(repair_region.sum()),
        "observed_texels": int(observed.sum()),
        "filled_texels": int(filled.sum()),
        "fallback_or_low_conf_texels": int(fallback.sum()),
        "bad_texels": int(masks["bad"].sum()),
        "empty_texels": int(masks["empty"].sum()),
        "observed_coverage": float(observed.sum() / max(int(repair_region.sum()), 1)),
        "filled_coverage": float(filled.sum() / max(int(repair_region.sum()), 1)),
        "bad_ratio": float(masks["bad"].sum() / max(int(repair_region.sum()), 1)),
        "mean_abs_luma": float(np.mean(luma_values)) if luma_values else None,
        "mean_abs_rgb": float(np.mean(rgb_values)) if rgb_values else None,
        "seam_score": seam_score(texture, filled_mask | masks["bad"]),
        "compare_frames": compare,
    }


def save_iteration(
    *,
    output_dir: Path,
    iteration: int,
    texture: np.ndarray,
    confidence: np.ndarray,
    filled_mask: np.ndarray,
    observed_mask: np.ndarray,
    metrics: dict[str, Any],
) -> dict[str, str]:
    iter_dir = output_dir / f"iter_{iteration:02d}"
    iter_dir.mkdir(parents=True, exist_ok=True)
    texture_path = iter_dir / "base_color_v3.png"
    confidence_path = iter_dir / "confidence.png"
    filled_path = iter_dir / "filled_mask.png"
    observed_path = iter_dir / "observed_mask.png"
    Image.fromarray(texture, mode="RGB").save(texture_path)
    Image.fromarray(confidence, mode="L").save(confidence_path)
    Image.fromarray(filled_mask.astype(np.uint8) * 255, mode="L").save(filled_path)
    Image.fromarray(observed_mask.astype(np.uint8) * 255, mode="L").save(observed_path)
    (iter_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "texture": str(texture_path),
        "confidence": str(confidence_path),
        "filled_mask": str(filled_path),
        "observed_mask": str(observed_path),
        "metrics": str(iter_dir / "metrics.json"),
    }


def choose_final_iteration(metrics: list[dict[str, Any]]) -> int:
    """Pick the first clean-enough pass instead of the flattest late pass."""
    for index, metric in enumerate(metrics):
        if index == 0:
            continue
        if (
            int(metric.get("empty_texels", 0)) == 0
            and float(metric.get("bad_ratio", 1.0)) <= 0.001
            and float(metric.get("seam_score", 99.0)) <= 1.25
        ):
            return index
    if not metrics:
        return 0
    scores = []
    for index, metric in enumerate(metrics):
        luma = float(metric.get("mean_abs_luma") or 99.0)
        seam = float(metric.get("seam_score") or 99.0)
        bad = float(metric.get("bad_ratio") or 0.0)
        late_penalty = max(index - 1, 0) * 0.45
        scores.append(luma + (seam * 0.18) + (bad * 250.0) + late_penalty)
    return int(np.argmin(np.asarray(scores, dtype=np.float32)))


def render_front45_sheet(
    *,
    output_path: Path,
    person: str,
    mesh: Any,
    uv_coords: np.ndarray,
    textures: list[np.ndarray],
    metrics: list[dict[str, Any]],
    flame_masks: dict[str, np.ndarray],
    render_size: int,
    uv_mode: str,
) -> None:
    columns = list(FRONT45_YAWS)
    left_width = 220
    header_height = 66
    row_height = render_size + 34
    width = left_width + len(columns) * render_size
    height = header_height + len(textures) * row_height
    sheet = Image.new("RGB", (width, height), (28, 28, 28))
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 14), f"{PERSON_LABELS.get(person, person)} v3 front~45 iterations", fill=(245, 245, 245))
    draw.text((16, 38), "rows=iteration, columns=yaw, geometry fixed", fill=(175, 175, 175))
    for col, yaw in enumerate(columns):
        draw.text((left_width + col * render_size + 8, 44), f"yaw {yaw:+03d}", fill=(225, 225, 225))

    material_vertex_colors = build_material_vertex_colors(mesh.vertices.shape[0], flame_masks, estimate_skin_color(textures[-1]))
    for row, texture in enumerate(textures):
        y = header_height + row * row_height
        m = metrics[row]
        draw.rectangle((0, y, left_width - 8, y + row_height - 1), fill=(38, 38, 38))
        draw.text((16, y + 12), f"iter {row:02d}", fill=(255, 255, 255))
        draw.text((16, y + 34), f"obs {m['observed_coverage']*100:.1f}% fill {m['filled_coverage']*100:.1f}%", fill=(195, 195, 195))
        luma = m.get("mean_abs_luma")
        bad = m.get("bad_ratio")
        draw.text((16, y + 56), f"luma {luma:.1f}" if luma is not None else "luma n/a", fill=(195, 195, 195))
        draw.text((16, y + 78), f"bad {bad*100:.1f}%", fill=(195, 195, 195))
        for col, yaw in enumerate(columns):
            image = render_mesh(
                mesh=mesh,
                uv_coords=uv_coords,
                texture=texture,
                image_size=render_size,
                padding=36,
                uv_mode=uv_mode,
                depth_mode="max",
                view=f"yaw_{yaw:03d}",
                valid_vertices=None,
                mask_mode="none",
                material_vertex_colors=material_vertex_colors,
                confidence=None,
                flame_masks=flame_masks,
                eye_overlay=True,
            )
            sheet.paste(Image.fromarray(image, mode="RGB"), (left_width + col * render_size, y + 24))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def render_fitted_iteration_sheet(
    *,
    output_path: Path,
    packets: list[FramePacket],
    textures: list[np.ndarray],
    confidences: list[np.ndarray],
    metrics: list[dict[str, Any]],
    uv_coords: np.ndarray,
    flame_masks: dict[str, np.ndarray],
    material_vertex_colors: np.ndarray,
    image_size: int,
    uv_mode: str,
    tile_size: int,
) -> None:
    columns = ["crop"] + [f"iter {idx:02d}" for idx in range(len(textures))]
    left_width = 150
    header_height = 66
    width = left_width + len(columns) * tile_size
    row_height = tile_size + 30
    height = header_height + len(packets) * row_height
    sheet = Image.new("RGB", (width, height), (28, 28, 28))
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 14), "Fitted-camera texture iterations", fill=(245, 245, 245))
    draw.text((16, 38), "crop plus same-camera renders; labels show mean luma error", fill=(175, 175, 175))
    for col, label in enumerate(columns):
        draw.text((left_width + col * tile_size + 8, 44), label, fill=(225, 225, 225))

    for row, packet in enumerate(packets):
        y = header_height + row * row_height
        draw.rectangle((0, y, left_width - 8, y + row_height - 1), fill=(38, 38, 38))
        draw.text((16, y + 14), f"frame {packet.frame.frame_id}", fill=(255, 255, 255))
        draw.text((16, y + 36), f"score {float(packet.quality.get('overall_score', 0.0)):.3f}", fill=(190, 190, 190))
        crop = Image.fromarray(packet.raw_rgb, mode="RGB").resize((tile_size, tile_size), Image.BILINEAR)
        sheet.paste(crop, (left_width, y + 24))
        if packet.checkpoint is None or packet.mesh_path is None:
            continue
        mesh = read_ply(packet.mesh_path)
        for idx, texture in enumerate(textures):
            render, _points, _depth, zbuffer, _cal = render_fitted_frame(
                crop=packet.raw_rgb,
                segmentation=packet.segmentation,
                mesh=mesh,
                checkpoint=packet.checkpoint,
                flame_masks=flame_masks,
                uv_coords=uv_coords,
                texture=texture,
                confidence=confidences[idx],
                material_vertex_colors=material_vertex_colors,
                image_size=image_size,
                uv_mode=uv_mode,
                eye_overlay=True,
                fallback_confidence_threshold=0,
                projection_flip_y=True,
            )
            foreground = np.isfinite(zbuffer)
            metric_mask = foreground
            if packet.segmentation is not None:
                metric_mask &= np.isin(packet.segmentation, list(CENTRAL_FACE_LABELS))
            diff = make_diff_image(packet.raw_rgb, render, metric_mask)
            thumb = Image.fromarray(render, mode="RGB").resize((tile_size, tile_size), Image.BILINEAR)
            x = left_width + (idx + 1) * tile_size
            sheet.paste(thumb, (x, y + 24))
            luma = metrics[idx].get("mean_abs_luma")
            draw.text((x + 6, y + 6), f"{luma:.1f}" if luma is not None else "n/a", fill=(235, 235, 235))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def choose_primary_mesh(bundle: Any) -> Any:
    for mesh in bundle.meshes:
        if mesh.exists:
            return read_ply(Path(mesh.path))
    raise FileNotFoundError("No mesh candidate found for preview rendering.")


def process_variant(
    *,
    private_root: Path,
    person: str,
    variant: VariantConfig,
    output_prefix: str,
    atlas_size: int,
    image_size: int,
    iterations: int,
    min_score: float,
    max_abs_yaw: float,
    splat_radius: int,
    uv_mode: str,
    camera_pass_weight: float,
) -> dict[str, Any]:
    bundle = load_person(person, private_root=private_root)
    quality_report = analyze_person(person, private_root, min_score=min_score)
    tracking_dirs = find_tracking_dirs(Path(bundle.output_dir))
    quality_dir = private_root / "output" / person / "texture_baker" / "quality_v3"
    write_report(quality_report, quality_dir)

    quality_by_id = {frame["frame_id"]: frame for frame in quality_report["frames"]}
    references = estimate_reference_regions(bundle.frames, quality_by_id, image_size)
    reference_skin = np.asarray(references.get("skin", [168.0, 132.0, 118.0]), dtype=np.float32)
    packets, packet_reports = load_frame_packets(
        bundle=bundle,
        quality_report=quality_report,
        tracking_dirs=tracking_dirs,
        variant=variant,
        references=references,
        reference_skin=reference_skin,
        image_size=image_size,
        min_score=min_score,
        max_abs_yaw=max_abs_yaw,
    )
    if not packets:
        raise RuntimeError(f"No usable frames for {person} {variant.name}")

    packets.sort(key=lambda packet: float(packet.quality.get("overall_score", 0.0)), reverse=True)
    compare_packets = packets[: min(4, len(packets))]
    uv_coords = np.load(resolve_uv_coords(private_root, None)).astype(np.float32)
    valid_vertices_path = resolve_valid_vertices(private_root, None)
    valid_vertices = np.load(valid_vertices_path) if valid_vertices_path is not None else np.arange(uv_coords.shape[0])
    valid_vertex_mask = np.zeros((uv_coords.shape[0],), dtype=bool)
    valid_vertex_mask[valid_vertices[(valid_vertices >= 0) & (valid_vertices < uv_coords.shape[0])]] = True
    flame_masks = load_flame_masks(resolve_flame_masks(private_root, None))

    primary_mesh = choose_primary_mesh(bundle)
    region_masks = build_region_masks(
        faces=primary_mesh.faces,
        uv_coords=uv_coords,
        flame_masks=flame_masks,
        atlas_size=atlas_size,
    )
    material = material_canvas(
        reference_skin=reference_skin,
        region_masks=region_masks,
        shape=(atlas_size, atlas_size),
    )

    best_rgb, best_score, rgb_sum, weight_sum, seed_frame_reports = direct_bake_seed(
        packets=packets,
        uv_coords=uv_coords,
        valid_vertex_mask=valid_vertex_mask,
        flame_masks=flame_masks,
        atlas_size=atlas_size,
        image_size=image_size,
        splat_radius=splat_radius,
        camera_pass_weight=camera_pass_weight,
    )
    texture, confidence = build_seed_texture(
        best_rgb=best_rgb,
        best_score=best_score,
        rgb_sum=rgb_sum,
        weight_sum=weight_sum,
        material=material,
    )
    observed_mask = best_score > 0
    filled_mask = np.zeros(best_score.shape, dtype=bool)
    material_vertex_colors = build_material_vertex_colors(uv_coords.shape[0], flame_masks, estimate_skin_color(texture))

    output_dir = private_root / "output" / person / "texture_baker" / f"{output_prefix}_{variant.name}"
    output_dir.mkdir(parents=True, exist_ok=True)
    textures: list[np.ndarray] = []
    confidences: list[np.ndarray] = []
    metrics: list[dict[str, Any]] = []
    iteration_outputs: list[dict[str, Any]] = []

    for iteration in range(iterations + 1):
        if iteration > 0:
            texture, residual_stats = apply_residual_step(
                texture=texture,
                packets=packets,
                compare_packets=compare_packets,
                uv_coords=uv_coords,
                flame_masks=flame_masks,
                confidence=confidence,
                material_vertex_colors=material_vertex_colors,
                region_masks=region_masks,
                variant=variant,
                iteration=iteration,
                image_size=image_size,
                uv_mode=uv_mode,
            )
            texture, confidence, filled_mask, repair_stats = repair_iteration(
                texture=texture,
                confidence=confidence,
                filled_mask=filled_mask,
                region_masks=region_masks,
                material=material,
                iteration=iteration,
                repair_strength=variant.repair_strength,
            )
        else:
            texture, confidence, filled_mask, repair_stats = repair_iteration(
                texture=texture,
                confidence=confidence,
                filled_mask=filled_mask,
                region_masks=region_masks,
                material=material,
                iteration=iteration,
                repair_strength=variant.repair_strength,
            )
            residual_stats = {"skipped": "initial_iteration"}

        metric = compute_metrics(
            texture=texture,
            confidence=confidence,
            filled_mask=filled_mask,
            observed_mask=observed_mask,
            region_masks=region_masks,
            material=material,
            compare_packets=compare_packets,
            uv_coords=uv_coords,
            flame_masks=flame_masks,
            material_vertex_colors=material_vertex_colors,
            image_size=image_size,
            uv_mode=uv_mode,
        )
        metric["iteration"] = iteration
        metric["repair"] = repair_stats
        metric["residual"] = residual_stats
        outputs = save_iteration(
            output_dir=output_dir,
            iteration=iteration,
            texture=texture,
            confidence=confidence,
            filled_mask=filled_mask,
            observed_mask=observed_mask,
            metrics=metric,
        )
        iteration_outputs.append({"iteration": iteration, **outputs})
        textures.append(texture.copy())
        confidences.append(confidence.copy())
        metrics.append(metric)

    selected_final_iteration = choose_final_iteration(metrics)
    final_texture_path = output_dir / "base_color_v3_final.png"
    Image.fromarray(textures[selected_final_iteration], mode="RGB").save(final_texture_path)
    Image.fromarray(confidences[selected_final_iteration], mode="L").save(output_dir / "confidence_final.png")
    render_front45_sheet(
        output_path=output_dir / "front45_iteration_review_sheet.png",
        person=person,
        mesh=primary_mesh,
        uv_coords=uv_coords,
        textures=textures,
        metrics=metrics,
        flame_masks=flame_masks,
        render_size=288,
        uv_mode=uv_mode,
    )
    render_fitted_iteration_sheet(
        output_path=output_dir / "fitted_camera_iteration_compare_sheet.png",
        packets=compare_packets,
        textures=textures,
        confidences=confidences,
        metrics=metrics,
        uv_coords=uv_coords,
        flame_masks=flame_masks,
        material_vertex_colors=material_vertex_colors,
        image_size=image_size,
        uv_mode=uv_mode,
        tile_size=190,
    )

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "person": person,
        "variant": variant.name,
        "lighting_normalized": variant.lighting_normalized,
        "purpose": "Texture Baker v3 direct pose-fitted selfie bake with iterative repair.",
        "privacy": "Private biometric runtime artifact. Do not commit generated textures/renders.",
        "output_dir": str(output_dir),
        "quality_report": str(quality_dir / "quality_report.json"),
        "reference_regions": references,
        "reference_skin_rgb": [float(value) for value in reference_skin],
        "settings": {
            "atlas_size": atlas_size,
            "image_size": image_size,
            "iterations": iterations,
            "min_score": min_score,
            "max_abs_yaw": max_abs_yaw,
            "splat_radius": splat_radius,
            "uv_mode": uv_mode,
            "camera_pass_weight": camera_pass_weight,
            "residual_strength": variant.residual_strength,
            "repair_strength": variant.repair_strength,
        },
        "used_frame_count": len(packets),
        "compare_frame_ids": [packet.frame.frame_id for packet in compare_packets],
        "frame_reports": packet_reports,
        "seed_frame_reports": seed_frame_reports,
        "iteration_outputs": iteration_outputs,
        "metrics": metrics,
        "selected_final_iteration": selected_final_iteration,
        "selected_final_metrics": metrics[selected_final_iteration] if metrics else None,
        "final_texture": str(final_texture_path),
        "front45_iteration_review_sheet": str(output_dir / "front45_iteration_review_sheet.png"),
        "fitted_camera_iteration_compare_sheet": str(output_dir / "fitted_camera_iteration_compare_sheet.png"),
        "limitations": [
            "Geometry is fixed; v3 only changes texture.",
            "Lighting-normalized variant optimizes stable avatar texture, not exact raw-photo relighting.",
            "Feature regions still use diagnostic eye overlay and simple lip/eye material handling.",
            "Region-aware inpainting avoids empty/broken texels but can still look flat where no reliable source exists.",
            "Final texture is the earliest clean-enough iteration, not always the last one, to avoid over-smoothing.",
        ],
    }
    (output_dir / "texture_baker_v3_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def make_person_variant_overview(manifests: list[dict[str, Any]], output_path: Path) -> None:
    tile_w = 620
    tile_h = 390
    width = tile_w * len(manifests)
    height = tile_h
    sheet = Image.new("RGB", (width, height), (28, 28, 28))
    draw = ImageDraw.Draw(sheet)
    for index, manifest in enumerate(manifests):
        x = index * tile_w
        image = Image.open(manifest["front45_iteration_review_sheet"]).convert("RGB")
        image.thumbnail((tile_w, tile_h - 70), Image.BILINEAR)
        sheet.paste(image, (x, 70))
        final_iteration = int(manifest.get("selected_final_iteration", len(manifest["metrics"]) - 1))
        final_metrics = manifest.get("selected_final_metrics") or manifest["metrics"][final_iteration]
        title = f"{PERSON_LABELS.get(manifest['person'], manifest['person'])} {manifest['variant']}"
        luma_text = f"{final_metrics['mean_abs_luma']:.1f}" if final_metrics.get("mean_abs_luma") is not None else "n/a"
        draw.text((x + 12, 12), title, fill=(245, 245, 245))
        draw.text(
            (x + 12, 36),
            f"final iter {final_iteration:02d} obs {final_metrics['observed_coverage']*100:.1f}% fill {final_metrics['filled_coverage']*100:.1f}% bad {final_metrics['bad_ratio']*100:.1f}% luma {luma_text}",
            fill=(195, 195, 195),
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Texture Baker v3 no-lighting and lighting-normalized experiments.")
    parser.add_argument("--private-root", type=Path, default=None)
    parser.add_argument("--person", action="append", default=None)
    parser.add_argument("--variant", action="append", choices=VARIANTS, default=None)
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument("--atlas-size", type=int, default=DEFAULT_ATLAS_SIZE)
    parser.add_argument("--image-size", type=int, default=DEFAULT_IMAGE_SIZE)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--min-score", type=float, default=0.62)
    parser.add_argument("--max-abs-yaw", type=float, default=58.0)
    parser.add_argument("--splat-radius", type=int, default=1)
    parser.add_argument("--uv-mode", default="flip_y")
    parser.add_argument("--camera-pass-weight", type=float, default=0.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    private_root = args.private_root or default_private_root()
    people = args.person or list(DEFAULT_PEOPLE)
    requested = args.variant or list(VARIANTS)
    configs = {
        "v3_no_lighting": VariantConfig(
            name="v3_no_lighting",
            lighting_normalized=False,
            residual_strength=0.30,
            repair_strength=1.0,
        ),
        "v3_lighting_normalized": VariantConfig(
            name="v3_lighting_normalized",
            lighting_normalized=True,
            residual_strength=0.26,
            repair_strength=1.0,
        ),
    }
    all_manifests = []
    for person in people:
        person_manifests = []
        for variant_name in requested:
            manifest = process_variant(
                private_root=private_root,
                person=person,
                variant=configs[variant_name],
                output_prefix=args.output_prefix,
                atlas_size=args.atlas_size,
                image_size=args.image_size,
                iterations=args.iterations,
                min_score=args.min_score,
                max_abs_yaw=args.max_abs_yaw,
                splat_radius=args.splat_radius,
                uv_mode=args.uv_mode,
                camera_pass_weight=args.camera_pass_weight,
            )
            person_manifests.append(manifest)
            all_manifests.append(manifest)
        if len(person_manifests) > 1:
            make_person_variant_overview(
                person_manifests,
                private_root / "output" / "_comparison" / f"{args.output_prefix}_{person}_variant_overview.png",
            )
    print(json.dumps(all_manifests, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
