"""Run Step 6 material-specific texture post-processing.

Step 6 starts from the Step 5 blend texture. The first implemented stage,
`v01_hard_skin_holes`, only fills small black COMPLETION_NEEDED holes that are
surrounded by reliable skin-like pixels. It intentionally does not fill eyes,
mouth, brows, nostrils, scalp, or clothing regions.

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
    if not args.skip_render:
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

    if not args.skip_render:
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
        "stages": ["v00_baseline", "v01_hard_skin_holes"],
        "parameters": {
            "close_radius": int(args.close_radius),
            "max_fill_distance": float(args.max_fill_distance),
            "max_component_area": int(args.max_component_area),
            "max_component_width": int(args.max_component_width),
            "max_component_height": int(args.max_component_height),
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
            }
            for item in summary["people"]
        ],
    }, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
