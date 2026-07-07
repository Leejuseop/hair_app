"""Score photo-level eye/brow/lip feature candidates for Step 7.

This diagnostic stage does not write a new texture. It reviews the crop photos
that can be used as feature sources, extracts parser/object-mask based
candidate regions, and scores whether each photo is a good source for brows,
eyes, lips, and inner mouth.

Private review outputs stay in Drive and must not be committed.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy import ndimage


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DRIVE_ROOT = Path(os.environ.get("HAIR_APP_DRIVE_ROOT", "G:/\ub0b4 \ub4dc\ub77c\uc774\ube0c/hair_app"))
PERSONS = ("juseop", "eunchae")

FEATURES = {
    "eyebrow": {
        "labels": {6, 7},
        "color": (0, 220, 255),
        "min_area": 16,
        "keep_components": 4,
        "expected_area": (0.0020, 0.0280),
        "weight": 0.28,
    },
    "eye": {
        "labels": {8, 9},
        "color": (45, 120, 255),
        "min_area": 14,
        "keep_components": 4,
        "expected_area": (0.0015, 0.0300),
        "weight": 0.28,
    },
    "lip": {
        "labels": {12, 13},
        "color": (255, 80, 210),
        "min_area": 14,
        "keep_components": 3,
        "expected_area": (0.0010, 0.0280),
        "weight": 0.28,
    },
    "inner_mouth": {
        "labels": {11},
        "color": (255, 60, 60),
        "min_area": 8,
        "keep_components": 2,
        "expected_area": (0.0002, 0.0200),
        "weight": 0.16,
    },
}

FACE_RELATED_LABELS = {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13}
BAD_OCCLUDER_LABELS = {3, 14, 15, 16, 17, 18, 20}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive-root", type=Path, default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--step1-root", type=Path, default=None)
    parser.add_argument("--step2-root", type=Path, default=None)
    parser.add_argument("--step3-root", type=Path, default=None)
    parser.add_argument("--step6-root", type=Path, default=None)
    parser.add_argument("--step3-version", default="v2_farl_grounded_sam")
    parser.add_argument("--source-version", default="facebuilder_semantic_v2")
    parser.add_argument("--person", action="append", choices=PERSONS)
    parser.add_argument("--include-scans", action="store_true")
    parser.add_argument("--max-review-width", type=int, default=1400)
    return parser.parse_args(argv)


def _safe_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    return Path(str(value).replace("/", os.sep))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _latest_dir(parent: Path) -> Path:
    candidates = [p for p in parent.iterdir() if p.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No directories under {parent}")
    return sorted(candidates, key=lambda p: p.name)[-1]


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


def _load_rgb(path: Path | str) -> Image.Image:
    resolved = _path(path)
    if resolved is None:
        raise FileNotFoundError(path)
    return ImageOps.exif_transpose(Image.open(resolved)).convert("RGB")


def _load_label(path: Path | str, target_size: tuple[int, int]) -> np.ndarray:
    resolved = _path(path)
    if resolved is None:
        raise FileNotFoundError(path)
    with Image.open(resolved) as image:
        arr = np.asarray(image)
    if arr.ndim == 3:
        arr = arr[:, :, 0]
    if (arr.shape[1], arr.shape[0]) != target_size:
        arr = np.asarray(Image.fromarray(arr.astype(np.uint8)).resize(target_size, Image.Resampling.NEAREST))
    return arr.astype(np.uint8)


def _load_mask(path: Path | str | None, target_size: tuple[int, int]) -> np.ndarray:
    if path is None:
        return np.zeros((target_size[1], target_size[0]), dtype=bool)
    resolved = _path(path)
    if resolved is None or not resolved.exists():
        return np.zeros((target_size[1], target_size[0]), dtype=bool)
    with Image.open(resolved) as image:
        arr = np.asarray(image.convert("L"))
    if (arr.shape[1], arr.shape[0]) != target_size:
        arr = np.asarray(Image.fromarray(arr).resize(target_size, Image.Resampling.NEAREST))
    return arr > 127


def _bbox(mask: np.ndarray) -> list[int] | None:
    ys, xs = np.where(mask)
    if xs.size == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def _bbox_area(box: list[int] | None) -> float:
    if not box:
        return 0.0
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def _bbox_iou(a: list[int] | None, b: list[int] | None) -> float:
    if not a or not b:
        return 0.0
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = _bbox_area(a) + _bbox_area(b) - inter
    return float(inter / union) if union > 0 else 0.0


def _mask_center_x(mask: np.ndarray) -> float:
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return float(mask.shape[1]) * 0.5
    return float(xs.mean())


def _face_center_x(label: np.ndarray) -> float:
    nose = label == 10
    if int(nose.sum()) >= 20:
        return _mask_center_x(nose)
    face_mask = np.isin(label, list(FACE_RELATED_LABELS))
    box = _bbox(face_mask)
    if box:
        return float(box[0] + box[2]) * 0.5
    return float(label.shape[1]) * 0.5


def _split_eyebrow_by_image_side(mask: np.ndarray, label: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Split a union eyebrow mask into image-space left/right components.

    FaRL's anatomical left/right labels are intentionally ignored here. We first
    trust only the union eyebrow region, then classify connected components by
    their centroid relative to the face centerline in the crop image.
    """
    center_x = _face_center_x(label)
    labels, count = ndimage.label(mask)
    image_left = np.zeros_like(mask, dtype=bool)
    image_right = np.zeros_like(mask, dtype=bool)
    components: list[dict[str, Any]] = []
    for label_id in range(1, count + 1):
        component = labels == label_id
        area = int(component.sum())
        if area == 0:
            continue
        ys, xs = np.nonzero(component)
        centroid_x = float(xs.mean())
        side = "image_left" if centroid_x < center_x else "image_right"
        if side == "image_left":
            image_left |= component
        else:
            image_right |= component
        box = _bbox(component)
        components.append({
            "component": int(label_id),
            "area": area,
            "bbox": box,
            "centroid_x": centroid_x,
            "center_x": center_x,
            "side": side,
        })
    return image_left, image_right, {
        "centerline_source": "nose_label_10_or_face_bbox_fallback",
        "center_x": center_x,
        "image_left_pixels": int(image_left.sum()),
        "image_right_pixels": int(image_right.sum()),
        "components": components,
        "definition": "image_left/right are crop-image directions; FaRL left/right labels are merged before this split.",
    }


def _component_filter(mask: np.ndarray, *, min_area: int, keep_components: int) -> tuple[np.ndarray, list[dict[str, Any]]]:
    labels, count = ndimage.label(mask)
    components: list[dict[str, Any]] = []
    for label_id in range(1, count + 1):
        component = labels == label_id
        area = int(component.sum())
        if area == 0:
            continue
        box = _bbox(component)
        width = int(box[2] - box[0]) if box else 0
        height = int(box[3] - box[1]) if box else 0
        components.append({
            "label": int(label_id),
            "area": area,
            "bbox": box,
            "width": width,
            "height": height,
            "kept": False,
        })
    keep_ids = {
        item["label"]
        for item in sorted(
            [item for item in components if item["area"] >= min_area],
            key=lambda item: item["area"],
            reverse=True,
        )[:keep_components]
    }
    keep = np.isin(labels, list(keep_ids))
    for item in components:
        item["kept"] = item["label"] in keep_ids
    return keep, components


def _score_interval(value: float, low: float, high: float) -> float:
    if value <= 0:
        return 0.0
    if low <= value <= high:
        return 1.0
    if value < low:
        return max(0.0, value / max(low, 1e-8))
    return max(0.0, 1.0 - (value - high) / max(high, 1e-8))


def _laplacian_var(gray: np.ndarray, mask: np.ndarray | None = None) -> float:
    gray_f = gray.astype(np.float32)
    lap = (
        -4.0 * gray_f
        + np.roll(gray_f, 1, axis=0)
        + np.roll(gray_f, -1, axis=0)
        + np.roll(gray_f, 1, axis=1)
        + np.roll(gray_f, -1, axis=1)
    )
    valid = mask if mask is not None and int(mask.sum()) >= 64 else np.ones_like(gray, dtype=bool)
    return float(np.var(lap[valid]))


def _blur_score(lap_var: float) -> float:
    lo = math.log1p(18.0)
    hi = math.log1p(420.0)
    value = math.log1p(max(0.0, lap_var))
    return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))


def _exposure_score(rgb: np.ndarray, mask: np.ndarray) -> tuple[float, dict[str, float]]:
    if int(mask.sum()) < 8:
        return 0.0, {"mean_luma": 0.0, "clip_ratio": 1.0}
    pixels = rgb[mask].astype(np.float32)
    luma = pixels[:, 0] * 0.2126 + pixels[:, 1] * 0.7152 + pixels[:, 2] * 0.0722
    mean_luma = float(luma.mean())
    mid = 1.0 - min(1.0, abs(mean_luma - 128.0) / 118.0)
    clip_ratio = float(((luma < 8.0) | (luma > 248.0)).mean())
    score = float(np.clip(mid * 0.72 + (1.0 - clip_ratio) * 0.28, 0.0, 1.0))
    return score, {"mean_luma": mean_luma, "clip_ratio": clip_ratio}


def _camera_maps(step1_root: Path, step2_root: Path, person: str) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    step1_path = step1_root / person / "projection" / "camera_projection_wireframe.json"
    step2_path = step2_root / person / "projection" / "uv_visibility.json"
    step1 = _read_json(step1_path)
    step2 = _read_json(step2_path)
    return (
        {int(item["camera_index"]): item for item in step1.get("cameras", [])},
        {int(item["camera_index"]): item for item in step2.get("cameras", [])},
    )


def _alignment_score(label: np.ndarray, projected_bbox: list[int] | None) -> tuple[float, dict[str, Any]]:
    face_mask = np.isin(label, list(FACE_RELATED_LABELS))
    face_box = _bbox(face_mask)
    if not face_box or not projected_bbox:
        return 0.35, {"face_bbox": face_box, "projected_bbox": projected_bbox, "bbox_iou": 0.0}
    iou = _bbox_iou(face_box, projected_bbox)
    cx_face = (face_box[0] + face_box[2]) * 0.5
    cy_face = (face_box[1] + face_box[3]) * 0.5
    cx_proj = (projected_bbox[0] + projected_bbox[2]) * 0.5
    cy_proj = (projected_bbox[1] + projected_bbox[3]) * 0.5
    h, w = label.shape
    center_distance = math.sqrt(((cx_face - cx_proj) / w) ** 2 + ((cy_face - cy_proj) / h) ** 2)
    center_score = float(np.clip(1.0 - center_distance / 0.18, 0.0, 1.0))
    score = float(np.clip(0.68 * min(1.0, iou / 0.50) + 0.32 * center_score, 0.0, 1.0))
    return score, {
        "face_bbox": face_box,
        "projected_bbox": projected_bbox,
        "bbox_iou": float(iou),
        "center_distance": float(center_distance),
    }


def _camera_score(row: dict[str, Any], label: np.ndarray, step1_camera: dict[str, Any] | None, step2_camera: dict[str, Any] | None) -> tuple[float, dict[str, Any]]:
    texture_score = 1.0 if row.get("texture_enabled") else 0.35
    pins = float((step1_camera or {}).get("pins_count", 0))
    pins_score = float(np.clip(pins / 20.0, 0.0, 1.0))
    view_conf = float((step2_camera or {}).get("mean_view_confidence", 0.0))
    view_score = float(np.clip(view_conf / 0.62, 0.0, 1.0))
    projected_bbox = (step1_camera or {}).get("projected_bbox")
    align_score, align_meta = _alignment_score(label, projected_bbox)
    score = float(np.clip(0.25 * texture_score + 0.25 * pins_score + 0.25 * view_score + 0.25 * align_score, 0.0, 1.0))
    return score, {
        "texture_enabled_score": texture_score,
        "pins_count": pins,
        "pins_score": pins_score,
        "mean_view_confidence": view_conf,
        "view_score": view_score,
        "alignment_score": align_score,
        **align_meta,
    }


def _quality_label(score: float) -> str:
    if score >= 0.78:
        return "good"
    if score >= 0.58:
        return "ok"
    if score >= 0.38:
        return "weak"
    return "bad"


def _score_feature(
    *,
    name: str,
    config: dict[str, Any],
    label: np.ndarray,
    crop_arr: np.ndarray,
    object_mask: np.ndarray,
    bad_occluder_mask: np.ndarray,
    camera_score: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    raw = np.isin(label, list(config["labels"]))
    object_dilated = ndimage.binary_dilation(object_mask, iterations=2)
    candidate_raw = raw & ~object_dilated
    candidate, components = _component_filter(
        candidate_raw,
        min_area=int(config["min_area"]),
        keep_components=int(config["keep_components"]),
    )
    area_ratio = float(candidate.sum() / candidate.size)
    raw_area_ratio = float(raw.sum() / raw.size)
    low, high = config["expected_area"]
    area_score = _score_interval(area_ratio, float(low), float(high))
    kept_count = sum(1 for item in components if item["kept"])
    if name in {"eyebrow", "eye"}:
        component_score = 1.0 if 1 <= kept_count <= 4 else (0.45 if kept_count > 0 else 0.0)
    else:
        component_score = 1.0 if 1 <= kept_count <= 3 else (0.45 if kept_count > 0 else 0.0)
    object_overlap = float((raw & object_dilated).sum() / max(1, int(raw.sum())))
    bad_label_overlap = float((raw & bad_occluder_mask).sum() / max(1, int(raw.sum())))
    occlusion_score = float(np.clip(1.0 - object_overlap * 1.35 - bad_label_overlap * 0.35, 0.0, 1.0))
    gray = np.asarray(Image.fromarray(crop_arr).convert("L"))
    blur_var = _laplacian_var(gray, candidate if int(candidate.sum()) >= 64 else None)
    blur = _blur_score(blur_var)
    exposure, exposure_meta = _exposure_score(crop_arr, candidate)
    parser_score = float(np.clip(area_score * 0.70 + component_score * 0.30, 0.0, 1.0))
    total = float(np.clip(
        0.34 * parser_score
        + 0.16 * blur
        + 0.16 * exposure
        + 0.18 * occlusion_score
        + 0.16 * camera_score,
        0.0,
        1.0,
    ))
    return candidate, {
        "score": total,
        "score_100": round(total * 100.0, 1),
        "quality": _quality_label(total),
        "parser_score": parser_score,
        "area_score": area_score,
        "component_score": component_score,
        "blur_score": blur,
        "blur_laplacian_var": blur_var,
        "exposure_score": exposure,
        "occlusion_score": occlusion_score,
        "camera_score": camera_score,
        "area_ratio": area_ratio,
        "raw_area_ratio": raw_area_ratio,
        "object_overlap_ratio": object_overlap,
        "bad_label_overlap_ratio": bad_label_overlap,
        "bbox": _bbox(candidate),
        "components_kept": int(kept_count),
        "components_total": int(len(components)),
        "components_preview": components[:12],
        **exposure_meta,
    }


def _overlay_features(crop: Image.Image, feature_masks: dict[str, np.ndarray], object_mask: np.ndarray) -> Image.Image:
    base = crop.convert("RGBA")
    arr = np.zeros((base.height, base.width, 4), dtype=np.uint8)
    if np.any(object_mask):
        arr[object_mask] = (255, 210, 30, 115)
    for name, mask in feature_masks.items():
        color = FEATURES[name]["color"]
        arr[mask] = (color[0], color[1], color[2], 145)
    overlay = Image.fromarray(arr, mode="RGBA")
    return Image.alpha_composite(base, overlay).convert("RGB")


def _overlay_eyebrow_sides(crop: Image.Image, image_left: np.ndarray, image_right: np.ndarray) -> Image.Image:
    base = crop.convert("RGBA")
    arr = np.zeros((base.height, base.width, 4), dtype=np.uint8)
    arr[image_left] = (0, 220, 255, 155)
    arr[image_right] = (255, 170, 45, 155)
    overlay = Image.fromarray(arr, mode="RGBA")
    return Image.alpha_composite(base, overlay).convert("RGB")


def _mask_cutout(crop: Image.Image, mask: np.ndarray, *, label: str, size: tuple[int, int] = (300, 210)) -> Image.Image:
    panel = Image.new("RGB", size, (10, 10, 10))
    draw = ImageDraw.Draw(panel)
    small = _font(13)
    box = _bbox(mask)
    if not box:
        draw.text((18, 84), "empty", fill=(155, 155, 155), font=_font(24))
        return panel
    margin = 14
    x0 = max(0, box[0] - margin)
    y0 = max(0, box[1] - margin)
    x1 = min(crop.width, box[2] + margin)
    y1 = min(crop.height, box[3] + margin)
    crop_arr = np.asarray(crop)
    local_mask = mask[y0:y1, x0:x1]
    local_rgb = crop_arr[y0:y1, x0:x1].copy()
    bg = np.zeros_like(local_rgb)
    bg[..., :] = 24
    cutout = np.where(local_mask[..., None], local_rgb, bg)
    image = Image.fromarray(cutout.astype(np.uint8), mode="RGB")
    image.thumbnail((size[0] - 16, size[1] - 24), Image.Resampling.NEAREST)
    panel.paste(image, ((size[0] - image.width) // 2, 12))
    draw.text((8, size[1] - 20), f"{int(mask.sum())} px", fill=(180, 180, 180), font=small)
    return panel


def _make_eyebrow_side_review_sheet(
    person: str,
    rows: list[dict[str, Any]],
    side_review_images: dict[int, dict[str, Image.Image]],
    output_path: Path,
) -> None:
    tile_w = 1240
    tile_h = 260
    header_h = 112
    sheet = Image.new("RGB", (tile_w, header_h + max(1, len(rows)) * tile_h), (12, 12, 12))
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 12), f"{person} v07a eyebrow image-side split review", fill=(245, 245, 245), font=_font(26))
    draw.text(
        (16, 48),
        "cyan=image_left_brow, orange=image_right_brow. FaRL left/right labels are merged first, then split by face centerline.",
        fill=(190, 190, 190),
        font=_font(13),
    )
    draw.text(
        (16, 70),
        "This sheet checks side assignment only. It does not apply color normalization or dark-pixel filtering.",
        fill=(170, 170, 170),
        font=_font(13),
    )
    for i, row in enumerate(rows):
        y = header_h + i * tile_h
        draw.text((14, y + 16), f"{row['index']:03d}", fill=(255, 235, 120), font=_font(22))
        draw.text((14, y + 48), str(row["source_name"])[:22], fill=(220, 220, 220), font=_font(13))
        eyebrow = row["features"]["eyebrow"]
        side = row.get("eyebrow_image_side_split") or {}
        draw.text((14, y + 72), f"brow {eyebrow['score_100']:05.1f}", fill=(190, 190, 190), font=_font(12))
        draw.text(
            (14, y + 92),
            f"L {side.get('image_left_pixels', 0)} / R {side.get('image_right_pixels', 0)} px",
            fill=(190, 190, 190),
            font=_font(12),
        )
        images = side_review_images[row["index"]]
        x = 190
        for key, label in (
            ("source", "source crop"),
            ("overlay", "side overlay"),
            ("image_left", "image_left_brow"),
            ("image_right", "image_right_brow"),
        ):
            panel = Image.new("RGB", (250, 230), (18, 18, 18))
            draw_panel = ImageDraw.Draw(panel)
            draw_panel.text((8, 8), label, fill=(230, 230, 230), font=_font(13))
            image = images[key].copy()
            image.thumbnail((234, 190), Image.Resampling.LANCZOS if key in {"source", "overlay"} else Image.Resampling.NEAREST)
            panel.paste(image, ((250 - image.width) // 2, 34))
            sheet.paste(panel, (x, y + 14))
            x += 260
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def _make_tile(row: dict[str, Any], overlay: Image.Image, tile_w: int = 420, tile_h: int = 440) -> Image.Image:
    tile = Image.new("RGB", (tile_w, tile_h), (18, 18, 18))
    draw = ImageDraw.Draw(tile)
    title_font = _font(18)
    small = _font(12)
    medium = _font(14)
    image = overlay.copy()
    image.thumbnail((tile_w - 24, 274), Image.Resampling.LANCZOS)
    x = (tile_w - image.width) // 2
    tile.paste(image, (x, 42))
    name = str(row["source_name"])
    title = f"{row['index']:03d} {name}"
    draw.text((12, 10), title[:46], fill=(245, 245, 245), font=title_font)
    draw.text((12, 320), f"overall {row['overall_score_100']:05.1f}  {row['overall_quality']}", fill=(255, 235, 150), font=medium)
    y = 344
    for feature in ("eyebrow", "eye", "lip", "inner_mouth"):
        item = row["features"][feature]
        color = FEATURES[feature]["color"]
        draw.rectangle((12, y + 3, 24, y + 15), fill=color)
        text = f"{feature:<11} {item['score_100']:05.1f} {item['quality']:<4} area {item['area_ratio']*100:.2f}% occ {item['object_overlap_ratio']*100:.1f}%"
        draw.text((30, y), text, fill=(220, 220, 220), font=small)
        y += 20
    camera = row["camera"]
    draw.text(
        (12, y + 2),
        f"cam {camera['score_100']:05.1f} pins {camera['pins_count']:.0f} view {camera['mean_view_confidence']:.2f} bboxIoU {camera.get('bbox_iou', 0):.2f}",
        fill=(170, 190, 220),
        font=small,
    )
    return tile


def _make_review_sheet(person: str, rows: list[dict[str, Any]], overlays: dict[int, Image.Image], output_path: Path, *, max_width: int) -> None:
    tile_w, tile_h = 420, 440
    cols = max(1, min(3, max_width // tile_w))
    rows_count = int(math.ceil(len(rows) / cols)) if rows else 1
    header_h = 104
    sheet = Image.new("RGB", (cols * tile_w, header_h + rows_count * tile_h), (12, 12, 12))
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 12), f"{person} v07a feature source candidates", fill=(245, 245, 245), font=_font(26))
    draw.text(
        (16, 46),
        "Overlay: cyan=brow, blue=eye, magenta=lip, red=inner mouth, yellow=object/occlusion. Texture-enabled crop photos only.",
        fill=(190, 190, 190),
        font=_font(13),
    )
    draw.text(
        (16, 68),
        "Scores combine parser area/components, blur, exposure, object overlap, FaceBuilder pins/view confidence, and projected bbox alignment proxy.",
        fill=(170, 170, 170),
        font=_font(13),
    )
    for i, row in enumerate(rows):
        tile = _make_tile(row, overlays[row["index"]], tile_w=tile_w, tile_h=tile_h)
        x = (i % cols) * tile_w
        y = header_h + (i // cols) * tile_h
        sheet.paste(tile, (x, y))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def _resolve_roots(args: argparse.Namespace) -> dict[str, Path]:
    output_root = args.drive_root / "output"
    return {
        "step1": args.step1_root or _latest_dir(output_root / "facebuilder_mask_aware_step1"),
        "step2": args.step2_root or _latest_dir(output_root / "facebuilder_mask_aware_step2"),
        "step3": args.step3_root or _latest_dir(output_root / "facebuilder_mask_aware_step3"),
        "step6": args.step6_root or _latest_dir(output_root / "facebuilder_mask_aware_step6"),
    }


def _score_person(
    *,
    person: str,
    args: argparse.Namespace,
    roots: dict[str, Path],
    person_output: Path,
) -> dict[str, Any]:
    manifest_path = roots["step3"] / args.step3_version / person / "mask_manifest.json"
    manifest = _read_json(manifest_path)
    step1_by_camera, step2_by_camera = _camera_maps(roots["step1"], roots["step2"], person)
    rows_out: list[dict[str, Any]] = []
    overlays: dict[int, Image.Image] = {}
    eyebrow_side_review_images: dict[int, dict[str, Image.Image]] = {}
    per_image_dir = person_output / "per_image"
    per_image_dir.mkdir(parents=True, exist_ok=True)

    for row in manifest.get("rows", []):
        if not args.include_scans and not bool(row.get("texture_enabled")):
            continue
        if not row.get("ok"):
            continue
        index = int(row["index"])
        crop = _load_rgb(row["paths"]["crop"])
        crop_arr = np.asarray(crop)
        target_size = crop.size
        label = _load_label(row["paths"]["parser_label"], target_size)
        object_mask = _load_mask(row["paths"].get("object_mask"), target_size)
        bad_occluder_mask = np.isin(label, list(BAD_OCCLUDER_LABELS))
        camera_score, camera_meta = _camera_score(row, label, step1_by_camera.get(index), step2_by_camera.get(index))
        feature_masks: dict[str, np.ndarray] = {}
        feature_scores: dict[str, Any] = {}
        for feature_name, feature_config in FEATURES.items():
            mask, score = _score_feature(
                name=feature_name,
                config=feature_config,
                label=label,
                crop_arr=crop_arr,
                object_mask=object_mask,
                bad_occluder_mask=bad_occluder_mask,
                camera_score=camera_score,
            )
            feature_masks[feature_name] = mask
            feature_scores[feature_name] = score
        image_left_brow, image_right_brow, eyebrow_side_meta = _split_eyebrow_by_image_side(feature_masks["eyebrow"], label)
        total_weight = sum(float(FEATURES[name]["weight"]) for name in FEATURES)
        overall = sum(feature_scores[name]["score"] * float(FEATURES[name]["weight"]) for name in FEATURES) / total_weight
        overlay = _overlay_features(crop, feature_masks, object_mask)
        eyebrow_side_overlay = _overlay_eyebrow_sides(crop, image_left_brow, image_right_brow)
        overlay_path = per_image_dir / f"{index:03d}_{row['image_id']}_feature_overlay.png"
        eyebrow_side_overlay_path = per_image_dir / f"{index:03d}_{row['image_id']}_eyebrow_image_side_overlay.png"
        overlay.save(overlay_path)
        eyebrow_side_overlay.save(eyebrow_side_overlay_path)
        masks_dir = per_image_dir / f"{index:03d}_{row['image_id']}_masks"
        masks_dir.mkdir(parents=True, exist_ok=True)
        mask_paths: dict[str, str] = {}
        for feature_name, mask in feature_masks.items():
            mask_path = masks_dir / f"{feature_name}.png"
            Image.fromarray((mask.astype(np.uint8) * 255), mode="L").save(mask_path)
            mask_paths[feature_name] = _safe_path(mask_path)
        for side_name, side_mask in (
            ("eyebrow_image_left", image_left_brow),
            ("eyebrow_image_right", image_right_brow),
        ):
            side_path = masks_dir / f"{side_name}.png"
            Image.fromarray((side_mask.astype(np.uint8) * 255), mode="L").save(side_path)
            mask_paths[side_name] = _safe_path(side_path)
        image_left_cutout = _mask_cutout(crop, image_left_brow, label="image_left_brow")
        image_right_cutout = _mask_cutout(crop, image_right_brow, label="image_right_brow")
        image_left_cutout_path = masks_dir / "eyebrow_image_left_cutout.png"
        image_right_cutout_path = masks_dir / "eyebrow_image_right_cutout.png"
        image_left_cutout.save(image_left_cutout_path)
        image_right_cutout.save(image_right_cutout_path)
        mask_paths["eyebrow_image_left_cutout"] = _safe_path(image_left_cutout_path)
        mask_paths["eyebrow_image_right_cutout"] = _safe_path(image_right_cutout_path)
        mask_paths["eyebrow_image_side_overlay"] = _safe_path(eyebrow_side_overlay_path)
        overlays[index] = overlay
        source_thumb = crop.copy()
        source_thumb.thumbnail((260, 210), Image.Resampling.LANCZOS)
        eyebrow_side_review_images[index] = {
            "source": source_thumb,
            "overlay": eyebrow_side_overlay,
            "image_left": image_left_cutout,
            "image_right": image_right_cutout,
        }
        row_out = {
            "index": index,
            "image_id": row.get("image_id"),
            "source_name": row.get("source_name"),
            "texture_enabled": bool(row.get("texture_enabled")),
            "crop_path": row["paths"]["crop"],
            "overlay_path": _safe_path(overlay_path),
            "mask_paths": mask_paths,
            "overall_score": float(overall),
            "overall_score_100": round(float(overall) * 100.0, 1),
            "overall_quality": _quality_label(float(overall)),
            "features": feature_scores,
            "eyebrow_image_side_split": eyebrow_side_meta,
            "camera": {
                **camera_meta,
                "score": camera_score,
                "score_100": round(camera_score * 100.0, 1),
            },
        }
        rows_out.append(row_out)

    rows_out.sort(key=lambda item: item["index"])
    review_sheet = person_output / "v07a_feature_source_review_sheet.png"
    _make_review_sheet(person, rows_out, overlays, review_sheet, max_width=args.max_review_width)
    eyebrow_side_review_sheet = person_output / "v07a_eyebrow_image_side_split_review_sheet.png"
    _make_eyebrow_side_review_sheet(person, rows_out, eyebrow_side_review_images, eyebrow_side_review_sheet)
    csv_path = person_output / "v07a_feature_source_scores.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "index",
            "source_name",
            "overall",
            "quality",
            "eyebrow",
            "eye",
            "lip",
            "inner_mouth",
            "camera",
            "eyebrow_image_left_px",
            "eyebrow_image_right_px",
            "object_ratio",
            "texture_enabled",
            "overlay_path",
            "eyebrow_image_side_overlay_path",
        ])
        for item in rows_out:
            side_split = item.get("eyebrow_image_side_split") or {}
            writer.writerow([
                item["index"],
                item["source_name"],
                item["overall_score_100"],
                item["overall_quality"],
                item["features"]["eyebrow"]["score_100"],
                item["features"]["eye"]["score_100"],
                item["features"]["lip"]["score_100"],
                item["features"]["inner_mouth"]["score_100"],
                item["camera"]["score_100"],
                side_split.get("image_left_pixels", 0),
                side_split.get("image_right_pixels", 0),
                manifest.get("mean_object_ratio", 0.0),
                item["texture_enabled"],
                item["overlay_path"],
                item["mask_paths"].get("eyebrow_image_side_overlay"),
            ])
    person_summary = {
        "person": person,
        "ok": True,
        "input_manifest": _safe_path(manifest_path),
        "rows_total": len(rows_out),
        "texture_only": not args.include_scans,
        "review_sheet": _safe_path(review_sheet),
        "eyebrow_image_side_review_sheet": _safe_path(eyebrow_side_review_sheet),
        "score_csv": _safe_path(csv_path),
        "rows": rows_out,
        "eyebrow_side_definition": "image_left/right are crop-image directions. FaRL left/right labels are merged into eyebrow first, then connected components are assigned by centroid relative to face centerline.",
        "top_by_overall": sorted(
            [
                {
                    "index": item["index"],
                    "source_name": item["source_name"],
                    "overall_score_100": item["overall_score_100"],
                    "quality": item["overall_quality"],
                }
                for item in rows_out
            ],
            key=lambda item: item["overall_score_100"],
            reverse=True,
        )[:8],
    }
    _write_json(person_output / "v07a_feature_source_summary.json", person_summary)
    return person_summary


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    people = args.person or list(PERSONS)
    roots = _resolve_roots(args)
    created_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (args.drive_root / "output" / "facebuilder_mask_aware_step7" / created_at / "v07a_feature_source_review")
    summaries = []
    for person in people:
        summaries.append(_score_person(person=person, args=args, roots=roots, person_output=output_dir / person))
    summary = {
        "schema_version": "facebuilder_mask_aware_step7_feature_sources_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": _safe_path(REPO_ROOT),
        "drive_root": _safe_path(args.drive_root),
        "output_dir": _safe_path(output_dir),
        "source_version": args.source_version,
        "step3_version": args.step3_version,
        "include_scans": bool(args.include_scans),
        "roots": {key: _safe_path(value) for key, value in roots.items()},
        "people": summaries,
    }
    _write_json(output_dir / "v07a_feature_source_summary.json", summary)
    print(json.dumps({
        "ok": True,
        "output_dir": _safe_path(output_dir),
        "people": [
            {
                "person": item["person"],
                "rows_total": item["rows_total"],
                "review_sheet": item["review_sheet"],
                "score_csv": item["score_csv"],
                "top_by_overall": item["top_by_overall"][:3],
            }
            for item in summaries
        ],
    }, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
