"""Run Step 6 material-specific texture post-processing.

Step 6 starts from the Step 5 blend texture. Each stage is intentionally narrow
and produces diagnostic review sheets. Implemented stages:

- `v01_hard_skin_holes`: only tiny black COMPLETION_NEEDED skin holes.
- `v02_forehead_tone`: protect eyes/brows/hairline, then repair forehead tone.

Private generated assets stay in Drive. Do not commit outputs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from scipy import ndimage


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")
DEFAULT_DRIVE_ROOT = Path(os.environ.get("HAIR_APP_DRIVE_ROOT", "G:/\ub0b4 \ub4dc\ub77c\uc774\ube0c/hair_app"))
PERSONS = ("juseop", "eunchae")

CLEAN_ONLY = 1
RAW_ONLY = 2
BOTH_OK = 3
COMPLETION_NEEDED = 4


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive-root", type=Path, default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--blender-exe", type=Path, default=DEFAULT_BLENDER_EXE)
    parser.add_argument("--source-version", default="facebuilder_semantic_v2")
    parser.add_argument("--step5-root", type=Path, default=None)
    parser.add_argument("--person", action="append", choices=PERSONS)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--headnum", type=int, default=0)
    parser.add_argument("--close-radius", type=int, default=5)
    parser.add_argument("--max-fill-distance", type=float, default=5.0)
    parser.add_argument("--max-component-area", type=int, default=180)
    parser.add_argument("--max-component-width", type=int, default=24)
    parser.add_argument("--max-component-height", type=int, default=20)
    parser.add_argument("--forehead-y-min", type=float, default=0.30)
    parser.add_argument("--forehead-y-max", type=float, default=0.45)
    parser.add_argument("--forehead-x-min", type=float, default=0.28)
    parser.add_argument("--forehead-x-max", type=float, default=0.72)
    parser.add_argument("--skip-baseline-renders", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    return parser.parse_args(argv)


def _safe_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _as_path(path_text: str | Path) -> Path:
    return Path(str(path_text).replace("/", "\\"))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _load_rgb(path: Path | str, size: tuple[int, int] | None = None) -> Image.Image:
    image = ImageOps.exif_transpose(Image.open(_as_path(path))).convert("RGB")
    if size is not None and image.size != size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    return image


def _save_rgb(path: Path, arr: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr.astype(np.uint8), mode="RGB").save(path)
    return _safe_path(path) or ""


def _save_l(path: Path, arr: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr.astype(np.uint8), mode="L").save(path)
    return _safe_path(path) or ""


def _find_one(pattern_root: Path, pattern: str) -> Path:
    matches = sorted(pattern_root.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No match under {pattern_root}: {pattern}")
    return matches[0]


def _find_latest_step5(drive_root: Path, people: list[str]) -> Path:
    root = drive_root / "output" / "facebuilder_mask_aware_step5"
    candidates = sorted([path for path in root.iterdir() if path.is_dir()], reverse=True)
    for candidate in candidates:
        if all((candidate / person / "step5_person_summary.json").exists() for person in people):
            return candidate
    raise FileNotFoundError(f"No ready Step 5 output found under {root}")


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "malgun.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                pass
    return ImageFont.load_default()


def _make_tile(title: str, image: Image.Image, width: int = 315) -> Image.Image:
    image = image.convert("RGB")
    ratio = width / image.width
    thumb = image.resize((width, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
    band_h = 34
    out = Image.new("RGB", (thumb.width, thumb.height + band_h), (28, 28, 28))
    out.paste(thumb, (0, band_h))
    draw = ImageDraw.Draw(out)
    draw.text((8, 8), title[:44], fill=(240, 240, 240), font=_font(14))
    return out


def _make_grid_sheet(title: str, subtitle: str, tiles: list[tuple[str, Image.Image]], path: Path, columns: int = 4) -> None:
    if not tiles:
        return
    gap = 12
    header_h = 82
    rendered = [_make_tile(label, image) for label, image in tiles]
    tile_w = max(tile.width for tile in rendered)
    tile_h = max(tile.height for tile in rendered)
    rows = (len(rendered) + columns - 1) // columns
    width = columns * tile_w + (columns + 1) * gap
    height = header_h + rows * tile_h + (rows + 1) * gap
    sheet = Image.new("RGB", (width, height), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 12), title, fill=(245, 245, 245), font=_font(24))
    draw.text((16, 48), subtitle, fill=(180, 180, 180), font=_font(14))
    for index, tile in enumerate(rendered):
        row = index // columns
        col = index % columns
        x = gap + col * (tile_w + gap)
        y = header_h + gap + row * (tile_h + gap)
        sheet.paste(tile, (x, y))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=95)


def _make_render_sheet(person: str, stage: str, render_dir: Path, path: Path) -> str | None:
    images = []
    for render_path in sorted(render_dir.glob("render_yaw_*.png")):
        images.append((render_path.stem.replace("render_yaw_", "yaw "), Image.open(render_path).convert("RGB")))
    if not images:
        return None
    _make_grid_sheet(
        f"{person} Step 6 {stage} render review",
        "FaceBuilder mesh rendered with Step 6 diagnostic texture. Private; do not commit.",
        images,
        path,
        columns=4,
    )
    return _safe_path(path)


def _render_texture(
    *,
    blender_exe: Path,
    blend: Path,
    render_script: Path,
    texture: Path,
    output_dir: Path,
    output_json: Path,
    log_path: Path,
    headnum: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(blender_exe),
        "--background",
        str(blend),
        "--python",
        str(render_script),
        "--",
        "--texture",
        str(texture),
        "--output-dir",
        str(output_dir),
        "--output-json",
        str(output_json),
        "--headnum",
        str(headnum),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    log_path.write_text((completed.stdout or "") + "\n--- STDERR ---\n" + (completed.stderr or ""), encoding="utf-8")
    render_summary = _read_json(output_json) if output_json.exists() else {}
    return {
        "ok": completed.returncode == 0 and bool(render_summary.get("ok")),
        "returncode": completed.returncode,
        "render_json": _safe_path(output_json),
        "render_dir": _safe_path(output_dir),
        "log": _safe_path(log_path),
    }


def _disk(radius: int) -> np.ndarray:
    radius = max(1, int(radius))
    y, x = np.ogrid[-radius : radius + 1, -radius : radius + 1]
    return (x * x + y * y) <= radius * radius


def _broad_skin_mask(texture: np.ndarray, decision: np.ndarray) -> np.ndarray:
    rgb = texture.astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    maxc = rgb.max(axis=2)
    minc = rgb.min(axis=2)
    chroma = maxc - minc
    cb = 128.0 - 0.168736 * rgb[..., 0] - 0.331264 * rgb[..., 1] + 0.5 * rgb[..., 2]
    cr = 128.0 + 0.5 * rgb[..., 0] - 0.418688 * rgb[..., 1] - 0.081312 * rgb[..., 2]
    broad_ycbcr = (cb > 68.0) & (cb < 160.0) & (cr > 105.0) & (cr < 205.0)
    valid_decision = decision != COMPLETION_NEEDED
    not_feature_dark = luma > 42.0
    not_blowout = luma < 245.0
    not_extreme_chroma = chroma < 145.0
    return valid_decision & not_feature_dark & not_blowout & not_extreme_chroma & broad_ycbcr


def _filter_small_holes(
    candidates: np.ndarray,
    *,
    max_area: int,
    max_width: int,
    max_height: int,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    labels, count = ndimage.label(candidates)
    keep = np.zeros(candidates.shape, dtype=bool)
    components: list[dict[str, Any]] = []
    objects = ndimage.find_objects(labels)
    for label_id, slices in enumerate(objects, start=1):
        if slices is None:
            continue
        ys, xs = slices
        component = labels[slices] == label_id
        area = int(component.sum())
        height = int(ys.stop - ys.start)
        width = int(xs.stop - xs.start)
        aspect = max(width / max(1, height), height / max(1, width))
        # Eyes, brows, lip gaps, and nostril/mouth fragments usually become
        # thin dark horizontal/vertical islands in UV. Rejecting elongated
        # islands keeps this first pass focused on dot-like skin holes only.
        feature_like = aspect >= 2.15 and (width >= 10 or height >= 10)
        kept = area <= max_area and width <= max_width and height <= max_height and not feature_like
        if kept:
            keep[slices][component] = True
        components.append({
            "label": label_id,
            "area": area,
            "width": width,
            "height": height,
            "aspect": float(aspect),
            "feature_like": bool(feature_like),
            "bbox": [int(xs.start), int(ys.start), int(xs.stop), int(ys.stop)],
            "kept": bool(kept),
        })
    return keep, components


def _feature_protect_mask(
    texture: np.ndarray,
    decision: np.ndarray,
    reliable_skin: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    rgb = texture.astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    skin_neighborhood = ndimage.binary_dilation(reliable_skin, structure=_disk(18))
    dark_completion = (decision == COMPLETION_NEEDED) & (luma < 52.0) & skin_neighborhood
    labels, count = ndimage.label(dark_completion)
    protect = np.zeros(dark_completion.shape, dtype=bool)
    components: list[dict[str, Any]] = []
    for label_id, slices in enumerate(ndimage.find_objects(labels), start=1):
        if slices is None:
            continue
        ys, xs = slices
        component = labels[slices] == label_id
        area = int(component.sum())
        height = int(ys.stop - ys.start)
        width = int(xs.stop - xs.start)
        aspect = max(width / max(1, height), height / max(1, width))
        feature_like = area >= 12 or width >= 5 or height >= 5 or aspect >= 2.5
        if feature_like:
            protect[slices][component] = True
        components.append({
            "label": label_id,
            "area": area,
            "width": width,
            "height": height,
            "aspect": float(aspect),
            "feature_like": bool(feature_like),
            "bbox": [int(xs.start), int(ys.start), int(xs.stop), int(ys.stop)],
        })
    protect = ndimage.binary_dilation(protect, structure=_disk(3))
    return protect, {
        "dark_completion_components": int(count),
        "feature_protected_components": int(sum(1 for item in components if item["feature_like"])),
        "feature_protected_texels": int(protect.sum()),
        "feature_components_preview": components[:30],
    }


def _step_v01_hard_skin_holes(
    baseline: np.ndarray,
    decision: np.ndarray,
    *,
    close_radius: int,
    max_fill_distance: float,
    max_component_area: int,
    max_component_width: int,
    max_component_height: int,
) -> tuple[np.ndarray, dict[str, np.ndarray], dict[str, Any]]:
    reliable_skin = _broad_skin_mask(baseline, decision)
    completion = decision == COMPLETION_NEEDED
    feature_protect, feature_meta = _feature_protect_mask(baseline, decision, reliable_skin)
    structure = _disk(close_radius)
    closed_skin = ndimage.binary_closing(reliable_skin, structure=structure)
    distance, nearest = ndimage.distance_transform_edt(~reliable_skin, return_indices=True)
    candidates = completion & closed_skin & (distance <= max_fill_distance) & ~feature_protect
    fill_target, components = _filter_small_holes(
        candidates,
        max_area=max_component_area,
        max_width=max_component_width,
        max_height=max_component_height,
    )

    filled = baseline.copy()
    nearest_y, nearest_x = nearest
    nearest_colors = baseline[nearest_y, nearest_x]
    filled[fill_target] = nearest_colors[fill_target]

    # Smooth only the newly-filled texels so the hard hole does not become a
    # nearest-neighbor patch. Non-target texels remain bit-identical to baseline.
    smoothed = cv2.GaussianBlur(filled, (5, 5), 0)
    filled[fill_target] = np.clip(
        filled[fill_target].astype(np.float32) * 0.55 + smoothed[fill_target].astype(np.float32) * 0.45,
        0,
        255,
    ).astype(np.uint8)

    changed = np.any(filled != baseline, axis=2)
    source_skin_rgb = np.zeros_like(baseline, dtype=np.uint8)
    source_skin_rgb[reliable_skin] = (80, 210, 120)
    fill_rgb = np.zeros_like(baseline, dtype=np.uint8)
    fill_rgb[fill_target] = (0, 220, 255)
    feature_rgb = np.zeros_like(baseline, dtype=np.uint8)
    feature_rgb[feature_protect] = (255, 90, 210)
    changed_rgb = baseline.copy()
    changed_rgb[fill_target] = np.clip(
        baseline[fill_target].astype(np.float32) * 0.35 + np.asarray([0, 220, 255], dtype=np.float32) * 0.65,
        0,
        255,
    ).astype(np.uint8)
    dist_vis = np.clip(distance / max(1.0, max_fill_distance), 0.0, 1.0)
    distance_rgb = np.zeros_like(baseline, dtype=np.uint8)
    distance_rgb[..., 0] = np.clip((1.0 - dist_vis) * 255.0, 0, 255).astype(np.uint8)
    distance_rgb[..., 1] = np.clip((1.0 - dist_vis * 0.35) * 210.0, 0, 255).astype(np.uint8)
    distance_rgb[..., 2] = np.clip(dist_vis * 255.0, 0, 255).astype(np.uint8)
    distance_rgb[~candidates] = (8, 8, 8)

    maps = {
        "texture": filled,
        "reliable_skin_mask": reliable_skin.astype(np.uint8) * 255,
        "closed_skin_mask": closed_skin.astype(np.uint8) * 255,
        "candidate_mask": candidates.astype(np.uint8) * 255,
        "feature_protect_mask": feature_protect.astype(np.uint8) * 255,
        "fill_target_mask": fill_target.astype(np.uint8) * 255,
        "changed_mask": changed.astype(np.uint8) * 255,
        "source_skin_rgb": source_skin_rgb,
        "fill_target_rgb": fill_rgb,
        "feature_protect_rgb": feature_rgb,
        "changed_overlay": changed_rgb,
        "distance_rgb": distance_rgb,
    }
    meta = {
        "close_radius": int(close_radius),
        "max_fill_distance": float(max_fill_distance),
        "max_component_area": int(max_component_area),
        "max_component_width": int(max_component_width),
        "max_component_height": int(max_component_height),
        "reliable_skin_texels": int(reliable_skin.sum()),
        "completion_texels": int(completion.sum()),
        "candidate_texels_before_component_filter": int(candidates.sum()),
        "feature_protected_texels": int(feature_protect.sum()),
        "dark_completion_components": feature_meta["dark_completion_components"],
        "feature_protected_components": feature_meta["feature_protected_components"],
        "filled_texels": int(fill_target.sum()),
        "changed_texels": int(changed.sum()),
        "components_total": len(components),
        "components_kept": int(sum(1 for item in components if item["kept"])),
        "components_rejected": int(sum(1 for item in components if not item["kept"])),
        "largest_kept_component_area": int(max([item["area"] for item in components if item["kept"]] or [0])),
        "components_preview": components[:30],
        "feature_components_preview": feature_meta["feature_components_preview"],
    }
    return filled, maps, meta


def _mask_rgb(mask: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    out = np.zeros((*mask.shape, 3), dtype=np.uint8)
    out[mask] = color
    return out


def _blend_overlay(base: np.ndarray, mask: np.ndarray, color: tuple[int, int, int], alpha: float = 0.65) -> np.ndarray:
    out = base.copy()
    if np.any(mask):
        color_arr = np.asarray(color, dtype=np.float32)
        out[mask] = np.clip(
            base[mask].astype(np.float32) * (1.0 - alpha) + color_arr.reshape(1, 3) * alpha,
            0,
            255,
        ).astype(np.uint8)
    return out


def _safe_percentile(values: np.ndarray, percentile: float, fallback: float) -> float:
    if values.size == 0:
        return fallback
    return float(np.percentile(values, percentile))


def _masked_median_rgb(texture: np.ndarray, mask: np.ndarray, fallback: np.ndarray) -> tuple[np.ndarray, int]:
    pixels = texture[mask].astype(np.float32)
    if pixels.shape[0] == 0:
        return fallback.astype(np.float32), 0
    return np.median(pixels, axis=0).astype(np.float32), int(pixels.shape[0])


def _keep_central_forehead_components(mask: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    h, w = mask.shape
    labels, count = ndimage.label(mask)
    filtered = np.zeros(mask.shape, dtype=bool)
    components: list[dict[str, Any]] = []
    central_min = int(w * 0.38)
    central_max = int(w * 0.62)

    for label_id, slices in enumerate(ndimage.find_objects(labels), start=1):
        if slices is None:
            continue
        ys, xs = slices
        component = labels[slices] == label_id
        area = int(component.sum())
        width = int(xs.stop - xs.start)
        height = int(ys.stop - ys.start)
        center_x = float((xs.start + xs.stop) * 0.5 / max(1, w))
        overlaps_central_forehead = xs.start <= central_max and xs.stop >= central_min
        large_enough = area >= 24 and width >= 4 and height >= 3
        kept = bool(overlaps_central_forehead and large_enough)
        if kept:
            filtered[slices][component] = True
        components.append({
            "label": label_id,
            "area": area,
            "width": width,
            "height": height,
            "center_x": center_x,
            "overlaps_central_forehead": bool(overlaps_central_forehead),
            "kept": kept,
            "bbox": [int(xs.start), int(ys.start), int(xs.stop), int(ys.stop)],
        })

    # If the UV layout changes enough that this filter removes almost
    # everything, fall back to the original mask and make that visible in
    # metrics instead of silently disabling the stage.
    fallback_used = bool(mask.sum() > 0 and filtered.sum() < max(256, int(mask.sum() * 0.18)))
    if fallback_used:
        filtered = mask.copy()

    return filtered, {
        "forehead_component_count": int(count),
        "forehead_components_kept": int(sum(1 for item in components if item["kept"])),
        "forehead_components_rejected": int(sum(1 for item in components if not item["kept"])),
        "forehead_component_filter_fallback_used": fallback_used,
        "forehead_components_preview": components[:30],
    }


def _step_v02_forehead_tone(
    base: np.ndarray,
    decision: np.ndarray,
    clean_score: np.ndarray,
    raw_score: np.ndarray,
    confidence: np.ndarray,
    source_count: np.ndarray,
    *,
    forehead_y_min: float,
    forehead_y_max: float,
    forehead_x_min: float,
    forehead_x_max: float,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    reliable_skin = _broad_skin_mask(base, decision)
    feature_protect, feature_meta = _feature_protect_mask(base, decision, reliable_skin)
    h, w = decision.shape
    yy, xx = np.indices((h, w))
    roi = (
        (xx >= int(w * forehead_x_min))
        & (xx <= int(w * forehead_x_max))
        & (yy >= int(h * forehead_y_min))
        & (yy <= int(h * forehead_y_max))
    )

    rgb = base.astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    max_score = np.maximum(clean_score.astype(np.float32), raw_score.astype(np.float32))

    skin_near = ndimage.binary_dilation(reliable_skin, structure=_disk(14))
    very_dark_feature = (luma < 36.0) & skin_near & roi
    guard = ndimage.binary_dilation(feature_protect | very_dark_feature, structure=_disk(2))

    forehead_skin = reliable_skin & roi & ~guard
    if int(forehead_skin.sum()) < 256:
        # Fallback for unusual UV/raster outputs: still exclude explicit guard
        # regions, but loosen the color gate so the review sheet exposes the
        # failed mask instead of silently doing nothing.
        foreground = (decision != COMPLETION_NEEDED) & (luma > 38.0)
        forehead_skin = foreground & roi & ~guard
    forehead_skin, component_meta = _keep_central_forehead_components(forehead_skin)

    ref_roi = (
        reliable_skin
        & ~guard
        & (xx >= int(w * 0.24))
        & (xx <= int(w * 0.76))
        & (yy >= int(h * 0.44))
        & (yy <= int(h * 0.68))
        & (max_score > 0.28)
    )
    if int(ref_roi.sum()) < 512:
        ref_roi = reliable_skin & ~guard & (max_score > 0.20)

    default_skin = np.asarray([155.0, 122.0, 108.0], dtype=np.float32)
    face_median, face_ref_count = _masked_median_rgb(base, ref_roi, default_skin)

    forehead_good = forehead_skin & (max_score > 0.30)
    forehead_luma_values = luma[forehead_good]
    luma_floor = _safe_percentile(forehead_luma_values, 35.0, float(np.dot(face_median, [0.2126, 0.7152, 0.0722])))
    luma_ceiling = _safe_percentile(forehead_luma_values, 90.0, float(np.dot(face_median, [0.2126, 0.7152, 0.0722]) + 28.0))
    forehead_good = forehead_good & (luma >= max(42.0, luma_floor - 12.0)) & (luma <= min(235.0, luma_ceiling + 22.0))
    forehead_median, forehead_ref_count = _masked_median_rgb(base, forehead_good, face_median)

    # Do not replace the forehead with cheek color. The target is a tempered
    # mix: mostly the best forehead pixels, partially stable midface skin.
    target_rgb = np.clip(forehead_median * 0.68 + face_median * 0.32, 0, 255)
    target_luma = float(target_rgb[0] * 0.2126 + target_rgb[1] * 0.7152 + target_rgb[2] * 0.0722)
    current_forehead_luma = luma[forehead_skin]
    current_median_luma = _safe_percentile(current_forehead_luma, 50.0, target_luma)
    dark_deficit = np.maximum(0.0, target_luma - luma - 6.0)
    bright_excess = np.maximum(0.0, luma - target_luma - 14.0)
    color_dist = np.sqrt(np.mean(((rgb - target_rgb.reshape(1, 1, 3)) / 42.0) ** 2.0, axis=2))
    color_outlier = np.clip((color_dist - 0.72) / 1.45, 0.0, 1.0)
    low_trust = np.clip((0.38 - max_score) / 0.38, 0.0, 1.0)
    source_sparse = np.clip((2.0 - source_count.astype(np.float32)) / 2.0, 0.0, 1.0)
    tone_candidate = forehead_skin & (
        (dark_deficit > 10.0)
        | (bright_excess > 12.0)
        | (color_outlier > 0.30)
        | (low_trust > 0.38)
        | (source_sparse > 0.55)
    )

    variants: dict[str, np.ndarray] = {}
    overlays: dict[str, np.ndarray] = {}
    weight_maps: dict[str, np.ndarray] = {}
    changed_masks: dict[str, np.ndarray] = {}
    variant_metrics: dict[str, Any] = {}
    edge_feather = np.clip(ndimage.distance_transform_edt(forehead_skin).astype(np.float32) / 14.0, 0.0, 1.0)
    strengths = {
        "light": 0.38,
        "medium": 0.78,
        "strong": 1.08,
    }

    delta = np.clip(target_rgb.reshape(1, 1, 3) - forehead_median.reshape(1, 1, 3), -36.0, 36.0)
    for label, strength in strengths.items():
        repaired = base.copy()
        base_weight = 0.08 * strength
        dark_weight = np.clip(dark_deficit / 44.0, 0.0, 1.0) * (0.74 * strength)
        bright_weight = np.clip(bright_excess / 42.0, 0.0, 1.0) * (0.54 * strength)
        outlier_weight = color_outlier * (0.62 * strength)
        trust_weight = np.maximum(low_trust * 0.20 * strength, source_sparse * 0.16 * strength)
        weight = np.clip(base_weight + dark_weight + bright_weight + outlier_weight + trust_weight, 0.0, 0.90)
        weight *= edge_feather
        weight[~forehead_skin] = 0.0

        luma_shift = np.clip(dark_deficit * 0.95 * strength - bright_excess * 0.42 * strength, -36.0, 72.0)
        target = rgb + delta * (0.70 * strength)
        target += luma_shift[..., None] * np.asarray([1.0, 0.94, 0.88], dtype=np.float32).reshape(1, 1, 3)
        target_pull = np.clip(outlier_weight * edge_feather, 0.0, min(0.78, 0.58 * strength))
        target = target * (1.0 - target_pull[..., None]) + target_rgb.reshape(1, 1, 3) * target_pull[..., None]
        target = np.clip(target, 0.0, 255.0)
        mixed = rgb * (1.0 - weight[..., None]) + target * weight[..., None]
        repaired[forehead_skin] = np.clip(mixed[forehead_skin], 0.0, 255.0).astype(np.uint8)

        changed = np.any(repaired != base, axis=2)
        variants[label] = repaired
        changed_masks[label] = changed.astype(np.uint8) * 255
        weight_maps[label] = np.clip(weight * 255.0, 0, 255).astype(np.uint8)
        overlays[label] = _blend_overlay(base, changed, (255, 176, 32), alpha=0.62)
        if np.any(changed):
            abs_delta = np.abs(repaired.astype(np.int16) - base.astype(np.int16)).sum(axis=2)
            variant_metrics[label] = {
                "changed_texels": int(changed.sum()),
                "mean_abs_rgb_delta_on_changed": float(abs_delta[changed].mean()),
                "max_abs_rgb_delta_on_changed": int(abs_delta[changed].max()),
            }
        else:
            variant_metrics[label] = {
                "changed_texels": 0,
                "mean_abs_rgb_delta_on_changed": 0.0,
                "max_abs_rgb_delta_on_changed": 0,
            }

    guard_rgb = _mask_rgb(guard, (255, 82, 210))
    forehead_rgb = _mask_rgb(forehead_skin, (58, 220, 105))
    tone_candidate_rgb = _mask_rgb(tone_candidate, (255, 218, 45))
    combined_rgb = np.zeros_like(base, dtype=np.uint8)
    combined_rgb[forehead_skin] = (58, 220, 105)
    combined_rgb[tone_candidate] = (255, 218, 45)
    combined_rgb[guard] = (255, 82, 210)
    combined_overlay = base.copy()
    for mask, color, alpha in [
        (forehead_skin, (58, 220, 105), 0.42),
        (tone_candidate, (255, 218, 45), 0.62),
        (guard, (255, 82, 210), 0.72),
    ]:
        combined_overlay = _blend_overlay(combined_overlay, mask, color, alpha=alpha)

    maps: dict[str, np.ndarray] = {
        "guard_mask": guard.astype(np.uint8) * 255,
        "guard_rgb": guard_rgb,
        "forehead_skin_mask": forehead_skin.astype(np.uint8) * 255,
        "forehead_skin_rgb": forehead_rgb,
        "tone_candidate_mask": tone_candidate.astype(np.uint8) * 255,
        "tone_candidate_rgb": tone_candidate_rgb,
        "combined_mask_rgb": combined_rgb,
        "combined_overlay": combined_overlay,
        "reference_skin_rgb": _mask_rgb(ref_roi, (80, 160, 255)),
        "forehead_good_rgb": _mask_rgb(forehead_good, (120, 255, 185)),
        "edge_feather": np.clip(edge_feather * 255.0, 0, 255).astype(np.uint8),
    }
    for label in variants:
        maps[f"{label}_texture"] = variants[label]
        maps[f"{label}_changed_mask"] = changed_masks[label]
        maps[f"{label}_changed_overlay"] = overlays[label]
        maps[f"{label}_weight"] = weight_maps[label]

    meta = {
        "forehead_roi_normalized": {
            "x_min": float(forehead_x_min),
            "x_max": float(forehead_x_max),
            "y_min": float(forehead_y_min),
            "y_max": float(forehead_y_max),
        },
        "guard_texels": int(guard.sum()),
        "forehead_skin_texels": int(forehead_skin.sum()),
        "tone_candidate_texels": int(tone_candidate.sum()),
        "reference_skin_texels": int(ref_roi.sum()),
        "forehead_reference_texels": int(forehead_good.sum()),
        "face_reference_sample_count": int(face_ref_count),
        "forehead_reference_sample_count": int(forehead_ref_count),
        "face_reference_median_rgb": [float(x) for x in face_median.tolist()],
        "forehead_reference_median_rgb": [float(x) for x in forehead_median.tolist()],
        "target_rgb": [float(x) for x in target_rgb.tolist()],
        "target_luma": float(target_luma),
        "current_forehead_median_luma": float(current_median_luma),
        "feature_protected_texels": int(feature_protect.sum()),
        "feature_protected_components": feature_meta["feature_protected_components"],
        "edge_feather_mean_on_forehead": float(edge_feather[forehead_skin].mean()) if np.any(forehead_skin) else 0.0,
        "variant_metrics": variant_metrics,
    }
    meta.update(component_meta)
    return maps, meta


def _render_stage(
    *,
    person: str,
    stage: str,
    texture_path: Path,
    source_person_dir: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    render_script = REPO_ROOT / "experiments" / "facebuilder_mask_aware_correction" / "blender_step4_render_texture.py"
    blend = _find_one(source_person_dir / "03_facebuilder_scene", "*.blend")
    render_dir = output_dir / "renders" / stage
    render_json = render_dir / "render_summary.json"
    render_log = output_dir / "logs" / f"blender_step6_render_{stage}_stdout_stderr.txt"
    result = _render_texture(
        blender_exe=args.blender_exe,
        blend=blend,
        render_script=render_script,
        texture=texture_path,
        output_dir=render_dir,
        output_json=render_json,
        log_path=render_log,
        headnum=args.headnum,
    )
    sheet = _make_render_sheet(person, stage, render_dir, output_dir / f"step6_{stage}_render_review_sheet.png")
    if sheet:
        result["render_review_sheet"] = sheet
    return result


def _process_person(person: str, step5_person_dir: Path, output_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    step5_summary_path = step5_person_dir / "step5_person_summary.json"
    step5_summary = _read_json(step5_summary_path)
    arrays_path = _as_path(step5_summary["paths"]["arbitration_arrays"])
    source_person_dir = _as_path(step5_summary["source_person_dir"])

    with np.load(arrays_path) as data:
        baseline = data["blend_texture"].astype(np.uint8)
        select_texture = data["select_texture"].astype(np.uint8)
        decision = data["decision"].astype(np.uint8)
        clean_score = data["clean_score"].astype(np.float32)
        raw_score = data["raw_score"].astype(np.float32)
        confidence = data["confidence"].astype(np.uint8)
        source_count = data["source_count"].astype(np.uint16)

    person_summary: dict[str, Any] = {
        "schema_version": "facebuilder_mask_aware_step6_person_v1",
        "person": person,
        "ok": True,
        "step5_person_dir": _safe_path(step5_person_dir),
        "step5_summary": _safe_path(step5_summary_path),
        "source_person_dir": _safe_path(source_person_dir),
        "baseline": "step5_blend_texture",
        "stages": {},
    }

    v00_dir = output_dir / "v00_baseline"
    v00_maps = v00_dir / "maps"
    v00_texture = v00_maps / "v00_baseline_blend_texture.png"
    v00_paths = {
        "baseline_blend_texture": _save_rgb(v00_texture, baseline),
        "diagnostic_select_texture": _save_rgb(v00_maps / "v00_diagnostic_select_texture.png", select_texture),
    }
    if not args.skip_render and not args.skip_baseline_renders:
        v00_paths["baseline_render"] = _render_stage(
            person=person,
            stage="v00_baseline",
            texture_path=v00_texture,
            source_person_dir=source_person_dir,
            output_dir=v00_dir,
            args=args,
        )
    person_summary["stages"]["v00_baseline"] = {"paths": v00_paths}

    v01_texture, v01_maps, v01_meta = _step_v01_hard_skin_holes(
        baseline,
        decision,
        close_radius=args.close_radius,
        max_fill_distance=args.max_fill_distance,
        max_component_area=args.max_component_area,
        max_component_width=args.max_component_width,
        max_component_height=args.max_component_height,
    )
    v01_dir = output_dir / "v01_hard_skin_holes"
    v01_maps_dir = v01_dir / "maps"
    v01_texture_path = v01_maps_dir / "v01_hard_skin_holes_texture.png"
    v01_paths: dict[str, Any] = {
        "texture": _save_rgb(v01_texture_path, v01_texture),
        "reliable_skin_mask": _save_l(v01_maps_dir / "v01_reliable_skin_mask.png", v01_maps["reliable_skin_mask"]),
        "closed_skin_mask": _save_l(v01_maps_dir / "v01_closed_skin_mask.png", v01_maps["closed_skin_mask"]),
        "candidate_mask": _save_l(v01_maps_dir / "v01_candidate_mask_before_component_filter.png", v01_maps["candidate_mask"]),
        "feature_protect_mask": _save_l(v01_maps_dir / "v01_feature_protect_mask.png", v01_maps["feature_protect_mask"]),
        "fill_target_mask": _save_l(v01_maps_dir / "v01_fill_target_mask.png", v01_maps["fill_target_mask"]),
        "changed_mask": _save_l(v01_maps_dir / "v01_changed_mask.png", v01_maps["changed_mask"]),
        "source_skin_rgb": _save_rgb(v01_maps_dir / "v01_reliable_skin_debug_rgb.png", v01_maps["source_skin_rgb"]),
        "fill_target_rgb": _save_rgb(v01_maps_dir / "v01_fill_target_debug_rgb.png", v01_maps["fill_target_rgb"]),
        "feature_protect_rgb": _save_rgb(v01_maps_dir / "v01_feature_protect_debug_rgb.png", v01_maps["feature_protect_rgb"]),
        "changed_overlay": _save_rgb(v01_maps_dir / "v01_changed_overlay.png", v01_maps["changed_overlay"]),
        "distance_rgb": _save_rgb(v01_maps_dir / "v01_candidate_distance_debug_rgb.png", v01_maps["distance_rgb"]),
    }

    review_tiles = [
        ("v00 baseline blend", Image.fromarray(baseline, mode="RGB")),
        ("v01 hard skin holes", Image.fromarray(v01_texture, mode="RGB")),
        ("changed overlay cyan", Image.fromarray(v01_maps["changed_overlay"], mode="RGB")),
        ("fill target cyan", Image.fromarray(v01_maps["fill_target_rgb"], mode="RGB")),
        ("feature protect magenta", Image.fromarray(v01_maps["feature_protect_rgb"], mode="RGB")),
        ("reliable skin debug", Image.fromarray(v01_maps["source_skin_rgb"], mode="RGB")),
        ("candidate distance", Image.fromarray(v01_maps["distance_rgb"], mode="RGB")),
        ("Step5 decision map", _load_rgb(step5_summary["paths"]["step5_decision_color_map"])),
        ("Step5 completion mask", _load_rgb(step5_summary["paths"]["step5_completion_needed_mask"])),
    ]
    uv_review = v01_dir / "step6_v01_uv_review_sheet.png"
    _make_grid_sheet(
        f"{person} Step 6 v01 hard skin holes UV review",
        "Only small completion-needed holes enclosed by reliable skin are filled. Eyes/mouth/scalp/clothes should stay untouched.",
        review_tiles,
        uv_review,
        columns=4,
    )
    v01_paths["uv_review_sheet"] = _safe_path(uv_review)

    if not args.skip_render and not args.skip_baseline_renders:
        v01_paths["v01_render"] = _render_stage(
            person=person,
            stage="v01_hard_skin_holes",
            texture_path=v01_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v01_dir,
            args=args,
        )
        changed_texture_path = v01_maps_dir / "v01_changed_overlay_render_texture.png"
        _save_rgb(changed_texture_path, v01_maps["changed_overlay"])
        v01_paths["changed_overlay_render"] = _render_stage(
            person=person,
            stage="v01_changed_overlay",
            texture_path=changed_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v01_dir,
            args=args,
        )

    person_summary["stages"]["v01_hard_skin_holes"] = {
        "logic": "small closed reliable-skin holes only; nearest reliable skin fill plus local smoothing",
        "paths": v01_paths,
        "metrics": v01_meta,
    }

    v02_maps, v02_meta = _step_v02_forehead_tone(
        v01_texture,
        decision,
        clean_score,
        raw_score,
        confidence,
        source_count,
        forehead_y_min=args.forehead_y_min,
        forehead_y_max=args.forehead_y_max,
        forehead_x_min=args.forehead_x_min,
        forehead_x_max=args.forehead_x_max,
    )
    v02_dir = output_dir / "v02_forehead_tone"
    v02_maps_dir = v02_dir / "maps"
    v02_paths: dict[str, Any] = {
        "guard_mask": _save_l(v02_maps_dir / "v02_guard_mask.png", v02_maps["guard_mask"]),
        "guard_rgb": _save_rgb(v02_maps_dir / "v02_guard_debug_rgb.png", v02_maps["guard_rgb"]),
        "forehead_skin_mask": _save_l(v02_maps_dir / "v02_forehead_skin_mask.png", v02_maps["forehead_skin_mask"]),
        "forehead_skin_rgb": _save_rgb(v02_maps_dir / "v02_forehead_skin_debug_rgb.png", v02_maps["forehead_skin_rgb"]),
        "tone_candidate_mask": _save_l(v02_maps_dir / "v02_tone_candidate_mask.png", v02_maps["tone_candidate_mask"]),
        "tone_candidate_rgb": _save_rgb(v02_maps_dir / "v02_tone_candidate_debug_rgb.png", v02_maps["tone_candidate_rgb"]),
        "combined_mask_rgb": _save_rgb(v02_maps_dir / "v02_combined_mask_rgb.png", v02_maps["combined_mask_rgb"]),
        "combined_overlay": _save_rgb(v02_maps_dir / "v02_combined_overlay.png", v02_maps["combined_overlay"]),
        "reference_skin_rgb": _save_rgb(v02_maps_dir / "v02_reference_skin_debug_rgb.png", v02_maps["reference_skin_rgb"]),
        "forehead_good_rgb": _save_rgb(v02_maps_dir / "v02_forehead_reference_debug_rgb.png", v02_maps["forehead_good_rgb"]),
        "edge_feather": _save_l(v02_maps_dir / "v02_forehead_edge_feather.png", v02_maps["edge_feather"]),
    }
    for label in ("light", "medium", "strong"):
        v02_paths[f"{label}_texture"] = _save_rgb(
            v02_maps_dir / f"v02_forehead_tone_{label}_texture.png",
            v02_maps[f"{label}_texture"],
        )
        v02_paths[f"{label}_changed_mask"] = _save_l(
            v02_maps_dir / f"v02_forehead_tone_{label}_changed_mask.png",
            v02_maps[f"{label}_changed_mask"],
        )
        v02_paths[f"{label}_changed_overlay"] = _save_rgb(
            v02_maps_dir / f"v02_forehead_tone_{label}_changed_overlay.png",
            v02_maps[f"{label}_changed_overlay"],
        )
        v02_paths[f"{label}_weight"] = _save_l(
            v02_maps_dir / f"v02_forehead_tone_{label}_weight.png",
            v02_maps[f"{label}_weight"],
        )

    v02_review_tiles = [
        ("v01 input", Image.fromarray(v01_texture, mode="RGB")),
        ("guard magenta", Image.fromarray(v02_maps["guard_rgb"], mode="RGB")),
        ("forehead skin green", Image.fromarray(v02_maps["forehead_skin_rgb"], mode="RGB")),
        ("tone candidates yellow", Image.fromarray(v02_maps["tone_candidate_rgb"], mode="RGB")),
        ("combined overlay", Image.fromarray(v02_maps["combined_overlay"], mode="RGB")),
        ("reference skin blue", Image.fromarray(v02_maps["reference_skin_rgb"], mode="RGB")),
        ("forehead reference", Image.fromarray(v02_maps["forehead_good_rgb"], mode="RGB")),
        ("edge feather", Image.fromarray(v02_maps["edge_feather"], mode="L").convert("RGB")),
        ("v02 light", Image.fromarray(v02_maps["light_texture"], mode="RGB")),
        ("v02 medium", Image.fromarray(v02_maps["medium_texture"], mode="RGB")),
        ("v02 strong", Image.fromarray(v02_maps["strong_texture"], mode="RGB")),
        ("medium changed orange", Image.fromarray(v02_maps["medium_changed_overlay"], mode="RGB")),
        ("medium weight", Image.fromarray(v02_maps["medium_weight"], mode="L").convert("RGB")),
    ]
    v02_uv_review = v02_dir / "step6_v02_forehead_tone_uv_review_sheet.png"
    _make_grid_sheet(
        f"{person} Step 6 v02 forehead tone UV review",
        "Magenta=guard, green=forehead skin to repair, yellow=stronger tone candidates. Eyes/brows/hairline are excluded.",
        v02_review_tiles,
        v02_uv_review,
        columns=4,
    )
    v02_paths["uv_review_sheet"] = _safe_path(v02_uv_review)

    if not args.skip_render:
        forehead_mask_texture_path = v02_maps_dir / "v02_forehead_skin_render_texture.png"
        _save_rgb(forehead_mask_texture_path, v02_maps["combined_mask_rgb"])
        v02_paths["forehead_mask_render"] = _render_stage(
            person=person,
            stage="v02_forehead_mask",
            texture_path=forehead_mask_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v02_dir,
            args=args,
        )
        for label in ("light", "medium", "strong"):
            v02_paths[f"{label}_render"] = _render_stage(
                person=person,
                stage=f"v02_forehead_{label}",
                texture_path=_as_path(v02_paths[f"{label}_texture"]),
                source_person_dir=source_person_dir,
                output_dir=v02_dir,
                args=args,
            )

    person_summary["stages"]["v02_forehead_tone"] = {
        "logic": "protect facial/hairline boundaries, select forehead skin, then gently normalize forehead tone in light/medium/strong variants",
        "paths": v02_paths,
        "metrics": v02_meta,
    }
    _write_json(output_dir / "step6_person_summary.json", person_summary)
    return person_summary


def _build_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Step 6 Postprocess Report",
        "",
        f"- Created at: `{summary['created_at']}`",
        f"- Step 5 root: `{summary['step5_root']}`",
        f"- Output: `{summary['output_dir']}`",
        f"- Baseline: Step 5 `blend` texture",
        "",
        "## v01_hard_skin_holes",
        "",
        "Only small black COMPLETION_NEEDED holes surrounded by reliable skin-like texels are filled.",
        "Eyes, mouth, brows, nostrils, scalp, and clothing regions are intentionally excluded by conservative size/distance/color gates.",
        "",
    ]
    for person in summary["people"]:
        stage = person["stages"]["v01_hard_skin_holes"]
        metrics = stage["metrics"]
        paths = stage["paths"]
        lines.extend([
            f"### {person['person']}",
            "",
            f"- UV review: `{paths.get('uv_review_sheet')}`",
            f"- Render review: `{paths.get('v01_render', {}).get('render_review_sheet')}`",
            f"- Changed render: `{paths.get('changed_overlay_render', {}).get('render_review_sheet')}`",
            f"- Reliable skin texels: {metrics['reliable_skin_texels']}",
            f"- Completion texels: {metrics['completion_texels']}",
            f"- Candidate texels before component filter: {metrics['candidate_texels_before_component_filter']}",
            f"- Feature-protected texels: {metrics['feature_protected_texels']}",
            f"- Filled texels: {metrics['filled_texels']}",
            f"- Components kept/rejected: {metrics['components_kept']} / {metrics['components_rejected']}",
            f"- Largest kept component area: {metrics['largest_kept_component_area']}",
            "",
        ])
    lines.extend([
        "## v02_forehead_tone",
        "",
        "Eyes, brows, mouth-like dark features, and hairline/scalp boundaries are protected first.",
        "The remaining forehead skin is repaired in three strengths: light, medium, and strong.",
        "",
    ])
    for person in summary["people"]:
        stage = person["stages"].get("v02_forehead_tone", {})
        if not stage:
            continue
        metrics = stage["metrics"]
        paths = stage["paths"]
        variant_metrics = metrics["variant_metrics"]
        lines.extend([
            f"### {person['person']}",
            "",
            f"- UV review: `{paths.get('uv_review_sheet')}`",
            f"- Forehead mask render: `{paths.get('forehead_mask_render', {}).get('render_review_sheet')}`",
            f"- Light render: `{paths.get('light_render', {}).get('render_review_sheet')}`",
            f"- Medium render: `{paths.get('medium_render', {}).get('render_review_sheet')}`",
            f"- Strong render: `{paths.get('strong_render', {}).get('render_review_sheet')}`",
            f"- Forehead skin texels: {metrics['forehead_skin_texels']}",
            f"- Guard texels: {metrics['guard_texels']}",
            f"- Tone candidate texels: {metrics['tone_candidate_texels']}",
            f"- Target RGB: {[round(x, 2) for x in metrics['target_rgb']]}",
            f"- Changed texels light/medium/strong: {variant_metrics['light']['changed_texels']} / {variant_metrics['medium']['changed_texels']} / {variant_metrics['strong']['changed_texels']}",
            "",
        ])
    return "\n".join(lines)


def _compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metrics.items() if not key.endswith("_preview")}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    people = args.person or list(PERSONS)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    step5_root = args.step5_root or _find_latest_step5(args.drive_root, people)
    output_root = args.output_dir or (args.drive_root / "output" / "facebuilder_mask_aware_step6" / stamp)

    summary: dict[str, Any] = {
        "schema_version": "facebuilder_mask_aware_step6_postprocess_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": _safe_path(REPO_ROOT),
        "drive_root": _safe_path(args.drive_root),
        "source_version": args.source_version,
        "step5_root": _safe_path(step5_root),
        "output_dir": _safe_path(output_root),
        "blender_exe": _safe_path(args.blender_exe),
        "people": [],
        "stages": ["v00_baseline", "v01_hard_skin_holes", "v02_forehead_tone"],
        "parameters": {
            "close_radius": int(args.close_radius),
            "max_fill_distance": float(args.max_fill_distance),
            "max_component_area": int(args.max_component_area),
            "max_component_width": int(args.max_component_width),
            "max_component_height": int(args.max_component_height),
            "forehead_x_min": float(args.forehead_x_min),
            "forehead_x_max": float(args.forehead_x_max),
            "forehead_y_min": float(args.forehead_y_min),
            "forehead_y_max": float(args.forehead_y_max),
            "skip_baseline_renders": bool(args.skip_baseline_renders),
        },
    }

    for person in people:
        person_summary = _process_person(person, step5_root / person, output_root / person, args)
        summary["people"].append(person_summary)

    summary_json = output_root / "step6_summary.json"
    report_md = output_root / "step6_report.md"
    _write_json(summary_json, summary)
    report_md.write_text(_build_report(summary), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "output_dir": _safe_path(output_root),
        "summary": _safe_path(summary_json),
        "people": [
            {
                "person": item["person"],
                "uv_review": item["stages"]["v01_hard_skin_holes"]["paths"].get("uv_review_sheet"),
                "render_review": item["stages"]["v01_hard_skin_holes"]["paths"].get("v01_render", {}).get("render_review_sheet"),
                "changed_render": item["stages"]["v01_hard_skin_holes"]["paths"].get("changed_overlay_render", {}).get("render_review_sheet"),
                "metrics": _compact_metrics(item["stages"]["v01_hard_skin_holes"]["metrics"]),
                "v02_uv_review": item["stages"].get("v02_forehead_tone", {}).get("paths", {}).get("uv_review_sheet"),
                "v02_medium_render": item["stages"].get("v02_forehead_tone", {}).get("paths", {}).get("medium_render", {}).get("render_review_sheet"),
                "v02_metrics": _compact_metrics(item["stages"].get("v02_forehead_tone", {}).get("metrics", {})),
            }
            for item in summary["people"]
        ],
    }, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
