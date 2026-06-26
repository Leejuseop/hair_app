"""Compare cleanup textures against fitted-camera crops and apply a weak residual correction.

All source photos, masks, renders, and optimized textures are private runtime
artifacts written under the private Drive root. This script only belongs in Git
as reproducible pipeline code.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from evidence_quality_report import (
    CENTRAL_FACE_LABELS,
    analyze_person,
    checkpoint_path_for_frame,
    find_tracking_dirs,
    load_frame_checkpoint,
    load_segmentation,
    tracking_mesh_path_for_frame,
)
from texture_baker_loader import FrameEvidence, default_private_root, load_person
from texture_baker_v2 import project_tracking_vertices
from textured_mesh_preview import (
    apply_uv_mode,
    build_material_vertex_colors,
    draw_eye_overlays,
    estimate_skin_color,
    load_flame_masks,
    rasterize_triangle,
    read_ply,
    resolve_flame_masks,
    resolve_uv_coords,
    sample_texture,
    texture_path_for_run,
)


DEFAULT_PEOPLE = ("\uc8fc\uc12d", "\uc740\ucc44")
DEFAULT_TEXTURE_NAME = "observed_v2_camera_visibility_front45_preview"
DEFAULT_OUTPUT_NAME = "fitted_camera_selfie_compare_v1"
DEFAULT_IMAGE_SIZE = 512
SKIN_METRIC_LABELS = tuple(sorted(CENTRAL_FACE_LABELS))
PERSON_LABELS = {
    "\uc8fc\uc12d": "Juseop",
    "\uc740\ucc44": "Eunchae",
}


@dataclass(frozen=True)
class FrameRender:
    frame_id: str
    quality: dict[str, Any]
    crop: np.ndarray
    segmentation: np.ndarray | None
    mesh: Any
    points: np.ndarray
    depth: np.ndarray
    zbuffer: np.ndarray
    render: np.ndarray
    foreground: np.ndarray
    metric_mask: np.ndarray
    calibration: dict[str, Any]


def as_uint8_rgb(image: np.ndarray) -> np.ndarray:
    return np.clip(image, 0, 255).astype(np.uint8)


def load_crop(path: Path, image_size: int) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    if image.size != (image_size, image_size):
        image = image.resize((image_size, image_size), Image.BILINEAR)
    return np.asarray(image, dtype=np.uint8)


def resize_segmentation(segmentation: np.ndarray | None, image_size: int) -> np.ndarray | None:
    if segmentation is None:
        return None
    if segmentation.shape == (image_size, image_size):
        return segmentation
    image = Image.fromarray(segmentation.astype(np.uint8), mode="L")
    return np.asarray(image.resize((image_size, image_size), Image.NEAREST), dtype=np.uint8)


def mask_for_metrics(segmentation: np.ndarray | None, foreground: np.ndarray) -> np.ndarray:
    if segmentation is None:
        return foreground
    face_mask = np.isin(segmentation, SKIN_METRIC_LABELS)
    mask = foreground & face_mask
    if int(mask.sum()) < 300:
        return foreground & (segmentation > 0)
    return mask


def color_match_to_crop(
    *,
    render: np.ndarray,
    crop: np.ndarray,
    foreground: np.ndarray,
    metric_mask: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    if int(metric_mask.sum()) < 300:
        return render.copy(), {"enabled": False, "reason": "not_enough_metric_pixels"}

    source = crop[metric_mask].astype(np.float32)
    target = render[metric_mask].astype(np.float32)
    source_mean = np.median(source, axis=0)
    target_mean = np.median(target, axis=0)
    source_std = np.std(source, axis=0)
    target_std = np.maximum(np.std(target, axis=0), 1.0)
    scale = np.clip(source_std / target_std, 0.88, 1.18)
    shift = np.clip(source_mean - (target_mean * scale), -30.0, 30.0)

    matched = render.astype(np.float32, copy=True)
    matched[foreground] = matched[foreground] * scale[None, :] + shift[None, :]
    return as_uint8_rgb(matched), {
        "enabled": True,
        "source_mean_rgb": [float(value) for value in source_mean],
        "render_mean_rgb": [float(value) for value in target_mean],
        "source_std_rgb": [float(value) for value in source_std],
        "render_std_rgb": [float(value) for value in target_std],
        "scale_rgb": [float(value) for value in scale],
        "shift_rgb": [float(value) for value in shift],
        "metric_pixels": int(metric_mask.sum()),
    }


def error_metrics(crop: np.ndarray, render: np.ndarray, mask: np.ndarray) -> dict[str, Any]:
    if int(mask.sum()) < 1:
        return {"pixels": 0, "mean_abs_rgb": None, "mean_abs_luma": None, "p90_abs_luma": None}
    diff = np.abs(crop.astype(np.float32) - render.astype(np.float32))
    masked = diff[mask]
    luma = (0.299 * masked[:, 0]) + (0.587 * masked[:, 1]) + (0.114 * masked[:, 2])
    return {
        "pixels": int(mask.sum()),
        "mean_abs_rgb": [float(value) for value in np.mean(masked, axis=0)],
        "mean_abs_luma": float(np.mean(luma)),
        "p90_abs_luma": float(np.percentile(luma, 90)),
    }


def make_diff_image(crop: np.ndarray, render: np.ndarray, mask: np.ndarray) -> np.ndarray:
    diff = np.abs(crop.astype(np.float32) - render.astype(np.float32))
    diff_rgb = np.clip(diff * 2.4, 0, 255).astype(np.uint8)
    output = np.full_like(diff_rgb, 18)
    output[mask] = diff_rgb[mask]
    outline = Image.fromarray((mask.astype(np.uint8) * 255), mode="L").filter(ImageFilter.GaussianBlur(1.2))
    outline_mask = np.asarray(outline, dtype=np.uint8) > 8
    output[outline_mask & ~mask] = (64, 64, 64)
    return output


def render_fitted_frame(
    *,
    crop: np.ndarray,
    segmentation: np.ndarray | None,
    mesh: Any,
    checkpoint: dict[str, Any],
    flame_masks: dict[str, np.ndarray],
    uv_coords: np.ndarray,
    texture: np.ndarray,
    confidence: np.ndarray | None,
    material_vertex_colors: np.ndarray | None,
    image_size: int,
    uv_mode: str,
    eye_overlay: bool,
    fallback_confidence_threshold: int,
    projection_flip_y: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    points, depth, _camera_vertices, calibration = project_tracking_vertices(
        mesh.vertices,
        checkpoint,
        segmentation,
        flame_masks,
        image_size,
    )
    if projection_flip_y:
        points = points.copy()
        points[:, 1] = (image_size - 1) - points[:, 1]
        calibration = {**calibration, "projection_flip_y": True}
    else:
        calibration = {**calibration, "projection_flip_y": False}
    image = np.full((image_size, image_size, 3), 18, dtype=np.uint8)
    zbuffer = np.full((image_size, image_size), -np.inf, dtype=np.float32)
    uv = apply_uv_mode(uv_coords, uv_mode)

    for face in mesh.faces:
        fallback_color = None
        if material_vertex_colors is not None:
            fallback_color = np.rint(material_vertex_colors[face].mean(axis=0)).astype(np.uint8)
        rasterize_triangle(
            image=image,
            zbuffer=zbuffer,
            texture=texture,
            points=points[face],
            depth=depth[face],
            uv=uv[face],
            depth_mode="max",
            fallback_color=fallback_color,
            fallback_dark_threshold=28,
            confidence=confidence,
            fallback_confidence_threshold=fallback_confidence_threshold,
        )

    if eye_overlay:
        draw_eye_overlays(image, zbuffer, points, depth, flame_masks, "max")

    foreground = np.isfinite(zbuffer)
    metric_mask = mask_for_metrics(segmentation, foreground)
    return image, points, depth, zbuffer, {
        **calibration,
        "foreground_pixels": int(foreground.sum()),
        "metric_pixels": int(metric_mask.sum()),
    }


def prepare_frame_render(
    *,
    frame: FrameEvidence,
    quality: dict[str, Any],
    tracking_dirs: Any,
    flame_masks: dict[str, np.ndarray],
    uv_coords: np.ndarray,
    texture: np.ndarray,
    confidence: np.ndarray | None,
    material_vertex_colors: np.ndarray | None,
    image_size: int,
    uv_mode: str,
    eye_overlay: bool,
    fallback_confidence_threshold: int,
    projection_flip_y: bool,
) -> FrameRender | None:
    checkpoint = load_frame_checkpoint(checkpoint_path_for_frame(tracking_dirs, frame.frame_id), frame.frame_id)
    mesh_path = tracking_mesh_path_for_frame(tracking_dirs, frame.frame_id)
    if checkpoint is None or mesh_path is None:
        return None

    crop = load_crop(Path(frame.crop), image_size)
    segmentation = resize_segmentation(load_segmentation(frame), image_size)
    mesh = read_ply(mesh_path)
    if mesh.vertices.shape[0] != uv_coords.shape[0]:
        return None

    render, points, depth, zbuffer, calibration = render_fitted_frame(
        crop=crop,
        segmentation=segmentation,
        mesh=mesh,
        checkpoint=checkpoint,
        flame_masks=flame_masks,
        uv_coords=uv_coords,
        texture=texture,
        confidence=confidence,
        material_vertex_colors=material_vertex_colors,
        image_size=image_size,
        uv_mode=uv_mode,
        eye_overlay=eye_overlay,
        fallback_confidence_threshold=fallback_confidence_threshold,
        projection_flip_y=projection_flip_y,
    )
    foreground = np.isfinite(zbuffer)
    metric_mask = mask_for_metrics(segmentation, foreground)
    return FrameRender(
        frame_id=frame.frame_id,
        quality=quality,
        crop=crop,
        segmentation=segmentation,
        mesh=mesh,
        points=points,
        depth=depth,
        zbuffer=zbuffer,
        render=render,
        foreground=foreground,
        metric_mask=metric_mask,
        calibration=calibration,
    )


def accumulate_residual(
    *,
    frame_render: FrameRender,
    uv_coords: np.ndarray,
    uv_mode: str,
    residual_sum: np.ndarray,
    residual_weight: np.ndarray,
    splat_radius: int,
) -> dict[str, Any]:
    image_size = frame_render.crop.shape[0]
    atlas_size = residual_weight.shape[0]
    uv = apply_uv_mode(uv_coords, uv_mode)
    sample_mask = frame_render.metric_mask
    residual = frame_render.crop.astype(np.float32) - frame_render.render.astype(np.float32)
    written = 0

    for face in frame_render.mesh.faces:
        pts = frame_render.points[face]
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

        interpolated_depth = (
            w0 * frame_render.depth[face[0]]
            + w1 * frame_render.depth[face[1]]
            + w2 * frame_render.depth[face[2]]
        )
        zpatch = frame_render.zbuffer[min_y : max_y + 1, min_x : max_x + 1]
        visible = inside & (np.abs(interpolated_depth - zpatch) <= 1e-4)
        pixel_x = grid_x.astype(np.int32)
        pixel_y = grid_y.astype(np.int32)
        valid = visible & sample_mask[pixel_y, pixel_x]
        if not np.any(valid):
            continue

        bary = np.stack([w0, w1, w2], axis=-1)
        uv_grid = (
            (bary[..., 0:1] * uv[face[0]])
            + (bary[..., 1:2] * uv[face[1]])
            + (bary[..., 2:3] * uv[face[2]])
        )
        tex_x = np.clip(np.rint(uv_grid[..., 0] * (atlas_size - 1)).astype(np.int32), 0, atlas_size - 1)
        tex_y = np.clip(np.rint(uv_grid[..., 1] * (atlas_size - 1)).astype(np.int32), 0, atlas_size - 1)
        base_x = tex_x[valid]
        base_y = tex_y[valid]
        values = residual[pixel_y[valid], pixel_x[valid]]
        weights = np.full((values.shape[0],), max(float(frame_render.quality.get("overall_score", 0.0)), 0.05), dtype=np.float32)

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
                np.add.at(residual_weight, (yy[ok], xx[ok]), weights[ok])
                for channel in range(3):
                    np.add.at(residual_sum[..., channel], (yy[ok], xx[ok]), values[ok, channel] * weights[ok])
                written += int(ok.sum())

    return {"written_residual_samples": written, "metric_pixels": int(sample_mask.sum())}


def gaussian_blur_float(values: np.ndarray, radius: float) -> np.ndarray:
    if radius <= 0:
        return values.astype(np.float32)
    kernel_radius = max(int(round(radius * 2.0)), 1)
    xs = np.arange(-kernel_radius, kernel_radius + 1, dtype=np.float32)
    kernel = np.exp(-(xs * xs) / max(2.0 * radius * radius, 1e-6))
    kernel /= np.sum(kernel)

    output = values.astype(np.float32, copy=False)
    for axis in (0, 1):
        pad_width = [(0, 0)] * output.ndim
        pad_width[axis] = (kernel_radius, kernel_radius)
        padded = np.pad(output, pad_width, mode="edge")
        blurred = np.zeros_like(output, dtype=np.float32)
        for index, weight in enumerate(kernel):
            slices = [slice(None)] * output.ndim
            slices[axis] = slice(index, index + output.shape[axis])
            blurred += padded[tuple(slices)] * float(weight)
        output = blurred
    return output.astype(np.float32)


def optimize_texture_from_residual(
    *,
    base_texture: np.ndarray,
    residual_sum: np.ndarray,
    residual_weight: np.ndarray,
    strength: float,
    max_shift: float,
    blur_radius: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    blurred_weight = gaussian_blur_float(residual_weight, blur_radius)
    blurred_sum = np.zeros_like(residual_sum, dtype=np.float32)
    for channel in range(3):
        blurred_sum[..., channel] = gaussian_blur_float(residual_sum[..., channel], blur_radius)

    observed = blurred_weight > 1e-5
    residual = np.zeros_like(residual_sum, dtype=np.float32)
    residual[observed] = blurred_sum[observed] / blurred_weight[observed, None]
    if np.any(observed):
        p90 = float(np.percentile(blurred_weight[observed], 90))
    else:
        p90 = 1.0
    coverage_alpha = np.clip(blurred_weight / max(p90, 1e-5), 0.0, 1.0)
    correction = np.clip(residual * strength * coverage_alpha[..., None], -max_shift, max_shift)
    optimized = as_uint8_rgb(base_texture.astype(np.float32) + correction)
    return optimized, {
        "covered_texels": int(observed.sum()),
        "covered_fraction": float(observed.mean()),
        "p90_weight": p90,
        "strength": strength,
        "max_shift": max_shift,
        "blur_radius": blur_radius,
        "mean_abs_correction_rgb": [
            float(value) for value in np.mean(np.abs(correction[observed]), axis=0)
        ]
        if np.any(observed)
        else None,
    }


def save_image(path: Path, image: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(as_uint8_rgb(image), mode="RGB").save(path)
    return str(path)


def labeled_tile(image: np.ndarray, label: str, size: int) -> Image.Image:
    tile = Image.fromarray(as_uint8_rgb(image), mode="RGB")
    if tile.size != (size, size):
        tile = tile.resize((size, size), Image.BILINEAR)
    canvas = Image.new("RGB", (size, size + 24), (24, 24, 24))
    canvas.paste(tile, (0, 24))
    draw = ImageDraw.Draw(canvas)
    draw.text((7, 6), label, fill=(230, 230, 230))
    return canvas


def make_person_sheet(
    *,
    output_path: Path,
    person: str,
    frame_outputs: list[dict[str, Any]],
    tile_size: int,
) -> None:
    columns = ("crop", "before", "matched", "diff", "after", "after diff")
    person_label = PERSON_LABELS.get(person, person)
    left_width = 220
    header_height = 70
    row_height = tile_size + 24
    width = left_width + (len(columns) * tile_size)
    height = header_height + (len(frame_outputs) * row_height)
    sheet = Image.new("RGB", (width, height), (28, 28, 28))
    draw = ImageDraw.Draw(sheet)
    draw.text((18, 16), f"{person_label} fitted-camera selfie comparison", fill=(245, 245, 245))
    draw.text((18, 40), "crop / render / lighting matched / diff / weak texture residual", fill=(175, 175, 175))
    for index, label in enumerate(columns):
        draw.text((left_width + (index * tile_size) + 8, 48), label, fill=(220, 220, 220))

    for row_index, frame in enumerate(frame_outputs):
        y = header_height + row_index * row_height
        draw.rectangle((0, y, left_width - 10, y + row_height - 1), fill=(38, 38, 38))
        draw.text((18, y + 20), f"frame {frame['frame_id']}", fill=(255, 255, 255))
        draw.text((18, y + 48), f"score {frame['quality_score']:.3f}", fill=(190, 190, 190))
        draw.text((18, y + 76), f"raw {frame['before_raw_luma']:.1f} -> {frame['after_raw_luma']:.1f}", fill=(180, 180, 180))

        paths = [
            frame["crop_path"],
            frame["before_render_path"],
            frame["before_matched_path"],
            frame["before_diff_path"],
            frame["after_render_path"],
            frame["after_diff_path"],
        ]
        for col_index, path in enumerate(paths):
            tile = Image.open(path).convert("RGB").resize((tile_size, tile_size), Image.BILINEAR)
            sheet.paste(tile, (left_width + (col_index * tile_size), y + 24))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def select_quality_frames(report: dict[str, Any], max_frames: int, max_abs_yaw: float) -> list[dict[str, Any]]:
    candidates = []
    for frame in report["frames"]:
        if not frame.get("selected_for_bake"):
            continue
        yaw = frame.get("yaw_degrees")
        if yaw is not None and abs(float(yaw)) > max_abs_yaw:
            continue
        candidates.append(frame)
    candidates.sort(
        key=lambda item: (
            float(item.get("overall_score", 0.0)),
            -abs(float(item.get("yaw_degrees") or 0.0)),
        ),
        reverse=True,
    )
    return candidates[:max_frames]


def process_person(
    *,
    private_root: Path,
    person: str,
    texture_name: str,
    texture_kind: str,
    output_name: str,
    image_size: int,
    uv_mode: str,
    max_frames: int,
    max_abs_yaw: float,
    correction_strength: float,
    max_shift: float,
    residual_blur_radius: float,
    residual_splat_radius: int,
    fallback_confidence_threshold: int,
    eye_overlay: bool,
    projection_flip_y: bool,
    tile_size: int,
) -> dict[str, Any]:
    bundle = load_person(person, private_root=private_root)
    tracking_dirs = find_tracking_dirs(Path(bundle.output_dir))
    quality_report = analyze_person(person, private_root, min_score=0.5)
    selected_frames = select_quality_frames(quality_report, max_frames, max_abs_yaw)
    frame_by_id = {frame.frame_id: frame for frame in bundle.frames}

    texture_dir = private_root / "output" / person / "texture_baker" / texture_name
    texture_path = texture_path_for_run(texture_dir, texture_kind)
    base_texture = np.asarray(Image.open(texture_path).convert("RGB"), dtype=np.uint8)
    confidence_path = texture_dir / "confidence.png"
    confidence = None
    if confidence_path.exists():
        confidence = np.asarray(Image.open(confidence_path).convert("L"), dtype=np.uint8)

    uv_coords = np.load(resolve_uv_coords(private_root, None)).astype(np.float32)
    flame_masks = load_flame_masks(resolve_flame_masks(private_root, None))
    material_vertex_colors = build_material_vertex_colors(
        uv_coords.shape[0],
        flame_masks,
        estimate_skin_color(base_texture),
    )

    output_dir = private_root / "output" / person / "texture_baker" / output_name
    frames_dir = output_dir / "frames"
    output_dir.mkdir(parents=True, exist_ok=True)
    residual_sum = np.zeros((base_texture.shape[0], base_texture.shape[1], 3), dtype=np.float32)
    residual_weight = np.zeros((base_texture.shape[0], base_texture.shape[1]), dtype=np.float32)

    before_renders: list[FrameRender] = []
    frame_reports: list[dict[str, Any]] = []
    for quality in selected_frames:
        frame = frame_by_id.get(quality["frame_id"])
        if frame is None:
            continue
        prepared = prepare_frame_render(
            frame=frame,
            quality=quality,
            tracking_dirs=tracking_dirs,
            flame_masks=flame_masks,
            uv_coords=uv_coords,
            texture=base_texture,
            confidence=confidence,
            material_vertex_colors=material_vertex_colors,
            image_size=image_size,
            uv_mode=uv_mode,
            eye_overlay=eye_overlay,
            fallback_confidence_threshold=fallback_confidence_threshold,
            projection_flip_y=projection_flip_y,
        )
        if prepared is None:
            continue
        before_renders.append(prepared)
        residual_stats = accumulate_residual(
            frame_render=prepared,
            uv_coords=uv_coords,
            uv_mode=uv_mode,
            residual_sum=residual_sum,
            residual_weight=residual_weight,
            splat_radius=residual_splat_radius,
        )
        frame_reports.append(
            {
                "frame_id": prepared.frame_id,
                "quality_score": float(quality.get("overall_score", 0.0)),
                "yaw_degrees": quality.get("yaw_degrees"),
                "residual_accumulation": residual_stats,
                "projection_calibration": prepared.calibration,
            }
        )

    optimized_texture, optimization_stats = optimize_texture_from_residual(
        base_texture=base_texture,
        residual_sum=residual_sum,
        residual_weight=residual_weight,
        strength=correction_strength,
        max_shift=max_shift,
        blur_radius=residual_blur_radius,
    )
    optimized_path = texture_dir / "base_color_selfie_optimized_preview.png"
    Image.fromarray(optimized_texture, mode="RGB").save(optimized_path)
    Image.fromarray(np.clip(residual_weight, 0, 255).astype(np.uint8), mode="L").save(
        output_dir / "residual_weight.png"
    )

    frame_outputs: list[dict[str, Any]] = []
    for before in before_renders:
        frame = frame_by_id[before.frame_id]
        checkpoint = load_frame_checkpoint(checkpoint_path_for_frame(tracking_dirs, before.frame_id), before.frame_id)
        if checkpoint is None:
            continue
        after_render, _points, _depth, after_zbuffer, _calibration = render_fitted_frame(
            crop=before.crop,
            segmentation=before.segmentation,
            mesh=before.mesh,
            checkpoint=checkpoint,
            flame_masks=flame_masks,
            uv_coords=uv_coords,
            texture=optimized_texture,
            confidence=confidence,
            material_vertex_colors=material_vertex_colors,
            image_size=image_size,
            uv_mode=uv_mode,
            eye_overlay=eye_overlay,
            fallback_confidence_threshold=fallback_confidence_threshold,
            projection_flip_y=projection_flip_y,
        )
        after_foreground = np.isfinite(after_zbuffer)
        after_mask = mask_for_metrics(before.segmentation, after_foreground)

        before_matched, match_stats = color_match_to_crop(
            render=before.render,
            crop=before.crop,
            foreground=before.foreground,
            metric_mask=before.metric_mask,
        )
        after_matched, after_match_stats = color_match_to_crop(
            render=after_render,
            crop=before.crop,
            foreground=after_foreground,
            metric_mask=after_mask,
        )
        before_raw_metrics = error_metrics(before.crop, before.render, before.metric_mask)
        before_matched_metrics = error_metrics(before.crop, before_matched, before.metric_mask)
        after_raw_metrics = error_metrics(before.crop, after_render, after_mask)
        after_matched_metrics = error_metrics(before.crop, after_matched, after_mask)
        before_diff = make_diff_image(before.crop, before_matched, before.metric_mask)
        after_diff = make_diff_image(before.crop, after_matched, after_mask)

        frame_dir = frames_dir / before.frame_id
        output_record = {
            "frame_id": before.frame_id,
            "quality_score": float(before.quality.get("overall_score", 0.0)),
            "yaw_degrees": before.quality.get("yaw_degrees"),
            "crop_path": save_image(frame_dir / "crop.png", before.crop),
            "before_render_path": save_image(frame_dir / "render_before_raw.png", before.render),
            "before_matched_path": save_image(frame_dir / "render_before_lighting_matched.png", before_matched),
            "before_diff_path": save_image(frame_dir / "diff_before_lighting_matched.png", before_diff),
            "after_render_path": save_image(frame_dir / "render_after_texture_residual.png", after_render),
            "after_matched_path": save_image(frame_dir / "render_after_lighting_matched.png", after_matched),
            "after_diff_path": save_image(frame_dir / "diff_after_lighting_matched.png", after_diff),
            "before_raw_metrics": before_raw_metrics,
            "before_lighting_matched_metrics": before_matched_metrics,
            "after_raw_metrics": after_raw_metrics,
            "after_lighting_matched_metrics": after_matched_metrics,
            "before_color_match": match_stats,
            "after_color_match": after_match_stats,
            "before_raw_luma": float(before_raw_metrics.get("mean_abs_luma") or 0.0),
            "after_raw_luma": float(after_raw_metrics.get("mean_abs_luma") or 0.0),
        }
        frame_outputs.append(output_record)

    sheet_path = output_dir / "fitted_camera_selfie_comparison_sheet.png"
    make_person_sheet(output_path=sheet_path, person=person, frame_outputs=frame_outputs, tile_size=tile_size)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "person": person,
        "purpose": "Fitted-camera crop/render comparison and first weak texture residual correction.",
        "privacy": "Private biometric runtime artifact. Do not commit generated crops, renders, textures, or metrics.",
        "texture_name": texture_name,
        "texture_kind": texture_kind,
        "input_texture": str(texture_path),
        "optimized_texture": str(optimized_path),
        "output_dir": str(output_dir),
        "sheet_path": str(sheet_path),
        "image_size": image_size,
        "uv_mode": uv_mode,
        "projection_flip_y": projection_flip_y,
        "selected_frame_count": len(before_renders),
        "quality_frame_reports": frame_reports,
        "optimization": optimization_stats,
        "frame_outputs": frame_outputs,
        "limitations": [
            "This does not train a network.",
            "This does not modify geometry or identity shape yet.",
            "The residual pass is deliberately weak so it cannot destroy the observed texture.",
            "Fitted camera projection still uses bbox calibration from the v2 baker.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "fitted_camera_selfie_compare_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (texture_dir / "selfie_render_optimization_manifest.json").write_text(
        json.dumps(
            {
                "created_at": manifest["created_at"],
                "source_compare_manifest": str(output_dir / "fitted_camera_selfie_compare_manifest.json"),
                "optimized_texture": str(optimized_path),
                "optimization": optimization_stats,
                "selected_frame_count": len(before_renders),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create fitted-camera selfie comparisons and weak texture residual previews.")
    parser.add_argument("--private-root", type=Path, default=None)
    parser.add_argument("--person", action="append", default=None)
    parser.add_argument("--texture-name", default=DEFAULT_TEXTURE_NAME)
    parser.add_argument("--texture-kind", default="cleanup_completed")
    parser.add_argument("--output-name", default=DEFAULT_OUTPUT_NAME)
    parser.add_argument("--image-size", type=int, default=DEFAULT_IMAGE_SIZE)
    parser.add_argument("--uv-mode", default="flip_y")
    parser.add_argument("--max-frames", type=int, default=4)
    parser.add_argument("--max-abs-yaw", type=float, default=45.0)
    parser.add_argument("--correction-strength", type=float, default=0.34)
    parser.add_argument("--max-shift", type=float, default=24.0)
    parser.add_argument("--residual-blur-radius", type=float, default=2.0)
    parser.add_argument("--residual-splat-radius", type=int, default=1)
    parser.add_argument("--fallback-confidence-threshold", type=int, default=0)
    parser.add_argument("--no-eye-overlay", action="store_true")
    parser.add_argument("--no-projection-flip-y", action="store_true")
    parser.add_argument("--tile-size", type=int, default=256)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    private_root = args.private_root or default_private_root()
    people = args.person or list(DEFAULT_PEOPLE)
    manifests = [
        process_person(
            private_root=private_root,
            person=person,
            texture_name=args.texture_name,
            texture_kind=args.texture_kind,
            output_name=args.output_name,
            image_size=args.image_size,
            uv_mode=args.uv_mode,
            max_frames=args.max_frames,
            max_abs_yaw=args.max_abs_yaw,
            correction_strength=args.correction_strength,
            max_shift=args.max_shift,
            residual_blur_radius=args.residual_blur_radius,
            residual_splat_radius=args.residual_splat_radius,
            fallback_confidence_threshold=args.fallback_confidence_threshold,
            eye_overlay=not args.no_eye_overlay,
            projection_flip_y=not args.no_projection_flip_y,
            tile_size=args.tile_size,
        )
        for person in people
    ]
    print(json.dumps(manifests, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
