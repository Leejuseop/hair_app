"""Run Step 4 clean-pixel UV projection.

Step 4 keeps FaceBuilder geometry/camera alignment, but does not trust the raw
FaceBuilder texture pixels blindly. It projects only Step 3 usable-skin pixels
back into the UV atlas and writes diagnostic textures/maps for review.

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

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")
DEFAULT_DRIVE_ROOT = Path(os.environ.get("HAIR_APP_DRIVE_ROOT", "G:/\ub0b4 \ub4dc\ub77c\uc774\ube0c/hair_app"))
PERSONS = ("juseop", "eunchae")
DEFAULT_MASK_VERSION = "v2_farl_grounded_sam"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive-root", type=Path, default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--blender-exe", type=Path, default=DEFAULT_BLENDER_EXE)
    parser.add_argument("--source-version", default="facebuilder_semantic_v2")
    parser.add_argument("--mask-step3-dir", type=Path, default=None)
    parser.add_argument("--mask-version", default=DEFAULT_MASK_VERSION)
    parser.add_argument("--person", action="append", choices=PERSONS)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--headnum", type=int, default=0)
    parser.add_argument("--atlas-size", type=int, default=1024)
    parser.add_argument("--min-confidence", type=float, default=0.08)
    parser.add_argument("--include-align-only", action="store_true")
    parser.add_argument("--skip-blender", action="store_true")
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


def _find_one(pattern_root: Path, pattern: str) -> Path:
    matches = sorted(pattern_root.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No match under {pattern_root}: {pattern}")
    return matches[0]


def _find_latest_step3(drive_root: Path, mask_version: str, people: list[str]) -> Path:
    root = drive_root / "output" / "facebuilder_mask_aware_step3"
    candidates = sorted([path for path in root.iterdir() if path.is_dir()], reverse=True)
    for candidate in candidates:
        ok = True
        for person in people:
            manifest = candidate / mask_version / person / "mask_manifest.json"
            if not manifest.exists():
                ok = False
                break
            data = _read_json(manifest)
            if not data.get("ready_for_comparison"):
                ok = False
                break
        if ok:
            return candidate
    raise FileNotFoundError(f"No ready Step 3 output found for {mask_version} under {root}")


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


def _load_rgb(path: Path | str, size: tuple[int, int] | None = None) -> Image.Image:
    image = ImageOps.exif_transpose(Image.open(_as_path(path))).convert("RGB")
    if size is not None and image.size != size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    return image


def _load_mask(path: Path | str, size: tuple[int, int] | None = None) -> np.ndarray:
    image = Image.open(_as_path(path)).convert("L")
    if size is not None and image.size != size:
        image = image.resize(size, Image.Resampling.NEAREST)
    return np.asarray(image) > 127


def _mask_image(mask: np.ndarray) -> Image.Image:
    return Image.fromarray((mask.astype(np.uint8) * 255), mode="L")


def _bilinear_sample(image: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    x = np.clip(x.astype(np.float32), 0.0, max(0.0, width - 1.001))
    y = np.clip(y.astype(np.float32), 0.0, max(0.0, height - 1.001))
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    dx = (x - x0).reshape(-1, 1)
    dy = (y - y0).reshape(-1, 1)
    c00 = image[y0, x0].astype(np.float32)
    c10 = image[y0, x1].astype(np.float32)
    c01 = image[y1, x0].astype(np.float32)
    c11 = image[y1, x1].astype(np.float32)
    top = c00 * (1.0 - dx) + c10 * dx
    bottom = c01 * (1.0 - dx) + c11 * dx
    return top * (1.0 - dy) + bottom * dy


def _skin_median(image: Image.Image, usable: np.ndarray) -> np.ndarray | None:
    arr = np.asarray(image).astype(np.float32)
    if usable.shape != arr.shape[:2]:
        usable = np.asarray(_mask_image(usable).resize(image.size, Image.Resampling.NEAREST)) > 127
    pixels = arr[usable]
    if pixels.shape[0] < 256:
        return None
    luminance = pixels[:, 0] * 0.2126 + pixels[:, 1] * 0.7152 + pixels[:, 2] * 0.0722
    pixels = pixels[(luminance > 25.0) & (luminance < 242.0)]
    if pixels.shape[0] < 256:
        return None
    return np.median(pixels, axis=0)


def _make_texture(accum: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    covered = weights > 1e-8
    out = np.zeros(accum.shape, dtype=np.uint8)
    if np.any(covered):
        rgb = np.zeros(accum.shape, dtype=np.float32)
        rgb[covered] = accum[covered] / weights[covered, None]
        out[covered] = np.clip(rgb[covered], 0, 255).astype(np.uint8)
    return out, covered


def _confidence_rgb(arr: np.ndarray) -> np.ndarray:
    value = arr.astype(np.float32) / 255.0
    rgb = np.zeros((*arr.shape, 3), dtype=np.uint8)
    mask = arr > 0
    rgb[..., 0] = np.clip((value * 1.55) * 255.0, 0, 255).astype(np.uint8)
    rgb[..., 1] = np.clip((0.18 + value * 0.82) * 255.0, 0, 255).astype(np.uint8)
    rgb[..., 2] = np.clip((0.95 - value * 0.85) * 255.0, 0, 255).astype(np.uint8)
    rgb[~mask] = (8, 8, 8)
    return rgb


def _count_rgb(arr: np.ndarray) -> np.ndarray:
    max_value = float(arr.max()) if arr.size else 0.0
    norm = arr.astype(np.float32) / max(1.0, max_value)
    rgb = np.zeros((*arr.shape, 3), dtype=np.uint8)
    mask = arr > 0
    rgb[..., 0] = np.clip((norm ** 1.3) * 255.0, 0, 255).astype(np.uint8)
    rgb[..., 1] = np.clip((0.15 + np.minimum(norm * 1.35, 1.0)) * 210.0, 0, 255).astype(np.uint8)
    rgb[..., 2] = np.clip((1.0 - norm * 0.45) * 255.0, 0, 255).astype(np.uint8)
    rgb[~mask] = (8, 8, 8)
    return rgb


def _source_rgb(arr: np.ndarray) -> np.ndarray:
    rgb = np.zeros((*arr.shape, 3), dtype=np.uint8)
    valid = arr != 255
    values = arr.astype(np.uint32)
    rgb[..., 0] = ((values * 53 + 41) % 255).astype(np.uint8)
    rgb[..., 1] = ((values * 97 + 103) % 255).astype(np.uint8)
    rgb[..., 2] = ((values * 151 + 179) % 255).astype(np.uint8)
    rgb[~valid] = (8, 8, 8)
    return rgb


def _save_rgb(path: Path, arr: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr.astype(np.uint8), mode="RGB").save(path)
    return _safe_path(path) or ""


def _save_l(path: Path, arr: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr.astype(np.uint8), mode="L").save(path)
    return _safe_path(path) or ""


def _save_rgba(path: Path, rgb: np.ndarray, alpha: np.ndarray) -> str:
    rgba = np.dstack([rgb.astype(np.uint8), alpha.astype(np.uint8)])
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path)
    return _safe_path(path) or ""


def _overlay_on_base(base_path: Path, texture: np.ndarray, alpha: np.ndarray, out_path: Path) -> str | None:
    if not base_path.exists():
        return None
    base = Image.open(base_path).convert("RGB")
    clean = Image.fromarray(texture, mode="RGB").resize(base.size, Image.Resampling.BICUBIC)
    mask = Image.fromarray(alpha, mode="L").resize(base.size, Image.Resampling.NEAREST)
    out = Image.composite(clean, base, mask)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path)
    return _safe_path(out_path)


def _make_tile(title: str, image: Image.Image, width: int = 310) -> Image.Image:
    image = image.convert("RGB")
    ratio = width / image.width
    thumb = image.resize((width, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
    band_h = 34
    out = Image.new("RGB", (thumb.width, thumb.height + band_h), (28, 28, 28))
    out.paste(thumb, (0, band_h))
    draw = ImageDraw.Draw(out)
    draw.text((8, 8), title[:42], fill=(240, 240, 240), font=_font(14))
    return out


def _make_grid_sheet(title: str, subtitle: str, tiles: list[tuple[str, Image.Image]], path: Path, columns: int = 4) -> None:
    if not tiles:
        return
    gap = 12
    header_h = 78
    rendered = [_make_tile(label, image) for label, image in tiles]
    tile_w = max(tile.width for tile in rendered)
    tile_h = max(tile.height for tile in rendered)
    rows = (len(rendered) + columns - 1) // columns
    width = columns * tile_w + (columns + 1) * gap
    height = header_h + rows * tile_h + (rows + 1) * gap
    sheet = Image.new("RGB", (width, height), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 12), title, fill=(245, 245, 245), font=_font(24))
    draw.text((16, 46), subtitle, fill=(180, 180, 180), font=_font(14))
    for index, tile in enumerate(rendered):
        row = index // columns
        col = index % columns
        x = gap + col * (tile_w + gap)
        y = header_h + gap + row * (tile_h + gap)
        sheet.paste(tile, (x, y))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=95)


def _make_source_sheet(person: str, camera_tiles: list[tuple[str, Image.Image]], path: Path) -> None:
    _make_grid_sheet(
        f"{person} Step 4 source contribution review",
        "original crop, usable mask, and UV contribution map for each texture camera. Private; do not commit.",
        camera_tiles,
        path,
        columns=3,
    )


def _make_render_sheet(person: str, render_dir: Path, path: Path) -> str | None:
    images = []
    for render_path in sorted(render_dir.glob("render_yaw_*.png")):
        images.append((render_path.stem.replace("render_yaw_", "yaw "), Image.open(render_path).convert("RGB")))
    if not images:
        return None
    _make_grid_sheet(
        f"{person} Step 4 overlay render review",
        "Projected clean pixels over FaceBuilder cleanup texture. Diagnostic render; not final arbitration.",
        images,
        path,
        columns=4,
    )
    return _safe_path(path)


def _camera_rows(mask_manifest: dict[str, Any]) -> dict[int, dict[str, Any]]:
    rows = {}
    for row in mask_manifest.get("rows") or []:
        rows[int(row["index"])] = row
    return rows


def _estimate_color_reference(rows: list[dict[str, Any]], include_align_only: bool) -> tuple[np.ndarray | None, list[dict[str, Any]]]:
    medians = []
    records = []
    for row in rows:
        if not row.get("ok"):
            continue
        if (not include_align_only) and (not row.get("texture_enabled")):
            continue
        paths = row.get("paths") or {}
        crop_path = paths.get("crop")
        usable_path = paths.get("usable_skin")
        if not crop_path or not usable_path:
            continue
        image = _load_rgb(crop_path)
        usable = _load_mask(usable_path, image.size)
        median = _skin_median(image, usable)
        if median is None:
            continue
        medians.append(median)
        records.append({
            "index": int(row["index"]),
            "image_id": row.get("image_id"),
            "source_name": row.get("source_name"),
            "skin_median_rgb": [float(v) for v in median.tolist()],
        })
    if not medians:
        return None, records
    global_median = np.median(np.stack(medians, axis=0), axis=0)
    return global_median.astype(np.float32), records


def _process_person(
    person: str,
    coord_json: Path,
    coord_npz: Path,
    mask_manifest_path: Path,
    source_person_dir: Path,
    output_dir: Path,
    min_confidence: float,
    include_align_only: bool,
) -> dict[str, Any]:
    coords = _read_json(coord_json)
    mask_manifest = _read_json(mask_manifest_path)
    rows_by_index = _camera_rows(mask_manifest)
    atlas_size = int(coords["atlas_size"])

    output_maps = output_dir / "maps"
    per_camera_dir = output_maps / "per_camera"
    raw_texture = source_person_dir / "05_postprocess" / "facebuilder_texture_bake.png"
    cleanup_texture = source_person_dir / "05_postprocess" / "facebuilder_texture_bald_cleanup.png"

    accum_raw = np.zeros((atlas_size, atlas_size, 3), dtype=np.float64)
    accum_cc = np.zeros((atlas_size, atlas_size, 3), dtype=np.float64)
    weights = np.zeros((atlas_size, atlas_size), dtype=np.float64)
    source_count = np.zeros((atlas_size, atlas_size), dtype=np.uint16)
    best_conf = np.zeros((atlas_size, atlas_size), dtype=np.uint8)
    best_source = np.full((atlas_size, atlas_size), 255, dtype=np.uint8)

    rows = list(rows_by_index.values())
    global_median, median_records = _estimate_color_reference(rows, include_align_only)
    if global_median is None:
        global_median = np.asarray([172.0, 132.0, 112.0], dtype=np.float32)

    camera_summaries: list[dict[str, Any]] = []
    camera_tiles: list[tuple[str, Image.Image]] = []

    with np.load(coord_npz) as data:
        for camera in coords.get("cameras") or []:
            if not camera.get("ok"):
                continue
            index = int(camera["camera_index"])
            row = rows_by_index.get(index)
            if row is None or not row.get("ok"):
                camera_summaries.append({"camera_index": index, "used": False, "reason": "missing_mask_row"})
                continue
            if (not include_align_only) and (not row.get("texture_enabled")):
                camera_summaries.append({"camera_index": index, "used": False, "reason": "alignment_only"})
                continue
            if not camera.get("use_in_tex_baking") and not include_align_only:
                camera_summaries.append({"camera_index": index, "used": False, "reason": "camera_texture_disabled"})
                continue

            prefix = f"camera_{index:03d}"
            required = [f"{prefix}_sample_x", f"{prefix}_sample_y", f"{prefix}_confidence"]
            if any(name not in data.files for name in required):
                camera_summaries.append({"camera_index": index, "used": False, "reason": "missing_coordinate_arrays"})
                continue

            paths = row.get("paths") or {}
            crop_path = paths.get("crop")
            usable_path = paths.get("usable_skin")
            if not crop_path or not usable_path:
                camera_summaries.append({"camera_index": index, "used": False, "reason": "missing_crop_or_usable"})
                continue

            source_w, source_h = [int(v) for v in camera.get("source_image_size") or [0, 0]]
            image = _load_rgb(crop_path)
            image_arr = np.asarray(image).astype(np.float32)
            usable = _load_mask(usable_path, image.size)
            sample_x = data[f"{prefix}_sample_x"]
            sample_y = data[f"{prefix}_sample_y"]
            confidence = data[f"{prefix}_confidence"]

            scale_x = image.width / max(1, source_w)
            scale_y = image.height / max(1, source_h)
            sx = sample_x * scale_x
            sy = sample_y * scale_y
            valid = (
                (confidence.astype(np.float32) / 255.0 >= min_confidence)
                & (sx >= 0.0)
                & (sy >= 0.0)
                & (sx < image.width)
                & (sy < image.height)
            )
            xi = np.clip(np.rint(sx).astype(np.int32), 0, image.width - 1)
            yi = np.clip(np.rint(sy).astype(np.int32), 0, image.height - 1)
            valid &= usable[yi, xi]

            atlas_y, atlas_x = np.nonzero(valid)
            if atlas_y.size == 0:
                camera_summaries.append({
                    "camera_index": index,
                    "used": True,
                    "reason": "no_clean_projected_texels",
                    "image_id": row.get("image_id"),
                    "source_name": row.get("source_name"),
                    "texture_enabled": row.get("texture_enabled"),
                    "clean_texels": 0,
                })
                continue

            rgb = _bilinear_sample(image_arr, sx[valid], sy[valid])
            local_median = _skin_median(image, usable)
            if local_median is None:
                gains = np.ones(3, dtype=np.float32)
            else:
                gains = np.clip(global_median / np.maximum(local_median, 1.0), 0.72, 1.35).astype(np.float32)
            rgb_cc = np.clip(rgb * gains.reshape(1, 3), 0.0, 255.0)
            conf_float = confidence[valid].astype(np.float32) / 255.0
            weight = np.maximum(conf_float, min_confidence) ** 2.0

            accum_raw[atlas_y, atlas_x] += rgb * weight.reshape(-1, 1)
            accum_cc[atlas_y, atlas_x] += rgb_cc * weight.reshape(-1, 1)
            weights[atlas_y, atlas_x] += weight
            source_count[atlas_y, atlas_x] += 1
            update_best = confidence[valid] > best_conf[atlas_y, atlas_x]
            if np.any(update_best):
                uy = atlas_y[update_best]
                ux = atlas_x[update_best]
                best_conf[uy, ux] = confidence[valid][update_best]
                best_source[uy, ux] = index if index < 255 else 254

            contribution = np.zeros((atlas_size, atlas_size), dtype=np.uint8)
            contribution[atlas_y, atlas_x] = confidence[valid]
            contribution_path = per_camera_dir / f"camera_{index:03d}_clean_contribution.png"
            _save_rgb(contribution_path, _confidence_rgb(contribution))
            contribution_mask_path = per_camera_dir / f"camera_{index:03d}_clean_mask.png"
            _save_l(contribution_mask_path, (contribution > 0).astype(np.uint8) * 255)

            camera_summaries.append({
                "camera_index": index,
                "used": True,
                "image_id": row.get("image_id"),
                "source_name": row.get("source_name"),
                "texture_enabled": bool(row.get("texture_enabled")),
                "clean_texels": int(atlas_y.size),
                "clean_coverage_ratio": float(atlas_y.size / max(1, atlas_size * atlas_size)),
                "mean_confidence": float(conf_float.mean()) if conf_float.size else 0.0,
                "median_gain_rgb": [float(v) for v in gains.tolist()],
                "contribution_map": _safe_path(contribution_path),
            })

            if len(camera_tiles) < 36:
                camera_tiles.append((f"cam {index:02d} crop", image))
                camera_tiles.append((f"cam {index:02d} usable", _mask_image(usable).convert("RGB")))
                camera_tiles.append((f"cam {index:02d} UV contribution", Image.open(contribution_path).convert("RGB")))

    texture_raw, covered = _make_texture(accum_raw, weights)
    texture_cc, _ = _make_texture(accum_cc, weights)
    alpha = (covered.astype(np.uint8) * 255)
    confidence_map = best_conf
    source_count_map = source_count
    source_map = best_source

    paths = {
        "projected_clean_texture_raw": _save_rgb(output_maps / "projected_clean_texture_raw.png", texture_raw),
        "projected_clean_texture_color_corrected": _save_rgb(output_maps / "projected_clean_texture_color_corrected.png", texture_cc),
        "projected_clean_texture_rgba": _save_rgba(output_maps / "projected_clean_texture_rgba.png", texture_cc, alpha),
        "projected_coverage_alpha": _save_l(output_maps / "projected_coverage_alpha.png", alpha),
        "projected_best_confidence": _save_rgb(output_maps / "projected_best_confidence.png", _confidence_rgb(confidence_map)),
        "projected_source_count": _save_rgb(output_maps / "projected_source_count.png", _count_rgb(source_count_map)),
        "projected_best_source_camera": _save_rgb(output_maps / "projected_best_source_camera.png", _source_rgb(source_map)),
    }
    overlay_base = cleanup_texture if cleanup_texture.exists() else raw_texture
    overlay_path = _overlay_on_base(
        overlay_base,
        texture_cc,
        alpha,
        output_maps / "projected_over_facebuilder_cleanup_texture.png",
    )
    if overlay_path:
        paths["projected_over_facebuilder_cleanup_texture"] = overlay_path
    arrays_path = output_dir / "step4_projection_arrays.npz"
    np.savez_compressed(
        arrays_path,
        texture_raw=texture_raw,
        texture_color_corrected=texture_cc,
        alpha=alpha,
        best_confidence=confidence_map,
        source_count=source_count_map,
        best_source_camera=source_map,
        weights=weights.astype(np.float32),
    )
    paths["projection_arrays"] = _safe_path(arrays_path) or ""

    main_tiles: list[tuple[str, Image.Image]] = []
    if raw_texture.exists():
        main_tiles.append(("FaceBuilder raw texture", _load_rgb(raw_texture)))
    if cleanup_texture.exists():
        main_tiles.append(("FaceBuilder cleanup texture", _load_rgb(cleanup_texture)))
    main_tiles.extend([
        ("Step4 projected raw", Image.fromarray(texture_raw, mode="RGB")),
        ("Step4 projected color-corrected", Image.fromarray(texture_cc, mode="RGB")),
        ("Step4 over cleanup preview", _load_rgb(overlay_path) if overlay_path else Image.fromarray(texture_cc, mode="RGB")),
        ("Step4 coverage alpha", Image.fromarray(alpha, mode="L").convert("RGB")),
        ("Step4 source count", Image.open(_as_path(paths["projected_source_count"])).convert("RGB")),
        ("Step4 best confidence", Image.open(_as_path(paths["projected_best_confidence"])).convert("RGB")),
        ("Step4 best source camera", Image.open(_as_path(paths["projected_best_source_camera"])).convert("RGB")),
    ])
    review_sheet = output_dir / "review_sheet.png"
    _make_grid_sheet(
        f"{person} Step 4 clean UV projection",
        "Only v2 usable-skin pixels are projected; color-corrected is median-normalized. Private; do not commit.",
        main_tiles,
        review_sheet,
        columns=4,
    )
    source_sheet = output_dir / "source_contribution_sheet.png"
    _make_source_sheet(person, camera_tiles, source_sheet)
    paths["review_sheet"] = _safe_path(review_sheet) or ""
    paths["source_contribution_sheet"] = _safe_path(source_sheet) or ""

    used_cameras = [item for item in camera_summaries if item.get("used") and int(item.get("clean_texels") or 0) > 0]
    covered_pixels = int(covered.sum())
    summary = {
        "person": person,
        "ok": bool(covered_pixels > 0),
        "mask_manifest": _safe_path(mask_manifest_path),
        "coord_json": _safe_path(coord_json),
        "coord_npz": _safe_path(coord_npz),
        "raw_texture": _safe_path(raw_texture) if raw_texture.exists() else None,
        "cleanup_texture": _safe_path(cleanup_texture) if cleanup_texture.exists() else None,
        "atlas_size": atlas_size,
        "min_confidence": min_confidence,
        "include_align_only": include_align_only,
        "global_skin_median_rgb": [float(v) for v in global_median.tolist()],
        "median_records": median_records,
        "counts": {
            "mask_rows": len(rows_by_index),
            "camera_coord_rows": len(coords.get("cameras") or []),
            "used_cameras": len(used_cameras),
            "covered_texels": covered_pixels,
            "coverage_ratio": float(covered_pixels / max(1, atlas_size * atlas_size)),
            "max_source_count": int(source_count_map.max()) if source_count_map.size else 0,
            "mean_source_count_on_covered": float(source_count_map[covered].mean()) if np.any(covered) else 0.0,
            "mean_confidence_on_covered": float(confidence_map[covered].mean() / 255.0) if np.any(covered) else 0.0,
        },
        "paths": paths,
        "camera_summaries": camera_summaries,
    }
    _write_json(output_dir / "step4_person_summary.json", summary)
    return summary


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# FaceBuilder Mask-Aware Correction Step 4 Clean Projection",
        "",
        f"- Created: {summary['created_at']}",
        f"- Source version: `{summary['source_version']}`",
        f"- Mask Step 3 dir: `{summary['mask_step3_dir']}`",
        f"- Mask version: `{summary['mask_version']}`",
        f"- Output root: `{summary['output_dir']}`",
        f"- Atlas size: `{summary['atlas_size']}`",
        f"- Min confidence: `{summary['min_confidence']}`",
        "",
    ]
    for person in summary["people"]:
        counts = person["counts"]
        lines += [
            f"## {person['person']}",
            "",
            f"- Status: {'OK' if person['ok'] else 'NO COVERAGE'}",
            f"- Used cameras: {counts['used_cameras']}",
            f"- Covered texels: {counts['covered_texels']} ({counts['coverage_ratio']:.3f})",
            f"- Max source count: {counts['max_source_count']}",
            f"- Mean source count on covered: {counts['mean_source_count_on_covered']:.3f}",
            f"- Mean confidence on covered: {counts['mean_confidence_on_covered']:.3f}",
            f"- Review: `{person['paths'].get('review_sheet')}`",
            f"- Source sheet: `{person['paths'].get('source_contribution_sheet')}`",
            f"- Render sheet: `{person['paths'].get('render_review_sheet')}`",
            "",
            "### Camera Usage",
            "",
        ]
        for camera in person["camera_summaries"]:
            if camera.get("used"):
                lines.append(
                    f"- cam {camera['camera_index']:02d}: used, clean_texels={camera.get('clean_texels', 0)}, "
                    f"source=`{camera.get('source_name')}`"
                )
            else:
                lines.append(f"- cam {camera['camera_index']:02d}: skipped, reason={camera.get('reason')}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    people = args.person or list(PERSONS)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = args.output_dir or (args.drive_root / "output" / "facebuilder_mask_aware_step4" / stamp)
    source_root = args.drive_root / "output" / args.source_version
    mask_step3_dir = args.mask_step3_dir or _find_latest_step3(args.drive_root, args.mask_version, people)
    blender_script = REPO_ROOT / "experiments" / "facebuilder_mask_aware_correction" / "blender_step4_uv_sample_coords.py"
    render_script = REPO_ROOT / "experiments" / "facebuilder_mask_aware_correction" / "blender_step4_render_texture.py"

    summary: dict[str, Any] = {
        "schema_version": "facebuilder_mask_aware_step4_clean_projection_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": _safe_path(REPO_ROOT),
        "drive_root": _safe_path(args.drive_root),
        "source_version": args.source_version,
        "source_root": _safe_path(source_root),
        "mask_step3_dir": _safe_path(mask_step3_dir),
        "mask_version": args.mask_version,
        "output_dir": _safe_path(output_root),
        "blender_exe": _safe_path(args.blender_exe),
        "atlas_size": args.atlas_size,
        "min_confidence": args.min_confidence,
        "include_align_only": bool(args.include_align_only),
        "people": [],
    }

    for person in people:
        person_dir = source_root / person
        blend = _find_one(person_dir / "03_facebuilder_scene", "*.blend")
        person_output = output_root / person
        projection_dir = person_output / "projection"
        coord_json = projection_dir / "uv_sample_coords.json"
        coord_npz = projection_dir / "uv_sample_coords_arrays.npz"
        blender_log = person_output / "logs" / "blender_step4_stdout_stderr.txt"
        mask_manifest = mask_step3_dir / args.mask_version / person / "mask_manifest.json"
        if not mask_manifest.exists():
            raise FileNotFoundError(mask_manifest)

        if not args.skip_blender:
            projection_dir.mkdir(parents=True, exist_ok=True)
            blender_log.parent.mkdir(parents=True, exist_ok=True)
            cmd = [
                str(args.blender_exe),
                "--background",
                str(blend),
                "--python",
                str(blender_script),
                "--",
                "--output-json",
                str(coord_json),
                "--output-npz",
                str(coord_npz),
                "--headnum",
                str(args.headnum),
                "--atlas-size",
                str(args.atlas_size),
            ]
            if not args.include_align_only:
                cmd.append("--texture-only")
            completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
            blender_log.write_text(
                (completed.stdout or "") + "\n--- STDERR ---\n" + (completed.stderr or ""),
                encoding="utf-8",
            )
            if completed.returncode != 0:
                raise RuntimeError(f"Blender Step 4 failed for {person}; see {blender_log}")

        person_summary = _process_person(
            person=person,
            coord_json=coord_json,
            coord_npz=coord_npz,
            mask_manifest_path=mask_manifest,
            source_person_dir=person_dir,
            output_dir=person_output,
            min_confidence=args.min_confidence,
            include_align_only=bool(args.include_align_only),
        )
        overlay_texture = person_summary.get("paths", {}).get("projected_over_facebuilder_cleanup_texture")
        if overlay_texture:
            render_dir = person_output / "renders" / "projected_over_cleanup"
            render_json = render_dir / "render_summary.json"
            render_log = person_output / "logs" / "blender_step4_render_stdout_stderr.txt"
            cmd = [
                str(args.blender_exe),
                "--background",
                str(blend),
                "--python",
                str(render_script),
                "--",
                "--texture",
                str(_as_path(overlay_texture)),
                "--output-dir",
                str(render_dir),
                "--output-json",
                str(render_json),
                "--headnum",
                str(args.headnum),
            ]
            completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
            render_log.write_text(
                (completed.stdout or "") + "\n--- STDERR ---\n" + (completed.stderr or ""),
                encoding="utf-8",
            )
            person_summary["render"] = {
                "ok": completed.returncode == 0 and render_json.exists() and _read_json(render_json).get("ok"),
                "render_json": _safe_path(render_json),
                "render_dir": _safe_path(render_dir),
                "log": _safe_path(render_log),
            }
            render_sheet = _make_render_sheet(person, render_dir, person_output / "render_review_sheet.png")
            if render_sheet:
                person_summary["paths"]["render_review_sheet"] = render_sheet
        summary["people"].append(person_summary)

    summary_json = output_root / "step4_summary.json"
    report_md = output_root / "step4_report.md"
    _write_json(summary_json, summary)
    _write_report(report_md, summary)
    print(json.dumps({
        "summary_json": _safe_path(summary_json),
        "report_md": _safe_path(report_md),
        "people": [
            {
                "person": person["person"],
                "ok": person["ok"],
                "coverage_ratio": person["counts"]["coverage_ratio"],
                "used_cameras": person["counts"]["used_cameras"],
                "review_sheet": person["paths"].get("review_sheet"),
                "source_contribution_sheet": person["paths"].get("source_contribution_sheet"),
                "render_review_sheet": person["paths"].get("render_review_sheet"),
            }
            for person in summary["people"]
        ],
    }, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
