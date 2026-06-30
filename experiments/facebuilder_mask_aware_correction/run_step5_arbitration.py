"""Run Step 5 raw-vs-clean texture arbitration.

Step 5 intentionally does not use the old cleanup texture and does not use the
Step 4 color-corrected texture. It compares FaceBuilder raw texture with Step 4
projected raw clean pixels, then writes two diagnostic outputs:

- select: BOTH_OK texels choose the higher-trust source.
- blend: only BOTH_OK texels are blended; all other categories match select.

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
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")
DEFAULT_DRIVE_ROOT = Path(os.environ.get("HAIR_APP_DRIVE_ROOT", "G:/\ub0b4 \ub4dc\ub77c\uc774\ube0c/hair_app"))
PERSONS = ("juseop", "eunchae")

CLEAN_ONLY = 1
RAW_ONLY = 2
BOTH_OK = 3
COMPLETION_NEEDED = 4

DECISION_COLORS = {
    CLEAN_ONLY: (235, 38, 38),        # red
    RAW_ONLY: (35, 86, 235),          # blue
    BOTH_OK: (34, 185, 72),           # green
    COMPLETION_NEEDED: (245, 214, 38),  # yellow
}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive-root", type=Path, default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--blender-exe", type=Path, default=DEFAULT_BLENDER_EXE)
    parser.add_argument("--source-version", default="facebuilder_semantic_v2")
    parser.add_argument("--step4-root", type=Path, default=None)
    parser.add_argument("--person", action="append", choices=PERSONS)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--headnum", type=int, default=0)
    parser.add_argument("--clean-good-threshold", type=float, default=0.34)
    parser.add_argument("--raw-good-threshold", type=float, default=0.46)
    parser.add_argument("--near-tie-low", type=float, default=0.40)
    parser.add_argument("--near-tie-high", type=float, default=0.60)
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


def _find_one(pattern_root: Path, pattern: str) -> Path:
    matches = sorted(pattern_root.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No match under {pattern_root}: {pattern}")
    return matches[0]


def _find_latest_step4(drive_root: Path, people: list[str]) -> Path:
    root = drive_root / "output" / "facebuilder_mask_aware_step4"
    candidates = sorted([path for path in root.iterdir() if path.is_dir()], reverse=True)
    for candidate in candidates:
        if all((candidate / person / "step4_person_summary.json").exists() for person in people):
            return candidate
    raise FileNotFoundError(f"No ready Step 4 output found under {root}")


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


def _save_rgb(path: Path, arr: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr.astype(np.uint8), mode="RGB").save(path)
    return _safe_path(path) or ""


def _save_l(path: Path, arr: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr.astype(np.uint8), mode="L").save(path)
    return _safe_path(path) or ""


def _mask_to_rgb(mask: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    out = np.zeros((*mask.shape, 3), dtype=np.uint8)
    out[mask] = color
    return out


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


def _make_decision_rgb(decision: np.ndarray) -> np.ndarray:
    out = np.zeros((*decision.shape, 3), dtype=np.uint8)
    for value, color in DECISION_COLORS.items():
        out[decision == value] = color
    return out


def _make_select_source_rgb(clean_choice: np.ndarray, raw_choice: np.ndarray, completion: np.ndarray) -> np.ndarray:
    out = np.zeros((*clean_choice.shape, 3), dtype=np.uint8)
    out[clean_choice] = DECISION_COLORS[CLEAN_ONLY]
    out[raw_choice] = DECISION_COLORS[RAW_ONLY]
    out[completion] = DECISION_COLORS[COMPLETION_NEEDED]
    return out


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


def _make_render_sheet(person: str, label: str, render_dir: Path, path: Path) -> str | None:
    images = []
    for render_path in sorted(render_dir.glob("render_yaw_*.png")):
        images.append((render_path.stem.replace("render_yaw_", "yaw "), Image.open(render_path).convert("RGB")))
    if not images:
        return None
    _make_grid_sheet(
        f"{person} Step 5 {label} render review",
        "FaceBuilder mesh rendered with Step 5 diagnostic texture. Private; do not commit.",
        images,
        path,
        columns=4,
    )
    return _safe_path(path)


def _edge_factor(alpha: np.ndarray) -> np.ndarray:
    coverage_img = Image.fromarray((alpha > 0).astype(np.uint8) * 255, mode="L")
    eroded = np.asarray(coverage_img.filter(ImageFilter.MinFilter(3))) > 127
    covered = alpha > 0
    boundary = covered & ~eroded
    factor = np.ones(alpha.shape, dtype=np.float32)
    factor[boundary] = 0.88
    factor[~covered] = 0.0
    return factor


def _skin_reference(clean: np.ndarray, alpha: np.ndarray, confidence: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    ref_mask = (alpha > 0) & (confidence >= 64)
    if int(ref_mask.sum()) < 512:
        ref_mask = alpha > 0
    pixels = clean[ref_mask].astype(np.float32)
    if pixels.shape[0] == 0:
        return np.asarray([150.0, 120.0, 105.0], dtype=np.float32), np.asarray([55.0, 55.0, 55.0], dtype=np.float32), 0
    median = np.median(pixels, axis=0).astype(np.float32)
    mad = np.median(np.abs(pixels - median), axis=0).astype(np.float32) * 1.4826
    scale = np.maximum(mad, np.asarray([48.0, 48.0, 48.0], dtype=np.float32))
    return median, scale, int(pixels.shape[0])


def _raw_score(raw: np.ndarray, clean: np.ndarray, alpha: np.ndarray, confidence: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    raw_f = raw.astype(np.float32)
    clean_f = clean.astype(np.float32)
    median, scale, ref_count = _skin_reference(clean, alpha, confidence)

    luma = raw_f[..., 0] * 0.2126 + raw_f[..., 1] * 0.7152 + raw_f[..., 2] * 0.0722
    maxc = raw_f.max(axis=2)
    minc = raw_f.min(axis=2)
    chroma = maxc - minc
    nonempty = (luma > 18.0) & (maxc > 24.0)
    not_blowout = luma < 248.0
    has_clean_projection_support = alpha > 0

    dist = np.sqrt(np.mean(((raw_f - median.reshape(1, 1, 3)) / scale.reshape(1, 1, 3)) ** 2.0, axis=2))
    skin_envelope = np.exp(-(dist ** 2.0) / 2.8)

    # Only punish obvious non-skin color casts; normal photo-to-photo skin tone
    # differences are allowed and handled in later global post-processing. Raw
    # texture is also only allowed where Step 4 had at least some projected skin
    # evidence. This keeps hair/clothes/background from filling unknown UV.
    cb = 128.0 - 0.168736 * raw_f[..., 0] - 0.331264 * raw_f[..., 1] + 0.5 * raw_f[..., 2]
    cr = 128.0 + 0.5 * raw_f[..., 0] - 0.418688 * raw_f[..., 1] - 0.081312 * raw_f[..., 2]
    broad_skin_ycbcr = (cb > 68.0) & (cb < 152.0) & (cr > 112.0) & (cr < 198.0)
    too_blue_green = (
        (raw_f[..., 2] > np.maximum(raw_f[..., 0], raw_f[..., 1]) * 1.55 + 24.0)
        | (raw_f[..., 1] > np.maximum(raw_f[..., 0], raw_f[..., 2]) * 1.70 + 30.0)
    )
    extreme_chroma = chroma > 155.0

    score = (0.05 + 0.95 * skin_envelope).astype(np.float32)
    score *= nonempty.astype(np.float32)
    score *= not_blowout.astype(np.float32)
    score *= has_clean_projection_support.astype(np.float32)
    score *= np.where(luma < 32.0, 0.40, 1.0).astype(np.float32)
    score *= np.where(broad_skin_ycbcr, 1.0, 0.25).astype(np.float32)
    score *= np.where(too_blue_green, 0.45, 1.0).astype(np.float32)
    score *= np.where(extreme_chroma, 0.65, 1.0).astype(np.float32)

    clean_visible = alpha > 0
    diff = np.linalg.norm(raw_f - clean_f, axis=2)
    huge_difference = clean_visible & (confidence >= 96) & (diff > 165.0)
    score *= np.where(huge_difference, 0.58, 1.0).astype(np.float32)

    score = np.clip(score, 0.0, 1.0)
    meta = {
        "skin_reference_rgb": [float(x) for x in median.tolist()],
        "skin_reference_scale_rgb": [float(x) for x in scale.tolist()],
        "skin_reference_sample_count": ref_count,
    }
    return score, meta


def _clean_score(alpha: np.ndarray, confidence: np.ndarray, source_count: np.ndarray) -> np.ndarray:
    covered = alpha > 0
    conf = confidence.astype(np.float32) / 255.0
    source_factor = 0.90 + 0.10 * np.minimum(source_count.astype(np.float32), 3.0) / 3.0
    score = conf * source_factor * _edge_factor(alpha)
    score[~covered] = 0.0
    return np.clip(score, 0.0, 1.0)


def _score_rgb(score: np.ndarray) -> np.ndarray:
    value = np.clip(score, 0.0, 1.0)
    rgb = np.zeros((*score.shape, 3), dtype=np.uint8)
    rgb[..., 0] = np.clip(value * 255.0, 0, 255).astype(np.uint8)
    rgb[..., 1] = np.clip((0.2 + value * 0.8) * 220.0, 0, 255).astype(np.uint8)
    rgb[..., 2] = np.clip((1.0 - value * 0.85) * 255.0, 0, 255).astype(np.uint8)
    rgb[value <= 0.0] = (8, 8, 8)
    return rgb


def _arbitrate(
    raw: np.ndarray,
    clean: np.ndarray,
    alpha: np.ndarray,
    confidence: np.ndarray,
    source_count: np.ndarray,
    clean_good_threshold: float,
    raw_good_threshold: float,
    near_tie_low: float,
    near_tie_high: float,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    clean_s = _clean_score(alpha, confidence, source_count)
    raw_s, raw_meta = _raw_score(raw, clean, alpha, confidence)

    clean_good = clean_s >= clean_good_threshold
    raw_good = raw_s >= raw_good_threshold
    both_ok = clean_good & raw_good
    clean_only = clean_good & ~raw_good
    raw_only = ~clean_good & raw_good
    completion = ~clean_good & ~raw_good

    decision = np.zeros(alpha.shape, dtype=np.uint8)
    decision[clean_only] = CLEAN_ONLY
    decision[raw_only] = RAW_ONLY
    decision[both_ok] = BOTH_OK
    decision[completion] = COMPLETION_NEEDED

    score_sum = clean_s + raw_s + 1e-6
    clean_share = clean_s / score_sum
    near_tie = both_ok & (clean_share >= near_tie_low) & (clean_share <= near_tie_high)

    select_clean = clean_only | (both_ok & (clean_s >= raw_s))
    select_raw = raw_only | (both_ok & (clean_s < raw_s))

    select_texture = np.zeros_like(raw, dtype=np.uint8)
    select_texture[select_clean] = clean[select_clean]
    select_texture[select_raw] = raw[select_raw]
    select_texture[completion] = 0

    blend_texture = np.zeros_like(raw, dtype=np.uint8)
    blend_texture[clean_only] = clean[clean_only]
    blend_texture[raw_only] = raw[raw_only]
    if np.any(both_ok):
        w = np.clip(clean_share[both_ok], 0.25, 0.75).reshape(-1, 1)
        blended = raw[both_ok].astype(np.float32) * (1.0 - w) + clean[both_ok].astype(np.float32) * w
        blend_texture[both_ok] = np.clip(blended, 0, 255).astype(np.uint8)
    blend_texture[completion] = 0

    total = int(decision.size)
    category_counts = {
        "clean_only": int(clean_only.sum()),
        "raw_only": int(raw_only.sum()),
        "both_ok": int(both_ok.sum()),
        "completion_needed": int(completion.sum()),
        "both_ok_select_clean": int((both_ok & select_clean).sum()),
        "both_ok_select_raw": int((both_ok & select_raw).sum()),
        "both_ok_near_tie_40_60": int(near_tie.sum()),
    }
    category_ratios = {key: float(value / max(1, total)) for key, value in category_counts.items()}
    both_total = max(1, category_counts["both_ok"])
    both_ratios = {
        "near_tie_within_both_ok": float(category_counts["both_ok_near_tie_40_60"] / both_total),
        "select_clean_within_both_ok": float(category_counts["both_ok_select_clean"] / both_total),
        "select_raw_within_both_ok": float(category_counts["both_ok_select_raw"] / both_total),
    }

    maps = {
        "clean_score": clean_s.astype(np.float32),
        "raw_score": raw_s.astype(np.float32),
        "clean_share": clean_share.astype(np.float32),
        "decision": decision,
        "clean_only": clean_only,
        "raw_only": raw_only,
        "both_ok": both_ok,
        "completion": completion,
        "near_tie": near_tie,
        "select_clean": select_clean,
        "select_raw": select_raw,
        "select_texture": select_texture,
        "blend_texture": blend_texture,
    }
    meta = {
        **raw_meta,
        "thresholds": {
            "clean_good": float(clean_good_threshold),
            "raw_good": float(raw_good_threshold),
            "near_tie_low": float(near_tie_low),
            "near_tie_high": float(near_tie_high),
        },
        "category_counts": category_counts,
        "category_ratios": category_ratios,
        "both_ok_analysis": both_ratios,
        "score_means": {
            "clean_score_on_clean_covered": float(clean_s[alpha > 0].mean()) if np.any(alpha > 0) else 0.0,
            "raw_score_mean": float(raw_s.mean()),
        },
    }
    return maps, meta


def _process_person(
    person: str,
    step4_person_dir: Path,
    source_person_dir: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    step4_summary_path = step4_person_dir / "step4_person_summary.json"
    if not step4_summary_path.exists():
        raise FileNotFoundError(step4_summary_path)
    step4_summary = _read_json(step4_summary_path)
    arrays_path = _as_path(step4_summary["paths"]["projection_arrays"])
    raw_texture_path = _as_path(step4_summary["raw_texture"])

    with np.load(arrays_path) as data:
        clean = data["texture_raw"].astype(np.uint8)
        alpha = data["alpha"].astype(np.uint8)
        confidence = data["best_confidence"].astype(np.uint8)
        source_count = data["source_count"].astype(np.uint16)

    height, width = alpha.shape
    raw_img = _load_rgb(raw_texture_path, (width, height))
    raw = np.asarray(raw_img).astype(np.uint8)

    maps, meta = _arbitrate(
        raw=raw,
        clean=clean,
        alpha=alpha,
        confidence=confidence,
        source_count=source_count,
        clean_good_threshold=args.clean_good_threshold,
        raw_good_threshold=args.raw_good_threshold,
        near_tie_low=args.near_tie_low,
        near_tie_high=args.near_tie_high,
    )

    output_maps = output_dir / "maps"
    paths: dict[str, str] = {
        "facebuilder_raw_texture_resized": _save_rgb(output_maps / "facebuilder_raw_texture_resized.png", raw),
        "step4_projected_raw": _save_rgb(output_maps / "step4_projected_raw.png", clean),
        "step5_select_texture": _save_rgb(output_maps / "step5_select_texture.png", maps["select_texture"]),
        "step5_blend_texture": _save_rgb(output_maps / "step5_blend_texture.png", maps["blend_texture"]),
        "step5_decision_color_map": _save_rgb(output_maps / "step5_decision_color_map.png", _make_decision_rgb(maps["decision"])),
        "step5_select_source_map": _save_rgb(
            output_maps / "step5_select_source_map.png",
            _make_select_source_rgb(maps["select_clean"], maps["select_raw"], maps["completion"]),
        ),
        "step5_clean_only_mask": _save_rgb(output_maps / "step5_clean_only_mask.png", _mask_to_rgb(maps["clean_only"], DECISION_COLORS[CLEAN_ONLY])),
        "step5_raw_only_mask": _save_rgb(output_maps / "step5_raw_only_mask.png", _mask_to_rgb(maps["raw_only"], DECISION_COLORS[RAW_ONLY])),
        "step5_both_ok_mask": _save_rgb(output_maps / "step5_both_ok_mask.png", _mask_to_rgb(maps["both_ok"], DECISION_COLORS[BOTH_OK])),
        "step5_completion_needed_mask": _save_rgb(
            output_maps / "step5_completion_needed_mask.png",
            _mask_to_rgb(maps["completion"], DECISION_COLORS[COMPLETION_NEEDED]),
        ),
        "step5_near_tie_mask": _save_rgb(output_maps / "step5_near_tie_mask.png", _mask_to_rgb(maps["near_tie"], (0, 220, 220))),
        "step5_clean_score": _save_rgb(output_maps / "step5_clean_score.png", _score_rgb(maps["clean_score"])),
        "step5_raw_score": _save_rgb(output_maps / "step5_raw_score.png", _score_rgb(maps["raw_score"])),
        "step4_confidence": _save_rgb(output_maps / "step4_confidence.png", _confidence_rgb(confidence)),
        "step4_source_count": _save_rgb(output_maps / "step4_source_count.png", _count_rgb(source_count)),
        "step4_coverage_alpha": _save_l(output_maps / "step4_coverage_alpha.png", alpha),
    }
    arrays_out = output_dir / "step5_arbitration_arrays.npz"
    arrays_out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        arrays_out,
        raw_texture=raw,
        step4_projected_raw=clean,
        select_texture=maps["select_texture"],
        blend_texture=maps["blend_texture"],
        alpha=alpha,
        confidence=confidence,
        source_count=source_count,
        clean_score=maps["clean_score"],
        raw_score=maps["raw_score"],
        clean_share=maps["clean_share"],
        decision=maps["decision"],
        clean_only=maps["clean_only"].astype(np.uint8),
        raw_only=maps["raw_only"].astype(np.uint8),
        both_ok=maps["both_ok"].astype(np.uint8),
        completion_needed=maps["completion"].astype(np.uint8),
        near_tie=maps["near_tie"].astype(np.uint8),
        select_clean=maps["select_clean"].astype(np.uint8),
        select_raw=maps["select_raw"].astype(np.uint8),
    )
    paths["arbitration_arrays"] = _safe_path(arrays_out) or ""

    review_tiles = [
        ("FaceBuilder raw texture", Image.fromarray(raw, mode="RGB")),
        ("Step4 projected raw", Image.fromarray(clean, mode="RGB")),
        ("Step5 select texture", Image.fromarray(maps["select_texture"], mode="RGB")),
        ("Step5 blend texture", Image.fromarray(maps["blend_texture"], mode="RGB")),
        ("Decision map R/B/G/Y", Image.open(_as_path(paths["step5_decision_color_map"])).convert("RGB")),
        ("Select source map", Image.open(_as_path(paths["step5_select_source_map"])).convert("RGB")),
        ("Red CLEAN_ONLY", Image.open(_as_path(paths["step5_clean_only_mask"])).convert("RGB")),
        ("Blue RAW_ONLY", Image.open(_as_path(paths["step5_raw_only_mask"])).convert("RGB")),
        ("Green BOTH_OK", Image.open(_as_path(paths["step5_both_ok_mask"])).convert("RGB")),
        ("Yellow COMPLETION_NEEDED", Image.open(_as_path(paths["step5_completion_needed_mask"])).convert("RGB")),
        ("Cyan BOTH_OK near tie", Image.open(_as_path(paths["step5_near_tie_mask"])).convert("RGB")),
        ("Step4 confidence", Image.open(_as_path(paths["step4_confidence"])).convert("RGB")),
        ("Step4 source count", Image.open(_as_path(paths["step4_source_count"])).convert("RGB")),
        ("Clean score", Image.open(_as_path(paths["step5_clean_score"])).convert("RGB")),
        ("Raw score", Image.open(_as_path(paths["step5_raw_score"])).convert("RGB")),
    ]
    uv_review = output_dir / "step5_uv_review_sheet.png"
    _make_grid_sheet(
        f"{person} Step 5 arbitration UV review",
        "No cleanup texture and no color-corrected texture. Completion-needed texels are black in outputs.",
        review_tiles,
        uv_review,
        columns=4,
    )
    paths["uv_review_sheet"] = _safe_path(uv_review) or ""

    summary = {
        "schema_version": "facebuilder_mask_aware_step5_person_v1",
        "person": person,
        "ok": True,
        "step4_person_dir": _safe_path(step4_person_dir),
        "step4_summary": _safe_path(step4_summary_path),
        "raw_texture": _safe_path(raw_texture_path),
        "source_person_dir": _safe_path(source_person_dir),
        "cleanup_texture_used": False,
        "color_corrected_texture_used": False,
        "completion_needed_output_rgb": [0, 0, 0],
        "decision_colors": {
            "clean_only": DECISION_COLORS[CLEAN_ONLY],
            "raw_only": DECISION_COLORS[RAW_ONLY],
            "both_ok": DECISION_COLORS[BOTH_OK],
            "completion_needed": DECISION_COLORS[COMPLETION_NEEDED],
        },
        **meta,
        "paths": paths,
    }
    _write_json(output_dir / "step5_person_summary.json", summary)
    return summary


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


def _build_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Step 5 Raw-vs-Clean Arbitration Report",
        "",
        f"- Created at: `{summary['created_at']}`",
        f"- Step 4 root: `{summary['step4_root']}`",
        f"- Output: `{summary['output_dir']}`",
        f"- Cleanup texture used: `{summary['cleanup_texture_used']}`",
        f"- Color-corrected Step 4 texture used: `{summary['color_corrected_texture_used']}`",
        "",
        "## Decision Colors",
        "",
        "- Red: CLEAN_ONLY, Step4 projected raw is trusted and raw is not.",
        "- Blue: RAW_ONLY, raw FaceBuilder texture is trusted and Step4 projected raw is weak or absent.",
        "- Green: BOTH_OK, both sources are acceptable. `select` chooses higher score; `blend` blends only this category.",
        "- Yellow: COMPLETION_NEEDED, neither source is trusted. Output texture is black here.",
        "",
        "## People",
        "",
    ]
    for person in summary["people"]:
        counts = person["category_counts"]
        ratios = person["category_ratios"]
        both = person["both_ok_analysis"]
        lines.extend([
            f"### {person['person']}",
            "",
            f"- UV review: `{person['paths'].get('uv_review_sheet')}`",
            f"- Select render: `{person['paths'].get('select_render_review_sheet')}`",
            f"- Blend render: `{person['paths'].get('blend_render_review_sheet')}`",
            f"- Decision render: `{person['paths'].get('decision_render_review_sheet')}`",
            f"- CLEAN_ONLY: {counts['clean_only']} ({ratios['clean_only']:.3f})",
            f"- RAW_ONLY: {counts['raw_only']} ({ratios['raw_only']:.3f})",
            f"- BOTH_OK: {counts['both_ok']} ({ratios['both_ok']:.3f})",
            f"- COMPLETION_NEEDED: {counts['completion_needed']} ({ratios['completion_needed']:.3f})",
            f"- BOTH_OK near tie 40:60-60:40: {counts['both_ok_near_tie_40_60']} ({both['near_tie_within_both_ok']:.3f} of BOTH_OK)",
            "",
        ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    people = args.person or list(PERSONS)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    step4_root = args.step4_root or _find_latest_step4(args.drive_root, people)
    output_root = args.output_dir or (args.drive_root / "output" / "facebuilder_mask_aware_step5" / stamp)
    source_root = args.drive_root / "output" / args.source_version
    render_script = REPO_ROOT / "experiments" / "facebuilder_mask_aware_correction" / "blender_step4_render_texture.py"

    summary: dict[str, Any] = {
        "schema_version": "facebuilder_mask_aware_step5_arbitration_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": _safe_path(REPO_ROOT),
        "drive_root": _safe_path(args.drive_root),
        "source_version": args.source_version,
        "source_root": _safe_path(source_root),
        "step4_root": _safe_path(step4_root),
        "output_dir": _safe_path(output_root),
        "blender_exe": _safe_path(args.blender_exe),
        "cleanup_texture_used": False,
        "color_corrected_texture_used": False,
        "thresholds": {
            "clean_good": float(args.clean_good_threshold),
            "raw_good": float(args.raw_good_threshold),
            "near_tie_low": float(args.near_tie_low),
            "near_tie_high": float(args.near_tie_high),
        },
        "people": [],
    }

    for person in people:
        source_person_dir = source_root / person
        step4_person_dir = step4_root / person
        person_output = output_root / person
        person_summary = _process_person(
            person=person,
            step4_person_dir=step4_person_dir,
            source_person_dir=source_person_dir,
            output_dir=person_output,
            args=args,
        )

        if not args.skip_render:
            blend = _find_one(source_person_dir / "03_facebuilder_scene", "*.blend")
            render_jobs = [
                ("select", person_summary["paths"]["step5_select_texture"]),
                ("blend", person_summary["paths"]["step5_blend_texture"]),
                ("decision", person_summary["paths"]["step5_decision_color_map"]),
            ]
            person_summary["renders"] = {}
            for label, texture_path in render_jobs:
                render_dir = person_output / "renders" / label
                render_json = render_dir / "render_summary.json"
                render_log = person_output / "logs" / f"blender_step5_render_{label}_stdout_stderr.txt"
                result = _render_texture(
                    blender_exe=args.blender_exe,
                    blend=blend,
                    render_script=render_script,
                    texture=_as_path(texture_path),
                    output_dir=render_dir,
                    output_json=render_json,
                    log_path=render_log,
                    headnum=args.headnum,
                )
                person_summary["renders"][label] = result
                sheet = _make_render_sheet(person, label, render_dir, person_output / f"step5_{label}_render_review_sheet.png")
                if sheet:
                    person_summary["paths"][f"{label}_render_review_sheet"] = sheet
        _write_json(person_output / "step5_person_summary.json", person_summary)
        summary["people"].append(person_summary)

    summary_json = output_root / "step5_summary.json"
    report_md = output_root / "step5_report.md"
    _write_json(summary_json, summary)
    report_md.write_text(_build_report(summary), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "output_dir": _safe_path(output_root),
        "summary": _safe_path(summary_json),
        "people": [
            {
                "person": item["person"],
                "uv_review": item["paths"].get("uv_review_sheet"),
                "select_render": item["paths"].get("select_render_review_sheet"),
                "blend_render": item["paths"].get("blend_render_review_sheet"),
                "decision_render": item["paths"].get("decision_render_review_sheet"),
                "counts": item["category_counts"],
                "both_ok_analysis": item["both_ok_analysis"],
            }
            for item in summary["people"]
        ],
    }, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
