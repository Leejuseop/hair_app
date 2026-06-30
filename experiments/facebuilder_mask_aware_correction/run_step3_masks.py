"""Build Step 3 usable-skin masks for parser/object-mask ablations.

Versions:
  v0_farl_only                 = FaRL face parser only
  v1_facexformer_only          = FaceXFormer face parser only
  v2_farl_grounded_sam         = FaRL + external object/occlusion masks
  v3_facexformer_grounded_sam  = FaceXFormer + external object/occlusion masks

This script can always build v0 from existing Pixel3DMM/FaRL artifacts. The
other versions are built when the expected Colab-generated external masks are
available in Drive.

Private mask/review outputs stay in Drive and must not be committed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DRIVE_ROOT = Path(os.environ.get("HAIR_APP_DRIVE_ROOT", "G:/\ub0b4 \ub4dc\ub77c\uc774\ube0c/hair_app"))
PERSONS = ("juseop", "eunchae")

FARL_LABELS = {
    0: "background",
    1: "neck",
    2: "face_skin",
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

# FaceXFormer's public inference visualization defines 11 parsing classes but
# does not name them in README/inference.py. These groups are intentionally
# conservative and can be adjusted after the first Colab output review.
FACEXFORMER_USABLE_LABELS = {1, 2, 3, 4}
FACEXFORMER_BAD_LABELS = {0, 5, 6, 7, 8, 9, 10}

FARL_USABLE_LABELS = {1, 2, 4, 5, 10}  # neck, face, ears, nose
FARL_FEATURE_LABELS = {6, 7, 8, 9, 11, 12, 13}
FARL_BAD_LABELS = {0, 3, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 20}

VERSION_CONFIG = {
    "v0_farl_only": {"parser": "farl", "object": False},
    "v1_facexformer_only": {"parser": "facexformer", "object": False},
    "v2_farl_grounded_sam": {"parser": "farl", "object": True},
    "v3_facexformer_grounded_sam": {"parser": "facexformer", "object": True},
}


@dataclass(frozen=True)
class PersonPaths:
    key: str
    pixel_output_name: str
    manifest_person_name: str


PERSON_PATHS = {
    "juseop": PersonPaths("juseop", "\uc8fc\uc12d", "juseop"),
    "eunchae": PersonPaths("eunchae", "\uc740\ucc44", "eunchae"),
}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive-root", type=Path, default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--source-version", default="facebuilder_semantic_v2")
    parser.add_argument("--version", action="append", choices=tuple(VERSION_CONFIG.keys()))
    parser.add_argument("--person", action="append", choices=PERSONS)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--usable-erode", type=int, default=1)
    parser.add_argument("--bad-dilate", type=int, default=2)
    parser.add_argument("--review-max-rows", type=int, default=None)
    return parser.parse_args(argv)


def _safe_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


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
    return ImageOps.exif_transpose(Image.open(Path(str(path).replace("/", "\\")))).convert("RGB")


def _load_label(path: Path, target_size: tuple[int, int]) -> np.ndarray:
    with Image.open(path) as image:
        arr = np.asarray(image)
    if arr.ndim == 3:
        arr = arr[:, :, 0]
    if (arr.shape[1], arr.shape[0]) != target_size:
        arr = np.asarray(Image.fromarray(arr.astype(np.uint8)).resize(target_size, Image.Resampling.NEAREST))
    return arr.astype(np.uint8)


def _load_binary_mask(path: Path, target_size: tuple[int, int]) -> np.ndarray:
    with Image.open(path) as image:
        arr = np.asarray(image.convert("L"))
    if (arr.shape[1], arr.shape[0]) != target_size:
        arr = np.asarray(Image.fromarray(arr).resize(target_size, Image.Resampling.NEAREST))
    return arr > 127


def _dilate(mask: np.ndarray, iterations: int) -> np.ndarray:
    result = mask.astype(bool)
    for _ in range(max(0, iterations)):
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


def _erode(mask: np.ndarray, iterations: int) -> np.ndarray:
    result = mask.astype(bool)
    for _ in range(max(0, iterations)):
        padded = np.pad(result, 1, mode="edge")
        result = (
            padded[1:-1, 1:-1]
            & padded[:-2, 1:-1]
            & padded[2:, 1:-1]
            & padded[1:-1, :-2]
            & padded[1:-1, 2:]
            & padded[:-2, :-2]
            & padded[:-2, 2:]
            & padded[2:, :-2]
            & padded[2:, 2:]
        )
    return result


def _mask_to_image(mask: np.ndarray) -> Image.Image:
    return Image.fromarray((mask.astype(np.uint8) * 255), mode="L")


def _label_color(label: np.ndarray, palette: dict[int, tuple[int, int, int]]) -> Image.Image:
    rgb = np.zeros((label.shape[0], label.shape[1], 3), dtype=np.uint8)
    for label_id, color in palette.items():
        rgb[label == label_id] = color
    unknown = ~np.isin(label, list(palette.keys()))
    rgb[unknown] = (120, 120, 120)
    return Image.fromarray(rgb, mode="RGB")


def _overlay_mask(image: Image.Image, usable: np.ndarray, bad: np.ndarray, obj: np.ndarray) -> Image.Image:
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    arr = np.zeros((base.height, base.width, 4), dtype=np.uint8)
    arr[usable] = (40, 230, 120, 120)
    arr[bad] = (255, 40, 80, 100)
    arr[obj] = (255, 210, 30, 150)
    overlay = Image.fromarray(arr, mode="RGBA")
    return Image.alpha_composite(base, overlay).convert("RGB")


def _find_external_mask(external_root: Path, family: str, person: str, item: dict[str, Any], kind: str) -> Path | None:
    candidates = []
    stem = Path(str(item.get("crop_path", ""))).stem
    source_stem = Path(str(item.get("source_name", ""))).stem
    image_id = str(item.get("image_id", ""))
    index = int(item.get("index", -1))
    names = [
        f"{index:03d}.png",
        f"{index:05d}.png",
        f"{image_id}.png",
        f"{stem}.png",
        f"{source_stem}.png",
        f"{index:03d}_{source_stem}.png",
    ]
    for subdir in (kind, f"{kind}s", "labels" if kind == "label" else "masks", ""):
        base = external_root / family / person / subdir if subdir else external_root / family / person
        for name in names:
            candidates.append(base / name)
    for path in candidates:
        if path.exists():
            return path
    return None


def _build_source_mapping(drive_root: Path, person: str) -> dict[str, dict[str, Any]]:
    paths = PERSON_PATHS[person]
    crop_meta_path = drive_root / "output" / paths.pixel_output_name / "crop_meta" / "manifest.json"
    data = _read_json(crop_meta_path)
    return {item["source_name"]: item for item in data.get("items", [])}


def _farl_label_path(drive_root: Path, person: str, item: dict[str, Any], source_map: dict[str, dict[str, Any]]) -> Path | None:
    paths = PERSON_PATHS[person]
    source_name = item.get("source_name")
    crop_item = source_map.get(source_name)
    if not crop_item:
        return None
    stem = Path(crop_item["derived_name"]).stem
    path = drive_root / "output" / paths.pixel_output_name / "segmentation" / "seg_og" / f"{stem}.png"
    return path if path.exists() else None


def _copy_or_save(path: Path, image: Image.Image) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return _safe_path(path) or ""


def _parser_masks(
    version_name: str,
    config: dict[str, Any],
    drive_root: Path,
    external_root: Path,
    person: str,
    item: dict[str, Any],
    source_map: dict[str, dict[str, Any]],
    target_size: tuple[int, int],
) -> tuple[np.ndarray | None, np.ndarray | None, Path | None, str]:
    parser = config["parser"]
    if parser == "farl":
        path = _farl_label_path(drive_root, person, item, source_map)
        if path is None:
            return None, None, None, "missing_farl_label"
        label = _load_label(path, target_size)
        usable = np.isin(label, list(FARL_USABLE_LABELS))
        bad = np.isin(label, list(FARL_BAD_LABELS))
        return usable, bad, path, "ok"

    if parser == "facexformer":
        path = _find_external_mask(external_root, "facexformer", person, item, "label")
        if path is None:
            return None, None, None, "missing_facexformer_label"
        label = _load_label(path, target_size)
        usable = np.isin(label, list(FACEXFORMER_USABLE_LABELS))
        bad = np.isin(label, list(FACEXFORMER_BAD_LABELS))
        return usable, bad, path, "ok"

    return None, None, None, f"unknown_parser_{parser}"


def _object_mask(
    external_root: Path,
    person: str,
    item: dict[str, Any],
    target_size: tuple[int, int],
    enabled: bool,
) -> tuple[np.ndarray, Path | None, str]:
    if not enabled:
        return np.zeros((target_size[1], target_size[0]), dtype=bool), None, "disabled"
    path = _find_external_mask(external_root, "grounded_sam", person, item, "object_mask")
    if path is None:
        return np.zeros((target_size[1], target_size[0]), dtype=bool), None, "missing_object_mask"
    return _load_binary_mask(path, target_size), path, "ok"


def _make_tile(title: str, image: Image.Image, width: int = 210) -> Image.Image:
    ratio = width / image.width
    thumb = image.resize((width, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
    band_h = 30
    out = Image.new("RGB", (thumb.width, thumb.height + band_h), (28, 28, 28))
    out.paste(thumb, (0, band_h))
    draw = ImageDraw.Draw(out)
    draw.text((7, 7), title[:34], fill=(240, 240, 240), font=_font(13))
    return out


def _make_row(item: dict[str, Any], crop: Image.Image, parser_vis: Image.Image, usable: np.ndarray, bad: np.ndarray, obj: np.ndarray, overlay: Image.Image) -> Image.Image:
    tiles = [
        _make_tile(f"{item['index']:03d} original", crop),
        _make_tile("parser labels", parser_vis),
        _make_tile("usable skin", _mask_to_image(usable).convert("RGB")),
        _make_tile("bad mask", _mask_to_image(bad).convert("RGB")),
        _make_tile("object mask", _mask_to_image(obj).convert("RGB")),
        _make_tile("overlay", overlay),
    ]
    gap = 8
    row_w = sum(tile.width for tile in tiles) + gap * (len(tiles) + 1)
    row_h = max(tile.height for tile in tiles) + gap * 2
    row = Image.new("RGB", (row_w, row_h), (18, 18, 18))
    x = gap
    for tile in tiles:
        row.paste(tile, (x, gap))
        x += tile.width + gap
    return row


def _make_review_sheet(version: str, person: str, rows: list[Image.Image], path: Path) -> None:
    if not rows:
        return
    header_h = 70
    gap = 10
    width = max(row.width for row in rows)
    height = header_h + sum(row.height for row in rows) + gap * (len(rows) + 1)
    sheet = Image.new("RGB", (width, height), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 12), f"{person} Step 3 {version} usable_skin masks", fill=(245, 245, 245), font=_font(24))
    draw.text((16, 44), "green=usable, red=bad, yellow=object. Private review sheet; do not commit.", fill=(180, 180, 180), font=_font(14))
    y = header_h + gap
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height + gap
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=95)


def _palette_for_parser(parser: str) -> dict[int, tuple[int, int, int]]:
    if parser == "farl":
        return {
            0: (0, 0, 0),
            1: (170, 120, 90),
            2: (245, 190, 155),
            3: (30, 80, 220),
            4: (225, 150, 120),
            5: (225, 150, 120),
            6: (80, 45, 25),
            7: (80, 45, 25),
            8: (235, 245, 255),
            9: (235, 245, 255),
            10: (250, 180, 145),
            11: (35, 0, 0),
            12: (235, 80, 120),
            13: (235, 80, 120),
            14: (20, 20, 20),
            15: (0, 240, 255),
            16: (255, 240, 0),
            17: (255, 0, 160),
            18: (255, 140, 0),
            20: (255, 0, 0),
        }
    return {
        0: (0, 0, 0),
        1: (245, 190, 155),
        2: (250, 180, 145),
        3: (225, 150, 120),
        4: (170, 120, 90),
        5: (235, 245, 255),
        6: (80, 45, 25),
        7: (235, 80, 120),
        8: (35, 0, 0),
        9: (20, 20, 20),
        10: (30, 80, 220),
    }


def _process_version_person(
    version: str,
    config: dict[str, Any],
    drive_root: Path,
    external_root: Path,
    source_root: Path,
    output_root: Path,
    person: str,
    usable_erode: int,
    bad_dilate: int,
    review_max_rows: int | None,
) -> dict[str, Any]:
    source_map = _build_source_mapping(drive_root, person)
    manifest_path = source_root / person / "01_input_manifest" / "input_manifest.json"
    manifest = _read_json(manifest_path)
    items = manifest.get("items", [])
    person_output = output_root / version / person
    review_rows: list[Image.Image] = []
    rows: list[dict[str, Any]] = []
    missing_reasons: dict[str, int] = {}

    for item in items:
        crop_path = Path(str(item["crop_path"]).replace("/", "\\"))
        crop = _load_rgb(crop_path)
        target_size = crop.size
        usable_raw, bad_raw, parser_path, parser_status = _parser_masks(
            version,
            config,
            drive_root,
            external_root,
            person,
            item,
            source_map,
            target_size,
        )
        object_raw, object_path, object_status = _object_mask(
            external_root,
            person,
            item,
            target_size,
            bool(config["object"]),
        )

        if usable_raw is None or bad_raw is None:
            missing_reasons[parser_status] = missing_reasons.get(parser_status, 0) + 1
            rows.append({
                "index": item["index"],
                "image_id": item["image_id"],
                "source_name": item["source_name"],
                "ok": False,
                "reason": parser_status,
                "parser_path": _safe_path(parser_path),
                "object_status": object_status,
                "object_path": _safe_path(object_path),
            })
            continue

        bad = _dilate(bad_raw | object_raw, bad_dilate)
        usable = _erode(usable_raw & ~bad, usable_erode)
        object_mask = _dilate(object_raw, 1)

        masks_dir = person_output / "per_image" / f"{int(item['index']):03d}_{item['image_id']}"
        usable_path = masks_dir / "usable_skin.png"
        bad_path = masks_dir / "bad_mask.png"
        object_out_path = masks_dir / "object_mask.png"
        overlay_path = masks_dir / "overlay.png"
        parser_copy_path = masks_dir / "parser_label.png"
        parser_vis_path = masks_dir / "parser_label_visual.png"

        _copy_or_save(usable_path, _mask_to_image(usable))
        _copy_or_save(bad_path, _mask_to_image(bad))
        _copy_or_save(object_out_path, _mask_to_image(object_mask))
        overlay = _overlay_mask(crop, usable, bad, object_mask)
        _copy_or_save(overlay_path, overlay)

        if parser_path is not None and parser_path.exists():
            shutil.copy2(parser_path, parser_copy_path)
            label = _load_label(parser_path, target_size)
            parser_vis = _label_color(label, _palette_for_parser(config["parser"]))
            _copy_or_save(parser_vis_path, parser_vis)
        else:
            parser_vis = Image.new("RGB", target_size, (0, 0, 0))

        total = usable.size
        row = {
            "index": item["index"],
            "image_id": item["image_id"],
            "source_name": item["source_name"],
            "texture_enabled": any(c.get("allow_texture_bake") for c in item.get("candidates", [])),
            "ok": True,
            "parser": config["parser"],
            "parser_path": _safe_path(parser_path),
            "object_status": object_status,
            "object_path": _safe_path(object_path),
            "paths": {
                "crop": _safe_path(crop_path),
                "usable_skin": _safe_path(usable_path),
                "bad_mask": _safe_path(bad_path),
                "object_mask": _safe_path(object_out_path),
                "overlay": _safe_path(overlay_path),
                "parser_label": _safe_path(parser_copy_path),
                "parser_label_visual": _safe_path(parser_vis_path),
            },
            "metrics": {
                "usable_ratio": float(usable.sum() / total),
                "bad_ratio": float(bad.sum() / total),
                "object_ratio": float(object_mask.sum() / total),
                "raw_parser_usable_ratio": float(usable_raw.sum() / total),
                "raw_parser_bad_ratio": float(bad_raw.sum() / total),
            },
        }
        rows.append(row)
        if review_max_rows is None or len(review_rows) < review_max_rows:
            review_rows.append(_make_row(item, crop, parser_vis, usable, bad, object_mask, overlay))

    ok_rows = [row for row in rows if row.get("ok")]
    object_missing_count = sum(1 for row in ok_rows if row.get("object_status") == "missing_object_mask")
    external_masks_complete = not (bool(config["object"]) and object_missing_count > 0)
    review_sheet = person_output / "review_sheet.png"
    _make_review_sheet(version, person, review_rows, review_sheet)
    manifest_out = person_output / "mask_manifest.json"
    person_summary = {
        "version": version,
        "person": person,
        "ok": len(ok_rows) > 0,
        "ready_for_comparison": len(ok_rows) > 0 and external_masks_complete,
        "external_masks_complete": external_masks_complete,
        "source_manifest": _safe_path(manifest_path),
        "items_total": len(items),
        "items_ok": len(ok_rows),
        "items_missing": len(items) - len(ok_rows),
        "object_missing_count": object_missing_count,
        "missing_reasons": missing_reasons,
        "mean_usable_ratio": float(np.mean([row["metrics"]["usable_ratio"] for row in ok_rows])) if ok_rows else 0.0,
        "mean_bad_ratio": float(np.mean([row["metrics"]["bad_ratio"] for row in ok_rows])) if ok_rows else 0.0,
        "mean_object_ratio": float(np.mean([row["metrics"]["object_ratio"] for row in ok_rows])) if ok_rows else 0.0,
        "review_sheet": _safe_path(review_sheet) if review_sheet.exists() else None,
        "rows": rows,
    }
    _write_json(manifest_out, person_summary)
    return person_summary


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# FaceBuilder Mask-Aware Correction Step 3 Masks",
        "",
        f"- Created: {summary['created_at']}",
        f"- Source version: `{summary['source_version']}`",
        f"- Output root: `{summary['output_dir']}`",
        f"- External root: `{summary['external_root']}`",
        "",
    ]
    for version in summary["versions"]:
        lines += [f"## {version['version']}", ""]
        for person in version["people"]:
            status = "OK" if person["ok"] else "MISSING"
            ready = "READY" if person.get("ready_for_comparison") else "WAITING"
            lines += [
                f"- {person['person']}: **{status}** / {ready}",
                f"  - items: {person['items_ok']} / {person['items_total']}",
                f"  - object masks missing: {person.get('object_missing_count', 0)}",
                f"  - mean usable: {person['mean_usable_ratio']:.3f}",
                f"  - mean bad: {person['mean_bad_ratio']:.3f}",
                f"  - mean object: {person['mean_object_ratio']:.3f}",
                f"  - review: `{person.get('review_sheet')}`",
            ]
            if person.get("missing_reasons"):
                lines.append(f"  - missing: `{person['missing_reasons']}`")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    versions = args.version or list(VERSION_CONFIG.keys())
    people = args.person or list(PERSONS)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = args.output_dir or (args.drive_root / "output" / "facebuilder_mask_aware_step3" / stamp)
    external_root = args.external_root or (args.drive_root / "output" / "facebuilder_mask_aware_step3_external")
    source_root = args.drive_root / "output" / args.source_version
    summary: dict[str, Any] = {
        "schema_version": "facebuilder_mask_aware_step3_masks_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": _safe_path(REPO_ROOT),
        "drive_root": _safe_path(args.drive_root),
        "source_version": args.source_version,
        "source_root": _safe_path(source_root),
        "output_dir": _safe_path(output_root),
        "external_root": _safe_path(external_root),
        "versions": [],
    }

    for version in versions:
        version_summary = {
            "version": version,
            "config": VERSION_CONFIG[version],
            "people": [],
        }
        for person in people:
            person_summary = _process_version_person(
                version,
                VERSION_CONFIG[version],
                args.drive_root,
                external_root,
                source_root,
                output_root,
                person,
                args.usable_erode,
                args.bad_dilate,
                args.review_max_rows,
            )
            version_summary["people"].append(person_summary)
        summary["versions"].append(version_summary)

    summary_json = output_root / "step3_summary.json"
    report_md = output_root / "step3_report.md"
    _write_json(summary_json, summary)
    _write_report(report_md, summary)
    print(json.dumps({
        "summary_json": _safe_path(summary_json),
        "report_md": _safe_path(report_md),
        "versions": [
            {
                "version": version["version"],
                "people": [
                    {
                        "person": person["person"],
                        "ok": person["ok"],
                        "ready_for_comparison": person.get("ready_for_comparison"),
                        "items_ok": person["items_ok"],
                        "items_total": person["items_total"],
                        "object_missing_count": person.get("object_missing_count"),
                        "review_sheet": person.get("review_sheet"),
                        "missing": person.get("missing_reasons"),
                    }
                    for person in version["people"]
                ],
            }
            for version in summary["versions"]
        ],
    }, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
