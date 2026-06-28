"""Run the FaceBuilder raw/crop/sentinel semantic ablation.

This host-side runner reuses private Pixel3DMM V4 preprocessing artifacts
(FaceBoxes crop + FaRL segmentation) and feeds them into the existing Blender
FaceBuilder batch script.

Private generated artifacts are written to Google Drive only. Do not commit
Drive outputs, masks, textures, renders, OBJ/GLB files, or review sheets.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.facebuilder_bridge.facebuilder_version_runner import (  # noqa: E402
    DEFAULT_BLENDER_EXE,
    _create_review_sheet,
    _run_blender,
    _safe_path,
    _write_json,
)


VERSION_ORDER = ("v1", "v2", "v3")
VERSION_DESCRIPTIONS = {
    "v1": "raw photos for auto-align and raw FaceBuilder texture bake",
    "v2": "Pixel3DMM V4 crops for auto-align and raw FaceBuilder texture bake",
    "v3": "Pixel3DMM V4 crops for auto-align, sentinel-colored semantic inputs for texture bake",
}

SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

FARL_LABELS = {
    0: "background",
    1: "neck",
    2: "face",
    3: "cloth",
    4: "right_ear_region",
    5: "left_ear_region",
    6: "right_brow",
    7: "left_brow",
    8: "right_eye",
    9: "left_eye",
    10: "nose",
    11: "inner_mouth",
    12: "lower_lip",
    13: "upper_lip",
    14: "hair",
    15: "eyeglasses",
    16: "hat_or_misc",
    17: "earring",
    18: "necklace_or_neck_detail",
    20: "uncovered_or_zero_logits",
}

SENTINEL_COLORS = {
    "background": (0, 255, 0),
    "cloth": (0, 0, 255),
    "hair": (190, 0, 255),
    "eyeglasses": (0, 255, 255),
    "hat_or_misc": (255, 255, 0),
    "earring": (255, 0, 128),
    "necklace_or_neck_detail": (255, 128, 0),
    "uncovered_or_zero_logits": (255, 0, 0),
    "skin_outlier_or_occlusion": (255, 0, 64),
}

BAD_LABELS = {
    0,   # background
    3,   # cloth
    14,  # hair
    15,  # eyeglasses
    16,  # hat/misc
    17,  # earring
    18,  # necklace/detail
    20,  # uncovered/zero logits
}

SKINISH_LABELS = {1, 2, 4, 5}
FEATURE_LABELS = {6, 7, 8, 9, 10, 11, 12, 13}


@dataclass(frozen=True)
class PersonBundle:
    key: str
    label: str
    raw_input_dir: Path
    pixel_output_dir: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive-root", type=Path, default=Path(os.environ.get("HAIR_APP_DRIVE_ROOT", "G:/내 드라이브/hair_app")))
    parser.add_argument("--blender-exe", type=Path, default=DEFAULT_BLENDER_EXE)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--version", action="append", choices=VERSION_ORDER)
    parser.add_argument("--person", action="append", choices=("juseop", "eunchae"))
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--archive-old", action="store_true")
    parser.add_argument("--skip-blender", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--no-review-sheet", action="store_true")
    parser.add_argument("--sentinel-dilate", type=int, default=2)
    parser.add_argument("--start-row", type=int, default=0, help="Debug: first preprocessing row to use.")
    parser.add_argument("--max-rows", type=int, default=None, help="Debug: maximum preprocessing rows to use.")
    parser.add_argument(
        "--texture-scan-frames",
        action="store_true",
        help="Also allow Juseop scan_* frames to contribute to FaceBuilder texture bake. Default keeps scan frames alignment-only.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def list_people(drive_root: Path) -> dict[str, PersonBundle]:
    return {
        "juseop": PersonBundle(
            key="juseop",
            label="Juseop",
            raw_input_dir=drive_root / "input" / "주섭" / "pixel3dmm_입력_19장",
            pixel_output_dir=drive_root / "output" / "주섭",
        ),
        "eunchae": PersonBundle(
            key="eunchae",
            label="Eunchae",
            raw_input_dir=drive_root / "input" / "은채" / "셀카",
            pixel_output_dir=drive_root / "output" / "은채",
        ),
    }


def validate_person_bundle(person: PersonBundle) -> list[dict[str, Any]]:
    manifest_path = person.pixel_output_dir / "crop_meta" / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    manifest = read_json(manifest_path)
    items = manifest.get("items", [])
    if not items:
        raise RuntimeError(f"No crop manifest items: {manifest_path}")

    rows: list[dict[str, Any]] = []
    for item in items:
        source_name = item["source_name"]
        derived_name = item["derived_name"]
        stem = Path(derived_name).stem
        raw_path = person.raw_input_dir / source_name
        crop_path = person.pixel_output_dir / "crop" / derived_name
        seg_path = person.pixel_output_dir / "segmentation" / "seg_og" / f"{stem}.png"
        seg_color_path = person.pixel_output_dir / "segmentation" / "seg_non_crop_annotations" / f"color_{stem}.png"
        missing = [
            str(path)
            for path in (raw_path, crop_path, seg_path)
            if not path.exists()
        ]
        if missing:
            raise FileNotFoundError(f"{person.key} missing inputs for {source_name}: {missing}")
        rows.append({
            "source_name": source_name,
            "derived_name": derived_name,
            "stem": stem,
            "raw_path": raw_path,
            "crop_path": crop_path,
            "seg_path": seg_path,
            "seg_color_path": seg_color_path if seg_color_path.exists() else None,
            "crop_meta": item,
        })
    return rows


def normalize_copy(src: Path, dst: Path, *, png: bool = False) -> dict[str, Any]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    if png:
        image.save(dst)
    else:
        image.save(dst, quality=96)
    return {
        "path": _safe_path(dst),
        "source": _safe_path(src),
        "width": image.width,
        "height": image.height,
    }


def dilate_mask(mask: np.ndarray, iterations: int) -> np.ndarray:
    if iterations <= 0:
        return mask.astype(bool)
    result = mask.astype(bool)
    for _ in range(iterations):
        padded = np.pad(result, 1, mode="edge")
        result = (
            padded[1:-1, 1:-1]
            | padded[:-2, 1:-1]
            | padded[2:, 1:-1]
            | padded[1:-1, :-2]
            | padded[1:-1, 2:]
            | padded[:-2, :-2]
            | padded[:-2, 2:]
            | padded[2:, :-2]
            | padded[2:, 2:]
        )
    return result


def create_sentinel_texture(crop_path: Path, seg_path: Path, out_path: Path, mask_path: Path, *, dilate: int) -> dict[str, Any]:
    with Image.open(crop_path) as crop_image:
        crop = np.asarray(crop_image.convert("RGB"), dtype=np.uint8)
    with Image.open(seg_path) as seg_image:
        seg = np.asarray(seg_image)
    if seg.ndim == 3:
        seg = seg[:, :, 0]
    if seg.shape[:2] != crop.shape[:2]:
        seg = np.asarray(Image.fromarray(seg.astype(np.uint8)).resize((crop.shape[1], crop.shape[0]), Image.Resampling.NEAREST))

    sentinel = crop.copy()
    combined_bad = np.zeros(seg.shape, dtype=bool)
    class_stats: list[dict[str, Any]] = []
    for label_id, label_name in FARL_LABELS.items():
        mask = seg == label_id
        count = int(mask.sum())
        if count == 0:
            continue
        class_stats.append({
            "id": label_id,
            "name": label_name,
            "pixels": count,
            "ratio": float(count / seg.size),
        })
        if label_id in BAD_LABELS:
            expanded = dilate_mask(mask, dilate)
            combined_bad |= expanded
            sentinel[expanded] = SENTINEL_COLORS[label_name]

    # FaRL is a face parser, not a hand/object detector. A perfume bottle, phone,
    # or high-contrast object can sometimes be mislabeled as face/neck/ear.
    # Keep this pass conservative: only skin-region pixels with extreme color
    # disagreement are painted as observable occlusion sentinels.
    arr = crop.astype(np.float32)
    luma = arr[:, :, 0] * 0.2126 + arr[:, :, 1] * 0.7152 + arr[:, :, 2] * 0.0722
    maxc = arr.max(axis=2)
    minc = arr.min(axis=2)
    saturation = (maxc - minc) / np.maximum(maxc, 1.0)
    skinish = np.isin(seg, list(SKINISH_LABELS))
    features = np.isin(seg, list(FEATURE_LABELS))
    skin_sample = (
        skinish
        & ~features
        & ~combined_bad
        & (luma > 45)
        & (luma < 225)
        & (saturation < 0.48)
        & (arr[:, :, 0] > arr[:, :, 2] * 0.92)
        & (arr[:, :, 1] > arr[:, :, 2] * 0.72)
    )
    skin_outlier_count = 0
    skin_reference = None
    if int(skin_sample.sum()) >= 128:
        skin_reference = np.median(arr[skin_sample], axis=0)
        color_distance = np.linalg.norm(arr - skin_reference.reshape((1, 1, 3)), axis=2)
        non_skin_color = (
            ((luma < 24) & (saturation < 0.88))
            | ((luma > 246) & (saturation < 0.34))
            | ((saturation > 0.82) & (color_distance > 82))
        )
        skin_outlier = skinish & ~features & ~combined_bad & non_skin_color
        skin_outlier = dilate_mask(skin_outlier, max(1, dilate - 1))
        skin_outlier &= skinish & ~features & ~combined_bad
        skin_outlier_count = int(skin_outlier.sum())
        if skin_outlier_count:
            combined_bad |= skin_outlier
            sentinel[skin_outlier] = SENTINEL_COLORS["skin_outlier_or_occlusion"]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sentinel, mode="RGB").save(out_path)
    Image.fromarray((combined_bad.astype(np.uint8) * 255), mode="L").save(mask_path)

    return {
        "path": _safe_path(out_path),
        "mask_path": _safe_path(mask_path),
        "crop_path": _safe_path(crop_path),
        "seg_path": _safe_path(seg_path),
        "dilate_iterations": dilate,
        "bad_pixels": int(combined_bad.sum()),
        "bad_ratio": float(combined_bad.mean()),
        "skin_reference_rgb": [float(value) for value in skin_reference] if skin_reference is not None else None,
        "skin_outlier_pixels": skin_outlier_count,
        "class_stats": class_stats,
        "sentinel_colors": SENTINEL_COLORS,
    }


def make_tile(path: Path, size: tuple[int, int]) -> Image.Image:
    tile = Image.new("RGB", size, (18, 18, 18))
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    tile.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return tile


def font_pair() -> tuple[Any, Any]:
    try:
        return ImageFont.truetype("arial.ttf", 17), ImageFont.truetype("arial.ttf", 12)
    except Exception:
        return None, None


def create_preprocess_review(person: PersonBundle, rows: list[dict[str, Any]], output_dir: Path) -> Path:
    review_dir = output_dir / "_preprocess_review" / person.key
    review_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = review_dir / f"{person.key}_crop_segmentation_sentinel_review.png"
    tile_w, tile_h = 220, 220
    label_h = 52
    gap = 10
    cols = 4
    max_rows = len(rows)
    width = cols * tile_w + (cols + 1) * gap
    height = max_rows * (tile_h + label_h + gap) + gap
    sheet = Image.new("RGB", (width, height), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    font, small = font_pair()
    headings = ("raw", "crop", "FaRL", "sentinel")
    for row_index, row in enumerate(rows):
        y = gap + row_index * (tile_h + label_h + gap)
        paths = [
            row["raw_path"],
            row["crop_path"],
            row.get("seg_color_path") or row["seg_path"],
            Path(row["sentinel"]["path"]),
        ]
        for col_index, path in enumerate(paths):
            x = gap + col_index * (tile_w + gap)
            draw.rectangle([x, y, x + tile_w, y + label_h - 1], fill=(42, 42, 42))
            draw.text((x + 7, y + 6), f"{row_index:02d} {headings[col_index]}", fill=(245, 245, 245), font=font)
            draw.text((x + 7, y + 29), Path(path).name[:30], fill=(190, 190, 190), font=small)
            sheet.paste(make_tile(Path(path), (tile_w, tile_h)), (x, y + label_h))
    sheet.save(sheet_path, quality=95)
    return sheet_path


def create_placeholder_tile(label: str, size: tuple[int, int]) -> Image.Image:
    tile = Image.new("RGB", size, (16, 16, 16))
    draw = ImageDraw.Draw(tile)
    font, small = font_pair()
    draw.rectangle([0, 0, size[0] - 1, size[1] - 1], outline=(72, 72, 72))
    draw.text((12, 14), label, fill=(240, 120, 120), font=font)
    draw.text((12, 42), "missing", fill=(180, 180, 180), font=small)
    return tile


def paste_labeled_tile(
    sheet: Image.Image,
    draw: ImageDraw.ImageDraw,
    path: Path | None,
    *,
    x: int,
    y: int,
    size: tuple[int, int],
    label: str,
    subtitle: str = "",
) -> None:
    font, small = font_pair()
    label_h = 52
    draw.rectangle([x, y, x + size[0], y + label_h - 1], fill=(42, 42, 42))
    draw.text((x + 7, y + 6), label[:36], fill=(245, 245, 245), font=font)
    if subtitle:
        draw.text((x + 7, y + 29), subtitle[:44], fill=(190, 190, 190), font=small)
    if path and path.exists():
        tile = make_tile(path, (size[0], size[1] - label_h))
    else:
        tile = create_placeholder_tile(label, (size[0], size[1] - label_h))
    sheet.paste(tile, (x, y + label_h))


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def create_run_review_sheet(version_output_dir: Path) -> Path | None:
    run_manifest_path = version_output_dir / "run_manifest.json"
    input_manifest_path = version_output_dir / "01_input_manifest" / "input_manifest.json"
    if not run_manifest_path.exists() or not input_manifest_path.exists():
        return None

    run_manifest = read_json(run_manifest_path)
    input_manifest = read_json(input_manifest_path)
    version = str(input_manifest.get("version", run_manifest.get("version", "unknown")))
    person = str(input_manifest.get("person", run_manifest.get("person", "unknown")))
    version_description = str(input_manifest.get("version_description", VERSION_DESCRIPTIONS.get(version, "")))
    items = input_manifest.get("items", [])
    texture_enabled = sum(
        1
        for item in items
        for candidate in item.get("candidates", [])
        if candidate.get("allow_texture_bake")
    )

    review_dir = version_output_dir / "07_review_sheets"
    review_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = review_dir / "semantic_review_sheet.png"

    tile_w, tile_h = 260, 260
    gap = 12
    cols = 4
    header_h = 112
    rows = 3
    width = cols * tile_w + (cols + 1) * gap
    height = header_h + rows * tile_h + (rows + 1) * gap
    sheet = Image.new("RGB", (width, height), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    font, small = font_pair()

    draw.text((gap, 14), f"{person} {version} FaceBuilder semantic ablation review", fill=(245, 245, 245), font=font)
    draw.text((gap, 40), version_description, fill=(195, 195, 195), font=small)
    draw.text(
        (gap, 62),
        f"input rows: {len(items)} | texture-enabled rows: {texture_enabled} | ok: {bool(run_manifest.get('ok'))}",
        fill=(195, 195, 195),
        font=small,
    )
    draw.text((gap, 84), "Private render/texture sheet. Do not commit generated image assets.", fill=(150, 150, 150), font=small)

    align_samples: list[Path] = []
    texture_sample: Path | None = None
    for item in items:
        candidates = item.get("candidates", [])
        if not candidates:
            continue
        candidate = candidates[0]
        working_path = candidate.get("path")
        texture_path = candidate.get("texture_path")
        if working_path and len(align_samples) < 3:
            align_samples.append(Path(working_path))
        if texture_path and texture_sample is None:
            texture_sample = Path(texture_path)
    sample_candidates: list[tuple[str, Path | None]] = []
    if align_samples:
        sample_candidates.append(("align input 1", align_samples[0]))
    if len(align_samples) > 1:
        sample_candidates.append(("align input 2", align_samples[1]))
    if texture_sample:
        sample_candidates.append(("texture input", texture_sample))
    elif len(align_samples) > 2:
        sample_candidates.append(("align input 3", align_samples[2]))
    while len(sample_candidates) < 3:
        sample_candidates.append(("input sample", None))

    third_sample_subtitle = "sentinel semantic image" if sample_candidates[2][0] == "texture input" else "third manifest image"
    assets: list[tuple[str, str, Path | None]] = [
        (sample_candidates[0][0], "first manifest image", sample_candidates[0][1]),
        (sample_candidates[1][0], "second manifest image", sample_candidates[1][1]),
        (sample_candidates[2][0], third_sample_subtitle, sample_candidates[2][1]),
        ("raw texture bake", "FaceBuilder output", version_output_dir / "05_postprocess" / "facebuilder_texture_bake.png"),
        ("cleanup texture", "current postprocess output", version_output_dir / "05_postprocess" / "facebuilder_texture_bald_cleanup.png"),
        ("yaw +00", "front render", version_output_dir / "07_review_sheets" / "render_yaw_+00.png"),
        ("yaw +15", "right-ish render", version_output_dir / "07_review_sheets" / "render_yaw_+15.png"),
        ("yaw -15", "left-ish render", version_output_dir / "07_review_sheets" / "render_yaw_-15.png"),
        ("yaw +30", "right render", version_output_dir / "07_review_sheets" / "render_yaw_+30.png"),
        ("yaw -30", "left render", version_output_dir / "07_review_sheets" / "render_yaw_-30.png"),
        ("yaw +45", "right 45 render", version_output_dir / "07_review_sheets" / "render_yaw_+45.png"),
        ("yaw -45", "left 45 render", version_output_dir / "07_review_sheets" / "render_yaw_-45.png"),
    ]

    for index, (label, subtitle, path) in enumerate(assets):
        row = index // cols
        col = index % cols
        x = gap + col * (tile_w + gap)
        y = header_h + gap + row * (tile_h + gap)
        paste_labeled_tile(sheet, draw, path, x=x, y=y, size=(tile_w, tile_h), label=label, subtitle=subtitle)

    sheet.save(sheet_path, quality=95)

    run_manifest["semantic_review_sheet"] = _safe_path(sheet_path)
    review_payload = run_manifest.get("review")
    if not isinstance(review_payload, dict):
        review_payload = {}
    review_payload["semantic_review_sheet"] = _safe_path(sheet_path)
    run_manifest["review"] = review_payload
    safe_write_json(run_manifest_path, run_manifest)
    return sheet_path


def prepare_person_inputs(
    person: PersonBundle,
    rows: list[dict[str, Any]],
    root_output_dir: Path,
    *,
    clean: bool,
    sentinel_dilate: int,
) -> dict[str, Any]:
    prep_root = root_output_dir / "_semantic_preprocess" / person.key
    if clean and prep_root.exists():
        shutil.rmtree(prep_root)
    raw_dir = prep_root / "raw"
    crop_dir = prep_root / "crop"
    sentinel_dir = prep_root / "sentinel_texture"
    mask_dir = prep_root / "sentinel_masks"

    prepared_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        stem = f"{index:03d}_{Path(row['source_name']).stem}"
        raw_dst = raw_dir / f"{stem}.jpg"
        crop_dst = crop_dir / f"{stem}_crop.jpg"
        sentinel_dst = sentinel_dir / f"{stem}_sentinel.png"
        sentinel_mask_dst = mask_dir / f"{stem}_sentinel_mask.png"
        raw_info = normalize_copy(row["raw_path"], raw_dst)
        crop_info = normalize_copy(row["crop_path"], crop_dst)
        sentinel = create_sentinel_texture(crop_dst, row["seg_path"], sentinel_dst, sentinel_mask_dst, dilate=sentinel_dilate)
        prepared_rows.append({
            **row,
            "image_id": f"{person.key}_{index:03d}",
            "raw": raw_info,
            "crop": crop_info,
            "sentinel": sentinel,
        })

    review_sheet = create_preprocess_review(person, prepared_rows, root_output_dir)
    summary = {
        "schema_version": "hair_app_facebuilder_semantic_preprocess_v1",
        "person": person.key,
        "person_label": person.label,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_input_dir": _safe_path(person.raw_input_dir),
        "pixel_output_dir": _safe_path(person.pixel_output_dir),
        "count": len(prepared_rows),
        "sentinel_dilate": sentinel_dilate,
        "review_sheet": _safe_path(review_sheet),
        "rows": [
            {
                "image_id": row["image_id"],
                "source_name": row["source_name"],
                "derived_name": row["derived_name"],
                "raw": row["raw"],
                "crop": row["crop"],
                "sentinel": row["sentinel"],
            }
            for row in prepared_rows
        ],
        "privacy": "Private biometric preprocessing artifacts. Do not commit generated outputs.",
    }
    safe_write_json(prep_root / "semantic_preprocess_manifest.json", summary)
    return {"rows": prepared_rows, "manifest": summary}


def output_folders(version_output_dir: Path) -> dict[str, Path]:
    folders = {
        "input_manifest": version_output_dir / "01_input_manifest",
        "working_images": version_output_dir / "02_working_images",
        "blend": version_output_dir / "03_blend",
        "exports": version_output_dir / "04_exports",
        "postprocess": version_output_dir / "05_postprocess",
        "glb": version_output_dir / "06_glb",
        "review": version_output_dir / "07_review_sheets",
    }
    for path in folders.values():
        path.mkdir(parents=True, exist_ok=True)
    return folders


def allow_texture_bake_for_row(person: PersonBundle, row: dict[str, Any], *, texture_scan_frames: bool) -> bool:
    if person.key == "juseop" and str(row["source_name"]).startswith("scan_") and not texture_scan_frames:
        return False
    return True


def create_version_manifest(
    version: str,
    person: PersonBundle,
    prepared_rows: list[dict[str, Any]],
    version_output_dir: Path,
    *,
    texture_scan_frames: bool,
) -> Path:
    folders = output_folders(version_output_dir)
    items: list[dict[str, Any]] = []
    for index, row in enumerate(prepared_rows):
        allow_texture = allow_texture_bake_for_row(person, row, texture_scan_frames=texture_scan_frames)
        if version == "v1":
            path = row["raw"]["path"]
            texture_path = None
            input_kind = "raw"
        elif version == "v2":
            path = row["crop"]["path"]
            texture_path = None
            input_kind = "crop"
        elif version == "v3":
            path = row["crop"]["path"]
            texture_path = row["sentinel"]["path"] if allow_texture else None
            input_kind = "crop_with_sentinel_texture"
        else:
            raise ValueError(version)

        items.append({
            "index": index,
            "image_id": row["image_id"],
            "source_path": _safe_path(row["raw_path"]),
            "source_name": row["source_name"],
            "working_path": path,
            "crop_path": row["crop"]["path"],
            "sentinel_path": row["sentinel"]["path"],
            "score": {
                "ok": True,
                "source_name": row["source_name"],
                "policy": "all_pixel3dmm_v4_preprocessed_rows",
            },
            "candidates": [
                {
                    "kind": input_kind,
                    "path": path,
                    "preferred": True,
                    "allow_texture_bake": allow_texture,
                    "texture_path": texture_path,
                    "texture_kind": "sentinel_semantic" if texture_path else ("alignment_only" if not allow_texture else input_kind),
                }
            ],
        })

    manifest = {
        "schema_version": "hair_app_facebuilder_semantic_ablation_manifest_v1",
        "version": version,
        "version_description": VERSION_DESCRIPTIONS[version],
        "version_config": {
            "raw_align": version == "v1",
            "crop_align": version in {"v2", "v3"},
            "sentinel_texture": version == "v3",
            "use_cleanup_texture": False,
            "texture_scan_frames": bool(texture_scan_frames),
            "scan_frames_alignment_only_by_default": True,
        },
        "person": person.key,
        "person_label": person.label,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "items": items,
        "quality_report": {
            "selection_policy": "use all rows from the existing Pixel3DMM V4 preprocessing manifest",
            "selected_count": len(items),
            "rejected_count": 0,
        },
        "notes": [
            "v1 uses raw standardized private input photos.",
            "v2 uses existing Pixel3DMM V4 FaceBoxes crops for both alignment and texture.",
            "v3 aligns on crops and swaps the texture image to sentinel-colored semantic crops after alignment.",
            "Juseop scan_* rows are alignment-only unless --texture-scan-frames is set; this avoids FaceBuilder stalls when many mixed scan/selfie cameras enter texture baking.",
        ],
        "privacy": "Private biometric runtime manifest. Do not commit generated outputs.",
    }
    manifest_path = folders["input_manifest"] / "input_manifest.json"
    _write_json(manifest_path, manifest)
    _write_json(folders["input_manifest"] / "photo_quality_report.json", {
        "version": version,
        "person": person.key,
        "selected_count": len(items),
        "rejected_count": 0,
        "selection_policy": "all_pixel3dmm_v4_preprocessed_rows",
        "items": items,
    })
    return manifest_path


def create_version_comparison_sheet(drive_root: Path, versions: list[str], people: list[str]) -> Path:
    comparison_dir = drive_root / "output" / "_comparison" / "facebuilder_semantic_v1_v3"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    sheet_path = comparison_dir / "facebuilder_semantic_v1_v3_comparison.png"
    tile_w, tile_h = 320, 420
    header_h = 76
    label_h = 62
    gap = 12
    rows = len(people)
    cols = len(versions)
    width = cols * tile_w + (cols + 1) * gap
    height = header_h + rows * (tile_h + label_h + gap) + gap
    sheet = Image.new("RGB", (width, height), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    font, small = font_pair()
    draw.text((gap, 16), "FaceBuilder semantic ablation: yaw 0 review comparison", fill=(245, 245, 245), font=font)
    draw.text((gap, 40), "v1 raw, v2 crop, v3 crop + sentinel texture", fill=(180, 180, 180), font=small)
    for person_index, person in enumerate(people):
        y = header_h + gap + person_index * (tile_h + label_h + gap)
        for version_index, version in enumerate(versions):
            x = gap + version_index * (tile_w + gap)
            run_dir = drive_root / "output" / f"facebuilder_semantic_{version}" / person
            render_path = run_dir / "07_review_sheets" / "render_yaw_+00.png"
            texture_path = run_dir / "05_postprocess" / "facebuilder_texture_bake.png"
            draw.rectangle([x, y, x + tile_w, y + label_h - 1], fill=(42, 42, 42))
            draw.text((x + 8, y + 6), f"{person} {version}", fill=(245, 245, 245), font=font)
            draw.text((x + 8, y + 31), VERSION_DESCRIPTIONS[version][:36], fill=(190, 190, 190), font=small)
            cell = Image.new("RGB", (tile_w, tile_h), (16, 16, 16))
            if render_path.exists():
                cell.paste(make_tile(render_path, (tile_w, 260)), (0, 0))
            else:
                cell.paste(create_placeholder_tile("missing yaw +00", (tile_w, 260)), (0, 0))
            if texture_path.exists():
                cell.paste(make_tile(texture_path, (tile_w, tile_h - 260)), (0, 260))
            else:
                cell.paste(create_placeholder_tile("missing texture", (tile_w, tile_h - 260)), (0, 260))
            sheet.paste(cell, (x, y + label_h))
    sheet.save(sheet_path, quality=95)
    return sheet_path


def archive_old_outputs(drive_root: Path) -> Path | None:
    output_root = drive_root / "output"
    old_dirs = [output_root / f"facebuilder_v{idx}" for idx in range(1, 5)]
    existing = [path for path in old_dirs if path.exists()]
    if not existing:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = output_root / "history_archive" / f"retired_facebuilder_color_mute_v1_v4_{stamp}"
    archive_dir.mkdir(parents=True, exist_ok=False)
    moved: list[dict[str, str]] = []
    for path in existing:
        target = archive_dir / path.name
        shutil.move(str(path), str(target))
        moved.append({"from": _safe_path(path), "to": _safe_path(target)})
    manifest = {
        "schema_version": "hair_app_retired_facebuilder_color_mute_archive_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reason": "Retired v1-v4 raw/preprocess/postprocess color-mute ablation. The preprocessing filled bad regions with skin-like colors and polluted FaceBuilder texture bake.",
        "moved": moved,
        "privacy": "Private generated outputs and review sheets. Keep in Drive archive; do not commit.",
    }
    safe_write_json(archive_dir / "archive_manifest.json", manifest)
    return archive_dir


def run() -> int:
    args = parse_args()
    versions = args.version or list(VERSION_ORDER)
    person_keys = args.person or ["juseop", "eunchae"]
    people = list_people(args.drive_root)
    root_output = args.drive_root / "output"

    archive_dir = archive_old_outputs(args.drive_root) if args.archive_old else None
    if archive_dir:
        print(f"Archived old FaceBuilder v1-v4 outputs: {archive_dir}")

    results: list[dict[str, Any]] = []
    for person_key in person_keys:
        person = people[person_key]
        source_rows = validate_person_bundle(person)
        if args.start_row or args.max_rows is not None:
            start = max(0, args.start_row)
            end = None if args.max_rows is None else start + max(0, args.max_rows)
            source_rows = source_rows[start:end]
            if not source_rows:
                raise RuntimeError(f"No rows selected for {person.key}: start={args.start_row} max={args.max_rows}")
        prepared = prepare_person_inputs(
            person,
            source_rows,
            root_output,
            clean=args.clean,
            sentinel_dilate=args.sentinel_dilate,
        )
        prepared_rows = prepared["rows"]
        print(f"{person.key}: prepared {len(prepared_rows)} rows")

        for version in versions:
            version_output_dir = root_output / f"facebuilder_semantic_{version}" / person.key
            if args.clean and version_output_dir.exists():
                shutil.rmtree(version_output_dir)
            manifest_path = create_version_manifest(
                version,
                person,
                prepared_rows,
                version_output_dir,
                texture_scan_frames=args.texture_scan_frames,
            )
            result: dict[str, Any] = {
                "version": version,
                "person": person.key,
                "output_dir": _safe_path(version_output_dir),
                "manifest": _safe_path(manifest_path),
                "skipped_blender": bool(args.skip_blender),
            }
            if not args.skip_blender:
                if args.skip_existing and (version_output_dir / "run_manifest.json").exists():
                    result["blender"] = {"skipped_existing": True}
                else:
                    result["blender"] = _run_blender(
                        blender_exe=args.blender_exe,
                        repo_root=args.repo_root,
                        manifest_path=manifest_path,
                        output_dir=version_output_dir,
                        use_cleanup_texture=False,
                    )
                if not args.no_review_sheet:
                    review_path = create_run_review_sheet(version_output_dir)
                    if not review_path:
                        review_path = _create_review_sheet(version_output_dir)
                    result["review_sheet"] = _safe_path(review_path) if review_path else None
            results.append(result)
            print(json.dumps(result, indent=2, ensure_ascii=False))

    comparison_sheet = None
    if not args.no_review_sheet:
        comparison_sheet = create_version_comparison_sheet(args.drive_root, list(versions), person_keys)

    run_manifest = {
        "schema_version": "hair_app_facebuilder_semantic_ablation_run_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "versions": list(versions),
        "people": person_keys,
        "archive_dir": _safe_path(archive_dir) if archive_dir else None,
        "comparison_sheet": _safe_path(comparison_sheet) if comparison_sheet else None,
        "results": results,
        "privacy": "Private generated outputs live in Drive. Do not commit generated assets.",
    }
    manifest_path = root_output / "_comparison" / "facebuilder_semantic_v1_v3" / "run_manifest.json"
    safe_write_json(manifest_path, run_manifest)
    print("Semantic FaceBuilder ablation complete")
    print(json.dumps(run_manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
