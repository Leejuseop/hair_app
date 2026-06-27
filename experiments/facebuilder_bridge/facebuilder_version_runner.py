"""Run FaceBuilder v1/v2/v3/v4 comparison batches from normal Python.

This host-side runner prepares private Drive output folders, scores/copies
photos, creates per-version input manifests, launches Blender in background
mode, and builds human-readable review sheets from private render outputs.

It does not commit or require committing any private photo, mesh, texture,
render, blend, or GLB file.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps


SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

DEFAULT_BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")
DEFAULT_DRIVE_ROOT = Path(os.environ.get("HAIR_APP_DRIVE_ROOT", "G:/\ub0b4 \ub4dc\ub77c\uc774\ube0c/hair_app"))
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JUSEOP_DIR = Path(os.environ.get("HAIR_APP_JUSEOP_DIR", str(Path.home() / "Desktop" / "\ub0b4\uc0ac\uc9c4")))
DEFAULT_EUNCHAE_DIR = Path(os.environ.get("HAIR_APP_EUNCHAE_DIR", str(Path.home() / "Desktop" / "\uc740\ucc44\uc0ac\uc9c4")))

VERSION_ORDER = ("v1", "v2", "v3", "v4")
VERSION_DESCRIPTIONS = {
    "v1": "original photos + raw FaceBuilder texture",
    "v2": "preprocessed texture photos + raw FaceBuilder texture",
    "v3": "original photos + postprocessed FaceBuilder texture",
    "v4": "preprocessed texture photos + postprocessed FaceBuilder texture",
}
VERSION_CONFIG = {
    "v1": {"preprocess_texture_inputs": False, "use_cleanup_texture": False},
    "v2": {"preprocess_texture_inputs": True, "use_cleanup_texture": False},
    "v3": {"preprocess_texture_inputs": False, "use_cleanup_texture": True},
    "v4": {"preprocess_texture_inputs": True, "use_cleanup_texture": True},
}

REVIEW_YAW_ORDER = [0, 15, 30, 45, -15, -30, -45]


@dataclass(frozen=True)
class PersonConfig:
    key: str
    label: str
    input_dir: Path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive-root", type=Path, default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--blender-exe", type=Path, default=DEFAULT_BLENDER_EXE)
    parser.add_argument("--juseop-dir", type=Path, default=DEFAULT_JUSEOP_DIR)
    parser.add_argument("--eunchae-dir", type=Path, default=DEFAULT_EUNCHAE_DIR)
    parser.add_argument("--version", action="append", choices=VERSION_ORDER)
    parser.add_argument("--person", action="append", choices=("juseop", "eunchae"))
    parser.add_argument("--max-images", type=int, default=None)
    parser.add_argument("--min-selected", type=int, default=5)
    parser.add_argument("--quality-threshold", type=float, default=0.48)
    parser.add_argument("--clean", action="store_true", help="Remove each version/person output folder before rerunning it.")
    parser.add_argument("--skip-blender", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--no-review-sheet", action="store_true")
    return parser.parse_args(argv)


def _safe_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _list_images(input_dir: Path, max_images: int | None = None) -> list[Path]:
    images = [
        path
        for path in sorted(input_dir.iterdir(), key=lambda p: p.name.lower())
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    ]
    if max_images is not None:
        return images[:max_images]
    return images


def _clip01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _blur_score(gray: np.ndarray) -> tuple[float, float]:
    if gray.size == 0:
        return 0.0, 0.0
    arr = gray.astype(np.float32)
    center = arr[1:-1, 1:-1] * -4.0
    lap = (
        center
        + arr[:-2, 1:-1]
        + arr[2:, 1:-1]
        + arr[1:-1, :-2]
        + arr[1:-1, 2:]
    )
    variance = float(np.var(lap)) if lap.size else 0.0
    # Ordinary selfies vary wildly. This log score avoids one sharp image
    # dwarfing the rest of the set.
    score = _clip01(math.log1p(variance) / math.log1p(1600.0))
    return variance, score


def _face_detection_metrics(image: Image.Image) -> dict[str, Any]:
    width, height = image.size
    try:
        import cv2  # type: ignore
    except Exception as exc:  # noqa: BLE001 - optional local dependency.
        return {
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
            "face_count": 0,
            "best_bbox": None,
            "face_area_ratio": 0.0,
            "face_width_ratio": 0.0,
            "center_score": 0.0,
            "size_score": 0.0,
            "score": 0.28,
            "detector": "unavailable",
        }

    max_dim = 1024
    scale = min(1.0, max_dim / max(width, height))
    if scale < 1.0:
        detect_image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS)
    else:
        detect_image = image
    arr = np.asarray(detect_image.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    cascade_dir = Path(cv2.data.haarcascades)
    detectors: list[tuple[str, Any]] = []
    for name, filename in (
        ("frontal", "haarcascade_frontalface_default.xml"),
        ("frontal_alt", "haarcascade_frontalface_alt2.xml"),
        ("profile", "haarcascade_profileface.xml"),
    ):
        cascade_path = cascade_dir / filename
        if cascade_path.exists():
            detector = cv2.CascadeClassifier(str(cascade_path))
            if not detector.empty():
                detectors.append((name, detector))

    candidates: list[dict[str, Any]] = []
    min_side = max(24, int(min(gray.shape[:2]) * 0.055))
    for name, detector in detectors:
        for flipped in (False, True) if name == "profile" else (False,):
            scan = cv2.flip(gray, 1) if flipped else gray
            faces = detector.detectMultiScale(
                scan,
                scaleFactor=1.08,
                minNeighbors=4,
                minSize=(min_side, min_side),
                flags=cv2.CASCADE_SCALE_IMAGE,
            )
            for x, y, w, h in faces:
                if flipped:
                    x = scan.shape[1] - x - w
                candidates.append({
                    "detector": f"{name}_flipped" if flipped else name,
                    "bbox_detect": [int(x), int(y), int(w), int(h)],
                    "area": int(w * h),
                })

    if not candidates:
        return {
            "available": True,
            "face_count": 0,
            "best_bbox": None,
            "face_area_ratio": 0.0,
            "face_width_ratio": 0.0,
            "center_score": 0.0,
            "size_score": 0.0,
            "score": 0.0,
            "detector": "none",
        }

    best = max(candidates, key=lambda item: item["area"])
    x, y, w, h = best["bbox_detect"]
    inv_scale = 1.0 / scale
    bbox = [
        int(round(x * inv_scale)),
        int(round(y * inv_scale)),
        int(round(w * inv_scale)),
        int(round(h * inv_scale)),
    ]
    area_ratio = (bbox[2] * bbox[3]) / max(1.0, float(width * height))
    width_ratio = bbox[2] / max(1.0, float(width))
    face_center_x = bbox[0] + bbox[2] * 0.5
    face_center_y = bbox[1] + bbox[3] * 0.5
    distance = math.sqrt(
        ((face_center_x - width * 0.5) / max(1.0, width * 0.5)) ** 2
        + ((face_center_y - height * 0.48) / max(1.0, height * 0.5)) ** 2
    )
    center_score = _clip01(1.0 - distance / 0.88)
    size_score = _clip01((width_ratio - 0.13) / 0.27)
    face_score = _clip01(0.68 * size_score + 0.24 * center_score + 0.08)
    return {
        "available": True,
        "face_count": len(candidates),
        "best_bbox": bbox,
        "face_area_ratio": float(area_ratio),
        "face_width_ratio": float(width_ratio),
        "center_score": float(center_score),
        "size_score": float(size_score),
        "score": float(face_score),
        "detector": best["detector"],
    }


def _color_cast_metrics(image: Image.Image, face_bbox: list[int] | None) -> dict[str, Any]:
    width, height = image.size
    if face_bbox:
        x, y, w, h = face_bbox
        pad_x = int(round(w * 0.15))
        pad_y = int(round(h * 0.12))
        box = (
            max(0, x - pad_x),
            max(0, y - pad_y),
            min(width, x + w + pad_x),
            min(height, y + h + pad_y),
        )
        region = image.crop(box)
    else:
        region = image
    region.thumbnail((384, 384), Image.Resampling.LANCZOS)
    arr = np.asarray(region.convert("RGB")).astype(np.float32) / 255.0
    if arr.size == 0:
        return {"score": 0.0, "median_rgb": [0.0, 0.0, 0.0], "channel_spread": 1.0}

    luma = arr[:, :, 0] * 0.2126 + arr[:, :, 1] * 0.7152 + arr[:, :, 2] * 0.0722
    valid = (luma > 0.10) & (luma < 0.92)
    if np.count_nonzero(valid) < 64:
        valid = np.ones(luma.shape, dtype=bool)
    median_rgb = np.median(arr[valid], axis=0)
    mean_level = float(np.mean(median_rgb))
    spread = float((np.max(median_rgb) - np.min(median_rgb)) / max(mean_level, 1e-5))
    balance_score = _clip01(1.0 - max(0.0, spread - 0.32) / 0.62)

    red, green, blue = [float(x) for x in median_rgb]
    blue_over_red = blue / max(red, 1e-5)
    green_over_red = green / max(red, 1e-5)
    blue_penalty = max(0.0, blue_over_red - 0.96) / 0.52
    green_penalty = max(0.0, 0.50 - green_over_red) / 0.32
    skin_order_score = _clip01(1.0 - blue_penalty - green_penalty)
    score = _clip01(0.48 * balance_score + 0.52 * skin_order_score)
    return {
        "score": float(score),
        "median_rgb": [red, green, blue],
        "channel_spread": spread,
        "blue_over_red": blue_over_red,
        "green_over_red": green_over_red,
    }


def _score_image(path: Path) -> dict[str, Any]:
    try:
        with Image.open(path) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
            width, height = image.size
            thumb = image.resize((min(512, width), min(512, height)))
            arr = np.asarray(thumb).astype(np.float32)
    except Exception as exc:  # noqa: BLE001 - scoring should not stop the batch.
        return {
            "path": _safe_path(path),
            "ok": False,
            "error": str(exc),
            "score": 0.0,
            "decision_notes": ["image_load_failed"],
        }

    gray = np.mean(arr, axis=2)
    blur_variance, blur_component = _blur_score(gray)
    luma = gray / 255.0
    mean_luma = float(np.mean(luma))
    contrast = float(np.std(luma))
    dark_clip = float(np.mean(luma < 0.04))
    bright_clip = float(np.mean(luma > 0.96))
    clipping = dark_clip + bright_clip
    exposure_component = _clip01(1.0 - abs(mean_luma - 0.52) / 0.38)
    contrast_component = _clip01(contrast / 0.24)
    clipping_component = _clip01(1.0 - clipping * 3.0)
    megapixels = (width * height) / 1_000_000.0
    resolution_component = _clip01(math.log1p(megapixels) / math.log1p(3.0))
    face_metrics = _face_detection_metrics(image)
    face_component = float(face_metrics.get("score", 0.0))
    color_metrics = _color_cast_metrics(image, face_metrics.get("best_bbox"))
    color_component = float(color_metrics.get("score", 0.0))

    # This is intentionally conservative. It scores image quality, not face
    # geometry. FaceBuilder alignment remains the authoritative face gate, but
    # obvious small-face/full-body photos should not dominate v2/v3 texture
    # baking just because they are sharp.
    score = (
        0.20 * blur_component
        + 0.13 * exposure_component
        + 0.10 * contrast_component
        + 0.07 * resolution_component
        + 0.04 * clipping_component
        + 0.32 * face_component
        + 0.14 * color_component
    )

    notes: list[str] = []
    if blur_component < 0.38:
        notes.append("possible_blur")
    if exposure_component < 0.42:
        notes.append("weak_exposure")
    if contrast_component < 0.34:
        notes.append("low_contrast")
    if clipping > 0.08:
        notes.append("heavy_clipping")
    if resolution_component < 0.45:
        notes.append("low_resolution")
    if face_metrics.get("available") is False:
        notes.append("face_detector_unavailable")
    elif not face_metrics.get("best_bbox"):
        notes.append("no_face_detected")
    elif face_metrics.get("face_width_ratio", 0.0) < 0.18:
        notes.append("small_face")
    if face_metrics.get("center_score", 1.0) < 0.45:
        notes.append("off_center_face")
    if color_component < 0.34:
        notes.append("severe_color_cast")
    elif color_component < 0.52:
        notes.append("color_cast")

    hard_reject = bool(
        (face_metrics.get("available") is True and not face_metrics.get("best_bbox"))
        or face_metrics.get("face_width_ratio", 1.0) < 0.12
        or color_component < 0.30
    )

    return {
        "path": _safe_path(path),
        "ok": True,
        "width": width,
        "height": height,
        "megapixels": megapixels,
        "blur_variance": blur_variance,
        "mean_luma": mean_luma,
        "contrast": contrast,
        "dark_clip": dark_clip,
        "bright_clip": bright_clip,
        "components": {
            "blur": blur_component,
            "exposure": exposure_component,
            "contrast": contrast_component,
            "resolution": resolution_component,
            "clipping": clipping_component,
            "face": face_component,
            "color": color_component,
        },
        "face": face_metrics,
        "color": color_metrics,
        "score": float(score),
        "hard_reject": hard_reject,
        "decision_notes": notes,
    }


def _copy_image_normalized(src: Path, dst: Path) -> dict[str, Any]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        image.save(dst, quality=96)
        return {"path": _safe_path(dst), "width": image.width, "height": image.height}


def _save_variant(src: Path, dst: Path, variant: str) -> dict[str, Any]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        if variant == "autocontrast":
            out = ImageOps.autocontrast(image, cutoff=1)
        elif variant == "bright_contrast":
            out = ImageEnhance.Brightness(image).enhance(1.08)
            out = ImageEnhance.Contrast(out).enhance(1.12)
            out = ImageOps.autocontrast(out, cutoff=0.5)
        elif variant == "sharp":
            out = image.filter(ImageFilter.UnsharpMask(radius=1.6, percent=140, threshold=3))
            out = ImageOps.autocontrast(out, cutoff=0.5)
        else:
            out = image
        out.save(dst, quality=96)
        return {"path": _safe_path(dst), "width": out.width, "height": out.height}


def _save_texture_preprocess_variant(
    src: Path,
    dst: Path,
    score: dict[str, Any],
) -> dict[str, Any]:
    """Create a same-size texture-bake input with obvious non-face pixels muted.

    This is intentionally conservative. Alignment still uses the original photo;
    this image is only swapped in for FaceBuilder texture baking. The output
    keeps the exact same width and height as the normalized original so the
    solved camera projection remains valid.
    """

    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")

    arr = np.asarray(image).astype(np.float32) / 255.0
    height, width = arr.shape[:2]
    yy, xx = np.mgrid[0:height, 0:width]
    luma = arr[:, :, 0] * 0.2126 + arr[:, :, 1] * 0.7152 + arr[:, :, 2] * 0.0722
    maxc = np.max(arr, axis=2)
    minc = np.min(arr, axis=2)
    saturation = (maxc - minc) / np.maximum(maxc, 1e-5)

    bbox = score.get("face", {}).get("best_bbox")
    if bbox:
        x, y, w, h = [float(v) for v in bbox]
        cx = x + w * 0.5
        # Keep face, ears, hairline, and neck plausible. Everything far outside
        # this soft oval is likely background/clothes for texture baking.
        cy = y + h * 0.57
        rx = max(1.0, w * 0.95)
        ry = max(1.0, h * 1.20)
        head_neck_oval = (((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2) <= 1.0
        face_core = (
            (xx >= x + w * 0.14)
            & (xx <= x + w * 0.86)
            & (yy >= y + h * 0.28)
            & (yy <= y + h * 0.84)
        )
        upper_head = yy < y + h * 0.36
        low_neck_or_clothes = yy > y + h * 0.88
    else:
        head_neck_oval = np.ones((height, width), dtype=bool)
        face_core = np.zeros((height, width), dtype=bool)
        upper_head = yy < height * 0.34
        low_neck_or_clothes = yy > height * 0.78

    skin_sample_mask = (
        head_neck_oval
        & ~upper_head
        & ~low_neck_or_clothes
        & (luma > 0.22)
        & (luma < 0.88)
        & (arr[:, :, 0] > arr[:, :, 2] * 1.03)
        & (arr[:, :, 1] > arr[:, :, 2] * 0.78)
        & (saturation < 0.55)
    )
    if np.count_nonzero(skin_sample_mask) >= 64:
        skin = np.median(arr[skin_sample_mask], axis=0)
    else:
        skin = np.array([0.62, 0.46, 0.38], dtype=np.float32)

    outside_subject = ~head_neck_oval
    dark_hair = head_neck_oval & upper_head & (luma < 0.30) & (saturation < 0.82)
    colored_leak = (
        (outside_subject | low_neck_or_clothes)
        & (saturation > 0.30)
        & (luma < 0.86)
        & ~face_core
    )
    very_dark_leak = (outside_subject | low_neck_or_clothes) & (luma < 0.20) & ~face_core
    replace_mask = outside_subject | dark_hair | colored_leak | very_dark_leak

    # Preserve a little local brightness so replacements are not one flat block.
    tone = np.clip(luma[:, :, None] * 0.30 + 0.84, 0.72, 1.08)
    replacement = np.clip(skin.reshape((1, 1, 3)) * tone, 0.0, 1.0)

    cleaned = arr.copy()
    cleaned[replace_mask] = replacement[replace_mask]

    # Feather only the replacement edge. Pillow keeps this dependency light and
    # avoids changing the image dimensions.
    mask_image = Image.fromarray((replace_mask.astype(np.uint8) * 255), mode="L").filter(ImageFilter.GaussianBlur(radius=2.0))
    replacement_image = Image.fromarray(np.clip(replacement * 255.0, 0, 255).astype(np.uint8), mode="RGB")
    cleaned_image = Image.fromarray(np.clip(cleaned * 255.0, 0, 255).astype(np.uint8), mode="RGB")
    original_image = Image.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8), mode="RGB")
    blended = Image.composite(cleaned_image, original_image, mask_image)
    blended.save(dst, quality=96)

    return {
        "path": _safe_path(dst),
        "width": width,
        "height": height,
        "skin_reference_rgb": [float(x) for x in skin],
        "replaced_pixels": int(np.count_nonzero(replace_mask)),
        "replaced_ratio": float(np.mean(replace_mask)),
        "face_bbox": bbox,
        "policy": "same_size_conservative_nonface_mute_v1",
    }


def _save_face_crop_variant(
    src: Path,
    dst: Path,
    bbox: list[int] | None,
    *,
    width_scale: float,
    top_scale: float,
    bottom_scale: float,
) -> dict[str, Any] | None:
    if not bbox:
        return None
    with Image.open(src) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        width, height = image.size
        x, y, w, h = bbox
        if w <= 0 or h <= 0:
            return None
        center_x = x + w * 0.5
        center_y = y + h * 0.50
        crop_w = w * width_scale
        left = max(0, int(round(center_x - crop_w * 0.5)))
        right = min(width, int(round(center_x + crop_w * 0.5)))
        top = max(0, int(round(center_y - h * top_scale)))
        bottom = min(height, int(round(center_y + h * bottom_scale)))
        if right - left < max(96, w) or bottom - top < max(96, h):
            return None
        cropped = image.crop((left, top, right, bottom))
        dst.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(dst, quality=96)
        return {
            "path": _safe_path(dst),
            "width": cropped.width,
            "height": cropped.height,
            "crop_box": [left, top, right, bottom],
            "source_face_bbox": bbox,
        }


def _select_for_version(
    version: str,
    scored: list[dict[str, Any]],
    threshold: float,
    min_selected: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    del version, threshold, min_selected
    # Current v1-v4 experiment intentionally removes quality-based selection.
    # Every readable photo is attempted in every version so the only variables
    # are texture-input preprocessing and texture-output postprocessing.
    selected = [item for item in scored if item.get("ok")]
    selected_paths = {item["path"] for item in selected}
    rejected = [
        {
            **item,
            "reject_reason": "unreadable_image",
        }
        for item in scored
        if item.get("path") not in selected_paths
    ]
    return selected, rejected


def _prepare_version_manifest(
    version: str,
    person: PersonConfig,
    output_dir: Path,
    max_images: int | None,
    threshold: float,
    min_selected: int,
) -> Path:
    folders = _make_output_folders(output_dir)
    source_images = _list_images(person.input_dir, max_images=max_images)
    scored = [_score_image(path) for path in source_images]
    selected, rejected = _select_for_version(version, scored, threshold, min_selected)
    version_config = VERSION_CONFIG[version]

    source_by_safe_path = {_safe_path(path): path for path in source_images}
    manifest_items: list[dict[str, Any]] = []
    texture_preprocess_rows: list[dict[str, Any]] = []
    for index, item in enumerate(selected):
        source_path = source_by_safe_path[item["path"]]
        stem = f"{index:03d}_{source_path.stem}"
        original_dst = folders["working_images"] / "originals" / f"{stem}.jpg"
        original_info = _copy_image_normalized(source_path, original_dst)
        texture_info = None
        if version_config["preprocess_texture_inputs"]:
            texture_dst = folders["working_images"] / "texture_preprocessed" / f"{stem}_texture_preprocessed.jpg"
            texture_info = _save_texture_preprocess_variant(source_path, texture_dst, item)
            texture_preprocess_rows.append({
                "image_id": f"{person.key}_{index:03d}",
                "source_path": item["path"],
                "preprocessed_path": texture_info["path"],
                "policy": texture_info["policy"],
                "replaced_ratio": texture_info["replaced_ratio"],
                "replaced_pixels": texture_info["replaced_pixels"],
            })
        candidates = [
            {
                "kind": "original",
                "path": original_info["path"],
                "preferred": True,
                "allow_texture_bake": True,
                "texture_path": texture_info["path"] if texture_info else None,
                "texture_kind": "preprocessed" if texture_info else "original",
            }
        ]

        manifest_items.append({
            "index": index,
            "image_id": f"{person.key}_{index:03d}",
            "source_path": item["path"],
            "working_path": original_info["path"],
            "score": item,
            "candidates": candidates,
        })

    quality_report = {
        "version": version,
        "person": person.key,
        "person_label": person.label,
        "input_dir": _safe_path(person.input_dir),
        "all_images_count": len(source_images),
        "selected_count": len(selected),
        "rejected_count": len(rejected),
        "quality_threshold": threshold,
        "min_selected": min_selected,
        "all_scores": scored,
        "selected": selected,
        "rejected": rejected,
        "selection_policy": "all_readable_images_no_quality_rejection",
        "texture_preprocess_count": len(texture_preprocess_rows),
        "texture_preprocess": texture_preprocess_rows,
    }
    _write_json(folders["input_manifest"] / "photo_quality_report.json", quality_report)

    manifest = {
        "schema_version": "facebuilder_batch_manifest_v1",
        "created_at_unix": time.time(),
        "version": version,
        "version_description": VERSION_DESCRIPTIONS[version],
        "version_config": version_config,
        "person": person.key,
        "person_label": person.label,
        "input_dir": _safe_path(person.input_dir),
        "output_dir": _safe_path(output_dir),
        "folders": {name: _safe_path(path) for name, path in folders.items()},
        "selection_policy": {
            "v1": "original photos + raw FaceBuilder texture",
            "v2": "original photos for align, same-size preprocessed photos for texture bake, raw texture material",
            "v3": "original photos + FaceBuilder raw bake + postprocessed cleanup material",
            "v4": "original photos for align, preprocessed photos for texture bake, postprocessed cleanup material",
            "active": version,
            "quality_rejection_active": False,
        },
        "items": manifest_items,
        "rejected": rejected,
    }
    manifest_path = folders["input_manifest"] / "facebuilder_input_manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path


def _make_output_folders(output_dir: Path) -> dict[str, Path]:
    folders = {
        "input_manifest": output_dir / "00_input_manifest",
        "working_images": output_dir / "01_working_images",
        "alignment": output_dir / "02_alignment",
        "scene": output_dir / "03_facebuilder_scene",
        "exports": output_dir / "04_exports",
        "postprocess": output_dir / "05_postprocess",
        "glb": output_dir / "06_glb",
        "review": output_dir / "07_review_sheets",
        "logs": output_dir / "logs",
    }
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)
    return folders


def _run_blender(
    blender_exe: Path,
    repo_root: Path,
    manifest_path: Path,
    output_dir: Path,
    *,
    use_cleanup_texture: bool,
) -> dict[str, Any]:
    script = repo_root / "experiments" / "facebuilder_bridge" / "blender_facebuilder_batch_scene.py"
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "blender_stdout.txt"
    stderr_path = log_dir / "blender_stderr.txt"
    command = [
        str(blender_exe),
        "--background",
        "--python",
        str(script),
        "--",
        "--input-manifest",
        str(manifest_path),
        "--output-dir",
        str(output_dir),
        "--bake-texture",
        "--save-blend",
        "--export-obj",
        "--export-glb",
        "--render-review",
    ]
    if use_cleanup_texture:
        command.append("--use-cleanup-texture")
    started = time.time()
    completed = subprocess.run(command, capture_output=True, text=False, check=False)
    stdout_path.write_bytes(completed.stdout or b"")
    stderr_path.write_bytes(completed.stderr or b"")
    return {
        "command": command,
        "returncode": completed.returncode,
        "duration_sec": time.time() - started,
        "stdout_path": _safe_path(stdout_path),
        "stderr_path": _safe_path(stderr_path),
        "ok": completed.returncode == 0,
    }


def _load_image_thumbnail(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (28, 28, 28))
    x = (size[0] - image.width) // 2
    y = (size[1] - image.height) // 2
    canvas.paste(image, (x, y))
    return canvas


def _draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fill: tuple[int, int, int]) -> None:
    # Keep text short and ASCII so default PIL fonts are enough.
    draw.text(xy, text, fill=fill)


def _create_review_sheet(output_dir: Path) -> Path | None:
    manifest_path = output_dir / "00_input_manifest" / "facebuilder_input_manifest.json"
    blender_result_path = output_dir / "run_manifest.json"
    if not manifest_path.exists():
        return None
    manifest = _read_json(manifest_path)
    blender_result = _read_json(blender_result_path) if blender_result_path.exists() else {}
    review_dir = output_dir / "07_review_sheets"
    review_dir.mkdir(parents=True, exist_ok=True)

    yaw_order = {yaw: index for index, yaw in enumerate(REVIEW_YAW_ORDER)}

    def yaw_sort_key(path: Path) -> tuple[int, str]:
        try:
            yaw = int(path.stem.replace("render_yaw_", ""))
        except ValueError:
            return (999, path.name)
        return (yaw_order.get(yaw, 900 + yaw), path.name)

    yaw_images = sorted(review_dir.glob("render_yaw_*.png"), key=yaw_sort_key)
    source_items = manifest.get("items", [])[:12]
    thumb_w, thumb_h = 116, 116
    yaw_w, yaw_h = 210, 260
    width = max(1100, 40 + len(yaw_images) * (yaw_w + 12))
    source_rows = math.ceil(max(1, len(source_items)) / 6)
    height = 230 + source_rows * (thumb_h + 44) + (yaw_h + 80)
    sheet = Image.new("RGB", (width, height), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)

    title = f"{manifest.get('version')} / {manifest.get('person')} FaceBuilder Review"
    _draw_text(draw, (24, 18), title, (245, 245, 245))
    _draw_text(draw, (24, 42), manifest.get("version_description", ""), (190, 190, 190))

    summary = blender_result.get("summary", {})
    _draw_text(
        draw,
        (24, 68),
        (
            f"images selected={len(manifest.get('items', []))} "
            f"aligned={summary.get('aligned_count', '?')} "
            f"failed={summary.get('failed_count', '?')} "
            f"texcams={summary.get('texture_enabled_count', '?')} "
            f"texture={summary.get('texture_ok', '?')} "
            f"cleanup={summary.get('texture_cleanup_ok', '?')} "
            f"glb={summary.get('glb_ok', '?')}"
        ),
        (210, 210, 210),
    )

    y = 105
    _draw_text(draw, (24, y), "Selected source photos", (230, 230, 230))
    y += 24
    for i, item in enumerate(source_items):
        row = i // 6
        col = i % 6
        x = 24 + col * (thumb_w + 22)
        yy = y + row * (thumb_h + 44)
        source_path = Path(item["working_path"])
        try:
            thumb = _load_image_thumbnail(source_path, (thumb_w, thumb_h))
            sheet.paste(thumb, (x, yy))
        except Exception:
            draw.rectangle([x, yy, x + thumb_w, yy + thumb_h], fill=(60, 20, 20))
        score = item.get("score", {}).get("score", 0.0)
        _draw_text(draw, (x, yy + thumb_h + 5), f"{i:02d} score={score:.2f}", (180, 180, 180))

    y = y + source_rows * (thumb_h + 44) + 24
    _draw_text(draw, (24, y), "Rendered review angles", (230, 230, 230))
    y += 24
    if yaw_images:
        for i, path in enumerate(yaw_images):
            x = 24 + i * (yaw_w + 12)
            try:
                thumb = _load_image_thumbnail(path, (yaw_w, yaw_h))
                sheet.paste(thumb, (x, y))
            except Exception:
                draw.rectangle([x, y, x + yaw_w, y + yaw_h], fill=(50, 50, 50))
            _draw_text(draw, (x, y + yaw_h + 6), path.stem.replace("render_", ""), (180, 180, 180))
    else:
        _draw_text(draw, (24, y), "No review renders were produced.", (240, 120, 120))

    review_path = review_dir / "review_sheet.png"
    sheet.save(review_path)
    return review_path


def _create_version_comparison_sheet(
    drive_root: Path,
    versions: list[str],
    person: PersonConfig,
) -> Path | None:
    output_root = drive_root / "output"
    comparison_dir = output_root / "_comparison" / "facebuilder_v1_v4"
    comparison_dir.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[str, Path]] = []
    for version in versions:
        output_dir = output_root / f"facebuilder_{version}" / person.key
        if (output_dir / "run_manifest.json").exists():
            rows.append((version, output_dir))
    if not rows:
        return None

    columns = [
        ("raw texture", lambda d: d / "05_postprocess" / "facebuilder_texture_bake.png"),
        ("cleanup texture", lambda d: d / "05_postprocess" / "facebuilder_texture_bald_cleanup.png"),
        ("yaw 0", lambda d: d / "07_review_sheets" / "render_yaw_+00.png"),
        ("yaw +45", lambda d: d / "07_review_sheets" / "render_yaw_+45.png"),
        ("yaw -45", lambda d: d / "07_review_sheets" / "render_yaw_-45.png"),
    ]
    thumb_w, thumb_h = 210, 210
    label_w = 190
    header_h = 76
    row_h = thumb_h + 70
    width = label_w + len(columns) * (thumb_w + 18) + 28
    height = header_h + len(rows) * row_h + 24
    sheet = Image.new("RGB", (width, height), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    _draw_text(draw, (22, 18), f"{person.key} FaceBuilder v1-v4 comparison", (245, 245, 245))
    _draw_text(draw, (22, 42), "Private review sheet. Do not commit generated assets.", (185, 185, 185))

    for col_index, (label, _) in enumerate(columns):
        x = label_w + col_index * (thumb_w + 18)
        _draw_text(draw, (x, header_h - 24), label, (225, 225, 225))

    for row_index, (version, output_dir) in enumerate(rows):
        y = header_h + row_index * row_h
        manifest_path = output_dir / "00_input_manifest" / "facebuilder_input_manifest.json"
        manifest = _read_json(manifest_path) if manifest_path.exists() else {}
        _draw_text(draw, (22, y + 18), version, (245, 245, 245))
        _draw_text(draw, (22, y + 42), VERSION_DESCRIPTIONS.get(version, ""), (180, 180, 180))
        summary = _read_json(output_dir / "run_manifest.json").get("summary", {})
        _draw_text(
            draw,
            (22, y + 66),
            f"aligned {summary.get('aligned_count', '?')} / texcams {summary.get('texture_enabled_count', '?')}",
            (170, 170, 170),
        )
        if manifest.get("version_config", {}).get("preprocess_texture_inputs"):
            _draw_text(draw, (22, y + 90), "pre-input: on", (150, 210, 170))
        if manifest.get("version_config", {}).get("use_cleanup_texture"):
            _draw_text(draw, (22, y + 112), "post-cleanup: material", (150, 210, 170))

        for col_index, (_, resolver) in enumerate(columns):
            path = resolver(output_dir)
            x = label_w + col_index * (thumb_w + 18)
            try:
                thumb = _load_image_thumbnail(path, (thumb_w, thumb_h))
                sheet.paste(thumb, (x, y + 28))
            except Exception:
                draw.rectangle([x, y + 28, x + thumb_w, y + 28 + thumb_h], fill=(54, 38, 38))
                _draw_text(draw, (x + 10, y + 42), "missing", (230, 130, 130))

    sheet_path = comparison_dir / f"{person.key}_facebuilder_v1_v4_comparison.png"
    sheet.save(sheet_path)
    return sheet_path


def _collect_run_summary(output_dir: Path) -> dict[str, Any] | None:
    run_path = output_dir / "run_manifest.json"
    quality_path = output_dir / "00_input_manifest" / "photo_quality_report.json"
    host_path = output_dir / "host_run_summary.json"
    if not run_path.exists() or not quality_path.exists():
        return None
    run = _read_json(run_path)
    quality = _read_json(quality_path)
    host = _read_json(host_path) if host_path.exists() else {}
    alignment = run.get("alignment", [])
    selected_kinds: dict[str, int] = {}
    for item in alignment:
        candidate = item.get("selected_candidate") or {}
        kind = candidate.get("kind") or "none"
        selected_kinds[kind] = selected_kinds.get(kind, 0) + 1
    return {
        "version": run.get("version"),
        "person": run.get("person"),
        "output_dir": _safe_path(output_dir),
        "selected_count": quality.get("selected_count"),
        "rejected_count": quality.get("rejected_count"),
        "quality_threshold": quality.get("quality_threshold"),
        "selection_policy": quality.get("selection_policy"),
        "texture_preprocess_count": quality.get("texture_preprocess_count"),
        "version_config": run.get("version_config"),
        "aligned_count": run.get("summary", {}).get("aligned_count"),
        "failed_count": run.get("summary", {}).get("failed_count"),
        "texture_enabled_count": run.get("summary", {}).get("texture_enabled_count"),
        "texture_ok": run.get("summary", {}).get("texture_ok"),
        "texture_cleanup_ok": run.get("summary", {}).get("texture_cleanup_ok"),
        "obj_ok": run.get("summary", {}).get("obj_ok"),
        "glb_ok": run.get("summary", {}).get("glb_ok"),
        "review_ok": run.get("summary", {}).get("review_ok"),
        "selected_candidate_kinds": selected_kinds,
        "review_sheet": host.get("review_sheet"),
        "glb_path": (
            run.get("exports", {})
            .get("glb", {})
            .get("value", {})
            .get("path")
        ),
        "texture_path": (
            run.get("texture_bake", {})
            .get("value", {})
            .get("saved_texture")
        ),
        "cleanup_texture_path": (
            run.get("texture_cleanup", {})
            .get("value", {})
            .get("cleanup_texture")
        ),
        "material_texture_path": (
            run.get("postprocess", {})
            .get("value", {})
            .get("texture_path")
        ),
    }


def _write_summary_report(drive_root: Path, versions: list[str], people: list[PersonConfig]) -> None:
    output_root = drive_root / "output"
    rows: list[dict[str, Any]] = []
    for version in versions:
        for person in people:
            output_dir = output_root / f"facebuilder_{version}" / person.key
            summary = _collect_run_summary(output_dir)
            if summary:
                rows.append(summary)

    summary_json = {
        "schema_version": "facebuilder_versions_summary_v1",
        "created_at_unix": time.time(),
        "rows": rows,
        "interpretation": {
            key: VERSION_DESCRIPTIONS[key]
            for key in VERSION_ORDER
        },
    }
    _write_json(output_root / "facebuilder_versions_summary.json", summary_json)

    lines = [
        "# FaceBuilder Version Summary",
        "",
        "Private generated output summary. Do not commit generated assets.",
        "",
        "| Version | Person | Selected | Rejected | Preproc | Aligned | Failed | TexCams | Texture | Cleanup | OBJ | GLB | Review | Candidate kinds |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        kinds = ", ".join(f"{key}:{value}" for key, value in sorted(row["selected_candidate_kinds"].items()))
        lines.append(
            "| {version} | {person} | {selected_count} | {rejected_count} | "
            "{texture_preprocess_count} | {aligned_count} | {failed_count} | {texture_enabled_count} | "
            "{texture_ok} | {texture_cleanup_ok} | "
            "{obj_ok} | {glb_ok} | {review_ok} | {kinds} |".format(
                kinds=kinds or "-",
                **row,
            )
        )
    lines.extend([
        "",
        "Output layout per version/person:",
        "",
        "```text",
        "00_input_manifest/",
        "01_working_images/",
        "02_alignment/",
        "03_facebuilder_scene/",
        "04_exports/",
        "05_postprocess/",
        "06_glb/",
        "07_review_sheets/",
        "logs/",
        "```",
        "",
        "Compare v1/v2/v3/v4 review sheets visually before making quality decisions.",
    ])
    (output_root / "facebuilder_versions_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _person_configs(args: argparse.Namespace) -> list[PersonConfig]:
    configs = {
        "juseop": PersonConfig("juseop", "Juseop", args.juseop_dir),
        "eunchae": PersonConfig("eunchae", "Eunchae", args.eunchae_dir),
    }
    selected = args.person or ["juseop", "eunchae"]
    return [configs[key] for key in selected]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    versions = args.version or list(VERSION_ORDER)
    people = _person_configs(args)
    batch_root = args.drive_root / "output"
    args.drive_root.mkdir(parents=True, exist_ok=True)
    (args.drive_root / "output").mkdir(parents=True, exist_ok=True)

    batch_results: list[dict[str, Any]] = []
    for version in versions:
        for person in people:
            output_dir = batch_root / f"facebuilder_{version}" / person.key
            if args.skip_existing and (output_dir / "run_manifest.json").exists():
                batch_results.append({
                    "version": version,
                    "person": person.key,
                    "output_dir": _safe_path(output_dir),
                    "skipped": True,
                    "reason": "run_manifest_exists",
                })
                continue
            if args.clean and output_dir.exists():
                shutil.rmtree(output_dir)

            manifest_path = _prepare_version_manifest(
                version=version,
                person=person,
                output_dir=output_dir,
                max_images=args.max_images,
                threshold=args.quality_threshold,
                min_selected=args.min_selected,
            )
            result: dict[str, Any] = {
                "version": version,
                "person": person.key,
                "output_dir": _safe_path(output_dir),
                "input_manifest": _safe_path(manifest_path),
                "skip_blender": args.skip_blender,
            }
            if not args.skip_blender:
                result["blender"] = _run_blender(
                    blender_exe=args.blender_exe,
                    repo_root=args.repo_root,
                    manifest_path=manifest_path,
                    output_dir=output_dir,
                    use_cleanup_texture=VERSION_CONFIG[version]["use_cleanup_texture"],
                )
            if not args.no_review_sheet:
                sheet_path = _create_review_sheet(output_dir)
                result["review_sheet"] = _safe_path(sheet_path) if sheet_path else None
            _write_json(output_dir / "host_run_summary.json", result)
            batch_results.append(result)

    comparison_sheets: list[dict[str, Any]] = []
    if not args.no_review_sheet:
        for person in people:
            sheet_path = _create_version_comparison_sheet(args.drive_root, versions, person)
            if sheet_path:
                comparison_sheets.append({
                    "person": person.key,
                    "path": _safe_path(sheet_path),
                })

    batch_manifest = {
        "schema_version": "facebuilder_version_batch_v1",
        "created_at_unix": time.time(),
        "drive_root": _safe_path(args.drive_root),
        "versions": versions,
        "people": [person.key for person in people],
        "results": batch_results,
        "comparison_sheets": comparison_sheets,
    }
    batch_manifest_path = args.drive_root / "output" / "facebuilder_versions_batch_manifest.json"
    _write_json(batch_manifest_path, batch_manifest)
    _write_summary_report(args.drive_root, versions, people)
    print(f"FACEBUILDER_VERSION_BATCH_MANIFEST {batch_manifest_path}")
    failed = [
        item for item in batch_results
        if item.get("blender") and not item["blender"].get("ok")
    ]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
