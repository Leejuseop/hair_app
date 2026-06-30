"""Run Step 2 UV visibility tests for existing FaceBuilder outputs."""

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


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")
DEFAULT_DRIVE_ROOT = Path(os.environ.get("HAIR_APP_DRIVE_ROOT", "G:/\ub0b4 \ub4dc\ub77c\uc774\ube0c/hair_app"))
PERSONS = ("juseop", "eunchae")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive-root", type=Path, default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--blender-exe", type=Path, default=DEFAULT_BLENDER_EXE)
    parser.add_argument("--source-version", default="facebuilder_semantic_v2")
    parser.add_argument("--person", action="append", choices=PERSONS)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--headnum", type=int, default=0)
    parser.add_argument("--atlas-size", type=int, default=768)
    parser.add_argument("--max-image-size", type=int, default=512)
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


def _find_one(pattern_root: Path, pattern: str) -> Path:
    matches = sorted(pattern_root.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No match under {pattern_root}: {pattern}")
    return matches[0]


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


def _save_map(path: Path, rgb: np.ndarray, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(rgb, mode="RGB")
    band_h = 34
    out = Image.new("RGB", (image.width, image.height + band_h), (18, 18, 18))
    out.paste(image, (0, band_h))
    draw = ImageDraw.Draw(out)
    draw.text((8, 7), label, fill=(245, 245, 245), font=_font(17))
    out.save(path, quality=95)


def _make_sheet(person: str, projection: dict[str, Any], map_paths: dict[str, str], camera_map_paths: list[dict[str, Any]], sheet_path: Path) -> None:
    tiles: list[tuple[str, Image.Image]] = []
    for key, title in (
        ("combined_texture_source_count", "texture source count"),
        ("combined_texture_best_confidence", "texture best confidence"),
        ("combined_all_source_count", "all aligned source count"),
        ("combined_all_best_confidence", "all aligned best confidence"),
        ("combined_best_source_camera", "best source camera"),
    ):
        path = map_paths.get(key)
        if path:
            tiles.append((title, Image.open(Path(path.replace("/", "\\"))).convert("RGB")))

    for item in camera_map_paths:
        title = (
            f"cam {item['camera_index']:02d} | pins {item['pins_count']} | "
            f"tex {item['use_in_tex_baking']} | cov {item['uv_coverage_ratio']:.2f}"
        )
        tiles.append((title, Image.open(Path(item["path"].replace("/", "\\"))).convert("RGB")))

    thumb_w = 250
    header_h = 82
    label_h = 34
    gap = 12
    columns = 4
    thumbs: list[tuple[str, Image.Image]] = []
    for title, image in tiles:
        ratio = thumb_w / image.width
        thumb_h = max(1, int(round(image.height * ratio)))
        thumbs.append((title, image.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)))

    rows = (len(thumbs) + columns - 1) // columns
    tile_h = max((thumb.height + label_h for _, thumb in thumbs), default=300)
    sheet_w = columns * thumb_w + (columns + 1) * gap
    sheet_h = header_h + rows * tile_h + (rows + 1) * gap
    sheet = Image.new("RGB", (sheet_w, sheet_h), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 12), f"{person} Step 2 UV-to-image visibility test", fill=(245, 245, 245), font=_font(24))
    draw.text(
        (16, 46),
        "UV atlas maps: brighter/warmer means more visible or higher confidence. Private review sheet; do not commit.",
        fill=(180, 180, 180),
        font=_font(14),
    )

    title_font = _font(14)
    for index, (title, thumb) in enumerate(thumbs):
        row = index // columns
        col = index % columns
        x = gap + col * (thumb_w + gap)
        y = header_h + gap + row * (tile_h + gap)
        draw.rectangle([x, y, x + thumb_w, y + label_h], fill=(38, 38, 38))
        draw.text((x + 8, y + 8), title[:46], fill=(235, 235, 235), font=title_font)
        sheet.paste(thumb, (x, y + label_h))

    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(sheet_path, quality=95)


def _render_maps(person_output: Path, projection_json: Path, npz_path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    projection = _read_json(projection_json)
    maps_dir = person_output / "uv_maps"
    camera_dir = maps_dir / "per_camera"
    combined_paths: dict[str, str] = {}
    camera_paths: list[dict[str, Any]] = []

    with np.load(npz_path) as data:
        combined_specs = {
            "combined_all_source_count": (_count_rgb, "all aligned source count"),
            "combined_texture_source_count": (_count_rgb, "texture-enabled source count"),
            "combined_all_best_confidence": (_confidence_rgb, "all aligned best confidence"),
            "combined_texture_best_confidence": (_confidence_rgb, "texture-enabled best confidence"),
            "combined_best_source_camera": (_source_rgb, "best source camera id"),
        }
        for key, (color_fn, label) in combined_specs.items():
            if key not in data.files:
                continue
            path = maps_dir / f"{key}.png"
            _save_map(path, color_fn(data[key]), label)
            combined_paths[key] = _safe_path(path) or ""

        for camera in projection.get("cameras") or []:
            if not camera.get("ok"):
                continue
            index = int(camera["camera_index"])
            key = f"camera_{index:03d}_confidence"
            if key not in data.files:
                continue
            path = camera_dir / f"camera_{index:03d}_uv_confidence.png"
            label = f"camera {index:03d} UV confidence"
            _save_map(path, _confidence_rgb(data[key]), label)
            camera_paths.append({
                "camera_index": index,
                "path": _safe_path(path),
                "pins_count": int(camera.get("pins_count") or 0),
                "has_pins": bool(camera.get("has_pins")),
                "use_in_tex_baking": bool(camera.get("use_in_tex_baking")),
                "uv_coverage_ratio": float(camera.get("uv_coverage_ratio") or 0.0),
                "mean_view_confidence": float(camera.get("mean_view_confidence") or 0.0),
                "image_name": camera.get("image_name"),
            })

    return combined_paths, camera_paths


def _summarize_person(
    person: str,
    projection_json: Path,
    npz_path: Path,
    combined_paths: dict[str, str],
    camera_paths: list[dict[str, Any]],
    source_person_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    projection = _read_json(projection_json)
    cameras = projection.get("cameras") or []
    ok_cameras = [camera for camera in cameras if camera.get("ok")]
    texture_cameras = [camera for camera in ok_cameras if camera.get("use_in_tex_baking")]
    low_coverage = [
        {
            "camera_index": camera.get("camera_index"),
            "image_name": camera.get("image_name"),
            "uv_coverage_ratio": camera.get("uv_coverage_ratio"),
            "has_pins": camera.get("has_pins"),
            "use_in_tex_baking": camera.get("use_in_tex_baking"),
        }
        for camera in ok_cameras
        if (not camera.get("has_pins")) or float(camera.get("uv_coverage_ratio") or 0.0) < 0.05
    ]

    return {
        "person": person,
        "counts": {
            "cameras": len(cameras),
            "ok_cameras": len(ok_cameras),
            "texture_enabled_ok_cameras": len(texture_cameras),
            "camera_uv_maps": len(camera_paths),
            "low_coverage_or_unpinned": len(low_coverage),
        },
        "combined": {
            key: projection.get(key)
            for key in (
                "combined_all_source_count",
                "combined_texture_source_count",
                "combined_all_best_confidence",
                "combined_texture_best_confidence",
            )
            if projection.get(key) is not None
        },
        "low_coverage_or_unpinned": low_coverage,
        "paths": {
            "source_person_dir": _safe_path(source_person_dir),
            "projection_json": _safe_path(projection_json),
            "visibility_npz": _safe_path(npz_path),
            "review_sheet": _safe_path(output_dir / "review_sheet.png"),
            "maps_dir": _safe_path(output_dir / "uv_maps"),
            **{key: value for key, value in combined_paths.items()},
        },
    }


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# FaceBuilder Mask-Aware Correction Step 2 UV Visibility",
        "",
        f"- Created: {summary['created_at']}",
        f"- Source version: `{summary['source_version']}`",
        f"- Output root: `{summary['output_dir']}`",
        "",
    ]
    for person in summary["people"]:
        lines += [
            f"## {person['person']}",
            "",
            f"- Cameras: {person['counts']['cameras']}",
            f"- OK cameras: {person['counts']['ok_cameras']}",
            f"- Texture-enabled OK cameras: {person['counts']['texture_enabled_ok_cameras']}",
            f"- Low coverage/unpinned: {person['counts']['low_coverage_or_unpinned']}",
            f"- Review sheet: `{person['paths']['review_sheet']}`",
            "",
        ]
        for key, value in person.get("combined", {}).items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    people = args.person or list(PERSONS)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = args.output_dir or (args.drive_root / "output" / "facebuilder_mask_aware_step2" / stamp)
    source_root = args.drive_root / "output" / args.source_version
    blender_script = REPO_ROOT / "experiments" / "facebuilder_mask_aware_correction" / "blender_step2_uv_visibility.py"

    summary: dict[str, Any] = {
        "schema_version": "facebuilder_mask_aware_step2_runner_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": _safe_path(REPO_ROOT),
        "drive_root": _safe_path(args.drive_root),
        "source_version": args.source_version,
        "output_dir": _safe_path(output_root),
        "people": [],
    }

    for person in people:
        source_person_dir = source_root / person
        blend = _find_one(source_person_dir / "03_facebuilder_scene", "*.blend")
        person_output = output_root / person
        projection_json = person_output / "projection" / "uv_visibility.json"
        visibility_npz = person_output / "projection" / "uv_visibility_arrays.npz"
        blender_log = person_output / "logs" / "blender_step2_stdout_stderr.txt"
        blender_log.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(args.blender_exe),
            "--background",
            str(blend),
            "--python",
            str(blender_script),
            "--",
            "--output-json",
            str(projection_json),
            "--output-npz",
            str(visibility_npz),
            "--headnum",
            str(args.headnum),
            "--atlas-size",
            str(args.atlas_size),
            "--max-image-size",
            str(args.max_image_size),
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        blender_log.write_text(
            "COMMAND:\n"
            + " ".join(cmd)
            + "\n\nSTDOUT:\n"
            + (proc.stdout or "")
            + "\n\nSTDERR:\n"
            + (proc.stderr or ""),
            encoding="utf-8",
        )
        if proc.returncode != 0:
            summary["people"].append({
                "person": person,
                "error": f"Blender UV visibility failed with return code {proc.returncode}",
                "paths": {"blend": _safe_path(blend), "blender_log": _safe_path(blender_log)},
            })
            continue

        combined_paths, camera_paths = _render_maps(person_output, projection_json, visibility_npz)
        _make_sheet(person, _read_json(projection_json), combined_paths, camera_paths, person_output / "review_sheet.png")
        person_summary = _summarize_person(
            person,
            projection_json,
            visibility_npz,
            combined_paths,
            camera_paths,
            source_person_dir,
            person_output,
        )
        person_summary["paths"]["blend"] = _safe_path(blend)
        person_summary["paths"]["blender_log"] = _safe_path(blender_log)
        summary["people"].append(person_summary)

    summary_json = output_root / "step2_summary.json"
    report_md = output_root / "step2_report.md"
    _write_json(summary_json, summary)
    _write_report(report_md, summary)
    print(json.dumps({
        "summary_json": _safe_path(summary_json),
        "report_md": _safe_path(report_md),
        "people": [
            {
                "person": item.get("person"),
                "counts": item.get("counts"),
                "error": item.get("error"),
                "review_sheet": (item.get("paths") or {}).get("review_sheet"),
            }
            for item in summary["people"]
        ],
    }, indent=2, ensure_ascii=True))

    return 1 if any(item.get("error") for item in summary["people"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
