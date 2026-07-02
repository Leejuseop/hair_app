"""Run Step 6 material-specific texture post-processing.

Step 6 starts from the Step 5 blend texture. Each stage is intentionally narrow
and produces diagnostic review sheets. Implemented stages:

- `v01_hard_skin_holes`: only tiny black COMPLETION_NEEDED skin holes.
- `v02_forehead_tone`: protect eyes/brows/hairline, then repair forehead tone.
- `v03_forehead_uniform_tone`: unify forehead skin to non-forehead face skin tone.
- `v04_forehead_redefined_region`: redefine forehead by position, then fill hair leftovers.
- `v04b_eyebrow_hairline_refine`: component-scored eyebrow guard, symmetric
  evidence-driven hairline lift, and eyebrow-baseline forehead definition.
- `v05_side_neck_temporary_skin`: fill side/temple/ear dark fragments and
  neck/jaw/clothing contamination with temporary skin material.
- `v06_simple_bald_skin_fill`: black out everything above the hairline, then
  keep good pixels and fill bad below-hairline pixels with simple skin.

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
    parser.add_argument("--skip-v02-renders", action="store_true")
    parser.add_argument("--skip-v03-renders", action="store_true")
    parser.add_argument("--skip-v04-renders", action="store_true")
    parser.add_argument("--skip-v04b-renders", action="store_true")
    parser.add_argument("--skip-v05-renders", action="store_true")
    parser.add_argument("--skip-v06-renders", action="store_true")
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


def _make_compact_before_after_sheet(
    *,
    person: str,
    title_stage: str,
    before_dir: Path,
    after_dir: Path,
    area_dir: Path | None,
    output_path: Path,
    legend: str,
    before_label: str = "before v01",
    after_label: str = "after v03",
    area_label: str = "area map",
    extra_rows: list[tuple[str, Path]] | None = None,
) -> str | None:
    yaw_items = [
        ("front", "+00"),
        ("left 45", "-45"),
        ("right 45", "+45"),
    ]
    rows: list[tuple[str, Path]] = [
        (before_label, before_dir),
        (after_label, after_dir),
    ]
    if area_dir is not None:
        rows.append((area_label, area_dir))
    if extra_rows:
        rows.extend(extra_rows)

    tile_w = 300
    band_h = 34
    row_label_w = 190
    gap = 12
    header_h = 96
    rendered_rows: list[tuple[str, list[Image.Image]]] = []
    for row_label, directory in rows:
        row_images: list[Image.Image] = []
        for col_label, yaw in yaw_items:
            image_path = directory / f"render_yaw_{yaw}.png"
            if not image_path.exists():
                return None
            image = Image.open(image_path).convert("RGB")
            row_images.append(_make_tile(col_label, image, width=tile_w))
        rendered_rows.append((row_label, row_images))

    tile_h = max(tile.height for _, row in rendered_rows for tile in row)
    width = row_label_w + len(yaw_items) * tile_w + (len(yaw_items) + 2) * gap
    height = header_h + len(rendered_rows) * tile_h + (len(rendered_rows) + 1) * gap
    sheet = Image.new("RGB", (width, height), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 12), f"{person} Step 6 {title_stage} compact review", fill=(245, 245, 245), font=_font(24))
    row_text = "Rows: before / after / area"
    if extra_rows:
        row_text += " / extra"
    draw.text((16, 48), row_text + ". " + legend, fill=(190, 190, 190), font=_font(14))
    draw.text((16, 70), "Main review sheet intentionally avoids UV atlas/debug maps.", fill=(160, 160, 160), font=_font(13))

    y = header_h + gap
    for row_label, row_images in rendered_rows:
        draw.text((gap, y + 12), row_label, fill=(235, 235, 235), font=_font(15))
        x = row_label_w + gap
        for tile in row_images:
            sheet.paste(tile, (x, y))
            x += tile_w + gap
        y += tile_h + gap

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, quality=95)
    return _safe_path(output_path)


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


def _render_stage_raw(
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
    result["stage"] = stage
    result["person"] = person
    return result


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


def _estimate_scan_hairline_ratio(image_path: Path, bounds: dict[str, Any] | None) -> dict[str, Any]:
    image = _load_rgb(image_path)
    arr = np.asarray(image, dtype=np.uint8)
    h, w = arr.shape[:2]
    if bounds:
        x0 = int(np.clip(float(bounds.get("minX", 0.28)) * w, 0, w - 1))
        x1 = int(np.clip(float(bounds.get("maxX", 0.72)) * w, x0 + 1, w))
        y0 = int(np.clip(float(bounds.get("minY", 0.18)) * h, 0, h - 1))
        y1 = int(np.clip(float(bounds.get("maxY", 0.88)) * h, y0 + 1, h))
    else:
        x0, x1 = int(w * 0.28), int(w * 0.72)
        y0, y1 = int(h * 0.18), int(h * 0.88)

    crop = arr[y0:y1, x0:x1]
    if crop.size == 0:
        return {"ok": False, "reason": "empty_crop"}

    rgb = crop.astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    cb = 128.0 - 0.168736 * rgb[..., 0] - 0.331264 * rgb[..., 1] + 0.5 * rgb[..., 2]
    cr = 128.0 + 0.5 * rgb[..., 0] - 0.418688 * rgb[..., 1] - 0.081312 * rgb[..., 2]
    skin = (luma > 72.0) & (cb > 72.0) & (cb < 154.0) & (cr > 112.0) & (cr < 190.0)
    skin = ndimage.binary_opening(skin, structure=_disk(2))
    skin = ndimage.binary_closing(skin, structure=_disk(3))

    ch, cw = skin.shape
    x_start = int(cw * 0.18)
    x_stop = int(cw * 0.82)
    y_stop = int(ch * 0.42)
    samples: list[float] = []
    for x in range(x_start, x_stop, max(1, cw // 90)):
        column = skin[:y_stop, max(0, x - 2) : min(cw, x + 3)]
        if column.size == 0:
            continue
        row_scores = column.mean(axis=1)
        stable = ndimage.uniform_filter1d(row_scores.astype(np.float32), size=7)
        hits = np.where(stable > 0.42)[0]
        if hits.size:
            samples.append(float(hits[0]) / max(1, ch))

    if not samples:
        return {
            "ok": False,
            "reason": "no_skin_transition",
            "image_path": _safe_path(image_path),
            "crop_bounds_px": [x0, y0, x1, y1],
        }

    ratio = float(np.median(np.asarray(samples, dtype=np.float32)))
    spread = float(np.percentile(samples, 75) - np.percentile(samples, 25))
    return {
        "ok": True,
        "image_path": _safe_path(image_path),
        "crop_bounds_px": [x0, y0, x1, y1],
        "estimated_hairline_skin_start_ratio": ratio,
        "sample_count": len(samples),
        "sample_iqr": spread,
        "usage": "hairline boundary hint only; never used as texture/color source",
    }


def _find_scan_hairline_hint(person: str, drive_root: Path) -> dict[str, Any]:
    if person != "juseop":
        return {"used": False, "reason": "no_scan_hairline_reference_for_person"}

    candidates: list[tuple[Path, dict[str, Any] | None, str]] = []
    input_root = drive_root / "input"
    person_tokens = ("juseop", "\uc8fc\uc12d")
    if input_root.exists():
        for image_path in sorted(input_root.rglob("*hairline*.*")):
            suffix = image_path.suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            path_text = str(image_path).lower()
            if not any(token.lower() in path_text for token in person_tokens):
                continue
            candidates.append((image_path, None, "drive_input_hairline_scan"))

    best: dict[str, Any] | None = None
    for image_path, bounds, source in candidates:
        estimate = _estimate_scan_hairline_ratio(image_path, bounds)
        estimate["source"] = source
        if not estimate.get("ok"):
            continue
        if best is None or int(estimate.get("sample_count", 0)) > int(best.get("sample_count", 0)):
            best = estimate

    if best is None:
        return {
            "used": False,
            "reason": "no_valid_hairline_scan_hint_found",
            "candidate_count": len(candidates),
        }

    best["used"] = True
    best["candidate_count"] = len(candidates)
    return best


def _trimmed_mean_rgb(texture: np.ndarray, mask: np.ndarray, fallback: np.ndarray) -> tuple[np.ndarray, int]:
    pixels = texture[mask].astype(np.float32)
    if pixels.shape[0] == 0:
        return fallback.astype(np.float32), 0
    luma = pixels[:, 0] * 0.2126 + pixels[:, 1] * 0.7152 + pixels[:, 2] * 0.0722
    lo = np.percentile(luma, 30.0)
    hi = np.percentile(luma, 92.0)
    keep = (luma >= lo) & (luma <= hi)
    if int(keep.sum()) >= 32:
        pixels = pixels[keep]
    return pixels.mean(axis=0).astype(np.float32), int(pixels.shape[0])


def _lower_feature_guard(
    texture: np.ndarray,
    decision: np.ndarray,
    reliable_skin: np.ndarray,
    roi: np.ndarray,
    yy: np.ndarray,
    y_min: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    h = decision.shape[0]
    rgb = texture.astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    lower_band = yy >= int(h * (y_min + 0.055))
    skin_near = ndimage.binary_dilation(reliable_skin, structure=_disk(9))
    dark = (decision == COMPLETION_NEEDED) & (luma < 70.0) & roi & lower_band & skin_near
    dark = ndimage.binary_closing(dark, structure=_disk(2))
    labels, count = ndimage.label(dark)
    guard = np.zeros(dark.shape, dtype=bool)
    components: list[dict[str, Any]] = []
    for label_id, slices in enumerate(ndimage.find_objects(labels), start=1):
        if slices is None:
            continue
        ys, xs = slices
        component = labels[slices] == label_id
        area = int(component.sum())
        width = int(xs.stop - xs.start)
        height = int(ys.stop - ys.start)
        aspect = max(width / max(1, height), height / max(1, width))
        kept = area >= 20 and (width >= 7 or height >= 4)
        if kept:
            guard[slices][component] = True
        components.append({
            "label": label_id,
            "area": area,
            "width": width,
            "height": height,
            "aspect": float(aspect),
            "kept": bool(kept),
            "bbox": [int(xs.start), int(ys.start), int(xs.stop), int(ys.stop)],
        })
    guard = ndimage.binary_dilation(guard, structure=_disk(1))
    return guard, {
        "lower_feature_component_count": int(count),
        "lower_feature_components_kept": int(sum(1 for item in components if item["kept"])),
        "lower_feature_guard_texels": int(guard.sum()),
        "lower_feature_components_preview": components[:30],
    }


def _top_boundary(mask: np.ndarray) -> np.ndarray:
    if not np.any(mask):
        return np.zeros(mask.shape, dtype=bool)
    eroded = ndimage.binary_erosion(mask, structure=np.ones((5, 1), dtype=bool))
    boundary = mask & ~eroded
    y_indices, _ = np.indices(mask.shape)
    ys = np.where(mask, y_indices, mask.shape[0])
    top_y = ys.min(axis=0)
    near_top = y_indices <= (top_y.reshape(1, -1) + 5)
    return boundary & near_top


def _predict_smooth_hairline(
    reliable_skin: np.ndarray,
    roi: np.ndarray,
    *,
    x_min_px: int,
    x_max_px: int,
    y_min_px: int,
    y_max_px: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    h, w = reliable_skin.shape
    skin = ndimage.binary_closing(reliable_skin & roi, structure=_disk(4))
    skin = ndimage.binary_opening(skin, structure=_disk(2))
    sample_x: list[int] = []
    sample_y: list[int] = []
    step = max(1, (x_max_px - x_min_px) // 160)
    for x in range(x_min_px, x_max_px + 1, step):
        local = skin[y_min_px:y_max_px, max(0, x - 2) : min(w, x + 3)]
        if local.size == 0:
            continue
        row_score = local.mean(axis=1)
        smoothed = ndimage.uniform_filter1d(row_score.astype(np.float32), size=7)
        hits = np.where(smoothed > 0.24)[0]
        if hits.size:
            y = int(y_min_px + hits[0])
            if y_min_px - 8 <= y <= y_max_px:
                sample_x.append(x)
                sample_y.append(y)

    xs_full = np.arange(w, dtype=np.float32)
    curve = np.full(w, float(y_min_px + max(4, int(h * 0.015))), dtype=np.float32)
    fit_mode = "fallback_arc"
    used_samples = 0
    rejected_samples = 0

    if len(sample_x) >= 12:
        sx = np.asarray(sample_x, dtype=np.float32)
        sy = np.asarray(sample_y, dtype=np.float32)
        center = (x_min_px + x_max_px) * 0.5
        scale = max(1.0, (x_max_px - x_min_px) * 0.5)
        tx = (sx - center) / scale
        coeff = np.polyfit(tx, sy, deg=2)
        pred = np.polyval(coeff, tx)
        residual = np.abs(sy - pred)
        cutoff = max(6.0, float(np.percentile(residual, 75.0)) * 1.8)
        keep = residual <= cutoff
        rejected_samples = int((~keep).sum())
        if int(keep.sum()) >= 10:
            coeff = np.polyfit(tx[keep], sy[keep], deg=2)
            fit_mode = "robust_quadratic"
            used_samples = int(keep.sum())
        else:
            used_samples = int(len(sample_x))

        full_tx = (xs_full - center) / scale
        curve = np.polyval(coeff, full_tx).astype(np.float32)

        # A real frontal hairline should be a smooth arc: center slightly
        # higher, sides slightly lower. If noisy samples invert that curve,
        # keep the observed center height and impose a conservative arc.
        side_probe = np.asarray([
            curve[int(np.clip(x_min_px, 0, w - 1))],
            curve[int(np.clip(x_max_px, 0, w - 1))],
        ])
        center_y = float(curve[int(np.clip(round(center), 0, w - 1))])
        min_side_drop = float(h * 0.018)
        if float(side_probe.mean()) < center_y + min_side_drop:
            t = (xs_full - center) / scale
            curve = center_y + min_side_drop + (np.clip(np.abs(t), 0.0, 1.0) ** 2) * float(h * 0.024)
            fit_mode = "arc_enforced_after_flat_or_inverted_fit"
    else:
        center = (x_min_px + x_max_px) * 0.5
        scale = max(1.0, (x_max_px - x_min_px) * 0.5)
        t = (xs_full - center) / scale
        curve = float(y_min_px + h * 0.012) + (np.clip(np.abs(t), 0.0, 1.0) ** 2) * float(h * 0.038)

    curve = ndimage.gaussian_filter1d(curve, sigma=8.0)
    active_curve = curve[x_min_px:x_max_px + 1] if x_max_px >= x_min_px else curve
    if active_curve.size and float(active_curve.max() - active_curve.min()) < float(h * 0.012):
        center = (x_min_px + x_max_px) * 0.5
        scale = max(1.0, (x_max_px - x_min_px) * 0.5)
        t = (xs_full - center) / scale
        median_y = float(np.median(active_curve))
        center_y = median_y - float(h * 0.026)
        curve = center_y + (np.clip(np.abs(t), 0.0, 1.0) ** 2) * float(h * 0.055)
        fit_mode = f"{fit_mode}_human_arc_from_flat_profile"
    curve = np.clip(curve, y_min_px - int(h * 0.012), y_max_px - int(h * 0.010))

    line = np.zeros_like(reliable_skin, dtype=bool)
    for x in range(max(0, x_min_px), min(w, x_max_px + 1)):
        y = int(np.clip(round(float(curve[x])), 0, h - 1))
        y0 = max(0, y - 1)
        y1 = min(h, y + 2)
        line[y0:y1, x] = True

    return curve, line, {
        "hairline_fit_mode": fit_mode,
        "hairline_sample_count": int(len(sample_x)),
        "hairline_samples_used": int(used_samples or len(sample_x)),
        "hairline_samples_rejected": rejected_samples,
        "hairline_curve_y_min_px": float(curve[x_min_px:x_max_px + 1].min()) if x_max_px >= x_min_px else 0.0,
        "hairline_curve_y_max_px": float(curve[x_min_px:x_max_px + 1].max()) if x_max_px >= x_min_px else 0.0,
    }


def _eye_brow_guard_for_redefined_forehead(
    texture: np.ndarray,
    decision: np.ndarray,
    reliable_skin: np.ndarray,
    roi: np.ndarray,
    yy: np.ndarray,
    *,
    y_min_px: int,
    y_bottom_px: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    h, _ = decision.shape
    rgb = texture.astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    skin_near = ndimage.binary_dilation(reliable_skin, structure=_disk(10))
    feature_band = (yy >= y_min_px + int(h * 0.045)) & (yy <= y_bottom_px)
    dark = (((decision == COMPLETION_NEEDED) & (luma < 84.0)) | (luma < 48.0)) & roi & feature_band & skin_near
    dark = ndimage.binary_closing(dark, structure=_disk(2))
    dark = ndimage.binary_opening(dark, structure=_disk(1))

    labels, count = ndimage.label(dark)
    guard = np.zeros(dark.shape, dtype=bool)
    components: list[dict[str, Any]] = []
    for label_id, slices in enumerate(ndimage.find_objects(labels), start=1):
        if slices is None:
            continue
        ys, xs = slices
        component = labels[slices] == label_id
        area = int(component.sum())
        width = int(xs.stop - xs.start)
        height = int(ys.stop - ys.start)
        center_y = float((ys.start + ys.stop) * 0.5)
        aspect = float(width / max(1, height))
        horizontal_feature = width >= 14 and height <= max(16, int(h * 0.025)) and aspect >= 1.55
        eye_like_blob = area >= 70 and center_y >= y_min_px + h * 0.075 and height <= int(h * 0.055)
        kept = bool(horizontal_feature or eye_like_blob)
        if kept:
            guard[slices][component] = True
        components.append({
            "label": label_id,
            "area": area,
            "width": width,
            "height": height,
            "center_y": center_y,
            "aspect": aspect,
            "horizontal_feature": bool(horizontal_feature),
            "eye_like_blob": bool(eye_like_blob),
            "kept": kept,
            "bbox": [int(xs.start), int(ys.start), int(xs.stop), int(ys.stop)],
        })

    guard = ndimage.binary_dilation(guard, structure=_disk(2))
    return guard, {
        "eye_brow_component_count": int(count),
        "eye_brow_components_kept": int(sum(1 for item in components if item["kept"])),
        "eye_brow_guard_texels": int(guard.sum()),
        "eye_brow_components_preview": components[:30],
    }


def _line_from_curve(
    curve: np.ndarray,
    shape: tuple[int, int],
    *,
    x_min_px: int,
    x_max_px: int,
    thickness: int = 1,
) -> np.ndarray:
    h, w = shape
    line = np.zeros((h, w), dtype=bool)
    radius = max(0, int(thickness))
    for x in range(max(0, x_min_px), min(w, x_max_px + 1)):
        y = int(np.clip(round(float(curve[x])), 0, h - 1))
        line[max(0, y - radius) : min(h, y + radius + 1), x] = True
    return line


def _lift_hairline_over_observed_skin(
    first_curve: np.ndarray,
    reliable_skin: np.ndarray,
    face_support: np.ndarray,
    yy: np.ndarray,
    xx: np.ndarray,
    *,
    x_min_px: int,
    x_max_px: int,
    y_min_px: int,
    y_bottom_px: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    h, w = reliable_skin.shape
    span = max(1, x_max_px - x_min_px)
    front_left = int(round(x_min_px + span * 0.16))
    front_right = int(round(x_max_px - span * 0.16))
    front_left = int(np.clip(front_left, x_min_px, x_max_px))
    front_right = int(np.clip(front_right, front_left + 1, x_max_px))

    natural_curve = first_curve.copy().astype(np.float32)
    front_x = np.arange(front_left, front_right + 1)
    if front_x.size >= 4:
        # Frontal hairlines are usually flatter than a pure circular arc.
        # Keep the first curve as the source shape, but reduce the front
        # curvature by blending toward a symmetric low-slope front line.
        left_y = float(np.percentile(first_curve[front_left : min(w, front_left + max(2, span // 18))], 45.0))
        right_y = float(np.percentile(first_curve[max(0, front_right - max(2, span // 18)) : front_right + 1], 45.0))
        front_level = (left_y + right_y) * 0.5
        low_curve_line = np.full(front_x.shape, front_level, dtype=np.float32)
        natural_curve[front_x] = first_curve[front_x].astype(np.float32) * 0.34 + low_curve_line * 0.66
        natural_curve[front_x] = ndimage.gaussian_filter1d(natural_curve[front_x], sigma=5.0)

    first_lookup = natural_curve[np.clip(xx, 0, w - 1)]
    upper_limit = max(0, y_min_px - int(h * 0.030))
    skin_above_first = (
        reliable_skin
        & face_support
        & (xx >= front_left)
        & (xx <= front_right)
        & (yy >= upper_limit)
        & (yy < first_lookup - 2.0)
        & (yy <= y_bottom_px)
    )
    skin_above_first = ndimage.binary_opening(skin_above_first, structure=_disk(1))

    max_lift = float(h * 0.070)
    min_column_pixels = max(3, int(h * 0.003))
    column_counts = skin_above_first.sum(axis=0)
    supported = np.zeros(w, dtype=bool)
    supported[front_left : front_right + 1] = column_counts[front_left : front_right + 1] >= min_column_pixels

    lift_delta = np.zeros(w, dtype=np.float32)
    if np.any(supported):
        ys, xs = np.where(skin_above_first & supported.reshape(1, -1))
        if ys.size:
            top_by_x: list[float] = []
            for x in np.unique(xs):
                y_values = ys[xs == x]
                if y_values.size >= min_column_pixels:
                    top_by_x.append(float(np.percentile(y_values, 8.0)))
            if top_by_x:
                observed_top = float(np.percentile(np.asarray(top_by_x, dtype=np.float32), 14.0))
                curve_reference = float(np.percentile(natural_curve[supported], 42.0))
                lift_amount = float(np.clip(curve_reference - (observed_top - 2.0), 0.0, max_lift))
                if lift_amount >= 3.0:
                    supported_x = np.where(supported)[0]
                    margin = int(max(8, span * 0.08))
                    lift_x0 = int(np.clip(supported_x.min() - margin, front_left, front_right))
                    lift_x1 = int(np.clip(supported_x.max() + margin, front_left, front_right))
                    center = (lift_x0 + lift_x1) * 0.5
                    half = max(1.0, (lift_x1 - lift_x0) * 0.5)
                    active_x = np.arange(lift_x0, lift_x1 + 1)
                    distance = np.clip(np.abs(active_x - center) / half, 0.0, 1.0)
                    profile = 0.5 + 0.5 * np.cos(distance * np.pi)
                    lift_delta[active_x] = (lift_amount * profile).astype(np.float32)
                    lift_delta = ndimage.gaussian_filter1d(lift_delta, sigma=7.5)

    # If reliable forehead skin appears above the first line on only one side,
    # use that evidence to lift the opposite side too. A frontal hairline can be
    # imperfect, but this diagnostic bald-head pass must not create an obviously
    # one-sided forehead boundary from a one-sided observation.
    symmetric_lift_delta = lift_delta.copy()
    if front_x.size >= 4 and np.any(lift_delta[front_left : front_right + 1] > 0.8):
        center = (front_left + front_right) * 0.5
        for x in range(front_left, front_right + 1):
            mirror_x = int(round(2.0 * center - x))
            if mirror_x < front_left or mirror_x > front_right:
                continue
            paired = max(float(symmetric_lift_delta[x]), float(symmetric_lift_delta[mirror_x]))
            symmetric_lift_delta[x] = paired
            symmetric_lift_delta[mirror_x] = paired
        symmetric_lift_delta[front_left : front_right + 1] = ndimage.gaussian_filter1d(
            symmetric_lift_delta[front_left : front_right + 1],
            sigma=5.0,
        )

    lifted_curve = natural_curve.astype(np.float32) - symmetric_lift_delta.astype(np.float32)
    if front_x.size >= 4:
        symmetric_curve = lifted_curve.copy()
        center = (front_left + front_right) * 0.5
        for x in range(front_left, front_right + 1):
            mirror_x = int(round(2.0 * center - x))
            if mirror_x < front_left or mirror_x > front_right:
                continue
            # Smaller y means a higher hairline in image space. Use the higher
            # of the paired positions so visible forehead skin is not cut away.
            paired_y = min(float(symmetric_curve[x]), float(symmetric_curve[mirror_x]))
            symmetric_curve[x] = paired_y
            symmetric_curve[mirror_x] = paired_y
        lifted_curve[front_left : front_right + 1] = ndimage.gaussian_filter1d(
            symmetric_curve[front_left : front_right + 1],
            sigma=4.0,
        )
    lifted_curve = np.minimum(lifted_curve, natural_curve)
    lifted_curve = np.clip(lifted_curve, y_min_px - int(h * 0.030), y_bottom_px - int(h * 0.010))

    final_line = _line_from_curve(
        lifted_curve,
        reliable_skin.shape,
        x_min_px=x_min_px,
        x_max_px=x_max_px,
        thickness=1,
    )
    lifted_columns = int(np.count_nonzero(symmetric_lift_delta[max(0, x_min_px) : min(w, x_max_px + 1)] > 0.8))
    return lifted_curve, final_line, skin_above_first, {
        "hairline_lift_candidate_texels": int(skin_above_first.sum()),
        "hairline_lift_supported_columns": int(np.count_nonzero(supported)),
        "hairline_lift_smoothed_columns": lifted_columns,
        "hairline_lift_max_px": float(symmetric_lift_delta.max()) if symmetric_lift_delta.size else 0.0,
        "hairline_lift_mean_px_on_lifted_columns": (
            float(symmetric_lift_delta[symmetric_lift_delta > 0.8].mean())
            if np.any(symmetric_lift_delta > 0.8)
            else 0.0
        ),
        "hairline_lift_raw_lifted_columns_before_symmetry": int(
            np.count_nonzero(lift_delta[max(0, x_min_px) : min(w, x_max_px + 1)] > 0.8)
        ),
        "hairline_front_left_px": int(front_left),
        "hairline_front_right_px": int(front_right),
        "hairline_shape_mode": "front_curve_flattened_then_symmetric_broad_lifted",
    }


def _eyebrow_side_stats(mask: np.ndarray) -> dict[str, Any]:
    if not np.any(mask):
        return {
            "area": 0,
            "width": 0,
            "height": 0,
            "bbox": None,
            "center_x": None,
            "center_y": None,
        }
    ys, xs = np.where(mask)
    return {
        "area": int(mask.sum()),
        "width": int(xs.max() - xs.min() + 1),
        "height": int(ys.max() - ys.min() + 1),
        "bbox": [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)],
        "center_x": float(xs.mean()),
        "center_y": float(ys.mean()),
    }


def _soft_range_score(value: float, low: float, high: float, falloff: float) -> float:
    if low <= value <= high:
        return 1.0
    if value < low:
        return float(np.clip(1.0 - (low - value) / max(1e-6, falloff), 0.0, 1.0))
    return float(np.clip(1.0 - (value - high) / max(1e-6, falloff), 0.0, 1.0))


def _score_eyebrow_component(
    *,
    area: int,
    width: int,
    height: int,
    aspect: float,
    center_y: float,
    bbox: list[int],
    side: str,
    h: int,
    w: int,
    brow_top: int,
    brow_bottom: int,
) -> dict[str, Any]:
    band_h = max(1.0, float(brow_bottom - brow_top))
    rel_y = (float(center_y) - float(brow_top)) / band_h
    area_rel = float(area) / float(max(1, h * w))
    width_rel = float(width) / float(max(1, w))
    height_rel = float(height) / float(max(1, h))

    width_score = _soft_range_score(width_rel, 0.045, 0.095, 0.035)
    height_score = _soft_range_score(height_rel, 0.009, 0.024, 0.012)
    area_score = _soft_range_score(area_rel, 0.00018, 0.00115, 0.00065)
    aspect_score = _soft_range_score(aspect, 2.4, 6.0, 1.8)
    vertical_score = _soft_range_score(rel_y, 0.58, 0.90, 0.22)

    too_wide = width_rel > 0.110
    too_tall = height_rel > 0.030
    too_big = area_rel > 0.00145
    too_high = rel_y < 0.45
    top_touch = bbox[1] <= brow_top + max(3, int(h * 0.006))
    size_penalty = 0.0
    if too_wide:
        size_penalty += 0.80
    if too_tall:
        size_penalty += 0.90
    if too_big:
        size_penalty += 0.95
    if too_high:
        size_penalty += 0.65
    if top_touch:
        size_penalty += 0.35

    score = width_score + height_score + area_score + aspect_score + vertical_score - size_penalty
    classification = "good"
    if area < 18 or width < 8:
        classification = "missing"
    elif score < 3.15 or too_tall or (too_wide and too_big) or too_high:
        classification = "bad"

    return {
        "side": side,
        "score": float(score),
        "classification": classification,
        "width_score": float(width_score),
        "height_score": float(height_score),
        "area_score": float(area_score),
        "aspect_score": float(aspect_score),
        "vertical_score": float(vertical_score),
        "penalty": float(size_penalty),
        "relative_y_in_brow_band": float(rel_y),
        "width_rel": float(width_rel),
        "height_rel": float(height_rel),
        "area_rel": float(area_rel),
        "too_wide": bool(too_wide),
        "too_tall": bool(too_tall),
        "too_big": bool(too_big),
        "too_high": bool(too_high),
        "top_touch": bool(top_touch),
    }


def _mirror_mask_x(mask: np.ndarray, *, center_x: int, x_min_px: int, x_max_px: int) -> np.ndarray:
    h, w = mask.shape
    mirrored = np.zeros_like(mask, dtype=bool)
    ys, xs = np.where(mask)
    mirrored_x = np.rint(2 * center_x - xs).astype(np.int32)
    valid = (mirrored_x >= x_min_px) & (mirrored_x <= x_max_px) & (mirrored_x >= 0) & (mirrored_x < w)
    if np.any(valid):
        mirrored[ys[valid], mirrored_x[valid]] = True
    return mirrored


def _component_count_meta(mask: np.ndarray, prefix: str) -> dict[str, Any]:
    labels, count = ndimage.label(mask)
    areas: list[int] = []
    for slices in ndimage.find_objects(labels):
        if slices is None:
            continue
        component = labels[slices] > 0
        areas.append(int(component.sum()))
    areas.sort(reverse=True)
    return {
        f"{prefix}_component_count": int(count),
        f"{prefix}_components_kept": int(count),
        f"{prefix}_components_rejected": 0,
        f"{prefix}_component_filter_fallback_used": False,
        f"{prefix}_component_areas_preview": areas[:12],
    }


def _symmetrize_eyebrow_guard(
    texture: np.ndarray,
    decision: np.ndarray,
    reliable_skin: np.ndarray,
    guard: np.ndarray,
    roi: np.ndarray,
    yy: np.ndarray,
    xx: np.ndarray,
    *,
    x_min_px: int,
    x_max_px: int,
    y_min_px: int,
    y_bottom_px: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    h, w = guard.shape
    rgb = texture.astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    center_x = int(round((x_min_px + x_max_px) * 0.5))
    brow_top = max(0, y_min_px + int(h * 0.035))
    brow_bottom = min(h - 1, y_min_px + int(h * 0.135))
    brow_band = (
        (xx >= x_min_px)
        & (xx <= x_max_px)
        & (yy >= brow_top)
        & (yy <= brow_bottom)
        & roi
    )
    skin_context = ndimage.binary_dilation(reliable_skin, structure=_disk(16))
    dark_seed = (((decision == COMPLETION_NEEDED) & (luma < 104.0)) | (luma < 78.0)) & brow_band & skin_context
    seed = ((guard & brow_band) | dark_seed)
    seed = ndimage.binary_closing(seed, structure=_disk(2))
    seed = ndimage.binary_opening(seed, structure=_disk(1))

    labels, count = ndimage.label(seed)
    eyebrow_seed = np.zeros_like(seed, dtype=bool)
    components: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for label_id, slices in enumerate(ndimage.find_objects(labels), start=1):
        if slices is None:
            continue
        ys, xs = slices
        component = labels[slices] == label_id
        area = int(component.sum())
        width = int(xs.stop - xs.start)
        height = int(ys.stop - ys.start)
        aspect = float(width / max(1, height))
        center_y = float((ys.start + ys.stop) * 0.5)
        center_x_value = float((xs.start + xs.stop) * 0.5)
        side = "left" if center_x_value < center_x else "right"
        bbox = [int(xs.start), int(ys.start), int(xs.stop), int(ys.stop)]
        quality = _score_eyebrow_component(
            area=area,
            width=width,
            height=height,
            aspect=aspect,
            center_y=center_y,
            bbox=bbox,
            side=side,
            h=h,
            w=w,
            brow_top=brow_top,
            brow_bottom=brow_bottom,
        )
        # This is deliberately stricter than the first guard pass. A large dark
        # blob is often hair/occlusion, not a better eyebrow. Keep geometric
        # candidates for diagnostics, but only good-scoring components can drive
        # the mirrored eyebrow mask.
        geom_kept = (
            area >= 18
            and width >= 8
            and height <= max(28, int(h * 0.036))
            and aspect >= 1.35
            and quality["relative_y_in_brow_band"] >= 0.42
        )
        component_full = np.zeros_like(seed, dtype=bool)
        if geom_kept:
            view = component_full[slices]
            view[component] = True
            candidate_mask = ndimage.binary_closing(component_full, structure=_disk(1))
            candidate_mask = ndimage.binary_dilation(candidate_mask, structure=_disk(1)) & brow_band
            eyebrow_seed |= candidate_mask
            candidates.append({
                "label": int(label_id),
                "side": side,
                "score": float(quality["score"]),
                "classification": quality["classification"],
                "mask": candidate_mask,
                "area": area,
                "width": width,
                "height": height,
                "aspect": aspect,
                "center_x": center_x_value,
                "center_y": center_y,
                "bbox": bbox,
                "quality": quality,
            })
        components.append({
            "label": int(label_id),
            "area": area,
            "width": width,
            "height": height,
            "aspect": aspect,
            "side": side,
            "score": float(quality["score"]),
            "classification": quality["classification"],
            "center_y": center_y,
            "kept": bool(geom_kept),
            "bbox": bbox,
            "quality": quality,
        })

    eyebrow_seed = ndimage.binary_closing(eyebrow_seed, structure=_disk(1)) & brow_band
    left = eyebrow_seed & (xx < center_x)
    right = eyebrow_seed & (xx > center_x)
    left_stats = _eyebrow_side_stats(left)
    right_stats = _eyebrow_side_stats(right)
    left_area = int(left_stats["area"])
    right_area = int(right_stats["area"])
    min_reasonable_area = 28
    ratio = float(min(left_area, right_area) / max(1, max(left_area, right_area)))

    symmetric_eyebrow_mask = np.zeros_like(guard, dtype=bool)
    symmetric_eyebrow_rgb = np.zeros_like(texture, dtype=np.uint8)
    mirror_mode = "none"
    mirror_source = np.zeros_like(guard, dtype=bool)
    black_brow_rgb = np.asarray([16, 13, 12], dtype=np.uint8)
    good_threshold = 3.15
    sorted_candidates = sorted(candidates, key=lambda item: float(item["score"]), reverse=True)
    left_candidates = [item for item in sorted_candidates if item["side"] == "left"]
    right_candidates = [item for item in sorted_candidates if item["side"] == "right"]
    left_best = left_candidates[0] if left_candidates else None
    right_best = right_candidates[0] if right_candidates else None
    selected_source: dict[str, Any] | None = None

    left_good = bool(left_best and left_best["classification"] == "good" and float(left_best["score"]) >= good_threshold)
    right_good = bool(right_best and right_best["classification"] == "good" and float(right_best["score"]) >= good_threshold)
    if left_good and right_good:
        score_gap = abs(float(left_best["score"]) - float(right_best["score"]))
        width_ratio = min(float(left_best["width"]), float(right_best["width"])) / max(1.0, max(float(left_best["width"]), float(right_best["width"])))
        height_ratio = min(float(left_best["height"]), float(right_best["height"])) / max(1.0, max(float(left_best["height"]), float(right_best["height"])))
        if score_gap <= 0.55 and width_ratio >= 0.72 and height_ratio >= 0.62:
            symmetric_eyebrow_mask = left_best["mask"] | right_best["mask"]
            mirror_mode = "both_good_keep_component_masks"
        else:
            selected_source = left_best if float(left_best["score"]) >= float(right_best["score"]) else right_best
    elif left_good:
        selected_source = left_best
    elif right_good:
        selected_source = right_best
    elif sorted_candidates and float(sorted_candidates[0]["score"]) >= 2.45:
        selected_source = sorted_candidates[0]

    if selected_source is not None:
        mirror_source = selected_source["mask"]
        mirrored = _mirror_mask_x(mirror_source, center_x=center_x, x_min_px=x_min_px, x_max_px=x_max_px)
        symmetric_eyebrow_mask = (mirror_source | mirrored) & brow_band
        symmetric_eyebrow_mask = ndimage.binary_closing(symmetric_eyebrow_mask, structure=_disk(1))
        symmetric_eyebrow_mask = ndimage.binary_opening(symmetric_eyebrow_mask, structure=_disk(1)) & brow_band
        mirror_mode = f"{selected_source['side']}_component_to_symmetric_pair"

    if not np.any(symmetric_eyebrow_mask):
        symmetric_eyebrow_mask = eyebrow_seed
        mirror_mode = "fallback_all_component_seed"
    symmetric_eyebrow_rgb[symmetric_eyebrow_mask] = black_brow_rgb

    eye_keep_y = y_min_px + int(h * 0.102)
    rejected_brow_seed = eyebrow_seed & ~ndimage.binary_dilation(symmetric_eyebrow_mask, structure=_disk(4))
    eye_guard = guard & brow_band & (yy >= eye_keep_y) & ~rejected_brow_seed
    final_guard = ((guard & ~brow_band) | eye_guard | symmetric_eyebrow_mask) & roi
    final_guard = ndimage.binary_dilation(final_guard, structure=_disk(1)) & roi
    return final_guard, symmetric_eyebrow_mask, symmetric_eyebrow_rgb, {
        "eyebrow_symmetry_component_count": int(count),
        "eyebrow_symmetry_components_kept": int(sum(1 for item in components if item["kept"])),
        "eyebrow_left_area_texels": left_area,
        "eyebrow_right_area_texels": right_area,
        "eyebrow_left_stats": left_stats,
        "eyebrow_right_stats": right_stats,
        "eyebrow_area_ratio": ratio,
        "eyebrow_mirror_mode": mirror_mode,
        "eyebrow_mirrored_texels": int(symmetric_eyebrow_mask.sum()),
        "eyebrow_mirror_source_texels": int(mirror_source.sum()) if mirror_mode != "none" else 0,
        "eyebrow_good_threshold": float(good_threshold),
        "eyebrow_selected_source": (
            {
                "label": int(selected_source["label"]),
                "side": selected_source["side"],
                "score": float(selected_source["score"]),
                "classification": selected_source["classification"],
                "bbox": selected_source["bbox"],
                "width": int(selected_source["width"]),
                "height": int(selected_source["height"]),
                "area": int(selected_source["area"]),
            }
            if selected_source is not None
            else None
        ),
        "eyebrow_left_best": (
            {
                "label": int(left_best["label"]),
                "score": float(left_best["score"]),
                "classification": left_best["classification"],
                "bbox": left_best["bbox"],
                "width": int(left_best["width"]),
                "height": int(left_best["height"]),
                "area": int(left_best["area"]),
            }
            if left_best is not None
            else None
        ),
        "eyebrow_right_best": (
            {
                "label": int(right_best["label"]),
                "score": float(right_best["score"]),
                "classification": right_best["classification"],
                "bbox": right_best["bbox"],
                "width": int(right_best["width"]),
                "height": int(right_best["height"]),
                "area": int(right_best["area"]),
            }
            if right_best is not None
            else None
        ),
        "eyebrow_symmetry_texture_mode": "fixed_black_mask_no_color_transfer",
        "eyebrow_symmetry_components_preview": components[:30],
    }


def _step_v03_forehead_uniform_tone(
    base: np.ndarray,
    decision: np.ndarray,
    clean_score: np.ndarray,
    raw_score: np.ndarray,
    source_count: np.ndarray,
    *,
    forehead_y_min: float,
    forehead_y_max: float,
    forehead_x_min: float,
    forehead_x_max: float,
    scan_hairline_hint: dict[str, Any],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    reliable_skin = _broad_skin_mask(base, decision)
    h, w = decision.shape
    yy, xx = np.indices((h, w))
    y_shift = 0.0
    if scan_hairline_hint.get("used"):
        ratio = float(scan_hairline_hint.get("estimated_hairline_skin_start_ratio", 0.16))
        y_shift = float(np.clip((ratio - 0.16) * 0.08, -0.012, 0.014))
    y_min = float(np.clip(forehead_y_min + y_shift, 0.24, 0.38))
    y_max = float(np.clip(max(forehead_y_max - 0.005, y_min + 0.08), y_min + 0.08, 0.46))
    x_min = float(max(0.26, forehead_x_min))
    x_max = float(min(0.74, forehead_x_max))
    roi = (
        (xx >= int(w * x_min))
        & (xx <= int(w * x_max))
        & (yy >= int(h * y_min))
        & (yy <= int(h * y_max))
    )
    max_score = np.maximum(clean_score.astype(np.float32), raw_score.astype(np.float32))
    lower_guard, lower_meta = _lower_feature_guard(base, decision, reliable_skin, roi, yy, y_min)

    forehead_skin = reliable_skin & roi & ~lower_guard
    forehead_skin = ndimage.binary_closing(forehead_skin, structure=_disk(2)) & reliable_skin & roi & ~lower_guard
    forehead_skin, component_meta = _keep_central_forehead_components(forehead_skin)
    hairline_edge = _top_boundary(forehead_skin)

    ref_roi = (
        reliable_skin
        & ~forehead_skin
        & ~lower_guard
        & (xx >= int(w * 0.24))
        & (xx <= int(w * 0.76))
        & (yy >= int(h * 0.44))
        & (yy <= int(h * 0.62))
        & (max_score > 0.22)
        & (source_count.astype(np.float32) >= 1.0)
    )
    fallback = np.asarray([150.0, 105.0, 88.0], dtype=np.float32)
    face_mean, face_ref_count = _trimmed_mean_rgb(base, ref_roi, fallback)

    edge_feather = np.clip(ndimage.distance_transform_edt(forehead_skin).astype(np.float32) / 6.0, 0.0, 1.0)
    weight = np.where(forehead_skin, np.clip(0.32 + 0.68 * edge_feather, 0.0, 1.0), 0.0).astype(np.float32)
    uniform = base.copy()
    rgb = base.astype(np.float32)
    target = face_mean.reshape(1, 1, 3)
    mixed = rgb * (1.0 - weight[..., None]) + target * weight[..., None]
    uniform[forehead_skin] = np.clip(mixed[forehead_skin], 0.0, 255.0).astype(np.uint8)

    changed = np.any(uniform != base, axis=2)
    area_rgb = np.full_like(base, 28, dtype=np.uint8)
    area_rgb[forehead_skin] = (40, 210, 95)
    area_rgb[hairline_edge] = (245, 218, 38)
    area_rgb[lower_guard] = (58, 130, 245)
    area_overlay = base.copy()
    for mask, color, alpha in [
        (forehead_skin, (40, 210, 95), 0.48),
        (hairline_edge, (245, 218, 38), 0.78),
        (lower_guard, (58, 130, 245), 0.70),
    ]:
        area_overlay = _blend_overlay(area_overlay, mask, color, alpha=alpha)

    maps = {
        "texture": uniform,
        "forehead_mask": forehead_skin.astype(np.uint8) * 255,
        "hairline_edge_mask": hairline_edge.astype(np.uint8) * 255,
        "lower_feature_guard_mask": lower_guard.astype(np.uint8) * 255,
        "changed_mask": changed.astype(np.uint8) * 255,
        "weight": np.clip(weight * 255.0, 0, 255).astype(np.uint8),
        "area_render_texture": area_rgb,
        "area_overlay": area_overlay,
        "reference_skin_rgb": _mask_rgb(ref_roi, (80, 160, 255)),
    }
    meta = {
        "forehead_roi_normalized": {
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
            "scan_y_shift": y_shift,
        },
        "scan_hairline_hint": scan_hairline_hint,
        "target_non_forehead_face_mean_rgb": [float(x) for x in face_mean.tolist()],
        "target_reference_texels": int(face_ref_count),
        "forehead_skin_texels": int(forehead_skin.sum()),
        "hairline_edge_texels": int(hairline_edge.sum()),
        "lower_feature_guard_texels": int(lower_guard.sum()),
        "changed_texels": int(changed.sum()),
        "mean_abs_rgb_delta_on_changed": (
            float(np.abs(uniform.astype(np.int16) - base.astype(np.int16)).sum(axis=2)[changed].mean())
            if np.any(changed)
            else 0.0
        ),
    }
    meta.update(lower_meta)
    meta.update(component_meta)
    return maps, meta


def _step_v04_forehead_redefined_region(
    base: np.ndarray,
    decision: np.ndarray,
    clean_score: np.ndarray,
    raw_score: np.ndarray,
    source_count: np.ndarray,
    *,
    forehead_y_min: float,
    forehead_y_max: float,
    forehead_x_min: float,
    forehead_x_max: float,
    scan_hairline_hint: dict[str, Any],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    reliable_skin = _broad_skin_mask(base, decision)
    h, w = decision.shape
    yy, xx = np.indices((h, w))
    y_shift = 0.0
    if scan_hairline_hint.get("used"):
        ratio = float(scan_hairline_hint.get("estimated_hairline_skin_start_ratio", 0.16))
        y_shift = float(np.clip((ratio - 0.16) * 0.08, -0.012, 0.014))

    y_min = float(np.clip(forehead_y_min + y_shift, 0.24, 0.38))
    y_bottom = float(np.clip(max(forehead_y_max + 0.010, y_min + 0.105), y_min + 0.095, 0.475))
    x_min = float(max(0.25, forehead_x_min - 0.015))
    x_max = float(min(0.75, forehead_x_max + 0.015))
    x_min_px = int(w * x_min)
    x_max_px = int(w * x_max)
    y_min_px = int(h * y_min)
    y_bottom_px = int(h * y_bottom)

    coarse_roi = (
        (xx >= x_min_px)
        & (xx <= x_max_px)
        & (yy >= max(0, y_min_px - int(h * 0.020)))
        & (yy <= y_bottom_px)
    )
    curve_y, predicted_hairline, hairline_meta = _predict_smooth_hairline(
        reliable_skin,
        coarse_roi,
        x_min_px=x_min_px,
        x_max_px=x_max_px,
        y_min_px=y_min_px,
        y_max_px=y_bottom_px,
    )
    curve_lookup = curve_y[np.clip(xx, 0, w - 1)]
    below_predicted_hairline = yy >= curve_lookup
    position_forehead = (
        (xx >= x_min_px)
        & (xx <= x_max_px)
        & below_predicted_hairline
        & (yy <= y_bottom_px)
    )
    face_support = ndimage.binary_dilation(reliable_skin & coarse_roi, structure=_disk(24))
    position_forehead &= face_support
    predicted_hairline &= ndimage.binary_dilation(face_support, structure=_disk(4))

    eye_brow_guard, guard_meta = _eye_brow_guard_for_redefined_forehead(
        base,
        decision,
        reliable_skin,
        position_forehead,
        yy,
        y_min_px=y_min_px,
        y_bottom_px=y_bottom_px,
    )
    forehead_region = position_forehead & ~eye_brow_guard
    forehead_region = ndimage.binary_closing(forehead_region, structure=_disk(2)) & position_forehead & ~eye_brow_guard
    forehead_region, component_meta = _keep_central_forehead_components(forehead_region)

    max_score = np.maximum(clean_score.astype(np.float32), raw_score.astype(np.float32))
    ref_roi = (
        reliable_skin
        & ~forehead_region
        & ~eye_brow_guard
        & (xx >= int(w * 0.24))
        & (xx <= int(w * 0.76))
        & (yy >= int(h * 0.44))
        & (yy <= int(h * 0.62))
        & (max_score > 0.22)
        & (source_count.astype(np.float32) >= 1.0)
    )
    fallback = np.asarray([150.0, 105.0, 88.0], dtype=np.float32)
    face_mean, face_ref_count = _trimmed_mean_rgb(base, ref_roi, fallback)

    rgb = base.astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    non_skin_forehead = forehead_region & (~reliable_skin | (decision == COMPLETION_NEEDED) | (luma < 56.0))
    observed_forehead = forehead_region & ~non_skin_forehead

    edge_feather = np.clip(ndimage.distance_transform_edt(forehead_region).astype(np.float32) / 7.0, 0.0, 1.0)
    weight = np.where(forehead_region, np.clip(0.34 + 0.66 * edge_feather, 0.0, 1.0), 0.0).astype(np.float32)
    weight[non_skin_forehead] = np.maximum(weight[non_skin_forehead], 0.96)

    uniform = base.copy()
    target = face_mean.reshape(1, 1, 3)
    mixed = rgb * (1.0 - weight[..., None]) + target * weight[..., None]
    uniform[forehead_region] = np.clip(mixed[forehead_region], 0.0, 255.0).astype(np.uint8)

    changed = np.any(uniform != base, axis=2)
    area_rgb = np.full_like(base, 28, dtype=np.uint8)
    area_rgb[forehead_region] = (40, 210, 95)
    area_rgb[non_skin_forehead] = (255, 142, 42)
    area_rgb[predicted_hairline] = (245, 218, 38)
    area_rgb[eye_brow_guard] = (58, 130, 245)

    area_overlay = base.copy()
    for mask, color, alpha in [
        (forehead_region, (40, 210, 95), 0.42),
        (non_skin_forehead, (255, 142, 42), 0.72),
        (predicted_hairline, (245, 218, 38), 0.86),
        (eye_brow_guard, (58, 130, 245), 0.70),
    ]:
        area_overlay = _blend_overlay(area_overlay, mask, color, alpha=alpha)

    maps = {
        "texture": uniform,
        "forehead_region_mask": forehead_region.astype(np.uint8) * 255,
        "filled_non_skin_mask": non_skin_forehead.astype(np.uint8) * 255,
        "observed_forehead_mask": observed_forehead.astype(np.uint8) * 255,
        "predicted_hairline_mask": predicted_hairline.astype(np.uint8) * 255,
        "eye_brow_guard_mask": eye_brow_guard.astype(np.uint8) * 255,
        "changed_mask": changed.astype(np.uint8) * 255,
        "weight": np.clip(weight * 255.0, 0, 255).astype(np.uint8),
        "area_render_texture": area_rgb,
        "area_overlay": area_overlay,
        "reference_skin_rgb": _mask_rgb(ref_roi, (80, 160, 255)),
    }
    meta = {
        "forehead_roi_normalized": {
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_bottom": y_bottom,
            "scan_y_shift": y_shift,
        },
        "scan_hairline_hint": scan_hairline_hint,
        "target_non_forehead_face_mean_rgb": [float(x) for x in face_mean.tolist()],
        "target_reference_texels": int(face_ref_count),
        "forehead_region_texels": int(forehead_region.sum()),
        "observed_forehead_texels": int(observed_forehead.sum()),
        "filled_non_skin_texels": int(non_skin_forehead.sum()),
        "predicted_hairline_texels": int(predicted_hairline.sum()),
        "eye_brow_guard_texels": int(eye_brow_guard.sum()),
        "changed_texels": int(changed.sum()),
        "mean_abs_rgb_delta_on_changed": (
            float(np.abs(uniform.astype(np.int16) - base.astype(np.int16)).sum(axis=2)[changed].mean())
            if np.any(changed)
            else 0.0
        ),
    }
    meta.update(hairline_meta)
    meta.update(guard_meta)
    meta.update(component_meta)
    return maps, meta


def _step_v04b_eyebrow_hairline_refine(
    base: np.ndarray,
    decision: np.ndarray,
    clean_score: np.ndarray,
    raw_score: np.ndarray,
    source_count: np.ndarray,
    *,
    forehead_y_min: float,
    forehead_y_max: float,
    forehead_x_min: float,
    forehead_x_max: float,
    scan_hairline_hint: dict[str, Any],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    reliable_skin = _broad_skin_mask(base, decision)
    h, w = decision.shape
    yy, xx = np.indices((h, w))
    y_shift = 0.0
    if scan_hairline_hint.get("used"):
        ratio = float(scan_hairline_hint.get("estimated_hairline_skin_start_ratio", 0.16))
        y_shift = float(np.clip((ratio - 0.16) * 0.08, -0.012, 0.014))

    y_min = float(np.clip(forehead_y_min + y_shift, 0.24, 0.38))
    y_bottom = float(np.clip(max(forehead_y_max + 0.010, y_min + 0.105), y_min + 0.095, 0.475))
    x_min = float(max(0.22, forehead_x_min - 0.045))
    x_max = float(min(0.78, forehead_x_max + 0.045))
    x_min_px = int(w * x_min)
    x_max_px = int(w * x_max)
    y_min_px = int(h * y_min)
    y_bottom_px = int(h * y_bottom)

    coarse_roi = (
        (xx >= x_min_px)
        & (xx <= x_max_px)
        & (yy >= max(0, y_min_px - int(h * 0.020)))
        & (yy <= y_bottom_px)
    )
    first_curve, first_pass_hairline, hairline_meta = _predict_smooth_hairline(
        reliable_skin,
        coarse_roi,
        x_min_px=x_min_px,
        x_max_px=x_max_px,
        y_min_px=y_min_px,
        y_max_px=y_bottom_px,
    )
    face_support = ndimage.binary_dilation(reliable_skin & coarse_roi, structure=_disk(24))
    lifted_curve, final_hairline, lift_skin_mask, lift_meta = _lift_hairline_over_observed_skin(
        first_curve,
        reliable_skin,
        face_support,
        yy,
        xx,
        x_min_px=x_min_px,
        x_max_px=x_max_px,
        y_min_px=y_min_px,
        y_bottom_px=y_bottom_px,
    )
    curve_lookup = lifted_curve[np.clip(xx, 0, w - 1)]
    below_final_hairline = yy >= curve_lookup
    position_forehead = (
        (xx >= x_min_px)
        & (xx <= x_max_px)
        & below_final_hairline
        & (yy <= y_bottom_px)
    )
    initial_position_forehead = position_forehead.copy()
    first_pass_hairline &= ndimage.binary_dilation(face_support, structure=_disk(4))
    final_hairline &= ndimage.binary_dilation(position_forehead | face_support, structure=_disk(4))

    initial_eye_brow_guard, guard_meta = _eye_brow_guard_for_redefined_forehead(
        base,
        decision,
        reliable_skin,
        position_forehead,
        yy,
        y_min_px=y_min_px,
        y_bottom_px=y_bottom_px,
    )
    raw_eye_brow_guard, mirrored_eyebrow_mask, mirrored_eyebrow_rgb, eyebrow_meta = _symmetrize_eyebrow_guard(
        base,
        decision,
        reliable_skin,
        initial_eye_brow_guard,
        position_forehead,
        yy,
        xx,
        x_min_px=x_min_px,
        x_max_px=x_max_px,
        y_min_px=y_min_px,
        y_bottom_px=y_bottom_px,
    )

    if np.any(mirrored_eyebrow_mask):
        brow_y = np.where(mirrored_eyebrow_mask)[0]
        brow_axis_px = int(np.clip(
            np.percentile(brow_y, 96.0) + h * 0.018,
            y_min_px + int(h * 0.090),
            y_bottom_px,
        ))
    else:
        brow_axis_px = int(np.clip(y_min_px + h * 0.145, y_min_px + int(h * 0.090), y_bottom_px))

    eye_zone_top = max(0, brow_axis_px - int(h * 0.058))
    eye_zone_bottom = min(h - 1, brow_axis_px + int(h * 0.035))
    eye_only_guard = (
        raw_eye_brow_guard
        & (yy >= eye_zone_top)
        & (yy <= eye_zone_bottom)
        & position_forehead
    )
    eyebrow_only_guard = ndimage.binary_dilation(mirrored_eyebrow_mask, structure=_disk(2)) & position_forehead
    forehead_feature_guard = (eye_only_guard | eyebrow_only_guard) & position_forehead
    # Final forehead definition for this pass:
    # below hairline + above eyebrow baseline + not actual eye/eyebrow.
    position_forehead = (
        initial_position_forehead
        & (yy <= brow_axis_px)
        & ~forehead_feature_guard
    )
    position_forehead = ndimage.binary_closing(position_forehead, structure=_disk(2)) & initial_position_forehead & (yy <= brow_axis_px) & ~forehead_feature_guard
    forehead_region = position_forehead
    component_meta = _component_count_meta(forehead_region, "forehead")
    eye_brow_guard = forehead_feature_guard

    max_score = np.maximum(clean_score.astype(np.float32), raw_score.astype(np.float32))
    ref_roi = (
        reliable_skin
        & ~forehead_region
        & ~eye_brow_guard
        & (xx >= int(w * 0.24))
        & (xx <= int(w * 0.76))
        & (yy >= int(h * 0.44))
        & (yy <= int(h * 0.62))
        & (max_score > 0.22)
        & (source_count.astype(np.float32) >= 1.0)
    )
    fallback = np.asarray([150.0, 105.0, 88.0], dtype=np.float32)
    face_mean, face_ref_count = _trimmed_mean_rgb(base, ref_roi, fallback)

    rgb = base.astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    non_skin_forehead = forehead_region & (~reliable_skin | (decision == COMPLETION_NEEDED) | (luma < 56.0))
    observed_forehead = forehead_region & ~non_skin_forehead

    edge_feather = np.clip(ndimage.distance_transform_edt(forehead_region).astype(np.float32) / 7.0, 0.0, 1.0)
    weight = np.where(forehead_region, np.clip(0.34 + 0.66 * edge_feather, 0.0, 1.0), 0.0).astype(np.float32)
    weight[non_skin_forehead] = np.maximum(weight[non_skin_forehead], 0.96)

    uniform = base.copy()
    target = face_mean.reshape(1, 1, 3)
    mixed = rgb * (1.0 - weight[..., None]) + target * weight[..., None]
    uniform[forehead_region] = np.clip(mixed[forehead_region], 0.0, 255.0).astype(np.uint8)
    if np.any(mirrored_eyebrow_mask):
        uniform[mirrored_eyebrow_mask] = mirrored_eyebrow_rgb[mirrored_eyebrow_mask]

    changed = np.any(uniform != base, axis=2)
    area_rgb = np.full_like(base, 28, dtype=np.uint8)
    area_rgb[forehead_region] = (40, 210, 95)
    area_rgb[non_skin_forehead] = (255, 142, 42)
    area_rgb[final_hairline] = (245, 218, 38)
    area_rgb[eye_brow_guard] = (58, 130, 245)
    area_rgb[mirrored_eyebrow_mask] = (70, 230, 245)

    area_overlay = base.copy()
    for mask, color, alpha in [
        (forehead_region, (40, 210, 95), 0.42),
        (non_skin_forehead, (255, 142, 42), 0.72),
        (final_hairline, (245, 218, 38), 0.86),
        (eye_brow_guard, (58, 130, 245), 0.70),
        (mirrored_eyebrow_mask, (70, 230, 245), 0.80),
    ]:
        area_overlay = _blend_overlay(area_overlay, mask, color, alpha=alpha)

    hairline_lift_rgb = np.full_like(base, 22, dtype=np.uint8)
    hairline_lift_rgb[forehead_region] = (38, 175, 86)
    hairline_lift_rgb[lift_skin_mask] = (70, 235, 245)
    hairline_lift_rgb[first_pass_hairline] = (176, 72, 224)
    hairline_lift_rgb[final_hairline] = (245, 218, 38)
    hairline_lift_rgb[eye_brow_guard] = (58, 130, 245)
    hairline_lift_rgb[mirrored_eyebrow_mask] = (90, 245, 255)

    maps = {
        "texture": uniform,
        "forehead_region_mask": forehead_region.astype(np.uint8) * 255,
        "filled_non_skin_mask": non_skin_forehead.astype(np.uint8) * 255,
        "observed_forehead_mask": observed_forehead.astype(np.uint8) * 255,
        "first_pass_hairline_mask": first_pass_hairline.astype(np.uint8) * 255,
        "final_hairline_mask": final_hairline.astype(np.uint8) * 255,
        "hairline_lift_skin_mask": lift_skin_mask.astype(np.uint8) * 255,
        "initial_eye_brow_guard_mask": initial_eye_brow_guard.astype(np.uint8) * 255,
        "raw_eye_brow_guard_mask": raw_eye_brow_guard.astype(np.uint8) * 255,
        "eye_brow_guard_mask": eye_brow_guard.astype(np.uint8) * 255,
        "mirrored_eyebrow_guard_mask": mirrored_eyebrow_mask.astype(np.uint8) * 255,
        "changed_mask": changed.astype(np.uint8) * 255,
        "weight": np.clip(weight * 255.0, 0, 255).astype(np.uint8),
        "area_render_texture": area_rgb,
        "hairline_lift_render_texture": hairline_lift_rgb,
        "area_overlay": area_overlay,
        "reference_skin_rgb": _mask_rgb(ref_roi, (80, 160, 255)),
    }
    meta = {
        "forehead_roi_normalized": {
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_bottom": y_bottom,
            "scan_y_shift": y_shift,
        },
        "scan_hairline_hint": scan_hairline_hint,
        "target_non_forehead_face_mean_rgb": [float(x) for x in face_mean.tolist()],
        "target_reference_texels": int(face_ref_count),
        "forehead_region_texels": int(forehead_region.sum()),
        "observed_forehead_texels": int(observed_forehead.sum()),
        "filled_non_skin_texels": int(non_skin_forehead.sum()),
        "first_pass_hairline_texels": int(first_pass_hairline.sum()),
        "final_hairline_texels": int(final_hairline.sum()),
        "eye_brow_guard_texels": int(eye_brow_guard.sum()),
        "initial_eye_brow_guard_texels": int(initial_eye_brow_guard.sum()),
        "raw_eye_brow_guard_texels": int(raw_eye_brow_guard.sum()),
        "mirrored_eyebrow_texels": int(mirrored_eyebrow_mask.sum()),
        "forehead_definition_mode": "below_hairline_above_brow_axis_except_tight_eye_brow_guard",
        "position_forehead_texels_before_brow_axis": int(initial_position_forehead.sum()),
        "brow_axis_y_px": int(brow_axis_px),
        "eye_zone_top_px": int(eye_zone_top),
        "eye_zone_bottom_px": int(eye_zone_bottom),
        "tight_eye_guard_texels": int(eye_only_guard.sum()),
        "forehead_feature_guard_texels": int(forehead_feature_guard.sum()),
        "changed_texels": int(changed.sum()),
        "mean_abs_rgb_delta_on_changed": (
            float(np.abs(uniform.astype(np.int16) - base.astype(np.int16)).sum(axis=2)[changed].mean())
            if np.any(changed)
            else 0.0
        ),
    }
    meta.update(hairline_meta)
    meta.update(lift_meta)
    meta.update(guard_meta)
    meta.update(eyebrow_meta)
    meta.update(component_meta)
    return maps, meta


def _step_v05_side_neck_temporary_skin(
    base: np.ndarray,
    decision: np.ndarray,
    clean_score: np.ndarray,
    raw_score: np.ndarray,
    source_count: np.ndarray,
    v04b_maps: dict[str, np.ndarray],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    reliable_skin = _broad_skin_mask(base, decision)
    h, w = decision.shape
    yy, xx = np.indices((h, w))
    x = xx.astype(np.float32) / max(1, w - 1)
    y = yy.astype(np.float32) / max(1, h - 1)

    rgb = base.astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    maxc = rgb.max(axis=2)
    minc = rgb.min(axis=2)
    chroma = maxc - minc
    max_score = np.maximum(clean_score.astype(np.float32), raw_score.astype(np.float32))

    eye_brow_guard = v04b_maps.get("eye_brow_guard_mask", np.zeros(decision.shape, dtype=np.uint8)) > 0
    mirrored_brow = v04b_maps.get("mirrored_eyebrow_guard_mask", np.zeros(decision.shape, dtype=np.uint8)) > 0
    final_hairline = v04b_maps.get("final_hairline_mask", np.zeros(decision.shape, dtype=np.uint8)) > 0
    forehead_region = v04b_maps.get("forehead_region_mask", np.zeros(decision.shape, dtype=np.uint8)) > 0

    skin_like = reliable_skin & (luma > 46.0) & (luma < 238.0)
    face_ref = (
        skin_like
        & (x >= 0.34)
        & (x <= 0.66)
        & (y >= 0.46)
        & (y <= 0.66)
        & (max_score > 0.22)
        & (source_count > 0)
    )
    default_face = np.asarray([150.0, 98.0, 76.0], dtype=np.float32)
    face_mean, face_ref_count = _trimmed_mean_rgb(base, face_ref, default_face)

    side_ref = (
        skin_like
        & (y >= 0.38)
        & (y <= 0.66)
        & (((x >= 0.18) & (x <= 0.38)) | ((x >= 0.62) & (x <= 0.84)))
        & (max_score > 0.16)
    )
    side_mean, side_ref_count = _trimmed_mean_rgb(base, side_ref, face_mean)
    side_target = np.clip(side_mean * 0.62 + face_mean * 0.38, 0, 255)

    neck_ref = (
        skin_like
        & (x >= 0.28)
        & (x <= 0.74)
        & (y >= 0.60)
        & (y <= 0.79)
        & (max_score > 0.14)
    )
    neck_fallback = np.clip(face_mean * np.asarray([0.82, 0.78, 0.75], dtype=np.float32), 0, 255)
    neck_mean, neck_ref_count = _trimmed_mean_rgb(base, neck_ref, neck_fallback)
    neck_target_top = np.clip(neck_mean * 0.55 + neck_fallback * 0.45, 0, 255)
    neck_target_bottom = np.clip(face_mean * np.asarray([0.66, 0.62, 0.60], dtype=np.float32), 0, 255)

    # Protect actual facial features and scalp/hairline boundaries. The pass is
    # allowed to repair side/neck skin, but not to eat eyes, brows, mouth, or
    # the newly defined forehead/hairline mask.
    central_mouth = (
        (x >= 0.38)
        & (x <= 0.62)
        & (y >= 0.46)
        & (y <= 0.565)
        & ((luma < 76.0) | (decision == COMPLETION_NEEDED))
    )
    mouth_guard = ndimage.binary_dilation(central_mouth, structure=_disk(3))
    hairline_guard = ndimage.binary_dilation(final_hairline | forehead_region, structure=_disk(2)) & (y <= 0.51)
    feature_guard = ndimage.binary_dilation(eye_brow_guard | mirrored_brow | mouth_guard, structure=_disk(2)) | hairline_guard
    visible_feature_guard = ndimage.binary_dilation(eye_brow_guard | mirrored_brow | mouth_guard | final_hairline, structure=_disk(2))

    ref_for_distance = skin_like & ~feature_guard & (max_score > 0.10)
    if int(ref_for_distance.sum()) < 512:
        ref_for_distance = skin_like & ~feature_guard
    distance, nearest = ndimage.distance_transform_edt(~ref_for_distance, return_indices=True)
    nearest_y, nearest_x = nearest
    nearest_colors = base[nearest_y, nearest_x].astype(np.float32)

    side_roi = (
        (y >= 0.36)
        & (y <= 0.66)
        & (((x >= 0.16) & (x <= 0.39)) | ((x >= 0.61) & (x <= 0.86)))
        & (distance <= 54.0)
    )
    temple_roi = (
        (y >= 0.34)
        & (y <= 0.53)
        & (((x >= 0.22) & (x <= 0.39)) | ((x >= 0.61) & (x <= 0.78)))
        & (distance <= 60.0)
    )
    neck_roi = (
        (x >= 0.20)
        & (x <= 0.82)
        & (y >= 0.57)
        & (y <= 0.84)
        & (distance <= 132.0)
    )
    jaw_under_roi = (
        (x >= 0.32)
        & (x <= 0.72)
        & (y >= 0.54)
        & (y <= 0.67)
        & (distance <= 116.0)
    )

    side_color_dist = np.sqrt(np.mean(((rgb - side_target.reshape(1, 1, 3)) / 48.0) ** 2.0, axis=2))
    neck_t = np.clip((y - 0.58) / 0.25, 0.0, 1.0)
    neck_target_map = neck_target_top.reshape(1, 1, 3) * (1.0 - neck_t[..., None]) + neck_target_bottom.reshape(1, 1, 3) * neck_t[..., None]
    neck_color_dist = np.sqrt(np.mean(((rgb - neck_target_map) / 52.0) ** 2.0, axis=2))

    severe_dark = (decision == COMPLETION_NEEDED) | (luma < 52.0)
    weak_skin = (~reliable_skin & (luma < 128.0)) | (max_score < 0.12) | (source_count == 0)
    cloth_like = (chroma > 72.0) | (neck_color_dist > 1.25) | ((luma > 160.0) & ~reliable_skin)

    side_candidate = (side_roi | temple_roi) & ~feature_guard & (severe_dark | weak_skin | (side_color_dist > 1.35))
    muted_cloth_or_shadow = (y >= 0.62) & (luma < 138.0) & (neck_color_dist > 0.72)
    neck_candidate = (neck_roi | jaw_under_roi) & ~feature_guard & (severe_dark | weak_skin | cloth_like | muted_cloth_or_shadow)

    # Keep the masks coherent without growing them into background.
    valid_surface = ndimage.binary_dilation(ref_for_distance | side_candidate | neck_candidate, structure=_disk(2))
    side_candidate = ndimage.binary_closing(side_candidate, structure=_disk(2)) & valid_surface & (distance <= 60.0)
    neck_candidate = ndimage.binary_closing(neck_candidate, structure=_disk(3)) & valid_surface & (distance <= 138.0)
    neck_candidate &= ~side_candidate | (y >= 0.59)
    side_candidate &= ~neck_candidate

    repaired = base.copy()

    side_edge = np.clip(ndimage.distance_transform_edt(side_candidate).astype(np.float32) / 7.0, 0.0, 1.0)
    side_weight = np.clip(0.46 + 0.34 * severe_dark.astype(np.float32) + 0.18 * (side_color_dist > 1.6).astype(np.float32), 0.0, 0.88)
    side_weight *= side_edge
    side_mix = np.clip(nearest_colors * 0.58 + side_target.reshape(1, 1, 3) * 0.42, 0, 255)
    side_result = rgb * (1.0 - side_weight[..., None]) + side_mix * side_weight[..., None]
    repaired[side_candidate] = np.clip(side_result[side_candidate], 0, 255).astype(np.uint8)

    neck_edge = np.clip(ndimage.distance_transform_edt(neck_candidate).astype(np.float32) / 10.0, 0.0, 1.0)
    neck_weight = np.clip(0.58 + 0.30 * severe_dark.astype(np.float32) + 0.20 * cloth_like.astype(np.float32), 0.0, 0.94)
    neck_weight *= neck_edge
    neck_mix = np.clip(nearest_colors * 0.30 + neck_target_map * 0.70, 0, 255)
    neck_result = rgb * (1.0 - neck_weight[..., None]) + neck_mix * neck_weight[..., None]
    repaired[neck_candidate] = np.clip(neck_result[neck_candidate], 0, 255).astype(np.uint8)

    changed = np.any(repaired != base, axis=2)

    area_rgb = np.zeros_like(base, dtype=np.uint8)
    area_rgb[side_candidate] = (42, 220, 120)
    area_rgb[neck_candidate] = (255, 142, 42)
    area_rgb[visible_feature_guard] = (45, 125, 255)
    overlay = base.copy()
    for mask, color, alpha in [
        (side_candidate, (42, 220, 120), 0.58),
        (neck_candidate, (255, 142, 42), 0.66),
        (visible_feature_guard, (45, 125, 255), 0.42),
    ]:
        overlay = _blend_overlay(overlay, mask, color, alpha=alpha)

    maps = {
        "texture": repaired,
        "side_candidate_mask": side_candidate.astype(np.uint8) * 255,
        "neck_candidate_mask": neck_candidate.astype(np.uint8) * 255,
        "feature_guard_mask": visible_feature_guard.astype(np.uint8) * 255,
        "changed_mask": changed.astype(np.uint8) * 255,
        "area_render_texture": area_rgb,
        "area_overlay": overlay,
        "side_weight": np.clip(side_weight * 255.0, 0, 255).astype(np.uint8),
        "neck_weight": np.clip(neck_weight * 255.0, 0, 255).astype(np.uint8),
        "side_reference_skin_rgb": _mask_rgb(side_ref, (95, 220, 145)),
        "neck_reference_skin_rgb": _mask_rgb(neck_ref, (255, 180, 80)),
    }
    meta = {
        "logic": "temporary skin fill for side/temple/ear dark fragments and neck/jaw/clothing contamination",
        "face_reference_texels": int(face_ref.sum()),
        "side_reference_texels": int(side_ref.sum()),
        "neck_reference_texels": int(neck_ref.sum()),
        "target_face_rgb": [float(v) for v in face_mean.tolist()],
        "target_side_rgb": [float(v) for v in side_target.tolist()],
        "target_neck_top_rgb": [float(v) for v in neck_target_top.tolist()],
        "target_neck_bottom_rgb": [float(v) for v in neck_target_bottom.tolist()],
        "side_candidate_texels": int(side_candidate.sum()),
        "neck_candidate_texels": int(neck_candidate.sum()),
        "feature_guard_texels": int(visible_feature_guard.sum()),
        "edit_block_guard_texels": int(feature_guard.sum()),
        "changed_texels": int(changed.sum()),
        "severe_dark_side_texels": int((side_candidate & severe_dark).sum()),
        "severe_dark_neck_texels": int((neck_candidate & severe_dark).sum()),
        "cloth_like_neck_texels": int((neck_candidate & cloth_like).sum()),
        "mean_side_weight": float(side_weight[side_candidate].mean()) if np.any(side_candidate) else 0.0,
        "mean_neck_weight": float(neck_weight[neck_candidate].mean()) if np.any(neck_candidate) else 0.0,
    }
    return maps, meta


def _hairline_curve_from_mask(mask: np.ndarray, *, fallback_y: int) -> np.ndarray:
    h, w = mask.shape
    curve = np.full(w, float(fallback_y), dtype=np.float32)
    xs_with_line: list[int] = []
    ys_with_line: list[float] = []
    for x in range(w):
        rows = np.where(mask[:, x])[0]
        if rows.size:
            xs_with_line.append(x)
            ys_with_line.append(float(np.percentile(rows, 50.0)))
    if len(xs_with_line) >= 2:
        curve = np.interp(
            np.arange(w, dtype=np.float32),
            np.asarray(xs_with_line, dtype=np.float32),
            np.asarray(ys_with_line, dtype=np.float32),
        ).astype(np.float32)
    elif len(xs_with_line) == 1:
        curve[:] = ys_with_line[0]
    curve = ndimage.gaussian_filter1d(curve, sigma=max(3.0, w / 96.0), mode="nearest")
    return np.clip(curve, 0, h - 1)


def _step_v06_simple_bald_skin_fill(
    base: np.ndarray,
    decision: np.ndarray,
    clean_score: np.ndarray,
    raw_score: np.ndarray,
    source_count: np.ndarray,
    v04b_maps: dict[str, np.ndarray],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    reliable_skin = _broad_skin_mask(base, decision)
    h, w = decision.shape
    yy, xx = np.indices((h, w))
    x = xx.astype(np.float32) / max(1, w - 1)
    y = yy.astype(np.float32) / max(1, h - 1)
    rgb = base.astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    maxc = rgb.max(axis=2)
    minc = rgb.min(axis=2)
    chroma = maxc - minc
    max_score = np.maximum(clean_score.astype(np.float32), raw_score.astype(np.float32))

    final_hairline = v04b_maps.get("final_hairline_mask", np.zeros(decision.shape, dtype=np.uint8)) > 0
    eye_brow_guard = v04b_maps.get("eye_brow_guard_mask", np.zeros(decision.shape, dtype=np.uint8)) > 0
    mirrored_brow = v04b_maps.get("mirrored_eyebrow_guard_mask", np.zeros(decision.shape, dtype=np.uint8)) > 0
    fallback_hairline_y = int(h * 0.405)
    hairline_curve = _hairline_curve_from_mask(final_hairline, fallback_y=fallback_hairline_y)
    curve_lookup = hairline_curve[np.clip(xx, 0, w - 1)]

    above_hairline = yy < (curve_lookup - max(2.0, h * 0.004))
    below_hairline = ~above_hairline

    # Lips/mouth are too important to skin-fill, but broad "red-ish" or
    # completion-needed tests spill onto the lower face. Keep only the compact
    # dark mouth core near the center of the FaceBuilder UV mouth area.
    mouth_anchor = (((x - 0.50) / 0.080) ** 2.0 + ((y - 0.535) / 0.047) ** 2.0) <= 1.0
    mouth_anchor &= (x >= 0.435) & (x <= 0.565) & (y >= 0.495) & (y <= 0.575)
    mouth_lip_seed = mouth_anchor & (luma < 58.0)
    labeled_mouth, mouth_components = ndimage.label(mouth_lip_seed)
    mouth_lip_keep = np.zeros_like(mouth_lip_seed, dtype=bool)
    for label in range(1, mouth_components + 1):
        component = labeled_mouth == label
        area = int(component.sum())
        if area < 24 or area > 5200:
            continue
        ys, xs = np.where(component)
        width = int(xs.max() - xs.min() + 1)
        height = int(ys.max() - ys.min() + 1)
        center_x = float(xs.mean()) / max(1, w - 1)
        center_y = float(ys.mean()) / max(1, h - 1)
        if width >= 6 and height >= 4 and 0.455 <= center_x <= 0.545 and 0.500 <= center_y <= 0.565:
            mouth_lip_keep |= component
    if int(mouth_lip_keep.sum()) < 120:
        fallback_core = (((x - 0.50) / 0.050) ** 2.0 + ((y - 0.535) / 0.028) ** 2.0) <= 1.0
        mouth_lip_keep = fallback_core & mouth_anchor & (luma < 96.0)
    mouth_lip_guard = ndimage.binary_dilation(mouth_lip_keep, structure=_disk(2)) & mouth_anchor
    nose_dark_seed = (
        (x >= 0.43)
        & (x <= 0.57)
        & (y >= 0.38)
        & (y <= 0.50)
        & (luma < 64.0)
    )
    feature_guard = ndimage.binary_dilation(
        eye_brow_guard | mirrored_brow | mouth_lip_guard | nose_dark_seed | final_hairline,
        structure=_disk(2),
    )

    skin_ref = (
        reliable_skin
        & below_hairline
        & ~feature_guard
        & (y >= 0.37)
        & (y <= 0.60)
        & (x >= 0.22)
        & (x <= 0.78)
        & (max_score > 0.16)
        & (source_count > 0)
    )
    default_skin = np.asarray([150.0, 100.0, 78.0], dtype=np.float32)
    skin_mean, skin_ref_count = _trimmed_mean_rgb(base, skin_ref, default_skin)
    neck_target = np.clip(skin_mean * np.asarray([0.78, 0.74, 0.72], dtype=np.float32), 0, 255)
    lower_t = np.clip((y - 0.56) / 0.30, 0.0, 1.0)
    target_map = skin_mean.reshape(1, 1, 3) * (1.0 - lower_t[..., None]) + neck_target.reshape(1, 1, 3) * lower_t[..., None]

    color_dist = np.sqrt(np.mean(((rgb - target_map) / 55.0) ** 2.0, axis=2))
    neck_start_y = 0.615
    face_below_hairline = below_hairline & (y < neck_start_y) & ~feature_guard
    neck_below_hairline = below_hairline & (y >= neck_start_y) & ~feature_guard
    excellent_skin = (
        face_below_hairline
        & reliable_skin
        & (decision != COMPLETION_NEEDED)
        & (source_count > 0)
        & (max_score >= 0.18)
        & (luma >= 54.0)
        & (luma <= 214.0)
        & (chroma <= 92.0)
        & (color_dist <= 1.08)
    )

    face_fill = face_below_hairline & ~excellent_skin
    neck_fill = neck_below_hairline
    bad_below_hairline = face_fill | neck_fill

    good_kept = excellent_skin
    repaired = base.copy()
    repaired[above_hairline] = (0, 0, 0)

    fill_weight = bad_below_hairline.astype(np.float32)
    repaired[bad_below_hairline] = np.clip(target_map[bad_below_hairline], 0, 255).astype(np.uint8)
    repaired[feature_guard & below_hairline] = base[feature_guard & below_hairline]

    changed = np.any(repaired != base, axis=2)
    area_rgb = np.zeros_like(base, dtype=np.uint8)
    area_rgb[above_hairline] = (0, 0, 0)
    area_rgb[good_kept] = (44, 210, 95)
    area_rgb[bad_below_hairline] = (255, 142, 42)
    area_rgb[feature_guard & below_hairline] = (45, 125, 255)
    area_rgb[final_hairline] = (245, 218, 38)

    overlay = base.copy()
    for mask, color, alpha in [
        (above_hairline, (0, 0, 0), 0.82),
        (good_kept, (44, 210, 95), 0.24),
        (bad_below_hairline, (255, 142, 42), 0.66),
        (feature_guard & below_hairline, (45, 125, 255), 0.52),
        (final_hairline, (245, 218, 38), 0.88),
    ]:
        overlay = _blend_overlay(overlay, mask, color, alpha=alpha)

    maps = {
        "texture": repaired,
        "above_hairline_mask": above_hairline.astype(np.uint8) * 255,
        "bad_below_hairline_mask": bad_below_hairline.astype(np.uint8) * 255,
        "good_kept_mask": good_kept.astype(np.uint8) * 255,
        "feature_guard_mask": (feature_guard & below_hairline).astype(np.uint8) * 255,
        "changed_mask": changed.astype(np.uint8) * 255,
        "area_render_texture": area_rgb,
        "area_overlay": overlay,
        "weight": np.clip(fill_weight * 255.0, 0, 255).astype(np.uint8),
        "skin_reference_rgb": _mask_rgb(skin_ref, (90, 220, 145)),
    }
    meta = {
        "logic": "black above hairline; below hairline keep only excellent skin and protected eyes/brows/lips/mouth, fill everything else; below neck start fill all non-protected texels",
        "skin_reference_texels": int(skin_ref.sum()),
        "target_skin_rgb": [float(v) for v in skin_mean.tolist()],
        "target_neck_rgb": [float(v) for v in neck_target.tolist()],
        "neck_start_y_normalized": float(neck_start_y),
        "above_hairline_texels": int(above_hairline.sum()),
        "good_kept_texels": int(good_kept.sum()),
        "bad_below_hairline_texels": int(bad_below_hairline.sum()),
        "face_fill_texels": int(face_fill.sum()),
        "neck_fill_texels": int(neck_fill.sum()),
        "feature_guard_texels": int((feature_guard & below_hairline).sum()),
        "mouth_lip_guard_texels": int((mouth_lip_guard & below_hairline).sum()),
        "changed_texels": int(changed.sum()),
        "hairline_curve_y_min_px": float(hairline_curve.min()),
        "hairline_curve_y_max_px": float(hairline_curve.max()),
        "mean_fill_weight": float(fill_weight[bad_below_hairline].mean()) if np.any(bad_below_hairline) else 0.0,
        "excellent_skin_texels": int(excellent_skin.sum()),
    }
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

    if not args.skip_render and not args.skip_v02_renders:
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

    scan_hairline_hint = _find_scan_hairline_hint(person, args.drive_root)
    v03_maps, v03_meta = _step_v03_forehead_uniform_tone(
        v01_texture,
        decision,
        clean_score,
        raw_score,
        source_count,
        forehead_y_min=args.forehead_y_min,
        forehead_y_max=args.forehead_y_max,
        forehead_x_min=args.forehead_x_min,
        forehead_x_max=args.forehead_x_max,
        scan_hairline_hint=scan_hairline_hint,
    )
    v03_dir = output_dir / "v03_forehead_uniform_tone"
    v03_maps_dir = v03_dir / "maps"
    v03_texture_path = v03_maps_dir / "v03_forehead_uniform_tone_texture.png"
    v03_area_texture_path = v03_maps_dir / "v03_forehead_uniform_area_render_texture.png"
    v03_paths: dict[str, Any] = {
        "texture": _save_rgb(v03_texture_path, v03_maps["texture"]),
        "forehead_mask": _save_l(v03_maps_dir / "v03_forehead_mask.png", v03_maps["forehead_mask"]),
        "hairline_edge_mask": _save_l(v03_maps_dir / "v03_hairline_edge_mask.png", v03_maps["hairline_edge_mask"]),
        "lower_feature_guard_mask": _save_l(v03_maps_dir / "v03_eye_brow_guard_mask.png", v03_maps["lower_feature_guard_mask"]),
        "changed_mask": _save_l(v03_maps_dir / "v03_changed_mask.png", v03_maps["changed_mask"]),
        "weight": _save_l(v03_maps_dir / "v03_uniform_weight.png", v03_maps["weight"]),
        "area_render_texture": _save_rgb(v03_area_texture_path, v03_maps["area_render_texture"]),
        "area_overlay": _save_rgb(v03_maps_dir / "v03_area_overlay.png", v03_maps["area_overlay"]),
        "reference_skin_rgb": _save_rgb(v03_maps_dir / "v03_non_forehead_reference_skin_debug_rgb.png", v03_maps["reference_skin_rgb"]),
    }
    if not args.skip_render and not args.skip_v03_renders:
        v03_paths["before_v01_render"] = _render_stage_raw(
            person=person,
            stage="v03_before_v01_skin_holes",
            texture_path=v01_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v03_dir,
            args=args,
        )
        v03_paths["after_uniform_render"] = _render_stage_raw(
            person=person,
            stage="v03_after_forehead_uniform",
            texture_path=v03_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v03_dir,
            args=args,
        )
        v03_paths["area_render"] = _render_stage_raw(
            person=person,
            stage="v03_area_map",
            texture_path=v03_area_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v03_dir,
            args=args,
        )
        compact_sheet = _make_compact_before_after_sheet(
            person=person,
            title_stage="v03_forehead_uniform_tone",
            before_dir=_as_path(v03_paths["before_v01_render"]["render_dir"]),
            after_dir=_as_path(v03_paths["after_uniform_render"]["render_dir"]),
            area_dir=_as_path(v03_paths["area_render"]["render_dir"]),
            output_path=v03_dir / "step6_v03_compact_review_sheet.png",
            legend="Green=edited forehead, yellow=hairline edge, blue=eye/brow guard, dark=not touched.",
        )
        if compact_sheet:
            v03_paths["compact_review_sheet"] = compact_sheet

    person_summary["stages"]["v03_forehead_uniform_tone"] = {
        "logic": "use scan hairline only as a boundary hint, then set forehead skin to non-forehead face-skin mean tone with thin feature guards",
        "paths": v03_paths,
        "metrics": v03_meta,
    }

    v04_maps, v04_meta = _step_v04_forehead_redefined_region(
        v01_texture,
        decision,
        clean_score,
        raw_score,
        source_count,
        forehead_y_min=args.forehead_y_min,
        forehead_y_max=args.forehead_y_max,
        forehead_x_min=args.forehead_x_min,
        forehead_x_max=args.forehead_x_max,
        scan_hairline_hint=scan_hairline_hint,
    )
    v04_dir = output_dir / "v04_forehead_redefined_region"
    v04_maps_dir = v04_dir / "maps"
    v04_texture_path = v04_maps_dir / "v04_forehead_redefined_region_texture.png"
    v04_area_texture_path = v04_maps_dir / "v04_forehead_redefined_area_render_texture.png"
    v04_paths: dict[str, Any] = {
        "texture": _save_rgb(v04_texture_path, v04_maps["texture"]),
        "forehead_region_mask": _save_l(v04_maps_dir / "v04_forehead_region_mask.png", v04_maps["forehead_region_mask"]),
        "filled_non_skin_mask": _save_l(v04_maps_dir / "v04_filled_non_skin_mask.png", v04_maps["filled_non_skin_mask"]),
        "observed_forehead_mask": _save_l(v04_maps_dir / "v04_observed_forehead_mask.png", v04_maps["observed_forehead_mask"]),
        "predicted_hairline_mask": _save_l(v04_maps_dir / "v04_predicted_hairline_mask.png", v04_maps["predicted_hairline_mask"]),
        "eye_brow_guard_mask": _save_l(v04_maps_dir / "v04_eye_brow_guard_mask.png", v04_maps["eye_brow_guard_mask"]),
        "changed_mask": _save_l(v04_maps_dir / "v04_changed_mask.png", v04_maps["changed_mask"]),
        "weight": _save_l(v04_maps_dir / "v04_uniform_weight.png", v04_maps["weight"]),
        "area_render_texture": _save_rgb(v04_area_texture_path, v04_maps["area_render_texture"]),
        "area_overlay": _save_rgb(v04_maps_dir / "v04_area_overlay.png", v04_maps["area_overlay"]),
        "reference_skin_rgb": _save_rgb(v04_maps_dir / "v04_non_forehead_reference_skin_debug_rgb.png", v04_maps["reference_skin_rgb"]),
    }
    if not args.skip_render and not args.skip_v04_renders:
        v04_paths["before_v01_render"] = _render_stage_raw(
            person=person,
            stage="v04_before_v01_skin_holes",
            texture_path=v01_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v04_dir,
            args=args,
        )
        v04_paths["after_redefined_render"] = _render_stage_raw(
            person=person,
            stage="v04_after_forehead_redefined",
            texture_path=v04_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v04_dir,
            args=args,
        )
        v04_paths["area_render"] = _render_stage_raw(
            person=person,
            stage="v04_area_map",
            texture_path=v04_area_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v04_dir,
            args=args,
        )
        compact_sheet = _make_compact_before_after_sheet(
            person=person,
            title_stage="v04_forehead_redefined_region",
            before_dir=_as_path(v04_paths["before_v01_render"]["render_dir"]),
            after_dir=_as_path(v04_paths["after_redefined_render"]["render_dir"]),
            area_dir=_as_path(v04_paths["area_render"]["render_dir"]),
            output_path=v04_dir / "step6_v04_compact_review_sheet.png",
            legend="Green=forehead region, orange=hair/black leftovers filled as forehead, yellow=smooth predicted hairline, blue=eye/brow guard, dark=not touched.",
            before_label="before v01",
            after_label="after v04",
            area_label="area map",
        )
        if compact_sheet:
            v04_paths["compact_review_sheet"] = compact_sheet

    person_summary["stages"]["v04_forehead_redefined_region"] = {
        "logic": "redefine upper-face forehead by smooth predicted hairline and eye/brow guard, then fill hair/black leftovers as forehead skin",
        "paths": v04_paths,
        "metrics": v04_meta,
    }

    v04b_maps, v04b_meta = _step_v04b_eyebrow_hairline_refine(
        v01_texture,
        decision,
        clean_score,
        raw_score,
        source_count,
        forehead_y_min=args.forehead_y_min,
        forehead_y_max=args.forehead_y_max,
        forehead_x_min=args.forehead_x_min,
        forehead_x_max=args.forehead_x_max,
        scan_hairline_hint=scan_hairline_hint,
    )
    v04b_dir = output_dir / "v04b_eyebrow_hairline_refine"
    v04b_maps_dir = v04b_dir / "maps"
    v04b_texture_path = v04b_maps_dir / "v04b_eyebrow_hairline_refine_texture.png"
    v04b_area_texture_path = v04b_maps_dir / "v04b_area_render_texture.png"
    v04b_hairline_texture_path = v04b_maps_dir / "v04b_hairline_lift_render_texture.png"
    v04b_paths: dict[str, Any] = {
        "texture": _save_rgb(v04b_texture_path, v04b_maps["texture"]),
        "forehead_region_mask": _save_l(v04b_maps_dir / "v04b_forehead_region_mask.png", v04b_maps["forehead_region_mask"]),
        "filled_non_skin_mask": _save_l(v04b_maps_dir / "v04b_filled_non_skin_mask.png", v04b_maps["filled_non_skin_mask"]),
        "observed_forehead_mask": _save_l(v04b_maps_dir / "v04b_observed_forehead_mask.png", v04b_maps["observed_forehead_mask"]),
        "first_pass_hairline_mask": _save_l(v04b_maps_dir / "v04b_first_pass_hairline_mask.png", v04b_maps["first_pass_hairline_mask"]),
        "final_hairline_mask": _save_l(v04b_maps_dir / "v04b_final_hairline_mask.png", v04b_maps["final_hairline_mask"]),
        "hairline_lift_skin_mask": _save_l(v04b_maps_dir / "v04b_hairline_lift_skin_mask.png", v04b_maps["hairline_lift_skin_mask"]),
        "initial_eye_brow_guard_mask": _save_l(v04b_maps_dir / "v04b_initial_eye_brow_guard_mask.png", v04b_maps["initial_eye_brow_guard_mask"]),
        "raw_eye_brow_guard_mask": _save_l(v04b_maps_dir / "v04b_raw_eye_brow_guard_mask.png", v04b_maps["raw_eye_brow_guard_mask"]),
        "eye_brow_guard_mask": _save_l(v04b_maps_dir / "v04b_eye_brow_guard_mask.png", v04b_maps["eye_brow_guard_mask"]),
        "mirrored_eyebrow_guard_mask": _save_l(v04b_maps_dir / "v04b_mirrored_eyebrow_guard_mask.png", v04b_maps["mirrored_eyebrow_guard_mask"]),
        "changed_mask": _save_l(v04b_maps_dir / "v04b_changed_mask.png", v04b_maps["changed_mask"]),
        "weight": _save_l(v04b_maps_dir / "v04b_uniform_weight.png", v04b_maps["weight"]),
        "area_render_texture": _save_rgb(v04b_area_texture_path, v04b_maps["area_render_texture"]),
        "hairline_lift_render_texture": _save_rgb(v04b_hairline_texture_path, v04b_maps["hairline_lift_render_texture"]),
        "area_overlay": _save_rgb(v04b_maps_dir / "v04b_area_overlay.png", v04b_maps["area_overlay"]),
        "reference_skin_rgb": _save_rgb(v04b_maps_dir / "v04b_non_forehead_reference_skin_debug_rgb.png", v04b_maps["reference_skin_rgb"]),
    }
    if not args.skip_render and not args.skip_v04b_renders:
        v04b_paths["before_v01_render"] = _render_stage_raw(
            person=person,
            stage="v04b_before_v01_skin_holes",
            texture_path=v01_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v04b_dir,
            args=args,
        )
        v04b_paths["after_refine_render"] = _render_stage_raw(
            person=person,
            stage="v04b_after_eyebrow_hairline_refine",
            texture_path=v04b_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v04b_dir,
            args=args,
        )
        v04b_paths["area_render"] = _render_stage_raw(
            person=person,
            stage="v04b_area_map",
            texture_path=v04b_area_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v04b_dir,
            args=args,
        )
        v04b_paths["hairline_lift_render"] = _render_stage_raw(
            person=person,
            stage="v04b_hairline_lift_map",
            texture_path=v04b_hairline_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v04b_dir,
            args=args,
        )
        compact_sheet = _make_compact_before_after_sheet(
            person=person,
            title_stage="v04b_eyebrow_hairline_refine",
            before_dir=_as_path(v04b_paths["before_v01_render"]["render_dir"]),
            after_dir=_as_path(v04b_paths["after_refine_render"]["render_dir"]),
            area_dir=_as_path(v04b_paths["area_render"]["render_dir"]),
            output_path=v04b_dir / "step6_v04b_compact_review_sheet.png",
            legend="Area row: green=forehead, orange=filled hair/black leftovers, yellow=final hairline, blue=eye/brow guard, cyan=symmetric black brow mask. Bottom row: purple=1st hairline, yellow=2nd hairline, cyan=skin evidence for broad lift.",
            before_label="before v01",
            after_label="after v04b",
            area_label="area map",
            extra_rows=[("2nd hairline", _as_path(v04b_paths["hairline_lift_render"]["render_dir"]))],
        )
        if compact_sheet:
            v04b_paths["compact_review_sheet"] = compact_sheet

    person_summary["stages"]["v04b_eyebrow_hairline_refine"] = {
        "logic": "start from v04 forehead redefinition, choose eyebrow source by component quality, mirror good brows as a fixed black mask, flatten and symmetrically lift the front hairline, then define forehead as below hairline and above eyebrow baseline except tight eye/brow guards",
        "paths": v04b_paths,
        "metrics": v04b_meta,
    }

    v05_maps, v05_meta = _step_v05_side_neck_temporary_skin(
        v04b_maps["texture"],
        decision,
        clean_score,
        raw_score,
        source_count,
        v04b_maps,
    )
    v05_dir = output_dir / "v05_side_neck_temporary_skin"
    v05_maps_dir = v05_dir / "maps"
    v05_texture_path = v05_maps_dir / "v05_side_neck_temporary_skin_texture.png"
    v05_area_texture_path = v05_maps_dir / "v05_area_render_texture.png"
    v05_paths: dict[str, Any] = {
        "texture": _save_rgb(v05_texture_path, v05_maps["texture"]),
        "side_candidate_mask": _save_l(v05_maps_dir / "v05_side_candidate_mask.png", v05_maps["side_candidate_mask"]),
        "neck_candidate_mask": _save_l(v05_maps_dir / "v05_neck_candidate_mask.png", v05_maps["neck_candidate_mask"]),
        "feature_guard_mask": _save_l(v05_maps_dir / "v05_feature_guard_mask.png", v05_maps["feature_guard_mask"]),
        "changed_mask": _save_l(v05_maps_dir / "v05_changed_mask.png", v05_maps["changed_mask"]),
        "area_render_texture": _save_rgb(v05_area_texture_path, v05_maps["area_render_texture"]),
        "area_overlay": _save_rgb(v05_maps_dir / "v05_area_overlay.png", v05_maps["area_overlay"]),
        "side_weight": _save_l(v05_maps_dir / "v05_side_weight.png", v05_maps["side_weight"]),
        "neck_weight": _save_l(v05_maps_dir / "v05_neck_weight.png", v05_maps["neck_weight"]),
        "side_reference_skin_rgb": _save_rgb(v05_maps_dir / "v05_side_reference_skin_debug_rgb.png", v05_maps["side_reference_skin_rgb"]),
        "neck_reference_skin_rgb": _save_rgb(v05_maps_dir / "v05_neck_reference_skin_debug_rgb.png", v05_maps["neck_reference_skin_rgb"]),
    }
    if not args.skip_render and not args.skip_v05_renders:
        v05_paths["before_v04b_render"] = _render_stage_raw(
            person=person,
            stage="v05_before_v04b",
            texture_path=v04b_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v05_dir,
            args=args,
        )
        v05_paths["after_side_neck_render"] = _render_stage_raw(
            person=person,
            stage="v05_after_side_neck_temporary_skin",
            texture_path=v05_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v05_dir,
            args=args,
        )
        v05_paths["area_render"] = _render_stage_raw(
            person=person,
            stage="v05_area_map",
            texture_path=v05_area_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v05_dir,
            args=args,
        )
        compact_sheet = _make_compact_before_after_sheet(
            person=person,
            title_stage="v05_side_neck_temporary_skin",
            before_dir=_as_path(v05_paths["before_v04b_render"]["render_dir"]),
            after_dir=_as_path(v05_paths["after_side_neck_render"]["render_dir"]),
            area_dir=_as_path(v05_paths["area_render"]["render_dir"]),
            output_path=v05_dir / "step6_v05_compact_review_sheet.png",
            legend="Green=side/temple/ear temporary skin, orange=neck/jaw/clothing temporary skin, blue=protected eye/brow/mouth/hairline, dark=not touched.",
            before_label="before v04b",
            after_label="after v05",
            area_label="v05 area",
        )
        if compact_sheet:
            v05_paths["compact_review_sheet"] = compact_sheet

    person_summary["stages"]["v05_side_neck_temporary_skin"] = {
        "logic": "fill side/temple/ear dark fragments and neck/jaw/clothing contamination as temporary skin while preserving protected facial features",
        "paths": v05_paths,
        "metrics": v05_meta,
    }

    v06_maps, v06_meta = _step_v06_simple_bald_skin_fill(
        v04b_maps["texture"],
        decision,
        clean_score,
        raw_score,
        source_count,
        v04b_maps,
    )
    v06_dir = output_dir / "v06_simple_bald_skin_fill"
    v06_maps_dir = v06_dir / "maps"
    v06_texture_path = v06_maps_dir / "v06_simple_bald_skin_fill_texture.png"
    v06_area_texture_path = v06_maps_dir / "v06_area_render_texture.png"
    v06_paths: dict[str, Any] = {
        "texture": _save_rgb(v06_texture_path, v06_maps["texture"]),
        "above_hairline_mask": _save_l(v06_maps_dir / "v06_above_hairline_mask.png", v06_maps["above_hairline_mask"]),
        "bad_below_hairline_mask": _save_l(v06_maps_dir / "v06_bad_below_hairline_mask.png", v06_maps["bad_below_hairline_mask"]),
        "good_kept_mask": _save_l(v06_maps_dir / "v06_good_kept_mask.png", v06_maps["good_kept_mask"]),
        "feature_guard_mask": _save_l(v06_maps_dir / "v06_feature_guard_mask.png", v06_maps["feature_guard_mask"]),
        "changed_mask": _save_l(v06_maps_dir / "v06_changed_mask.png", v06_maps["changed_mask"]),
        "area_render_texture": _save_rgb(v06_area_texture_path, v06_maps["area_render_texture"]),
        "area_overlay": _save_rgb(v06_maps_dir / "v06_area_overlay.png", v06_maps["area_overlay"]),
        "fill_weight": _save_l(v06_maps_dir / "v06_fill_weight.png", v06_maps["weight"]),
        "skin_reference_rgb": _save_rgb(v06_maps_dir / "v06_skin_reference_debug_rgb.png", v06_maps["skin_reference_rgb"]),
    }
    if not args.skip_render and not args.skip_v06_renders:
        v06_paths["before_v04b_render"] = _render_stage_raw(
            person=person,
            stage="v06_before_v04b",
            texture_path=v04b_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v06_dir,
            args=args,
        )
        v06_paths["after_simple_bald_skin_fill_render"] = _render_stage_raw(
            person=person,
            stage="v06_after_simple_bald_skin_fill",
            texture_path=v06_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v06_dir,
            args=args,
        )
        v06_paths["area_render"] = _render_stage_raw(
            person=person,
            stage="v06_area_map",
            texture_path=v06_area_texture_path,
            source_person_dir=source_person_dir,
            output_dir=v06_dir,
            args=args,
        )
        compact_sheet = _make_compact_before_after_sheet(
            person=person,
            title_stage="v06_simple_bald_skin_fill",
            before_dir=_as_path(v06_paths["before_v04b_render"]["render_dir"]),
            after_dir=_as_path(v06_paths["after_simple_bald_skin_fill_render"]["render_dir"]),
            area_dir=_as_path(v06_paths["area_render"]["render_dir"]),
            output_path=v06_dir / "step6_v06_compact_review_sheet.png",
            legend="Black=hair/scalp above hairline, green=good pixels kept, orange=bad pixels filled as simple skin, blue=protected eyes/brows/lips/mouth, yellow=hairline.",
            before_label="before v04b",
            after_label="after v06",
            area_label="v06 area",
        )
        if compact_sheet:
            v06_paths["compact_review_sheet"] = compact_sheet

    person_summary["stages"]["v06_simple_bald_skin_fill"] = {
        "logic": "start from v04b, black out all texels above the refined hairline, keep good below-hairline pixels, and fill bad below-hairline non-feature pixels with a simple skin/neck target",
        "paths": v06_paths,
        "metrics": v06_meta,
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
    lines.extend([
        "## v03_forehead_uniform_tone",
        "",
        "This stage uses v01 as the before state. It does not use scan frames as texture.",
        "For Juseop, available hairline scan frames are used only as a thin hairline-boundary hint.",
        "The edited forehead skin is set toward the mean tone of non-forehead face skin.",
        "The main review sheet is compact: before v01, after v03, and area map at front/+-45 only.",
        "",
    ])
    for person in summary["people"]:
        stage = person["stages"].get("v03_forehead_uniform_tone", {})
        if not stage:
            continue
        metrics = stage["metrics"]
        paths = stage["paths"]
        lines.extend([
            f"### {person['person']}",
            "",
            f"- Compact review: `{paths.get('compact_review_sheet')}`",
            f"- Texture: `{paths.get('texture')}`",
            f"- Target non-forehead face mean RGB: {[round(x, 2) for x in metrics['target_non_forehead_face_mean_rgb']]}",
            f"- Forehead skin texels: {metrics['forehead_skin_texels']}",
            f"- Hairline edge texels: {metrics['hairline_edge_texels']}",
            f"- Eye/brow guard texels: {metrics['lower_feature_guard_texels']}",
            f"- Changed texels: {metrics['changed_texels']}",
            f"- Scan hairline hint used: {metrics['scan_hairline_hint'].get('used')}",
            "",
        ])
    lines.extend([
        "## v04_forehead_redefined_region",
        "",
        "This stage restarts from v01, keeps the v03 uniform-tone idea, but redefines the forehead by position.",
        "The forehead is the upper-face region below a smooth predicted hairline and above/excluding eyes and brows.",
        "Hair/black leftovers inside that region are filled as forehead instead of being preserved as black.",
        "",
    ])
    for person in summary["people"]:
        stage = person["stages"].get("v04_forehead_redefined_region", {})
        if not stage:
            continue
        metrics = stage["metrics"]
        paths = stage["paths"]
        lines.extend([
            f"### {person['person']}",
            "",
            f"- Compact review: `{paths.get('compact_review_sheet')}`",
            f"- Texture: `{paths.get('texture')}`",
            f"- Target non-forehead face mean RGB: {[round(x, 2) for x in metrics['target_non_forehead_face_mean_rgb']]}",
            f"- Forehead region texels: {metrics['forehead_region_texels']}",
            f"- Filled hair/black/non-skin texels: {metrics['filled_non_skin_texels']}",
            f"- Observed forehead texels: {metrics['observed_forehead_texels']}",
            f"- Eye/brow guard texels: {metrics['eye_brow_guard_texels']}",
            f"- Hairline fit mode: {metrics['hairline_fit_mode']}",
            f"- Changed texels: {metrics['changed_texels']}",
            "",
        ])
    lines.extend([
        "## v04b_eyebrow_hairline_refine",
        "",
        "This stage keeps the v04 forehead definition idea, but fixes two issues seen in review.",
        "First, eyebrow/eye protection is strengthened with component-scored source selection. When one brow side is good and the other is bad/missing, the bad side is discarded and the good component is mirrored as a fixed black symmetric mask, not color-transferred texture.",
        "Second, the first smooth hairline is reshaped to be less circular across the front, then lifted from reliable forehead-skin evidence with a mirrored frontal lift so one-sided evidence cannot create a one-sided hairline.",
        "Third, the edited forehead is now below the hairline and above the eyebrow baseline, excluding only tight eye/brow guards, instead of keeping only a central reliable-skin component.",
        "The compact sheet adds a bottom row for the secondary hairline correction: purple is the first line, yellow is the lifted line, and cyan is the skin evidence used for the broad lift.",
        "",
    ])
    for person in summary["people"]:
        stage = person["stages"].get("v04b_eyebrow_hairline_refine", {})
        if not stage:
            continue
        metrics = stage["metrics"]
        paths = stage["paths"]
        lines.extend([
            f"### {person['person']}",
            "",
            f"- Compact review: `{paths.get('compact_review_sheet')}`",
            f"- Texture: `{paths.get('texture')}`",
            f"- Target non-forehead face mean RGB: {[round(x, 2) for x in metrics['target_non_forehead_face_mean_rgb']]}",
            f"- Forehead region texels: {metrics['forehead_region_texels']}",
            f"- Filled hair/black/non-skin texels: {metrics['filled_non_skin_texels']}",
            f"- Observed forehead texels: {metrics['observed_forehead_texels']}",
            f"- Forehead definition mode: {metrics.get('forehead_definition_mode')}",
            f"- Brow-axis y px: {metrics.get('brow_axis_y_px')}",
            f"- Initial/final eye-brow guard texels: {metrics['initial_eye_brow_guard_texels']} / {metrics['eye_brow_guard_texels']}",
            f"- Symmetric black eyebrow-mask texels: {metrics['mirrored_eyebrow_texels']} ({metrics['eyebrow_mirror_mode']})",
            f"- Selected eyebrow source: {metrics.get('eyebrow_selected_source')}",
            f"- Hairline lift candidate texels: {metrics['hairline_lift_candidate_texels']}",
            f"- Hairline lift supported/smoothed columns: {metrics['hairline_lift_supported_columns']} / {metrics['hairline_lift_smoothed_columns']}",
            f"- Hairline raw lifted columns before symmetry: {metrics.get('hairline_lift_raw_lifted_columns_before_symmetry')}",
            f"- Max hairline lift px: {round(metrics['hairline_lift_max_px'], 2)}",
            f"- Hairline fit mode: {metrics['hairline_fit_mode']}",
            f"- Changed texels: {metrics['changed_texels']}",
            "",
        ])
    lines.extend([
        "## v05_side_neck_temporary_skin",
        "",
        "This stage starts from v04b and repairs two broader temporary-skin regions before global skin blending.",
        "Green marks side/temple/ear dark fragments filled with a mild side-skin target. Orange marks neck, under-jaw, and clothing-contaminated regions filled with a darker neck target. Blue is protected eye/brow/mouth/hairline material.",
        "",
    ])
    for person in summary["people"]:
        stage = person["stages"].get("v05_side_neck_temporary_skin", {})
        if not stage:
            continue
        metrics = stage["metrics"]
        paths = stage["paths"]
        lines.extend([
            f"### {person['person']}",
            "",
            f"- Compact review: `{paths.get('compact_review_sheet')}`",
            f"- Texture: `{paths.get('texture')}`",
            f"- Side/temple/ear candidate texels: {metrics['side_candidate_texels']}",
            f"- Neck/jaw/clothing candidate texels: {metrics['neck_candidate_texels']}",
            f"- Protected feature texels: {metrics['feature_guard_texels']}",
            f"- Changed texels: {metrics['changed_texels']}",
            f"- Target side RGB: {[round(x, 2) for x in metrics['target_side_rgb']]}",
            f"- Target neck top/bottom RGB: {[round(x, 2) for x in metrics['target_neck_top_rgb']]} / {[round(x, 2) for x in metrics['target_neck_bottom_rgb']]}",
            f"- Mean side/neck weight: {round(metrics['mean_side_weight'], 3)} / {round(metrics['mean_neck_weight'], 3)}",
            "",
        ])
    lines.extend([
        "## v06_simple_bald_skin_fill",
        "",
        "This stage is the simplified bald-head cleanup rule requested after v05 review.",
        "It starts again from v04b instead of stacking on v05: everything above the refined hairline is blacked out as future hair/scalp territory.",
        "Below the hairline, eye/brow/lip/mouth feature guards are protected. Good pixels are kept; bad, black, untrusted, or strong outlier pixels are filled with a simple skin/neck target.",
        "Area-map render colors: black=above hairline, green=kept good pixels, orange=filled bad pixels, blue=protected features, yellow=hairline.",
        "",
    ])
    for person in summary["people"]:
        stage = person["stages"].get("v06_simple_bald_skin_fill", {})
        if not stage:
            continue
        metrics = stage["metrics"]
        paths = stage["paths"]
        lines.extend([
            f"### {person['person']}",
            "",
            f"- Compact review: `{paths.get('compact_review_sheet')}`",
            f"- Texture: `{paths.get('texture')}`",
            f"- Above-hairline black texels: {metrics['above_hairline_texels']}",
            f"- Good kept texels: {metrics['good_kept_texels']}",
            f"- Bad below-hairline filled texels: {metrics['bad_below_hairline_texels']}",
            f"- Protected feature texels: {metrics['feature_guard_texels']}",
            f"- Changed texels: {metrics['changed_texels']}",
            f"- Target skin/neck RGB: {[round(x, 2) for x in metrics['target_skin_rgb']]} / {[round(x, 2) for x in metrics['target_neck_rgb']]}",
            f"- Mean fill weight: {round(metrics['mean_fill_weight'], 3)}",
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
        "stages": [
            "v00_baseline",
            "v01_hard_skin_holes",
            "v02_forehead_tone",
            "v03_forehead_uniform_tone",
            "v04_forehead_redefined_region",
            "v04b_eyebrow_hairline_refine",
            "v05_side_neck_temporary_skin",
            "v06_simple_bald_skin_fill",
        ],
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
            "skip_v02_renders": bool(args.skip_v02_renders),
            "skip_v03_renders": bool(args.skip_v03_renders),
            "skip_v04_renders": bool(args.skip_v04_renders),
            "skip_v04b_renders": bool(args.skip_v04b_renders),
            "skip_v05_renders": bool(args.skip_v05_renders),
            "skip_v06_renders": bool(args.skip_v06_renders),
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
                "v03_compact_review": item["stages"].get("v03_forehead_uniform_tone", {}).get("paths", {}).get("compact_review_sheet"),
                "v03_metrics": _compact_metrics(item["stages"].get("v03_forehead_uniform_tone", {}).get("metrics", {})),
                "v04_compact_review": item["stages"].get("v04_forehead_redefined_region", {}).get("paths", {}).get("compact_review_sheet"),
                "v04_metrics": _compact_metrics(item["stages"].get("v04_forehead_redefined_region", {}).get("metrics", {})),
                "v04b_compact_review": item["stages"].get("v04b_eyebrow_hairline_refine", {}).get("paths", {}).get("compact_review_sheet"),
                "v04b_metrics": _compact_metrics(item["stages"].get("v04b_eyebrow_hairline_refine", {}).get("metrics", {})),
                "v05_compact_review": item["stages"].get("v05_side_neck_temporary_skin", {}).get("paths", {}).get("compact_review_sheet"),
                "v05_metrics": _compact_metrics(item["stages"].get("v05_side_neck_temporary_skin", {}).get("metrics", {})),
                "v06_compact_review": item["stages"].get("v06_simple_bald_skin_fill", {}).get("paths", {}).get("compact_review_sheet"),
                "v06_metrics": _compact_metrics(item["stages"].get("v06_simple_bald_skin_fill", {}).get("metrics", {})),
            }
            for item in summary["people"]
        ],
    }, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
