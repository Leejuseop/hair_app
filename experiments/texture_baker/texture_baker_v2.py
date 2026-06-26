"""Camera-aware observed texture baker for private FLAME-topology frames.

Texture Baker v2 is still a research/diagnostic tool, but unlike the v1 UV-map
splat baker it uses fitted tracking meshes, checkpoint cameras, z-buffer
visibility, frame quality scores, segmentation masks, and per-frame color
normalization before writing a shared FLAME UV atlas.
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

from evidence_quality_report import (
    CENTRAL_FACE_LABELS,
    FACE_LABELS,
    OCCLUDER_LABELS,
    SKIN_REFERENCE_LABELS,
    analyze_person,
    bbox_from_mask,
    checkpoint_path_for_frame,
    dilate_binary_mask,
    find_tracking_dirs,
    load_frame_checkpoint,
    load_rgb,
    load_segmentation,
    tracking_mesh_path_for_frame,
    write_report,
)
from observed_texture_baker import fill_preview_holes, load_uv
from texture_baker_loader import default_private_root, load_person
from textured_mesh_preview import load_flame_masks, read_ply, resolve_flame_masks, resolve_uv_coords, resolve_valid_vertices


DEFAULT_PEOPLE = ("\uc8fc\uc12d", "\uc740\ucc44")
DEFAULT_OUTPUT_NAME = "observed_v2_camera_visibility_front45_preview"
SEGMENT_WEIGHTS = {
    2: 2.2,
    10: 2.0,
    12: 1.65,
    13: 1.65,
    7: 1.35,
    8: 1.35,
    6: 1.05,
    9: 1.05,
    4: 0.72,
    5: 0.72,
}
SIDE_FACE_LABELS = {4, 5}
MOUTH_LABELS = {12, 13}
EYE_REGION_LABELS = {6, 9}


def safe_bbox(points: np.ndarray) -> tuple[float, float, float, float] | None:
    finite = np.isfinite(points).all(axis=1)
    if not np.any(finite):
        return None
    pts = points[finite]
    return float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max())


def bbox_center_size(bbox: tuple[float, float, float, float]) -> tuple[np.ndarray, np.ndarray]:
    x0, y0, x1, y1 = bbox
    center = np.asarray([(x0 + x1) * 0.5, (y0 + y1) * 0.5], dtype=np.float32)
    size = np.asarray([max(x1 - x0, 1.0), max(y1 - y0, 1.0)], dtype=np.float32)
    return center, size


def mask_indices(masks: dict[str, np.ndarray], names: tuple[str, ...], vertex_count: int) -> np.ndarray:
    values: list[np.ndarray] = []
    for name in names:
        indices = masks.get(name)
        if indices is None:
            continue
        values.append(indices[(indices >= 0) & (indices < vertex_count)])
    if not values:
        return np.arange(vertex_count, dtype=np.int64)
    return np.unique(np.concatenate(values)).astype(np.int64)


def target_bbox_from_segmentation(segmentation: np.ndarray | None) -> tuple[float, float, float, float] | None:
    if segmentation is None:
        return None
    central = np.isin(segmentation, list(CENTRAL_FACE_LABELS))
    bbox = bbox_from_mask(central)
    if bbox is None:
        bbox = bbox_from_mask(np.isin(segmentation, list(FACE_LABELS)))
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    width = x1 - x0
    height = y1 - y0
    pad_x = int(width * 0.03)
    pad_y = int(height * 0.03)
    return (
        float(max(x0 - pad_x, 0)),
        float(max(y0 - pad_y, 0)),
        float(min(x1 + pad_x, segmentation.shape[1])),
        float(min(y1 + pad_y, segmentation.shape[0])),
    )


def project_tracking_vertices(
    vertices: np.ndarray,
    checkpoint: dict[str, Any],
    segmentation: np.ndarray | None,
    masks: dict[str, np.ndarray],
    image_size: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    camera = checkpoint["camera"]
    rotation = np.asarray(camera["R_base_0"], dtype=np.float32)[0]
    translation = np.asarray(camera["t_base_0"], dtype=np.float32)[0]
    focal = float(np.asarray(camera["fl"])[0, 0])
    principal = np.asarray(camera["pp"], dtype=np.float32)[0]

    camera_vertices = vertices @ rotation.T + translation
    z = camera_vertices[:, 2]
    z_safe = np.where(np.abs(z) < 1e-6, np.sign(z) * 1e-6 + 1e-6, z)
    x_ndc = (focal * (camera_vertices[:, 0] / z_safe)) + principal[0]
    y_ndc = (focal * (camera_vertices[:, 1] / z_safe)) + principal[1]
    points = np.stack(
        [
            (x_ndc + 1.0) * 0.5 * image_size,
            (1.0 - y_ndc) * 0.5 * image_size,
        ],
        axis=1,
    ).astype(np.float32)

    reference_indices = mask_indices(
        masks,
        ("face", "forehead", "nose", "lips"),
        vertices.shape[0],
    )
    projected_bbox = safe_bbox(points[reference_indices])
    target_bbox = target_bbox_from_segmentation(segmentation)
    calibration = {
        "mode": "camera_projection",
        "focal": focal,
        "principal_point": [float(principal[0]), float(principal[1])],
        "projected_bbox": list(projected_bbox) if projected_bbox is not None else None,
        "target_bbox": list(target_bbox) if target_bbox is not None else None,
        "scale_xy": [1.0, 1.0],
        "offset_xy": [0.0, 0.0],
    }
    if projected_bbox is not None and target_bbox is not None:
        projected_center, projected_size = bbox_center_size(projected_bbox)
        target_center, target_size = bbox_center_size(target_bbox)
        scale = target_size / np.maximum(projected_size, 1.0)
        scale = np.clip(scale, 0.55, 2.8).astype(np.float32)
        points = ((points - projected_center[None, :]) * scale[None, :]) + target_center[None, :]
        offset = target_center - (projected_center * scale)
        calibration["mode"] = "camera_projection_bbox_calibrated"
        calibration["scale_xy"] = [float(scale[0]), float(scale[1])]
        calibration["offset_xy"] = [float(offset[0]), float(offset[1])]
    return points, camera_vertices[:, 2].astype(np.float32), camera_vertices.astype(np.float32), calibration


def color_correct_rgb(
    rgb: np.ndarray,
    segmentation: np.ndarray | None,
    reference_skin_rgb: np.ndarray | None,
) -> tuple[np.ndarray, dict[str, Any]]:
    stats: dict[str, Any] = {"enabled": False}
    if segmentation is None or reference_skin_rgb is None:
        return rgb, stats
    skin_mask = np.isin(segmentation, list(SKIN_REFERENCE_LABELS))
    if int(skin_mask.sum()) < 80:
        stats["skipped_reason"] = "not_enough_skin_pixels"
        return rgb, stats

    current = np.median(rgb[skin_mask], axis=0)
    shift = np.clip(reference_skin_rgb - current, -32.0, 32.0)
    corrected = np.clip(rgb + shift[None, None, :], 0.0, 255.0).astype(np.float32)
    stats.update(
        {
            "enabled": True,
            "current_skin_rgb": [float(value) for value in current],
            "reference_skin_rgb": [float(value) for value in reference_skin_rgb],
            "shift_rgb": [float(value) for value in shift],
        }
    )
    return corrected, stats


def frame_keep_mask(
    rgb: np.ndarray,
    segmentation: np.ndarray | None,
    *,
    occlusion_margin_iterations: int,
    skin_chroma_threshold: float,
    skin_luma_threshold: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    if segmentation is None:
        return np.ones(rgb.shape[:2], dtype=bool), {"segmentation": False}
    valid = np.isin(segmentation, list(FACE_LABELS))

    if occlusion_margin_iterations > 0:
        margin = dilate_binary_mask(np.isin(segmentation, list(OCCLUDER_LABELS)), occlusion_margin_iterations)
        valid &= ~margin

    skin_mask = valid & np.isin(segmentation, list(SKIN_REFERENCE_LABELS))
    removed_color = 0
    if int(skin_mask.sum()) >= 80:
        skin_pixels = rgb[skin_mask]
        luma = (0.299 * rgb[..., 0]) + (0.587 * rgb[..., 1]) + (0.114 * rgb[..., 2])
        cb = rgb[..., 2] - luma
        cr = rgb[..., 0] - luma
        ref_luma = float(np.median((0.299 * skin_pixels[:, 0]) + (0.587 * skin_pixels[:, 1]) + (0.114 * skin_pixels[:, 2])))
        ref_cb = float(np.median(skin_pixels[:, 2] - ((0.299 * skin_pixels[:, 0]) + (0.587 * skin_pixels[:, 1]) + (0.114 * skin_pixels[:, 2]))))
        ref_cr = float(np.median(skin_pixels[:, 0] - ((0.299 * skin_pixels[:, 0]) + (0.587 * skin_pixels[:, 1]) + (0.114 * skin_pixels[:, 2]))))
        chroma_distance = np.sqrt((cb - ref_cb) ** 2 + (cr - ref_cr) ** 2)
        luma_distance = np.abs(luma - ref_luma)
        filter_labels = np.isin(segmentation, [2, 4, 5])
        color_outlier = valid & filter_labels & (
            (chroma_distance > skin_chroma_threshold) | (luma_distance > skin_luma_threshold)
        )
        removed_color = int(color_outlier.sum())
        valid &= ~color_outlier

    return valid, {
        "segmentation": True,
        "valid_pixels": int(valid.sum()),
        "removed_by_color": removed_color,
        "occlusion_margin_iterations": occlusion_margin_iterations,
    }


def compute_vertex_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    normals = np.zeros_like(vertices, dtype=np.float32)
    tri = vertices[faces]
    face_normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    np.add.at(normals, faces[:, 0], face_normals)
    np.add.at(normals, faces[:, 1], face_normals)
    np.add.at(normals, faces[:, 2], face_normals)
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    return normals / np.maximum(norms, 1e-8)


def triangle_area_2d(points: np.ndarray) -> float:
    a = points[1] - points[0]
    b = points[2] - points[0]
    return float(abs((a[0] * b[1]) - (a[1] * b[0])) * 0.5)


def update_atlas_samples(
    *,
    atlas_rgb_sum: np.ndarray,
    atlas_weight_sum: np.ndarray,
    atlas_best_rgb: np.ndarray,
    atlas_best_score: np.ndarray,
    atlas_source_map: np.ndarray,
    atlas_source_score: np.ndarray,
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
    weights = weights[positive].astype(np.float64)

    np.add.at(atlas_rgb_sum, (target_y, target_x), colors * weights[:, None])
    np.add.at(atlas_weight_sum, (target_y, target_x), weights)

    replace_source = weights > atlas_source_score[target_y, target_x]
    if np.any(replace_source):
        atlas_source_score[target_y[replace_source], target_x[replace_source]] = weights[replace_source]
        atlas_source_map[target_y[replace_source], target_x[replace_source]] = frame_index + 1

    replace_best = weights > atlas_best_score[target_y, target_x]
    if np.any(replace_best):
        atlas_best_score[target_y[replace_best], target_x[replace_best]] = weights[replace_best]
        atlas_best_rgb[target_y[replace_best], target_x[replace_best]] = colors[replace_best]
    return int(target_y.size)


def frame_pixel_score_map(
    *,
    segmentation: np.ndarray | None,
    valid: np.ndarray,
    quality: dict[str, Any],
    pass_weight: float,
) -> np.ndarray:
    height, width = valid.shape
    yy, xx = np.mgrid[0:height, 0:width]
    center_x = (width - 1) * 0.5
    center_y = (height - 1) * 0.5
    norm_x = (xx - center_x) / max(center_x, 1.0)
    norm_y = (yy - center_y) / max(center_y, 1.0)
    center_weight = np.exp(-((norm_x * norm_x) + (norm_y * norm_y)) / (2.0 * 0.58 * 0.58))

    frame_score = max(float(quality.get("overall_score", 0.0)), 0.0)
    yaw = quality.get("yaw_degrees")
    yaw_abs = abs(float(yaw)) if yaw is not None else 0.0
    frontal_weight = float(np.clip(1.0 - (yaw_abs / 72.0), 0.16, 1.0) ** 1.35)
    side_weight = float(np.clip(0.45 + (0.55 * min(yaw_abs / 58.0, 1.0)), 0.45, 1.0))

    score = pass_weight * frame_score * (0.35 + (0.65 * center_weight))
    score = score.astype(np.float32)

    if segmentation is not None:
        label_weight = np.ones_like(score, dtype=np.float32)
        for label, weight in SEGMENT_WEIGHTS.items():
            label_weight[segmentation == label] = weight
        score *= label_weight

        central = np.isin(segmentation, list(CENTRAL_FACE_LABELS))
        side = np.isin(segmentation, list(SIDE_FACE_LABELS))
        score[central] *= frontal_weight
        score[side] *= side_weight

        mouth_score = quality.get("mouth_closed_score")
        if mouth_score is not None:
            mouth = np.isin(segmentation, list(MOUTH_LABELS))
            score[mouth] *= 0.35 + (0.65 * float(np.clip(mouth_score, 0.0, 1.0)))

        eye_score = quality.get("eyes_open_score")
        if eye_score is not None:
            eyes = np.isin(segmentation, list(EYE_REGION_LABELS))
            score[eyes] *= 0.65 + (0.35 * float(np.clip(eye_score, 0.0, 1.0)))

    score[~valid] = 0.0
    return score


def accumulate_uv_correspondence(
    *,
    rgb: np.ndarray,
    uv_map: np.ndarray,
    segmentation: np.ndarray | None,
    keep_mask: np.ndarray,
    quality: dict[str, Any],
    atlas_rgb_sum: np.ndarray,
    atlas_weight_sum: np.ndarray,
    atlas_best_rgb: np.ndarray,
    atlas_best_score: np.ndarray,
    atlas_source_map: np.ndarray,
    atlas_source_score: np.ndarray,
    frame_index: int,
    splat_radius: int,
    pass_weight: float,
) -> dict[str, Any]:
    atlas_size = atlas_weight_sum.shape[0]
    valid = keep_mask & ((uv_map[..., 0] > 0) | (uv_map[..., 1] > 0))
    if not np.any(valid):
        return {"used_pixels": 0, "reason": "no_valid_uv_pixels"}

    score = frame_pixel_score_map(
        segmentation=segmentation,
        valid=valid,
        quality=quality,
        pass_weight=pass_weight,
    )

    u = uv_map[..., 0].astype(np.float32) / 255.0
    v = uv_map[..., 1].astype(np.float32) / 255.0
    tex_x = np.clip(np.rint(u * (atlas_size - 1)).astype(np.int32), 0, atlas_size - 1)
    tex_y = np.clip(np.rint(v * (atlas_size - 1)).astype(np.int32), 0, atlas_size - 1)

    base_y = tex_y[valid]
    base_x = tex_x[valid]
    colors = rgb[valid]
    weights = score[valid].astype(np.float64)

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
            written += update_atlas_samples(
                atlas_rgb_sum=atlas_rgb_sum,
                atlas_weight_sum=atlas_weight_sum,
                atlas_best_rgb=atlas_best_rgb,
                atlas_best_score=atlas_best_score,
                atlas_source_map=atlas_source_map,
                atlas_source_score=atlas_source_score,
                target_y=yy[ok],
                target_x=xx[ok],
                colors=colors[ok],
                weights=weights[ok],
                frame_index=frame_index,
            )

    return {
        "used_pixels": int(valid.sum()),
        "written_samples": written,
        "uv_min": [int(uv_map[..., 0][valid].min()), int(uv_map[..., 1][valid].min())],
        "uv_max": [int(uv_map[..., 0][valid].max()), int(uv_map[..., 1][valid].max())],
    }


def rasterize_zbuffer(
    faces: np.ndarray,
    points: np.ndarray,
    depth: np.ndarray,
    image_size: int,
) -> np.ndarray:
    zbuffer = np.full((image_size, image_size), -np.inf, dtype=np.float32)
    for face in faces:
        pts = points[face]
        if not np.isfinite(pts).all():
            continue
        min_x = max(int(np.floor(pts[:, 0].min())), 0)
        max_x = min(int(np.ceil(pts[:, 0].max())), image_size - 1)
        min_y = max(int(np.floor(pts[:, 1].min())), 0)
        max_y = min(int(np.ceil(pts[:, 1].max())), image_size - 1)
        if max_x < min_x or max_y < min_y:
            continue

        p0, p1, p2 = pts.astype(np.float32)
        area = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
        if abs(float(area)) < 1e-8:
            continue
        xs = np.arange(min_x, max_x + 1, dtype=np.float32)
        ys = np.arange(min_y, max_y + 1, dtype=np.float32)
        grid_x, grid_y = np.meshgrid(xs, ys)
        w0 = ((p1[1] - p2[1]) * (grid_x - p2[0]) + (p2[0] - p1[0]) * (grid_y - p2[1])) / area
        w1 = ((p2[1] - p0[1]) * (grid_x - p2[0]) + (p0[0] - p2[0]) * (grid_y - p2[1])) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not np.any(inside):
            continue
        interpolated_depth = (w0 * depth[face[0]]) + (w1 * depth[face[1]]) + (w2 * depth[face[2]])
        patch = zbuffer[min_y : max_y + 1, min_x : max_x + 1]
        update = inside & (interpolated_depth > patch)
        patch[update] = interpolated_depth[update]
    return zbuffer


def accumulate_visible_triangles(
    *,
    rgb: np.ndarray,
    segmentation: np.ndarray | None,
    keep_mask: np.ndarray,
    faces: np.ndarray,
    uv_coords: np.ndarray,
    valid_vertex_mask: np.ndarray,
    points: np.ndarray,
    depth: np.ndarray,
    camera_vertices: np.ndarray,
    image_size: int,
    atlas_rgb_sum: np.ndarray,
    atlas_weight_sum: np.ndarray,
    atlas_best_rgb: np.ndarray,
    atlas_best_score: np.ndarray,
    atlas_source_map: np.ndarray,
    atlas_source_score: np.ndarray,
    frame_index: int,
    frame_score: float,
    zbuffer: np.ndarray,
    splat_radius: int,
    pass_weight: float,
) -> dict[str, Any]:
    atlas_size = atlas_weight_sum.shape[0]
    normals = compute_vertex_normals(camera_vertices, faces)
    used_pixels = 0
    used_triangles = 0

    for face in faces:
        if not np.all(valid_vertex_mask[face]):
            continue
        pts = points[face]
        if not np.isfinite(pts).all():
            continue
        min_x = max(int(np.floor(pts[:, 0].min())), 0)
        max_x = min(int(np.ceil(pts[:, 0].max())), image_size - 1)
        min_y = max(int(np.floor(pts[:, 1].min())), 0)
        max_y = min(int(np.ceil(pts[:, 1].max())), image_size - 1)
        if max_x < min_x or max_y < min_y:
            continue

        p0, p1, p2 = pts.astype(np.float32)
        area = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
        if abs(float(area)) < 1e-8:
            continue
        xs = np.arange(min_x, max_x + 1, dtype=np.float32)
        ys = np.arange(min_y, max_y + 1, dtype=np.float32)
        grid_x, grid_y = np.meshgrid(xs, ys)
        w0 = ((p1[1] - p2[1]) * (grid_x - p2[0]) + (p2[0] - p1[0]) * (grid_y - p2[1])) / area
        w1 = ((p2[1] - p0[1]) * (grid_x - p2[0]) + (p0[0] - p2[0]) * (grid_y - p2[1])) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not np.any(inside):
            continue

        interpolated_depth = (w0 * depth[face[0]]) + (w1 * depth[face[1]]) + (w2 * depth[face[2]])
        visible = inside & (np.abs(interpolated_depth - zbuffer[min_y : max_y + 1, min_x : max_x + 1]) <= 1e-4)
        if not np.any(visible):
            continue
        pixel_x = grid_x.astype(np.int32)
        pixel_y = grid_y.astype(np.int32)
        valid_pixels = visible & keep_mask[pixel_y, pixel_x]
        if not np.any(valid_pixels):
            continue

        bary = np.stack([w0, w1, w2], axis=-1)
        uv = (
            (bary[..., 0:1] * uv_coords[face[0]])
            + (bary[..., 1:2] * uv_coords[face[1]])
            + (bary[..., 2:3] * uv_coords[face[2]])
        )
        tex_x = np.clip(np.rint(uv[..., 0] * (atlas_size - 1)).astype(np.int32), 0, atlas_size - 1)
        tex_y = np.clip(np.rint((1.0 - uv[..., 1]) * (atlas_size - 1)).astype(np.int32), 0, atlas_size - 1)

        sampled_rgb = rgb[pixel_y, pixel_x]
        if segmentation is not None:
            labels = segmentation[pixel_y, pixel_x]
            label_weight = np.ones_like(w0, dtype=np.float32)
            for label, weight in SEGMENT_WEIGHTS.items():
                label_weight[labels == label] = weight
        else:
            label_weight = np.ones_like(w0, dtype=np.float32)

        face_normal = normals[face].mean(axis=0)
        view_weight = float(np.clip(abs(face_normal[2]), 0.08, 1.0))
        uv_area = max(triangle_area_2d(uv_coords[face]), 1e-8)
        image_area = max(triangle_area_2d(pts), 1e-6)
        texel_density = float(np.clip(np.sqrt(image_area / (uv_area * atlas_size * atlas_size)), 0.25, 2.0))
        scores = frame_score * view_weight * texel_density * label_weight

        mask = valid_pixels
        used_pixels += int(mask.sum())
        used_triangles += 1
        base_y = tex_y[mask]
        base_x = tex_x[mask]
        colors = sampled_rgb[mask]
        weights = scores[mask].astype(np.float64)
        positive = weights > 0
        if not np.any(positive):
            continue
        base_y = base_y[positive]
        base_x = base_x[positive]
        colors = colors[positive]
        weights = weights[positive]

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
                update_atlas_samples(
                    atlas_rgb_sum=atlas_rgb_sum,
                    atlas_weight_sum=atlas_weight_sum,
                    atlas_best_rgb=atlas_best_rgb,
                    atlas_best_score=atlas_best_score,
                    atlas_source_map=atlas_source_map,
                    atlas_source_score=atlas_source_score,
                    target_y=yy[ok],
                    target_x=xx[ok],
                    colors=colors[ok],
                    weights=weights[ok] * pass_weight,
                    frame_index=frame_index,
                )

    return {"used_pixels": used_pixels, "used_triangles": used_triangles}


def estimate_observed_skin(observed: np.ndarray) -> list[float]:
    nonblack = observed[np.sum(observed, axis=2) > 24]
    if nonblack.size == 0:
        return [168.0, 132.0, 118.0]
    return [float(value) for value in np.median(nonblack.astype(np.float32), axis=0)]


def write_outputs(
    output_dir: Path,
    manifest: dict[str, Any],
    atlas_rgb_sum: np.ndarray,
    atlas_weight_sum: np.ndarray,
    atlas_best_rgb: np.ndarray,
    atlas_best_score: np.ndarray,
    atlas_source_map: np.ndarray,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    covered = atlas_weight_sum > 0
    best_covered = atlas_best_score > 0
    observed = np.zeros_like(atlas_rgb_sum, dtype=np.uint8)
    observed[covered] = np.clip(atlas_rgb_sum[covered] / atlas_weight_sum[covered, None], 0, 255).astype(np.uint8)
    observed[best_covered] = np.clip(atlas_best_rgb[best_covered], 0, 255).astype(np.uint8)
    confidence = np.zeros_like(atlas_weight_sum, dtype=np.uint8)
    max_weight = float(atlas_weight_sum.max()) if np.any(covered) else 1.0
    confidence[covered] = np.clip((atlas_weight_sum[covered] / max_weight) * 255.0, 0, 255).astype(np.uint8)
    source_view = np.zeros_like(atlas_source_map, dtype=np.uint8)
    if atlas_source_map.max() > 0:
        source_view = np.clip((atlas_source_map.astype(np.float32) / atlas_source_map.max()) * 255.0, 0, 255).astype(np.uint8)

    Image.fromarray(observed, mode="RGB").save(output_dir / "base_color_observed.png")
    if int(manifest["preview_fill_iterations"]) > 0:
        preview = fill_preview_holes(
            observed,
            covered,
            int(manifest["preview_fill_iterations"]),
            int(manifest["preview_fill_min_neighbors"]),
        )
        Image.fromarray(preview, mode="RGB").save(output_dir / "base_color_preview_filled.png")
        visual_completed = fill_preview_holes(
            observed,
            covered,
            max(int(manifest["preview_fill_iterations"]) * 4, 40),
            1,
        )
        fallback_color = np.asarray(manifest.get("reference_skin_rgb") or estimate_observed_skin(observed), dtype=np.float32)
        still_empty = np.sum(visual_completed, axis=2) < 8
        visual_completed[still_empty] = np.clip(fallback_color, 0, 255).astype(np.uint8)
        Image.fromarray(visual_completed, mode="RGB").save(output_dir / "base_color_visual_completed.png")
    Image.fromarray(np.clip(atlas_weight_sum, 0, 255).astype(np.uint8), mode="L").save(output_dir / "coverage.png")
    Image.fromarray(confidence, mode="L").save(output_dir / "confidence.png")
    Image.fromarray(source_view, mode="L").save(output_dir / "source_view_map.png")

    manifest["coverage_summary"] = {
        "covered_texels": int(covered.sum()),
        "total_texels": int(covered.size),
        "covered_fraction": float(covered.mean()),
        "max_weight": max_weight,
    }
    manifest["outputs"] = {
        "base_color_observed": str(output_dir / "base_color_observed.png"),
        "base_color_preview_filled": str(output_dir / "base_color_preview_filled.png"),
        "base_color_visual_completed": str(output_dir / "base_color_visual_completed.png"),
        "coverage": str(output_dir / "coverage.png"),
        "confidence": str(output_dir / "confidence.png"),
        "source_view_map": str(output_dir / "source_view_map.png"),
        "texture_manifest": str(output_dir / "texture_manifest.json"),
    }
    (output_dir / "texture_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def bake_person(
    *,
    person: str,
    private_root: Path,
    output_name: str,
    atlas_size: int,
    image_size: int,
    min_score: float,
    max_abs_yaw: float,
    splat_radius: int,
    preview_fill_iterations: int,
    preview_fill_min_neighbors: int,
    occlusion_margin_iterations: int,
    skin_chroma_threshold: float,
    skin_luma_threshold: float,
    camera_pass_weight: float,
    uv_pass_weight: float,
) -> dict[str, Any]:
    bundle = load_person(person, private_root=private_root)
    quality_report = analyze_person(person, private_root, min_score)
    quality_dir = private_root / "output" / person / "texture_baker" / "quality_v2"
    write_report(quality_report, quality_dir)

    frame_quality = {frame["frame_id"]: frame for frame in quality_report["frames"]}
    tracking_dirs = find_tracking_dirs(Path(bundle.output_dir))
    uv_coords = np.load(resolve_uv_coords(private_root, None)).astype(np.float32)
    valid_vertices_path = resolve_valid_vertices(private_root, None)
    valid_vertices = np.load(valid_vertices_path) if valid_vertices_path is not None else np.arange(uv_coords.shape[0])
    valid_vertex_mask = np.zeros((uv_coords.shape[0],), dtype=bool)
    valid_vertex_mask[valid_vertices[(valid_vertices >= 0) & (valid_vertices < uv_coords.shape[0])]] = True
    flame_masks = load_flame_masks(resolve_flame_masks(private_root, None))

    skin_values = []
    skin_weights = []
    for frame in quality_report["frames"]:
        if frame["skin_median_rgb"] is None:
            continue
        if abs(frame["yaw_degrees"] or 0.0) > max_abs_yaw:
            continue
        weight = max(float(frame["overall_score"]), 0.0)
        skin_values.append(np.asarray(frame["skin_median_rgb"], dtype=np.float32))
        skin_weights.append(weight)
    reference_skin = None
    if skin_values:
        weights = np.asarray(skin_weights, dtype=np.float32)
        values = np.stack(skin_values, axis=0)
        reference_skin = np.average(values, axis=0, weights=np.maximum(weights, 1e-4))

    atlas_rgb_sum = np.zeros((atlas_size, atlas_size, 3), dtype=np.float64)
    atlas_weight_sum = np.zeros((atlas_size, atlas_size), dtype=np.float64)
    atlas_best_rgb = np.zeros((atlas_size, atlas_size, 3), dtype=np.float32)
    atlas_best_score = np.full((atlas_size, atlas_size), -np.inf, dtype=np.float64)
    atlas_source_map = np.zeros((atlas_size, atlas_size), dtype=np.int32)
    atlas_source_score = np.full((atlas_size, atlas_size), -np.inf, dtype=np.float64)

    frame_reports = []
    for frame_index, frame in enumerate(bundle.frames):
        quality = frame_quality.get(frame.frame_id)
        if quality is None:
            continue
        yaw = quality["yaw_degrees"]
        if not quality["selected_for_bake"] or (yaw is not None and abs(float(yaw)) > max_abs_yaw):
            frame_reports.append({"frame_id": frame.frame_id, "used": False, "quality": quality, "reason": "quality_or_yaw_filter"})
            continue

        checkpoint_path = checkpoint_path_for_frame(tracking_dirs, frame.frame_id)
        mesh_path = tracking_mesh_path_for_frame(tracking_dirs, frame.frame_id)
        checkpoint = load_frame_checkpoint(checkpoint_path, frame.frame_id)
        if checkpoint is None or mesh_path is None:
            frame_reports.append({"frame_id": frame.frame_id, "used": False, "quality": quality, "reason": "missing_tracking"})
            continue

        rgb = load_rgb(Path(frame.crop))
        if rgb.shape[0] != image_size or rgb.shape[1] != image_size:
            rgb = np.asarray(Image.open(frame.crop).convert("RGB").resize((image_size, image_size)), dtype=np.float32)
        segmentation = load_segmentation(frame)
        if segmentation is not None and segmentation.shape != rgb.shape[:2]:
            segmentation = np.asarray(Image.fromarray(segmentation, mode="L").resize((image_size, image_size), Image.NEAREST), dtype=np.uint8)
        uv_map = None
        if frame.uv_map is not None and Path(frame.uv_map).exists():
            uv_map = load_uv(Path(frame.uv_map))
            if uv_map.shape[:2] != rgb.shape[:2]:
                uv_map = np.asarray(
                    Image.open(frame.uv_map).convert("RGB").resize((image_size, image_size), Image.NEAREST),
                    dtype=np.uint8,
                )

        corrected_rgb, color_stats = color_correct_rgb(rgb, segmentation, reference_skin)
        keep_mask, keep_stats = frame_keep_mask(
            corrected_rgb,
            segmentation,
            occlusion_margin_iterations=occlusion_margin_iterations,
            skin_chroma_threshold=skin_chroma_threshold,
            skin_luma_threshold=skin_luma_threshold,
        )
        mesh = read_ply(mesh_path)
        if mesh.vertices.shape[0] != uv_coords.shape[0]:
            frame_reports.append({"frame_id": frame.frame_id, "used": False, "quality": quality, "reason": "vertex_count_mismatch"})
            continue

        points, depth, camera_vertices, calibration = project_tracking_vertices(
            mesh.vertices,
            checkpoint,
            segmentation,
            flame_masks,
            image_size,
        )
        zbuffer = rasterize_zbuffer(mesh.faces, points, depth, image_size)
        accum_stats = accumulate_visible_triangles(
            rgb=corrected_rgb,
            segmentation=segmentation,
            keep_mask=keep_mask,
            faces=mesh.faces,
            uv_coords=uv_coords,
            valid_vertex_mask=valid_vertex_mask,
            points=points,
            depth=depth,
            camera_vertices=camera_vertices,
            image_size=image_size,
            atlas_rgb_sum=atlas_rgb_sum,
            atlas_weight_sum=atlas_weight_sum,
            atlas_best_rgb=atlas_best_rgb,
            atlas_best_score=atlas_best_score,
            atlas_source_map=atlas_source_map,
            atlas_source_score=atlas_source_score,
            frame_index=frame_index,
            frame_score=float(quality["overall_score"]),
            zbuffer=zbuffer,
            splat_radius=splat_radius,
            pass_weight=camera_pass_weight,
        )
        uv_stats = {"used_pixels": 0, "reason": "missing_uv_map"}
        if uv_map is not None:
            uv_stats = accumulate_uv_correspondence(
                rgb=corrected_rgb,
                uv_map=uv_map,
                segmentation=segmentation,
                keep_mask=keep_mask,
                quality=quality,
                atlas_rgb_sum=atlas_rgb_sum,
                atlas_weight_sum=atlas_weight_sum,
                atlas_best_rgb=atlas_best_rgb,
                atlas_best_score=atlas_best_score,
                atlas_source_map=atlas_source_map,
                atlas_source_score=atlas_source_score,
                frame_index=frame_index,
                splat_radius=splat_radius,
                pass_weight=uv_pass_weight,
            )
        frame_reports.append(
            {
                "frame_id": frame.frame_id,
                "used": True,
                "quality": quality,
                "checkpoint": str(checkpoint_path),
                "tracking_mesh": str(mesh_path),
                "projection_calibration": calibration,
                "color_correction": color_stats,
                "keep_mask": keep_stats,
                "camera_projection": accum_stats,
                "uv_correspondence": uv_stats,
            }
        )

    output_dir = private_root / "output" / person / "texture_baker" / output_name
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "person": person,
        "purpose": "Texture Baker v2 camera-aware observed-photo FLAME UV atlas.",
        "privacy": "Private biometric runtime artifact. Keep generated textures/renders out of Git.",
        "private_root": str(private_root),
        "output_dir": str(output_dir),
        "quality_report": str(quality_dir / "quality_report.json"),
        "tracking_dirs": asdict(tracking_dirs),
        "atlas_size": atlas_size,
        "image_size": image_size,
        "min_score": min_score,
        "max_abs_yaw": max_abs_yaw,
        "splat_radius": splat_radius,
        "preview_fill_iterations": preview_fill_iterations,
        "preview_fill_min_neighbors": preview_fill_min_neighbors,
        "occlusion_margin_iterations": occlusion_margin_iterations,
        "skin_chroma_threshold": skin_chroma_threshold,
        "skin_luma_threshold": skin_luma_threshold,
        "camera_pass_weight": camera_pass_weight,
        "uv_pass_weight": uv_pass_weight,
        "output_policy": "best_sample_over_weighted_average",
        "reference_skin_rgb": [float(value) for value in reference_skin] if reference_skin is not None else None,
        "valid_vertices": str(valid_vertices_path) if valid_vertices_path is not None else None,
        "frame_reports": frame_reports,
        "limitations": [
            "Camera projection is calibrated to segmentation bboxes because Pixel3DMM checkpoint cameras are stored in the tracker crop coordinate system.",
            "This is still an observed-photo diagnostic texture, not final skin completion.",
            "Hybrid UV-correspondence pass is intentionally used to preserve face details while fitted camera projection remains a visibility diagnostic/fill source.",
            "Per-user render-to-selfie optimization is intentionally not included in v2 bake.",
        ],
    }
    write_outputs(output_dir, manifest, atlas_rgb_sum, atlas_weight_sum, atlas_best_rgb, atlas_best_score, atlas_source_map)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bake Texture Baker v2 camera-aware observed atlases.")
    parser.add_argument("--private-root", type=Path, default=None)
    parser.add_argument("--person", action="append", default=None)
    parser.add_argument("--output-name", default=DEFAULT_OUTPUT_NAME)
    parser.add_argument("--atlas-size", type=int, default=512)
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--min-score", type=float, default=0.48)
    parser.add_argument("--max-abs-yaw", type=float, default=65.0)
    parser.add_argument("--splat-radius", type=int, default=1)
    parser.add_argument("--preview-fill-iterations", type=int, default=10)
    parser.add_argument("--preview-fill-min-neighbors", type=int, default=5)
    parser.add_argument("--occlusion-margin-iterations", type=int, default=5)
    parser.add_argument("--skin-chroma-threshold", type=float, default=34.0)
    parser.add_argument("--skin-luma-threshold", type=float, default=58.0)
    parser.add_argument("--camera-pass-weight", type=float, default=0.55)
    parser.add_argument("--uv-pass-weight", type=float, default=3.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    private_root = args.private_root or default_private_root()
    people = args.person or list(DEFAULT_PEOPLE)
    manifests = [
        bake_person(
            person=person,
            private_root=private_root,
            output_name=args.output_name,
            atlas_size=args.atlas_size,
            image_size=args.image_size,
            min_score=args.min_score,
            max_abs_yaw=args.max_abs_yaw,
            splat_radius=args.splat_radius,
            preview_fill_iterations=args.preview_fill_iterations,
            preview_fill_min_neighbors=args.preview_fill_min_neighbors,
            occlusion_margin_iterations=args.occlusion_margin_iterations,
            skin_chroma_threshold=args.skin_chroma_threshold,
            skin_luma_threshold=args.skin_luma_threshold,
            camera_pass_weight=args.camera_pass_weight,
            uv_pass_weight=args.uv_pass_weight,
        )
        for person in people
    ]
    print(
        json.dumps(
            {
                "private_root": str(private_root),
                "people": [
                    {
                        "person": manifest["person"],
                        "output_dir": manifest["output_dir"],
                        "covered_fraction": manifest["coverage_summary"]["covered_fraction"],
                        "covered_texels": manifest["coverage_summary"]["covered_texels"],
                    }
                    for manifest in manifests
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
