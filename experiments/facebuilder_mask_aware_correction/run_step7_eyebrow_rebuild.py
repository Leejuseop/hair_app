"""Rebuild eyebrow texture from v07a feature masks.

This is a controlled Step 7 experiment:

- start from the accepted v06 texture;
- use v07a cyan eyebrow masks as-is;
- project only those eyebrow pixels through the FaceBuilder UV sample maps;
- clip the result to the existing v04b eyebrow guard as a maximum fence;
- write two comparison textures: best-source and weighted blend.

Private outputs stay in Drive and must not be committed.
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
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DRIVE_ROOT = Path(os.environ.get("HAIR_APP_DRIVE_ROOT", "G:/\ub0b4 \ub4dc\ub77c\uc774\ube0c/hair_app"))
DEFAULT_BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")
PERSONS = ("juseop", "eunchae")
REVIEW_YAWS = (0, -45, 45)
BROW_FILTERS = {
    "strict": {
        "skin_margin": 42.0,
        "absolute_luma_cap": 92.0,
        "soft_luma_cap": 105.0,
        "description": "dark brow pixels only",
    },
    "medium": {
        "skin_margin": 28.0,
        "absolute_luma_cap": 118.0,
        "soft_luma_cap": 136.0,
        "description": "dark plus mild brown/gray brow pixels",
    },
    "loose": {
        "skin_margin": 18.0,
        "absolute_luma_cap": 145.0,
        "soft_luma_cap": 160.0,
        "description": "widest brow filter, still removes bright skin/highlights",
    },
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive-root", type=Path, default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--step4-root", type=Path, default=None)
    parser.add_argument("--step6-root", type=Path, default=None)
    parser.add_argument("--v07a-root", type=Path, default=None)
    parser.add_argument("--source-version", default="facebuilder_semantic_v2")
    parser.add_argument("--person", action="append", choices=PERSONS)
    parser.add_argument("--min-confidence", type=float, default=0.08)
    parser.add_argument("--blender-exe", type=Path, default=DEFAULT_BLENDER_EXE)
    parser.add_argument("--headnum", type=int, default=0)
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--max-review-width", type=int, default=1800)
    return parser.parse_args(argv)


def _safe_path(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).replace("\\", "/")


def _as_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    return Path(str(value).replace("/", os.sep))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _find_latest(parent: Path, *, child: str | None = None) -> Path:
    candidates = [p for p in parent.iterdir() if p.is_dir()]
    if child:
        candidates = [p / child for p in candidates if (p / child).exists()]
    if not candidates:
        raise FileNotFoundError(f"No matching output under {parent}")
    return sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]


def _find_one(parent: Path, pattern: str) -> Path:
    matches = sorted(parent.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No match for {pattern} under {parent}")
    if len(matches) > 1:
        return matches[0]
    return matches[0]


def _load_rgb(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def _load_mask(path: Path, size: tuple[int, int] | None = None) -> np.ndarray:
    image = Image.open(path).convert("L")
    if size is not None and image.size != size:
        image = image.resize(size, Image.Resampling.NEAREST)
    return np.asarray(image) > 0


def _save_rgb(path: Path, arr: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB").save(path)
    return _safe_path(path) or ""


def _save_l(path: Path, arr: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="L").save(path)
    return _safe_path(path) or ""


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _bilinear_sample(image: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, w - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    x0 = np.clip(x0, 0, w - 1)
    y0 = np.clip(y0, 0, h - 1)
    wx = (x - x0).reshape(-1, 1)
    wy = (y - y0).reshape(-1, 1)
    top = image[y0, x0] * (1.0 - wx) + image[y0, x1] * wx
    bottom = image[y1, x0] * (1.0 - wx) + image[y1, x1] * wx
    return top * (1.0 - wy) + bottom * wy


def _count_rgb(counts: np.ndarray) -> np.ndarray:
    max_value = max(1, int(counts.max()))
    value = np.clip(counts.astype(np.float32) / max_value, 0.0, 1.0)
    rgb = np.zeros((*counts.shape, 3), dtype=np.uint8)
    rgb[..., 1] = (value * 255).astype(np.uint8)
    rgb[..., 2] = ((1.0 - value) * 120).astype(np.uint8)
    rgb[counts == 0] = (0, 0, 0)
    return rgb


def _source_rgb(source: np.ndarray) -> np.ndarray:
    palette = np.asarray(
        [
            (230, 80, 80),
            (80, 160, 240),
            (80, 210, 120),
            (230, 190, 80),
            (180, 90, 230),
            (80, 220, 220),
            (240, 130, 70),
            (170, 220, 80),
            (240, 90, 180),
            (120, 120, 240),
            (90, 180, 150),
            (230, 230, 90),
        ],
        dtype=np.uint8,
    )
    rgb = np.zeros((*source.shape, 3), dtype=np.uint8)
    valid = source >= 0
    rgb[valid] = palette[np.mod(source[valid], len(palette))]
    return rgb


def _skin_fill_color(texture: np.ndarray, guard: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    """Estimate a conservative skin fill color near the eyebrow band."""

    rgb = texture.astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    maxc = rgb.max(axis=2)
    minc = rgb.min(axis=2)
    chroma = maxc - minc
    cb = 128.0 - 0.168736 * rgb[..., 0] - 0.331264 * rgb[..., 1] + 0.5 * rgb[..., 2]
    cr = 128.0 + 0.5 * rgb[..., 0] - 0.418688 * rgb[..., 1] - 0.081312 * rgb[..., 2]
    skin_like = (
        (~guard)
        & (luma > 45.0)
        & (luma < 235.0)
        & (chroma < 120.0)
        & (cb > 70.0)
        & (cb < 155.0)
        & (cr > 105.0)
        & (cr < 205.0)
    )
    ys, xs = np.nonzero(guard)
    if ys.size:
        y0 = max(0, int(ys.min()) - 90)
        y1 = min(texture.shape[0], int(ys.max()) + 100)
        x0 = max(0, int(xs.min()) - 150)
        x1 = min(texture.shape[1], int(xs.max()) + 150)
        local = np.zeros(guard.shape, dtype=bool)
        local[y0:y1, x0:x1] = True
        candidates = skin_like & local
    else:
        candidates = skin_like
    if int(candidates.sum()) < 256:
        candidates = skin_like
    if int(candidates.sum()) < 256:
        candidates = (~guard) & (luma > 55.0) & (luma < 230.0)
    if int(candidates.sum()) == 0:
        color = np.asarray([128.0, 88.0, 68.0], dtype=np.float32)
    else:
        color = np.median(rgb[candidates], axis=0).astype(np.float32)
    color = np.clip(color, 0.0, 255.0)
    return color, {
        "skin_fill_rgb": [float(v) for v in color.tolist()],
        "candidate_texels": int(candidates.sum()),
    }


def _dark_brow_masks(crop_arr: np.ndarray, eyebrow_mask: np.ndarray) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Split a parser eyebrow mask into strict/medium/loose dark brow pixels.

    The parser mask is treated as the maximum image-space eyebrow region. Inside
    it, this function keeps pixels that are darker than the nearby skin or dark
    enough in absolute luma. This is intentionally image-space only, before UV
    projection.
    """

    rgb = crop_arr.astype(np.float32)
    luma = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    maxc = rgb.max(axis=2)
    minc = rgb.min(axis=2)
    chroma = maxc - minc
    cb = 128.0 - 0.168736 * rgb[..., 0] - 0.331264 * rgb[..., 1] + 0.5 * rgb[..., 2]
    cr = 128.0 + 0.5 * rgb[..., 0] - 0.418688 * rgb[..., 1] - 0.081312 * rgb[..., 2]
    skin_like = (
        (luma > 45.0)
        & (luma < 238.0)
        & (chroma < 135.0)
        & (cb > 70.0)
        & (cb < 160.0)
        & (cr > 102.0)
        & (cr < 208.0)
    )
    ys, xs = np.nonzero(eyebrow_mask)
    local = np.zeros(eyebrow_mask.shape, dtype=bool)
    if ys.size:
        y0 = max(0, int(ys.min()) - 55)
        y1 = min(eyebrow_mask.shape[0], int(ys.max()) + 70)
        x0 = max(0, int(xs.min()) - 70)
        x1 = min(eyebrow_mask.shape[1], int(xs.max()) + 70)
        local[y0:y1, x0:x1] = True
    else:
        local[:, :] = True
    skin_reference = skin_like & local & ~ndimage.binary_dilation(eyebrow_mask, iterations=4)
    if int(skin_reference.sum()) < 80:
        skin_reference = local & ~ndimage.binary_dilation(eyebrow_mask, iterations=4) & (luma > 55.0) & (luma < 225.0)
    if int(skin_reference.sum()) < 80:
        skin_luma = 135.0
    else:
        skin_luma = float(np.median(luma[skin_reference]))

    # Bright yellow/orange highlight pixels caused the previous brow result to
    # look painted. Keep dark brown/gray, reject bright skin and highlight tones.
    yellow_highlight = (rgb[..., 0] > 130.0) & (rgb[..., 1] > 105.0) & (rgb[..., 2] < 105.0) & (luma > 105.0)
    bright_skin = skin_like & (luma > skin_luma - 12.0)
    masks: dict[str, np.ndarray] = {}
    meta: dict[str, Any] = {
        "skin_reference_luma": skin_luma,
        "skin_reference_texels": int(skin_reference.sum()),
        "raw_eyebrow_texels": int(eyebrow_mask.sum()),
        "filters": {},
    }
    for name, config in BROW_FILTERS.items():
        margin = float(config["skin_margin"])
        absolute_cap = float(config["absolute_luma_cap"])
        soft_cap = float(config["soft_luma_cap"])
        dark_by_skin = luma <= (skin_luma - margin)
        dark_absolute = luma <= absolute_cap
        soft_brown = (luma <= soft_cap) & (chroma <= 95.0) & (rgb[..., 2] <= rgb[..., 0] + 42.0)
        mask = eyebrow_mask & (dark_by_skin | dark_absolute | soft_brown) & ~yellow_highlight & ~bright_skin
        masks[name] = mask
        meta["filters"][name] = {
            "description": config["description"],
            "selected_texels": int(mask.sum()),
            "selected_ratio_of_raw": float(mask.sum() / max(1, int(eyebrow_mask.sum()))),
        }
    return masks, meta


def _render_texture(
    *,
    blender_exe: Path,
    blend: Path,
    texture: Path,
    output_dir: Path,
    output_json: Path,
    log_path: Path,
    headnum: int,
) -> dict[str, Any]:
    script = REPO_ROOT / "experiments" / "facebuilder_mask_aware_correction" / "blender_step4_render_texture.py"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(blender_exe),
        "--background",
        str(blend),
        "--python",
        str(script),
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
    for yaw in REVIEW_YAWS:
        cmd.extend(["--yaw", str(yaw)])
    completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    log_path.write_text((completed.stdout or "") + "\n--- STDERR ---\n" + (completed.stderr or ""), encoding="utf-8")
    render_summary = _read_json(output_json) if output_json.exists() else {}
    return {
        "ok": completed.returncode == 0 and bool(render_summary.get("ok")),
        "returncode": completed.returncode,
        "render_json": _safe_path(output_json),
        "render_dir": _safe_path(output_dir),
        "log": _safe_path(log_path),
        "renders": render_summary.get("renders", []),
    }


def _load_render_tile(render: dict[str, Any], yaw: int, size: tuple[int, int]) -> Image.Image:
    for item in render.get("renders") or []:
        if int(item.get("yaw")) == int(yaw):
            path = _as_path(item.get("path"))
            if path and path.exists():
                image = Image.open(path).convert("RGB")
                return _fit_tile(image, size)
    return Image.new("RGB", size, (30, 30, 30))


def _fit_tile(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    tile = Image.new("RGB", size, (18, 18, 18))
    img = image.copy()
    img.thumbnail((size[0] - 10, size[1] - 10), Image.Resampling.LANCZOS)
    tile.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
    return tile


def _make_review_sheet(
    *,
    person: str,
    rows: list[tuple[str, dict[str, Any]]],
    output_path: Path,
    max_width: int,
) -> str:
    tile_w = max(280, min(440, (max_width - 150) // 3))
    tile_h = int(tile_w * 1.22)
    label_w = 150
    header_h = 96
    gap = 14
    width = label_w + gap + 3 * tile_w + 4 * gap
    height = header_h + gap + len(rows) * (tile_h + gap) + 18
    sheet = Image.new("RGB", (width, height), (14, 14, 14))
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 14), f"{person} v07c dark brow filter review", fill=(245, 245, 245), font=_font(25))
    draw.text((16, 48), "Columns: front / left 45 / right 45. Cyan = projected brow pixels; peach = guard leftover filled with skin.", fill=(190, 190, 190), font=_font(14))
    draw.text((16, 70), "This pass changes eyebrow pixels only; skin, eyes, lips, mouth, scalp, and hairline are untouched.", fill=(160, 160, 160), font=_font(13))
    headings = [("front", 0), ("left 45", -45), ("right 45", 45)]
    x = label_w + gap
    for title, _ in headings:
        draw.text((x + 8, header_h - 24), title, fill=(230, 230, 230), font=_font(15))
        x += tile_w + gap
    y = header_h + gap
    for label, render in rows:
        draw.text((gap, y + 14), label, fill=(235, 235, 235), font=_font(15))
        x = label_w + gap
        for _, yaw in headings:
            sheet.paste(_load_render_tile(render, yaw, (tile_w, tile_h)), (x, y))
            x += tile_w + gap
        y += tile_h + gap
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, quality=95)
    return _safe_path(output_path) or ""


def _resolve_roots(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "step4": args.step4_root or _find_latest(args.drive_root / "output" / "facebuilder_mask_aware_step4"),
        "step6": args.step6_root or _find_latest(args.drive_root / "output" / "facebuilder_mask_aware_step6"),
        "v07a": args.v07a_root or _find_latest(args.drive_root / "output" / "facebuilder_mask_aware_step7", child="v07a_feature_source_review"),
        "source": args.drive_root / "output" / args.source_version,
    }


def _person_paths(roots: dict[str, Path], person: str) -> dict[str, Path]:
    step6_person = roots["step6"] / person
    return {
        "v06_texture": step6_person / "v06_simple_bald_skin_fill" / "maps" / "v06_simple_bald_skin_fill_texture.png",
        "brow_guard": step6_person / "v04b_eyebrow_hairline_refine" / "maps" / "v04b_mirrored_eyebrow_guard_mask.png",
        "coord_json": roots["step4"] / person / "projection" / "uv_sample_coords.json",
        "coord_npz": roots["step4"] / person / "projection" / "uv_sample_coords_arrays.npz",
        "blend": _find_one(roots["source"] / person / "03_facebuilder_scene", "*.blend"),
    }


def _load_v07a_rows(v07a_root: Path, person: str) -> dict[int, dict[str, Any]]:
    summary = _read_json(v07a_root / "v07a_feature_source_summary.json")
    for item in summary.get("people") or []:
        if item.get("person") == person:
            return {int(row["index"]): row for row in item.get("rows") or []}
    raise KeyError(f"Missing v07a rows for {person}")


def _process_person(
    *,
    person: str,
    roots: dict[str, Path],
    args: argparse.Namespace,
    output_dir: Path,
) -> dict[str, Any]:
    paths = _person_paths(roots, person)
    coords = _read_json(paths["coord_json"])
    rows_by_index = _load_v07a_rows(roots["v07a"], person)
    atlas_size = int(coords["atlas_size"])

    base = np.asarray(_load_rgb(paths["v06_texture"])).astype(np.float32)
    if base.shape[:2] != (atlas_size, atlas_size):
        base_img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), mode="RGB")
        base = np.asarray(base_img.resize((atlas_size, atlas_size), Image.Resampling.BILINEAR)).astype(np.float32)

    brow_guard = _load_mask(paths["brow_guard"], (atlas_size, atlas_size))
    # A one-pixel dilation gives projection quantization a little room while
    # still treating the guard as a maximum fence, not as a fill target.
    brow_guard = ndimage.binary_dilation(brow_guard, iterations=1)

    variants: dict[str, dict[str, Any]] = {}
    for filter_name in BROW_FILTERS:
        variants[filter_name] = {
            "best_texture": base.copy(),
            "blend_accum": np.zeros_like(base, dtype=np.float64),
            "blend_weight": np.zeros((atlas_size, atlas_size), dtype=np.float64),
            "best_weight": np.zeros((atlas_size, atlas_size), dtype=np.float64),
            "best_source": np.full((atlas_size, atlas_size), -1, dtype=np.int16),
            "source_count": np.zeros((atlas_size, atlas_size), dtype=np.uint16),
        }
    camera_summaries: list[dict[str, Any]] = []

    with np.load(paths["coord_npz"]) as data:
        for camera in coords.get("cameras") or []:
            if not camera.get("ok"):
                continue
            if not camera.get("use_in_tex_baking"):
                continue
            index = int(camera["camera_index"])
            row = rows_by_index.get(index)
            if row is None or not row.get("texture_enabled"):
                continue
            prefix = f"camera_{index:03d}"
            required = [f"{prefix}_sample_x", f"{prefix}_sample_y", f"{prefix}_confidence"]
            if any(name not in data.files for name in required):
                camera_summaries.append({"camera_index": index, "used": False, "reason": "missing_coordinate_arrays"})
                continue

            crop_path = _as_path(row.get("crop_path"))
            eyebrow_path = _as_path((row.get("mask_paths") or {}).get("eyebrow"))
            if not crop_path or not eyebrow_path or not crop_path.exists() or not eyebrow_path.exists():
                camera_summaries.append({"camera_index": index, "used": False, "reason": "missing_crop_or_eyebrow_mask"})
                continue

            crop = _load_rgb(crop_path)
            crop_arr = np.asarray(crop).astype(np.float32)
            eyebrow_mask = _load_mask(eyebrow_path, crop.size)
            if int(eyebrow_mask.sum()) == 0:
                camera_summaries.append({"camera_index": index, "used": False, "reason": "empty_eyebrow_mask"})
                continue
            dark_masks, dark_meta = _dark_brow_masks(crop_arr, eyebrow_mask)

            sample_x = data[f"{prefix}_sample_x"].astype(np.float32)
            sample_y = data[f"{prefix}_sample_y"].astype(np.float32)
            confidence = data[f"{prefix}_confidence"].astype(np.float32) / 255.0
            source_w, source_h = [int(v) for v in camera.get("source_image_size") or [crop.width, crop.height]]
            sx = sample_x * (crop.width / max(1, source_w))
            sy = sample_y * (crop.height / max(1, source_h))
            xi = np.clip(np.rint(sx).astype(np.int32), 0, crop.width - 1)
            yi = np.clip(np.rint(sy).astype(np.int32), 0, crop.height - 1)
            base_valid = (
                brow_guard
                & (confidence >= args.min_confidence)
                & (sx >= 0.0)
                & (sy >= 0.0)
                & (sx < crop.width)
                & (sy < crop.height)
            )
            eyebrow_score = float((row.get("features") or {}).get("eyebrow", {}).get("score", 0.0))
            projected_by_filter: dict[str, int] = {}
            mean_conf_by_filter: dict[str, float] = {}
            mean_weight_by_filter: dict[str, float] = {}
            for filter_name, dark_mask in dark_masks.items():
                valid = base_valid & dark_mask[yi, xi]
                atlas_y, atlas_x = np.nonzero(valid)
                projected_by_filter[filter_name] = int(atlas_y.size)
                if atlas_y.size == 0:
                    mean_conf_by_filter[filter_name] = 0.0
                    mean_weight_by_filter[filter_name] = 0.0
                    continue
                rgb = _bilinear_sample(crop_arr, sx[valid], sy[valid])
                weight = np.maximum(confidence[valid], args.min_confidence) ** 2.0
                weight = weight * max(0.05, eyebrow_score)
                state = variants[filter_name]
                state["blend_accum"][atlas_y, atlas_x] += rgb * weight.reshape(-1, 1)
                state["blend_weight"][atlas_y, atlas_x] += weight
                state["source_count"][atlas_y, atlas_x] += 1

                update = weight > state["best_weight"][atlas_y, atlas_x]
                if np.any(update):
                    uy = atlas_y[update]
                    ux = atlas_x[update]
                    state["best_texture"][uy, ux] = rgb[update]
                    state["best_weight"][uy, ux] = weight[update]
                    state["best_source"][uy, ux] = index
                mean_conf_by_filter[filter_name] = float(confidence[valid].mean())
                mean_weight_by_filter[filter_name] = float(weight.mean())

            camera_summaries.append({
                "camera_index": index,
                "used": True,
                "source_name": row.get("source_name"),
                "eyebrow_score_100": float((row.get("features") or {}).get("eyebrow", {}).get("score_100", 0.0)),
                "raw_eyebrow_texels": int(eyebrow_mask.sum()),
                "dark_filter_meta": dark_meta,
                "projected_texels_by_filter": projected_by_filter,
                "mean_projection_confidence_by_filter": mean_conf_by_filter,
                "mean_weight_by_filter": mean_weight_by_filter,
            })

    skin_fill, skin_fill_meta = _skin_fill_color(base, brow_guard)

    maps_dir = output_dir / person / "maps"
    variant_outputs: dict[str, dict[str, Any]] = {}
    for filter_name, state in variants.items():
        blend_texture = base.copy()
        blend_weight = state["blend_weight"]
        blend_valid = blend_weight > 0
        blend_texture[blend_valid] = state["blend_accum"][blend_valid] / blend_weight[blend_valid].reshape(-1, 1)
        best_texture = state["best_texture"]
        best_valid = state["best_weight"] > 0
        changed_any = best_valid | blend_valid
        leftover_guard = brow_guard & ~changed_any
        if np.any(leftover_guard):
            best_texture[leftover_guard] = skin_fill
            blend_texture[leftover_guard] = skin_fill

        variant_dir = maps_dir / filter_name
        best_path = Path(_save_rgb(variant_dir / f"v07c_{filter_name}_eyebrow_best_source_texture.png", best_texture))
        blend_path = Path(_save_rgb(variant_dir / f"v07c_{filter_name}_eyebrow_blend_texture.png", blend_texture))
        coverage_path = _save_l(variant_dir / f"v07c_{filter_name}_eyebrow_replaced_mask.png", changed_any.astype(np.uint8) * 255)
        leftover_path = _save_l(variant_dir / f"v07c_{filter_name}_eyebrow_guard_skin_fill_mask.png", leftover_guard.astype(np.uint8) * 255)
        source_count_path = _save_rgb(variant_dir / f"v07c_{filter_name}_eyebrow_source_count.png", _count_rgb(state["source_count"]))
        best_source_path = _save_rgb(variant_dir / f"v07c_{filter_name}_eyebrow_best_source_camera.png", _source_rgb(state["best_source"]))

        area_texture = np.zeros_like(base, dtype=np.uint8)
        area_texture[..., :] = np.asarray([18, 18, 18], dtype=np.uint8)
        area_texture[brow_guard] = (48, 48, 48)
        area_texture[leftover_guard] = (235, 155, 120)
        area_texture[changed_any] = (0, 220, 255)
        area_texture_path = Path(_save_rgb(variant_dir / f"v07c_{filter_name}_eyebrow_area_render_texture.png", area_texture))
        variant_outputs[filter_name] = {
            "best_source_texture": best_path,
            "blend_texture": blend_path,
            "area_render_texture": area_texture_path,
            "replaced_mask": coverage_path,
            "guard_skin_fill_mask": leftover_path,
            "source_count": source_count_path,
            "best_source_camera": best_source_path,
            "metrics": {
                "brow_guard_texels": int(brow_guard.sum()),
                "best_source_replaced_texels": int(best_valid.sum()),
                "blend_replaced_texels": int(blend_valid.sum()),
                "guard_skin_fill_texels": int(leftover_guard.sum()),
                "unique_source_texels": int(changed_any.sum()),
                "mean_source_count_on_replaced": float(state["source_count"][changed_any].mean()) if np.any(changed_any) else 0.0,
                "max_source_count": int(state["source_count"].max()) if state["source_count"].size else 0,
                **skin_fill_meta,
            },
        }

    render_results: dict[str, dict[str, Any]] = {}
    if not args.skip_render:
        render_plan: list[tuple[str, Path]] = [("baseline_v06", paths["v06_texture"])]
        for filter_name, output in variant_outputs.items():
            render_plan.extend([
                (f"{filter_name}_best_source", output["best_source_texture"]),
                (f"{filter_name}_blend", output["blend_texture"]),
                (f"{filter_name}_area", output["area_render_texture"]),
            ])
        for stage, texture_path in render_plan:
            render_results[stage] = _render_texture(
                blender_exe=args.blender_exe,
                blend=paths["blend"],
                texture=texture_path,
                output_dir=output_dir / person / "renders" / stage,
                output_json=output_dir / person / "renders" / stage / "render_summary.json",
                log_path=output_dir / person / "logs" / f"blender_v07c_render_{stage}.txt",
                headnum=args.headnum,
            )

    review_sheet = ""
    if render_results:
        review_rows: list[tuple[str, dict[str, Any]]] = [("baseline v06", render_results.get("baseline_v06", {}))]
        for filter_name in BROW_FILTERS:
            review_rows.append((f"{filter_name} best", render_results.get(f"{filter_name}_best_source", {})))
            review_rows.append((f"{filter_name} blend", render_results.get(f"{filter_name}_blend", {})))
        for filter_name in BROW_FILTERS:
            review_rows.append((f"{filter_name} area", render_results.get(f"{filter_name}_area", {})))
        review_sheet = _make_review_sheet(
            person=person,
            rows=review_rows,
            output_path=output_dir / person / "v07c_dark_brow_filter_review_sheet.png",
            max_width=args.max_review_width,
        )

    summary = {
        "person": person,
        "ok": True,
        "paths": {
            "v06_texture": _safe_path(paths["v06_texture"]),
            "brow_guard": _safe_path(paths["brow_guard"]),
            "coord_json": _safe_path(paths["coord_json"]),
            "coord_npz": _safe_path(paths["coord_npz"]),
            "review_sheet": review_sheet,
            "variants": {
                filter_name: {
                    "best_source_texture": _safe_path(output["best_source_texture"]),
                    "blend_texture": _safe_path(output["blend_texture"]),
                    "area_render_texture": _safe_path(output["area_render_texture"]),
                    "replaced_mask": output["replaced_mask"],
                    "guard_skin_fill_mask": output["guard_skin_fill_mask"],
                    "source_count": output["source_count"],
                    "best_source_camera": output["best_source_camera"],
                }
                for filter_name, output in variant_outputs.items()
            },
        },
        "metrics": {
            "atlas_size": atlas_size,
            **skin_fill_meta,
            "variants": {
                filter_name: output["metrics"]
                for filter_name, output in variant_outputs.items()
            },
        },
        "camera_summaries": camera_summaries,
        "renders": render_results,
    }
    _write_json(output_dir / person / "v07c_dark_brow_filter_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    people = args.person or list(PERSONS)
    roots = _resolve_roots(args)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (args.drive_root / "output" / "facebuilder_mask_aware_step7" / stamp / "v07c_dark_brow_filter")
    summaries = [_process_person(person=person, roots=roots, args=args, output_dir=output_dir) for person in people]
    root_summary = {
        "schema_version": "facebuilder_mask_aware_step7_dark_brow_filter_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": _safe_path(REPO_ROOT),
        "drive_root": _safe_path(args.drive_root),
        "output_dir": _safe_path(output_dir),
        "roots": {key: _safe_path(value) for key, value in roots.items()},
        "min_confidence": args.min_confidence,
        "people": summaries,
        "notes": [
            "v07c changes eyebrow pixels only.",
            "v07a eyebrow masks are used as maximum image-space feature masks.",
            "strict/medium/loose keep only dark brow-like pixels inside those masks.",
            "v04b mirrored eyebrow guard is only a maximum fence.",
            "Remaining guard texels are filled with local skin color.",
            "No object cleanup, component cleanup, scale normalization, or symmetry is applied in this pass.",
        ],
    }
    _write_json(output_dir / "v07c_dark_brow_filter_summary.json", root_summary)
    print(json.dumps({
        "ok": True,
        "output_dir": _safe_path(output_dir),
        "people": [
            {
                "person": item["person"],
                "variant_metrics": item["metrics"].get("variants", {}),
                "review_sheet": item["paths"].get("review_sheet"),
            }
            for item in summaries
        ],
    }, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
